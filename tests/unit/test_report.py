import pytest

from npcbench.checks.base import CheckResult, mechanical_verdict
from npcbench.replies import group_replies
from npcbench.report import compute_metrics, render_report
from npcbench.schemas import ChatRequest, Recording, Scenario, Timings, Usage


def _scenario(sid, cls, turns=1):
    return Scenario.model_validate(
        {
            "id": sid,
            "character": "fixture-fence",
            "class": cls,
            "story_point": "act-1",
            "family_id": sid,
            "split": "dev",
            "turns": [{"player": "hi"}] * turns,
        }
    )


def _metrics(run_id, scenarios, recordings, verdicts):
    return compute_metrics(run_id, scenarios, group_replies(recordings), verdicts)


def _rec(sid, turn=0, failure=None, attempt=0, total=2.0, backoff=0.0, usage=None):
    return Recording(
        key=f"{sid}-{turn}-{attempt}",
        run_id="r1",
        scenario_id=sid,
        arm_id="direct@v1",
        strategy="direct",
        prompt_version="v1",
        turn_index=turn,
        attempt=attempt,
        backoff_ms=backoff,
        request=ChatRequest(model="m", messages=[]),
        response_text="x",
        failure=failure,
        timings=Timings(ttft_ms=1.0, total_ms=total),
        usage=usage or Usage(),
    )


def _verdict(flagged):
    return mechanical_verdict(CheckResult(check="overplay", flagged=flagged))


def test_metrics_count_failed_verdicts_per_class():
    scenarios = [
        _scenario("a", "on_script"),
        _scenario("b", "on_script"),
        _scenario("c", "spoiler"),
    ]
    recordings = [_rec("a"), _rec("b"), _rec("c")]
    metrics = _metrics(
        "r1", scenarios, recordings, [_verdict(True), _verdict(False), _verdict(True)]
    )
    assert metrics["overplay_rate"]["all"] == {"k": 2, "n": 3, "unknown": 0}
    assert metrics["overplay_rate"]["by_class"] == {
        "on_script": {"k": 1, "n": 2, "unknown": 0},
        "spoiler": {"k": 1, "n": 1, "unknown": 0},
    }


def test_unknown_verdicts_are_excluded_from_n_and_counted():
    scenarios = [
        _scenario("a", "on_script"),
        _scenario("b", "on_script"),
        _scenario("c", "spoiler"),
    ]
    recordings = [_rec("a"), _rec("b"), _rec("c")]
    metrics = _metrics(
        "r1", scenarios, recordings, [_verdict(None), _verdict(True), _verdict(None)]
    )
    assert metrics["overplay_rate"]["all"] == {"k": 1, "n": 1, "unknown": 2}
    assert metrics["overplay_rate"]["by_class"] == {
        "on_script": {"k": 1, "n": 1, "unknown": 1},
        "spoiler": {"k": 0, "n": 0, "unknown": 1},
    }
    report = render_report(metrics)
    assert "| `overplay_rate` | all | 1/1 (100.0%) | 2 |" in report
    assert "| `overplay_rate` | spoiler | 0/0 (n/a) | 1 |" in report


def test_report_renders_counts_and_shares():
    scenarios = [_scenario("a", "on_script"), _scenario("b", "on_script")]
    metrics = _metrics("r1", scenarios, [_rec("a"), _rec("b")], [_verdict(True), _verdict(False)])
    report = render_report(metrics)
    assert "1/2 (50.0%)" in report


def test_report_refuses_figures_without_a_run_id():
    with pytest.raises(ValueError):
        render_report({"status": "descriptive", "overplay_rate": {}})


def test_execution_failures_are_counted_over_every_reply():
    scenarios = [_scenario("a", "on_script"), _scenario("b", "off_script")]
    recordings = [_rec("a", failure="timeout"), _rec("b")]
    metrics = _metrics("r1", scenarios, recordings, [_verdict(None), _verdict(False)])
    assert metrics["execution_failure_rate"]["all"] == {"k": 1, "n": 2}
    assert metrics["execution_failure_rate"]["by_class"] == {
        "on_script": {"k": 1, "n": 1},
        "off_script": {"k": 0, "n": 1},
    }
    assert "| `execution_failure_rate` | all | 1/2 (50.0%) |" in render_report(metrics)


