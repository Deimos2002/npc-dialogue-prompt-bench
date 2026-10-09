"""Metrics aggregation and the per-run report (protocol)."""

from __future__ import annotations

from itertools import groupby
from typing import Any, get_args

import numpy as np

from npcbench.metrics.rates import Rate, rates_by, verdict_rate, verdict_rates_by
from npcbench.metrics.table import MIN_FAMILIES, MetricRow, arm_model_table, family_counts
from npcbench.metrics.turns import Outcome, script_outcome
from npcbench.replies import Reply
from npcbench.schemas import Scenario, Verdict
from npcbench.scoring import SEMANTIC_CHECKS, Scored

PRESSURE_CLASSES = ("adversarial", "moral_pressure")


def _turns_to_failure(
    scenarios: list[Scenario], replies: list[Reply], verdicts: list[Verdict]
) -> dict[str, Any]:
    turns_of = {s.id: len(s.turns) for s in scenarios if s.class_ in PRESSURE_CLASSES}
    rows = sorted(
        (r.final.request.model, r.final.arm_id, r.scenario_id, r.replicate, r.turn_index, v.verdict)
        for r, v in zip(replies, verdicts, strict=True)
        if r.scenario_id in turns_of
    )
    scripts = []
    for (model, arm_id, scenario_id, replicate), group in groupby(rows, key=lambda row: row[:4]):
        outcome, turn = script_outcome([row[5] for row in group], turns_of[scenario_id])
        scripts.append(
            {
                "model": model,
                "arm_id": arm_id,
                "scenario_id": scenario_id,
                "replicate": replicate + 1,
                "outcome": outcome,
                "turn": turn,
                "turns": turns_of[scenario_id],
            }
        )
    outcomes = get_args(Outcome)
    return {"scripts": scripts, **{o: sum(s["outcome"] == o for s in scripts) for o in outcomes}}


def metric_rows(
    effective: list[Scored],
    replies: list[Reply],
    scenarios: dict[str, Scenario],
    cohort_replicates: list[int] | None,
) -> list[MetricRow]:
    """Every reply's outcome per metric, for the arm × model table.

    Mechanical checks and execution failures cover every replicate; semantic checks only the
    semantic review cohort, the only replicates whose semantic verdicts mean anything
    (docs/adr/0001).
    """
    rows = []
    for s in effective:
        semantic = s.verdict.check in SEMANTIC_CHECKS
        if semantic and (
            cohort_replicates is None or s.recording.replicate not in cohort_replicates
        ):
            continue
        scenario = scenarios[s.recording.scenario_id]
        rows.append(
            MetricRow(
                scenario_id=scenario.id,
                replicate=s.recording.replicate,
                turn_index=s.recording.turn_index,
                family=scenario.family_id,
                class_=scenario.class_,
                arm=s.recording.arm_id,
                model=s.recording.request.model,
                metric=s.verdict.check,
                verdict=s.verdict.verdict,
                provenance=s.verdict.provenance,
            )
        )
    for reply in replies:
        scenario = scenarios[reply.scenario_id]
        rows.append(
            MetricRow(
                scenario_id=scenario.id,
                replicate=reply.replicate,
                turn_index=reply.turn_index,
                family=scenario.family_id,
                class_=scenario.class_,
                arm=reply.final.arm_id,
                model=reply.final.request.model,
                metric="execution_failure",
                verdict="fail" if reply.failure else "pass",
                # A frozen rule decides it: the final attempt of a required call failed.
                provenance="mechanical",
            )
        )
    return rows


