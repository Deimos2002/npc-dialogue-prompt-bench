"""`bench` command line. Live runs call a provider; replay and CI never do (protocol)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NoReturn, get_args

import typer

from npcbench.loaders import (
    load_characters,
    load_families,
    load_scenarios,
    load_world,
)
from npcbench.pacing import PacedSource
from npcbench.providers.anthropic import AnthropicClient
from npcbench.providers.base import MonotonicClock, ProviderConfigError
from npcbench.providers.chat_completions import DEFAULT_MAX_TOKENS, ChatCompletionsClient
from npcbench.providers.fake import FakeClient, FakeClock, echo_reply
from npcbench.providers.ollama import DEFAULT_URL as OLLAMA_URL
from npcbench.providers.ollama import OllamaClient
from npcbench.review.app import HOST, create_labelling_app, serve
from npcbench.review.labelling import LabelSample
from npcbench.runner import LiveSource
from npcbench.runs import LabelSampleSpec, RunError, RunSpec, RunWorkflows
from npcbench.schemas import Arm, Strategy
from npcbench.suite import PROFILES, suite_hash, validate_suite

app = typer.Typer(no_args_is_help=True, add_completion=False, pretty_exceptions_show_locals=False)

_STRATEGIES = get_args(Strategy)


def _fail(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(1)


PROVIDERS = ("fake", "ollama", "anthropic", "openai", "groq", "gemini")


def _live_source(
    provider: str, *, ollama_url: str, reasoning: str
) -> tuple[LiveSource, dict[str, Any]]:
    """The source of a live run, and what the run configuration records about the provider.

    The fake runs offline on a fake clock; providers run on the real clock. Credentials are
    never part of what is recorded.
    """
    if provider == "fake":
        clock = FakeClock()
        return LiveSource(FakeClient(reply=echo_reply, clock=clock), clock), {}
    if provider == "ollama":
        return LiveSource(OllamaClient(base_url=ollama_url), MonotonicClock()), {}
    if provider in ("openai", "groq", "gemini"):
        client = ChatCompletionsClient(provider, reasoning=reasoning)
        return LiveSource(client, MonotonicClock()), {
            "reasoning": client.reasoning,
            "reply_token_cap": DEFAULT_MAX_TOKENS,
        }
    client = AnthropicClient(reasoning=reasoning)
    return LiveSource(client, MonotonicClock()), {"reasoning": client.reasoning}


def _parse_arms(specs: list[str], prompt: Path | None) -> list[tuple[Arm, Path]]:
    """Arms from `STRATEGY=PATH` options; the version is the prompt file's stem."""
    pairs: list[tuple[str, Path]] = [("direct", prompt)] if prompt else []
    for spec in specs:
        strategy, sep, path = spec.partition("=")
        if not sep or strategy not in _STRATEGIES:
            _fail(f"Arm {spec!r} must be STRATEGY=PATH with a strategy from {_STRATEGIES}.")
        pairs.append((strategy, Path(path)))
    if not pairs:
        _fail("Name at least one arm with --prompt or --arm.")
    arms = []
    for strategy, path in pairs:
        if not path.is_file():
            _fail(f"Prompt file not found: {path}")
        arms.append((Arm.of(strategy, path.stem), path))
    ids = [a.arm_id for a, _ in arms]
    if len(set(ids)) != len(ids):
        _fail(f"Each arm must be a distinct strategy and prompt version: {ids}")
    return arms