def _pressure(sid, verdicts, turns=3, failure_at=None):
    recordings = [
        _rec(sid, turn, failure="timeout" if turn == failure_at else None)
        for turn in range(len(verdicts))
    ]
    return _scenario(sid, "adversarial", turns), recordings, [_verdict(v) for v in verdicts]


def _turns_to_failure(*scripts):
    scenarios = [s for s, _, _ in scripts]
    recordings = [r for _, rs, _ in scripts for r in rs]
    verdicts = [v for _, _, vs in scripts for v in vs]
    return _metrics("r1", scenarios, recordings, verdicts)


def test_turns_to_failure_is_the_first_failing_turn_one_based():
    metrics = _turns_to_failure(_pressure("a", [False, True, True]))
    script = metrics["turns_to_failure"]["overplay"]["scripts"][0]
    assert script == {
        "model": "m",
        "arm_id": "direct@v1",
        "scenario_id": "a",
        "replicate": 1,
        "outcome": "failed",
        "turn": 2,
        "turns": 3,
    }


def test_a_script_observed_without_failure_is_censored_at_its_turn_count():
    metrics = _turns_to_failure(_pressure("a", [False, False, False]))
    script = metrics["turns_to_failure"]["overplay"]["scripts"][0]
    assert (script["outcome"], script["turn"]) == ("censored", 3)


def test_unknown_verdicts_or_execution_failures_make_a_script_incomplete():
    metrics = _turns_to_failure(
        _pressure("unknown", [False, None, False]),
        _pressure("unknown-before-fail", [None, True, True]),
        _pressure("execution", [False, None], failure_at=1),
        _pressure("fails", [True, None, None]),
    )
    ttf = metrics["turns_to_failure"]["overplay"]
    outcomes = {s["scenario_id"]: (s["outcome"], s["turn"]) for s in ttf["scripts"]}
    assert outcomes == {
        "unknown": ("incomplete", None),
        "unknown-before-fail": ("incomplete", None),
        "execution": ("incomplete", None),
        "fails": ("failed", 1),
    }
    assert (ttf["failed"], ttf["censored"], ttf["incomplete"]) == (1, 0, 3)


def test_turns_to_failure_covers_pressure_scripts_only():
    scenarios = [_scenario("a", "on_script")]
    metrics = _metrics("r1", scenarios, [_rec("a")], [_verdict(True)])
    assert metrics["turns_to_failure"]["overplay"]["scripts"] == []


def test_report_lists_turns_to_failure_per_script():
    metrics = _turns_to_failure(_pressure("a", [False, True, True]), _pressure("b", [False] * 3))
    report = render_report(metrics)
    assert "| overplay | a | 1 | failed | 2 | 3 |" in report
    assert "| overplay | b | 1 | censored | 3 | 3 |" in report
    assert "1 failed, 1 censored, 0 incomplete" in report


def _three_replies():
    scenarios = [_scenario(sid, "on_script") for sid in ("a", "b", "c")]
    known = Usage(input_tokens=10, output_tokens=4)
    recordings = [
        # a: a timeout, then a retry that recovered.
        _rec("a", failure="timeout", total=3000),
        _rec("a", attempt=1, backoff=500, total=400, usage=known),
        # b: clean.
        _rec("b", total=200, usage=known),
        # c: two transport failures, an execution failure.
        _rec("c", failure="transport", total=100),
        _rec("c", attempt=1, failure="transport", backoff=500, total=100),
    ]
    verdicts = [_verdict(False), _verdict(False), _verdict(None)]
    return _metrics("r1", scenarios, recordings, verdicts)


def test_a_retried_reply_counts_once():
    metrics = _three_replies()
    assert metrics["overplay_rate"]["all"] == {"k": 0, "n": 2, "unknown": 1}
    assert metrics["execution_failure_rate"]["all"] == {"k": 1, "n": 3}


def test_retry_counts_and_the_share_of_replies_that_needed_one():
    assert _three_replies()["retries"] == {"retries": 2, "replies_retried": {"k": 2, "n": 3}}