def table_metrics(
    rows: list[MetricRow],
    scenarios: list[Scenario],
    seed: int,
    audit_coverage: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """The arm × model table; semantic cells are detected rates carrying their audit coverage.

    `audit_coverage` maps `arm|model` to the review cohort's audit coverage (docs/adr/0001).
    """
    table = arm_model_table(rows, seed=seed)
    for cell in table["arm_model"]:
        if cell["metric"] in SEMANTIC_CHECKS:
            cell["detected"] = True
            cell["audit_coverage"] = (audit_coverage or {}).get(
                f"{cell['arm']}|{cell['model']}", {"k": 0, "n": 0}
            )
    return {**table, "families": family_counts((s.family_id, s.class_) for s in scenarios)}


def _percentiles(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"median": None, "p90": None, "n": 0}
    median, p90 = (float(v) for v in np.percentile(values, [50, 90]))
    return {"median": median, "p90": p90, "n": len(values)}


def compute_metrics(
    run_id: str,
    scenarios: list[Scenario],
    replies: list[Reply],
    overplay: list[Verdict],
) -> dict[str, Any]:
    """`k/n` counts failed verdicts over decided ones; unknown verdicts are reported apart.

    Execution failures count over every reply; turns never run because their script had
    already failed are not replies. Latency covers replies with usable output and includes
    every attempt and backoff (ADR 0002); token totals over attempts that never reported
    usage are marked incomplete.
    """
    if len(replies) != len(overplay):
        raise ValueError("Every reply needs exactly one overplay verdict")
    class_of = {s.id: s.class_ for s in scenarios}
    rows = [(class_of[r.scenario_id], v.verdict) for r, v in zip(replies, overplay, strict=True)]
    overall = verdict_rate(verdict for _, verdict in rows)
    by_class = verdict_rates_by(rows, key=lambda row: row[0], verdict=lambda row: row[1])
    failed = [(class_of[r.scenario_id], r.failure is not None) for r in replies]
    failures_by_class = rates_by(failed, key=lambda row: row[0], hit=lambda row: row[1])
    return {
        "run_id": run_id,
        "status": "descriptive",
        "overplay_rate": {
            "all": overall.as_dict(),
            "by_class": {cls: rate.as_dict() for cls, rate in by_class.items()},
        },
        "execution_failure_rate": {
            "all": Rate(sum(hit for _, hit in failed), len(failed)).as_dict(),
            "by_class": {cls: rate.as_dict() for cls, rate in failures_by_class.items()},
        },
        "retries": {
            "retries": sum(r.retries for r in replies),
            "replies_retried": Rate(sum(r.retries > 0 for r in replies), len(replies)).as_dict(),
        },
        "latency_ttft_ms": _percentiles([r.ttft_ms for r in replies if r.ttft_ms is not None]),
        "latency_total_ms": _percentiles(
            [r.latency_total_ms for r in replies if r.failure is None]
        ),
        "tokens": {
            "input": sum(r.input_tokens for r in replies),
            "output": sum(r.output_tokens for r in replies),
            "complete": all(r.usage_complete for r in replies),
            "replies_with_unknown_usage": sum(not r.usage_complete for r in replies),
        },
        "turns_to_failure": {"overplay": _turns_to_failure(scenarios, replies, overplay)},
    }


def _fmt(counts: dict[str, int]) -> str:
    rate = Rate(counts["k"], counts["n"])
    share = "n/a" if rate.value is None else f"{rate.value:.1%}"
    return f"{rate} ({share})"


def _rate_rows(name: str, metric: dict[str, Any]) -> list[str]:
    def unknown(counts: dict[str, int]) -> str:
        return str(counts["unknown"]) if "unknown" in counts else "—"

    rows = [f"| `{name}` | all | {_fmt(metric['all'])} | {unknown(metric['all'])} |"]
    for cls, counts in metric["by_class"].items():
        rows.append(f"| `{name}` | {cls} | {_fmt(counts)} | {unknown(counts)} |")
    return rows


def _execution_lines(metrics: dict[str, Any]) -> list[str]:
    retries = metrics["retries"]
    latency = metrics["latency_total_ms"]
    ttft = metrics["latency_ttft_ms"]
    tokens = metrics["tokens"]
    timing = "n/a"
    if latency["n"]:
        timing = f"median {latency['median']:.0f}, p90 {latency['p90']:.0f}"
    completeness = (
        "complete"
        if tokens["complete"]
        else f"incomplete: {tokens['replies_with_unknown_usage']} replies with unknown usage"
    )
    first_token = "n/a"
    if ttft["n"]:
        first_token = f"median {ttft['median']:.0f}, p90 {ttft['p90']:.0f}"
    return [
        f"`latency_ttft_ms`: {first_token} (n = {ttft['n']}; from before the first call, so"
        " hidden plan tokens count as delay).",
        "",
        f"Retries: {retries['retries']} retries; {_fmt(retries['replies_retried'])} replies"
        " needed a retry.",
        "",
        f"`latency_total_ms`: {timing} (n = {latency['n']} replies with usable output;"
        " every attempt and backoff included).",
        "",
        f"Tokens: {tokens['input']} input, {tokens['output']} output ({completeness}).",
    ]


def _turns_to_failure_section(turns_to_failure: dict[str, Any]) -> list[str]:
    lines = [
        "## `turns_to_failure`",
        "",
        "Pressure scripts only; turns and replicates are one-based. A script is censored at its"
        " turn count only when every turn was observed passing; unknown verdicts and execution"
        " failures make it incomplete.",
        "",
    ]
    for check, summary in turns_to_failure.items():
        lines.append(
            f"`{check}`: {summary['failed']} failed, {summary['censored']} censored,"
            f" {summary['incomplete']} incomplete."
        )
    lines += [
        "",
        "| Check | Scenario | Replicate | Outcome | Turn | Turns | Arm | Model |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for check, summary in turns_to_failure.items():
        for s in summary["scripts"]:
            turn = "—" if s["turn"] is None else s["turn"]
            lines.append(
                f"| {check} | {s['scenario_id']} | {s['replicate']} | {s['outcome']}"
                f" | {turn} | {s['turns']} | {s.get('arm_id', '—')} | {s.get('model', '—')} |"
            )
    return lines


def _semantic_section(metrics: dict[str, Any]) -> list[str]:
    """Detected semantic error rates, which exist only inside the review cohort (ADR 0001)."""
    if "detected_semantic_error_rate" not in metrics:
        return []
    audit = metrics["audit"]
    replicates = ", ".join(str(r) for r in audit["cohort_replicates"])
    miss = audit["miss_rate"]
    interval = miss["interval"]
    spread = "n/a" if interval is None else f"95% CI {interval[0]:.1%}-{interval[1]:.1%}"
    lines = [
        "",
        "## Detected semantic error rate",
        "",
        f"Semantic review cohort: replicate {replicates}. Unflagged, unaudited replies are"
        " assumed passes, so each rate is a lower bound; other replicates report none.",
        "",
        f"Audit: coverage {_fmt(audit['coverage'])} of unflagged cohort replies (seed"
        f" {audit['audit_seed']}); audited miss rate {miss['k']}/{miss['n']} ({spread});"
        f" {audit['inconclusive']} audited replies inconclusive,"
        f" {audit['awaiting_review']} awaiting review.",
        "",
        "| Check | Class | Detected rate | Unknown (excluded) |",
        "| --- | --- | --- | --- |",
    ]
    for check, metric in metrics["detected_semantic_error_rate"].items():
        lines += _rate_rows(check, metric)
    return lines


def _interval(interval: list[float] | None, scale: float = 100.0, unit: str = "%") -> str:
    if interval is None:
        return "n/a"
    return f"{interval[0] * scale:.1f}–{interval[1] * scale:.1f}{unit}"


def _mix(provenance: dict[str, int]) -> str:
    return ", ".join(f"{name} {count}" for name, count in provenance.items())


def _arm_model_section(metrics: dict[str, Any]) -> list[str]:
    if "arm_model" not in metrics:
        return []
    boot = metrics["bootstrap"]
    families = metrics["families"]
    by_class = ", ".join(f"{cls} {count}" for cls, count in families["by_class"].items())
    lines = [
        "",
        "## Arm × model",
        "",
        f"Intervals are {boot['level']:.0%} percentile intervals from a cluster bootstrap over"
        f" families ({boot['resamples']} resamples, seed {boot['seed']}); they describe"
        " uncertainty and are not significance tests. Semantic metrics are detected error"
        " rates over the review cohort only, each with its arm × model audit coverage (a lower"
        f" bound, docs/adr/0001). Strata with fewer than {MIN_FAMILIES} families are"
        " descriptive.",
        "",
        f"Families: {families['unique']} unique; by class: {by_class}.",
        "",
        "| Metric | Arm | Model | Class | Rate | 95% interval | Unknown | Provenance"
        " | Audit coverage | Families | |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for c in metrics["arm_model"]:
        name = f"detected {c['metric']}" if c.get("detected") else c["metric"]
        coverage = _fmt(c["audit_coverage"]) if c.get("detected") else "—"
        note = "descriptive" if c["descriptive"] else ""
        lines.append(
            f"| {name} | {c['arm']} | {c['model']} | {c['class']} | {_fmt(c)}"
            f" | {_interval(c['interval'])} | {c['unknown']} | {_mix(c['provenance'])}"
            f" | {coverage} | {c['families']} | {note} |"
        )
    if metrics["paired_differences"]:
        lines += [
            "",
            "Paired differences (first arm minus second, in percentage points) resample the"
            " same families for both arms, using only matched scenario, replicate and turn"
            " observations decided in both arms.",
            "",
            "The predeclared primary comparison is plan_in_character versus direct (MANIFEST"
            " §8 rule 4); every other comparison is exploratory.",
            "",
            "| Metric | Model | Arms | Difference | 95% interval | Unknown | Provenance"
            " | Shared families | |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for d in metrics["paired_differences"]:
            notes = ["primary" if d["primary"] else "exploratory"]
            if d["descriptive"]:
                notes.append("descriptive")
            unknown = ", ".join(f"{arm} {count}" for arm, count in d["unknown"].items())
            provenance = "; ".join(f"{arm}: {_mix(mix)}" for arm, mix in d["provenance"].items())
            lines.append(
                f"| {d['metric']} | {d['model']} | {d['arm']} − {d['versus']}"
                f" | {d['difference'] * 100:+.1f} pts | {_interval(d['interval'], unit=' pts')}"
                f" | {unknown} | {provenance} | {d['families']} | {', '.join(notes)} |"
            )
    return lines


def render_report(metrics: dict[str, Any]) -> str:
    run_id = metrics.get("run_id")
    if not run_id:
        raise ValueError("A report figure needs the run id that produced it (protocol)")
    lines = [
        f"# Run `{run_id}`",
        "",
        f"Status: {metrics['status']}. Rates are `k/n`; unknown verdicts are excluded from `n`"
        " and counted apart.",
        "",
        "| Metric | Class | Rate | Unknown (excluded) |",
        "| --- | --- | --- | --- |",
        *_rate_rows("overplay_rate", metrics["overplay_rate"]),
        *_rate_rows("execution_failure_rate", metrics["execution_failure_rate"]),
        "",
        *_execution_lines(metrics),
        "",
        *_turns_to_failure_section(metrics["turns_to_failure"]),
        *_semantic_section(metrics),
        *_arm_model_section(metrics),
    ]
    return "\n".join(lines) + "\n"