@app.command()
def run(
    scenarios: Path = typer.Option(..., exists=True, dir_okay=False),
    character: Path = typer.Option(..., exists=True, dir_okay=False),
    prompt: Path | None = typer.Option(
        None, exists=True, dir_okay=False, help="A direct arm's prompt; shorthand for --arm."
    ),
    arm: list[str] = typer.Option(
        [], help="An arm as STRATEGY=PROMPT_PATH; repeat for a comparison run."
    ),
    provider: str = typer.Option("fake", help="fake, ollama, anthropic, openai, groq or gemini."),
    reasoning: str = typer.Option(
        "disabled",
        help="Anthropic reasoning: disabled, or lowest for a model that cannot disable it.",
    ),
    ollama_url: str = typer.Option(OLLAMA_URL, help="Base URL of the local Ollama server."),
    model: str = typer.Option(...),
    run_id: str = typer.Option(...),
    results_dir: Path = typer.Option(Path("results")),
    temperature: float = typer.Option(0.7),
    audit_seed: int = typer.Option(0, help="Seed of the review cohort's audit sample."),
    request_interval: float = typer.Option(
        0.0,
        min=0.0,
        max=3600.0,
        help="Seconds between attempts for quota pacing; excluded from measured call latency.",
    ),
    banned_content: Path | None = typer.Option(
        None, exists=True, dir_okay=False, help="YAML list of banned phrases (protocol)."
    ),
    world: Path | None = typer.Option(
        None, exists=True, file_okay=False, help="World directory; enables the lore checks."
    ),
) -> None:
    """Run one or more arms and write recordings, checks, metrics and a report.

    A prompt file's stem is its version, as in `prompts/<strategy>/<version>.md` (§7.2).
    Arms run in a predeclared, counterbalanced order per scenario, recorded in the run
    configuration.
    """
    if provider not in PROVIDERS:
        _fail(f"Unknown provider {provider!r}; choose from {PROVIDERS}.")
    arm_prompts = _parse_arms(arm, prompt)
    try:
        source, provider_config = _live_source(provider, ollama_url=ollama_url, reasoning=reasoning)
        if request_interval:
            source = PacedSource(source, MonotonicClock(), request_interval * 1000)
        provider_config["request_interval_seconds"] = request_interval
        summary = RunWorkflows(results_dir).create(
            RunSpec(
                run_id=run_id,
                scenarios=scenarios,
                character=character,
                arm_prompts=arm_prompts,
                model=model,
                provider=provider,
                provider_config=provider_config,
                params={"temperature": temperature},
                audit_seed=audit_seed,
                banned_content=banned_content,
                world=world,
            ),
            source=source,
        )
    except ProviderConfigError as exc:
        _fail(f"Cannot run: {exc}")
    except RunError as exc:
        _fail(str(exc))
    typer.echo(
        f"Run {run_id}: {summary.reply_count} replies ({summary.attempt_count} attempts)"
        f" recorded in {summary.run_dir}"
    )


@app.command()
def replay(
    run_id: str = typer.Option(...),
    results_dir: Path = typer.Option(Path("results")),
) -> None:
    """Recompute a run from its recordings only; never calls a model (protocol)."""
    try:
        RunWorkflows(results_dir).verify(run_id)
    except RunError as exc:
        _fail(str(exc))
    typer.echo(f"Replay of {run_id} matches the recorded checks and metrics.")


adjudicate_app = typer.Typer(no_args_is_help=True, help="Hand adjudication of pending verdicts.")
app.add_typer(adjudicate_app, name="adjudicate")


@adjudicate_app.command("export")
def adjudicate_export(
    run_id: str = typer.Option(...),
    out: Path = typer.Option(..., dir_okay=False),
    results_dir: Path = typer.Option(Path("results")),
) -> None:
    """Write the pending verdicts due for review, with reply and scenario context, to a CSV.

    With a semantic review cohort these are the cohort's flags and the audit sample;
    otherwise every pending flag.
    """
    try:
        exported = RunWorkflows(results_dir).export_adjudications(run_id)
        out.write_text(exported.text, encoding="utf-8", newline="")
    except RunError as exc:
        _fail(str(exc))
    except OSError as exc:
        _fail(f"Cannot export run {run_id}: {exc!r}")
    typer.echo(f"Wrote {exported.pending_count} pending verdicts to {out}")


@adjudicate_app.command("import")
def adjudicate_import(
    run_id: str = typer.Option(...),
    file: Path = typer.Option(..., exists=True, dir_okay=False),
    results_dir: Path = typer.Option(Path("results")),
) -> None:
    """Complete verdicts from a filled export; re-importing the same file changes nothing."""
    try:
        csv_text = file.read_text(encoding="utf-8-sig")
        summary = RunWorkflows(results_dir).import_adjudications(run_id, csv_text)
    except RunError as exc:
        _fail(str(exc))
    except (OSError, ValueError) as exc:
        _fail(f"Cannot import into run {run_id}: {exc!r}")
    typer.echo(
        f"Imported {summary.imported_count} adjudications into {run_id};"
        f" {summary.stored_count} stored."
    )