def test_latency_total_includes_failed_attempts_and_backoff():
    latency = _three_replies()["latency_total_ms"]
    # Replies with usable output only: a = 3000 + 500 + 400, b = 200; p90 interpolates.
    assert latency == {"median": 2050.0, "p90": 3530.0, "n": 2}


def test_token_totals_that_include_unknown_usage_are_marked_incomplete():
    tokens = _three_replies()["tokens"]
    assert tokens == {
        "input": 20,
        "output": 8,
        "complete": False,
        "replies_with_unknown_usage": 2,
    }


def test_report_shows_retries_latency_and_token_completeness():
    report = render_report(_three_replies())
    assert "Retries: 2 retries; 2/3 (66.7%) replies needed a retry." in report
    assert "`latency_total_ms`: median 2050, p90 3530 (n = 2" in report
    assert "Tokens: 20 input, 8 output (incomplete: 2 replies with unknown usage)." in report


def test_report_renders_the_arm_model_table_and_paired_differences():
    from npcbench.metrics.table import MetricRow, arm_model_table

    rows = [
        MetricRow(f"F{i}", "on_script", arm, "m1", "overplay", verdict, "mechanical", f"s{i}")
        for i in range(3)
        for arm, verdict in (("direct@v1", "fail"), ("plan_generic@v1", "pass"))
    ]
    table = arm_model_table(rows, seed=0, resamples=100)
    metrics = _metrics("r1", [_scenario("a", "on_script")], [_rec("a")], [_verdict(False)])
    metrics.update(table)
    metrics["families"] = {"by_class": {"on_script": 3}, "unique": 3}
    report = render_report(metrics)
    assert "## Arm × model" in report
    assert "| overplay | direct@v1 | m1 | on_script | 3/3 (100.0%) |" in report
    assert "mechanical 3" in report
    assert "descriptive" in report
    assert "not significance tests" in report
    assert "| overplay | m1 | direct@v1 − plan_generic@v1 | +100.0 pts |" in report
    assert "Families: 3 unique; by class: on_script 3." in report


def test_pressure_scripts_are_separate_for_each_model_arm_and_replicate():
    scenario = _scenario("pressure", "adversarial", turns=3)
    recordings, verdicts = [], []
    for model in ("m1", "m2"):
        for arm in ("direct@v1", "direct@v2"):
            for replicate in (0, 1):
                for turn in range(3):
                    rec = _rec("pressure", turn).model_copy(
                        update={
                            "key": f"{model}-{arm}-{replicate}-{turn}",
                            "arm_id": arm,
                            "replicate": replicate,
                            "request": ChatRequest(model=model, messages=[]),
                        }
                    )
                    recordings.append(rec)
                    verdicts.append(_verdict(arm == "direct@v2" and turn == 1))
    metrics = _metrics("r1", [scenario], recordings, verdicts)
    summary = metrics["turns_to_failure"]["overplay"]
    assert (summary["failed"], summary["censored"], summary["incomplete"]) == (4, 4, 0)
    assert len(summary["scripts"]) == 8
    for script in summary["scripts"]:
        assert script["turn"] == (2 if script["arm_id"] == "direct@v2" else 3)
    report = render_report(metrics)
    assert "| direct@v2 | m2 |" in report


def test_semantic_cells_are_detected_rates_with_their_audit_coverage():
    from npcbench.metrics.table import MetricRow
    from npcbench.report import table_metrics

    rows = [
        MetricRow(
            family=f"F{i}",
            class_="on_script",
            arm="direct@v1",
            model="m1",
            metric="collapse",
            verdict="pass",
            provenance="assumed",
            scenario_id=f"s{i}",
        )
        for i in range(3)
    ]
    coverage = {"direct@v1|m1": {"k": 1, "n": 3}}
    table = table_metrics(rows, [_scenario("s0", "on_script")], seed=0, audit_coverage=coverage)
    cell = next(c for c in table["arm_model"] if c["class"] == "all")
    assert cell["detected"] is True
    assert cell["audit_coverage"] == {"k": 1, "n": 3}
    metrics = _metrics("r1", [_scenario("a", "on_script")], [_rec("a")], [_verdict(False)])
    metrics.update(table)
    report = render_report(metrics)
    assert "| detected collapse | direct@v1 | m1 | all |" in report
    assert "1/3 (33.3%)" in report
    assert "fewer than 10 families" in report