label_app = typer.Typer(no_args_is_help=True, help="Blind labelling for judge validation.")
app.add_typer(label_app, name="label")


@label_app.command("sample")
def label_sample(
    run_id: str = typer.Option(...),
    out: Path = typer.Option(Path("labels/label_sample.json"), dir_okay=False),
    validation: int = typer.Option(20, min=1, help="Validation replies to label."),
    calibration: int = typer.Option(4, min=0, help="Judge prompt examples (3 to 5)."),
    seed: int = typer.Option(0),
    results_dir: Path = typer.Option(Path("results")),
) -> None:
    """Draw a stratified label sample; calibration and validation use disjoint families."""
    if out.exists():
        _fail(f"{out} already exists; a label sample is drawn once and never redrawn.")
    try:
        result = RunWorkflows(results_dir).draw_label_sample(
            run_id,
            LabelSampleSpec(validation_size=validation, calibration_size=calibration, seed=seed),
        )
    except RunError as exc:
        _fail(str(exc))
    sample = result.sample
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        text = (
            json.dumps(sample.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False)
            + "\n"
        )
        out.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:
        _fail(f"Could not write {out}: {exc}")
    typer.echo(
        f"Sampled {len(sample.validation)} validation and {len(sample.calibration)} calibration"
        f" replies from {result.candidate_count} into {out}"
    )


@label_app.command("serve")
def label_serve(
    sample: Path = typer.Option(Path("labels/label_sample.json"), exists=True, dir_okay=False),
    labels: Path = typer.Option(Path("labels/blind_labels.jsonl"), dir_okay=False),
    port: int = typer.Option(8765, min=1024, max=65535),
    results_dir: Path = typer.Option(Path("results")),
) -> None:
    """Serve the blind labelling screen on 127.0.0.1 for the sampled replies."""
    try:
        drawn = LabelSample.model_validate_json(sample.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _fail(f"Cannot read label sample {sample}: {exc}")
    try:
        items = RunWorkflows(results_dir).prepare_labelling(drawn)
    except RunError as exc:
        _fail(str(exc))
    typer.echo(f"Blind labelling at http://{HOST}:{port}/ ({len(items)} replies)")
    serve(create_labelling_app(items, labels_path=labels, seed=drawn.seed), port=port)


@app.command()
def validate(
    world: Path = typer.Option(Path("data/world"), exists=True, file_okay=False),
    characters: Path = typer.Option(Path("data/characters"), exists=True, file_okay=False),
    scenarios: Path = typer.Option(Path("data/scenarios"), exists=True),
    profile: str = typer.Option("v0.1", help="Release profile, or 'none' for general rules only."),
) -> None:
    """Check world, characters and scenarios against protocol and §6."""
    if profile != "none" and profile not in PROFILES:
        _fail(f"Unknown profile {profile!r}; choose from {sorted(PROFILES)} or 'none'.")
    try:
        loaded_world = load_world(world)
        sheets = load_characters(characters)
        loaded = load_scenarios(scenarios)
        reviews = load_families(scenarios)
    except (OSError, ValueError) as exc:
        _fail(f"Cannot load content: {exc}")
    issues = validate_suite(loaded, loaded_world, sheets, PROFILES.get(profile), families=reviews)
    for issue in issues:
        typer.echo(f"{issue.code:<26} {issue.scenario_id or '-':<32} {issue.message}")
    summary = f"{len(loaded)} scenarios, {len(issues)} issues"
    if issues:
        _fail(f"Suite invalid: {summary}.")
    typer.echo(f"Suite valid: {summary}; hash {suite_hash(loaded, reviews)}")


@app.command()
def report(
    run_id: str = typer.Option(...),
    results_dir: Path = typer.Option(Path("results")),
) -> None:
    """Re-render report.md from metrics.json."""
    try:
        path = RunWorkflows(results_dir).render_report(run_id)
    except RunError as exc:
        _fail(str(exc))
    typer.echo(f"Wrote {path}")
