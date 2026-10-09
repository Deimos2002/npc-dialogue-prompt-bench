"""Reusable run operations, independent of the command line.

Callers supply run inputs and a Source for generation. Review and labelling use
verified recordings only. Review policy, replay and artifact handling stay here,
so callers do not need to coordinate their ordering. Report rendering uses the
stored metrics without replaying, as the report command always has.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from npcbench._run_analysis import ScoredRun
from npcbench._run_storage import (
    ADJUDICATIONS_FILE,
    json_text,
    portable_path,
    read_adjudications,
    read_checks,
    replace_text,
    run_directory,
    write_checks,
    write_json,
)
from npcbench._run_storage import RunError as RunError
from npcbench.adjudication import AdjudicationError, export_csv, parse_adjudications
from npcbench.cohort import ReviewCohort
from npcbench.loaders import (
    load_character,
    load_phrase_list,
    load_scenarios,
    load_world,
    sha256_file,
    sha256_input,
)
from npcbench.providers.base import ProviderConfigError
from npcbench.recorder import MissingRecording, RecordingMismatch, RecordingStore
from npcbench.replies import group_replies
from npcbench.report import render_report
from npcbench.review.labelling import LabelSample, draw_label_sample, label_candidates, label_item
from npcbench.runner import ReplaySource, Source, arm_order, run_arms
from npcbench.schemas import Arm
from npcbench.scoring import ScoringContext, score


@dataclass(frozen=True, kw_only=True)
class RunSpec:
    """Inputs and recorded metadata for a new run; credentials belong in the Source.

    Each arm is paired with its prompt path. The paths are recorded and must remain
    available and unchanged for replay. Replicate 0 forms the v0.1 review cohort.
    """

    run_id: str
    scenarios: Path
    character: Path
    arm_prompts: list[tuple[Arm, Path]]
    model: str
    provider: str
    params: dict[str, Any] = field(default_factory=lambda: {"temperature": 0.7})
    provider_config: dict[str, Any] = field(default_factory=dict)
    audit_seed: int = 0
    banned_content: Path | None = None
    world: Path | None = None


@dataclass(frozen=True)
class RunSummary:
    run_dir: Path
    reply_count: int
    attempt_count: int


@dataclass(frozen=True)
class AdjudicationExport:
    text: str
    pending_count: int


@dataclass(frozen=True)
class AdjudicationSummary:
    imported_count: int
    stored_count: int


@dataclass(frozen=True, kw_only=True)
class LabelSampleSpec:
    validation_size: int = 20
    calibration_size: int = 4
    seed: int = 0


@dataclass(frozen=True)
class LabelSampleResult:
    sample: LabelSample
    candidate_count: int


class RunWorkflows:
    """Complete operations on runs beneath one results directory.

    Expected input and storage failures raise RunError rather than exiting the process.
    Evidence-based operations verify inputs, recordings and rebuilt raw checks every
    time; there is no live fallback or cache. Creation publishes a staged directory.
    Adjudication replaces each derived file separately, without promising multi-file
    crash recovery.
    """

    def __init__(self, results_dir: Path) -> None:
        self._results_dir = results_dir

    def create(self, spec: RunSpec, *, source: Source) -> RunSummary:
        """Generate and publish a new run; reject existing runs before fetching replies."""
        run_dir = run_directory(self._results_dir, spec.run_id)
        if run_dir.exists():
            raise RunError(f"{run_dir} already exists; results are never overwritten.")
        arms = [arm for arm, _ in spec.arm_prompts]
        if not arms or len({arm.arm_id for arm in arms}) != len(arms):
            raise RunError("Name at least one arm, with a distinct strategy and prompt version.")
        reserved = {
            "run_id", "arms", "arm_order", "provider", "model", "params",
            "semantic_review_cohort", "inputs", "recordings_sha256",
        }
        if overlap := reserved.intersection(spec.provider_config):
            raise RunError(f"Provider metadata cannot override run fields: {sorted(overlap)}")
        inputs = {"scenarios": spec.scenarios, "character": spec.character}
        inputs.update({f"prompt:{arm.arm_id}": path for arm, path in spec.arm_prompts})
        if spec.banned_content:
            inputs["banned_content"] = spec.banned_content
        if spec.world:
            inputs["world"] = spec.world
        try:
            hashes = {name: sha256_input(path) for name, path in inputs.items()}
            scenarios = load_scenarios(spec.scenarios)
            character = load_character(spec.character)
            templates = {
                arm.arm_id: path.read_text(encoding="utf-8") for arm, path in spec.arm_prompts
            }
            banned = load_phrase_list(spec.banned_content) if spec.banned_content else []
            world = load_world(spec.world) if spec.world else None
            _check_inputs(inputs, hashes)
        except (OSError, ValueError) as exc:
            raise RunError(f"Cannot load run inputs: {exc}") from exc

        # Predeclared before execution (ADR 0001): replicate 1 is stored as 0.
        cohort = ReviewCohort(replicates=[0], audit_seed=spec.audit_seed)
        order = arm_order([scenario.id for scenario in scenarios], [arm.arm_id for arm in arms])
        try:
            recordings = run_arms(
                scenarios=scenarios,
                character=character,
                templates=templates,
                arms=arms,
                order=order,
                run_id=spec.run_id,
                model=spec.model,
                params=spec.params,
                source=source,
            )
        except (ValueError, ProviderConfigError) as exc:
            raise RunError(f"Cannot run: {exc}") from exc
        context = ScoringContext(
            character=character,
            banned_content=banned,
            world=world,
            scenarios={scenario.id: scenario for scenario in scenarios},
        )
        replies = group_replies(recordings)
        run = ScoredRun(scenarios, character, replies, score(replies, context), cohort)
        store = RecordingStore()
        for recording in recordings:
            store.add(recording)
        _publish_run(run_dir, spec, order, run, store, inputs, hashes)
        return RunSummary(run_dir, len(replies), len(recordings))

    def verify(self, run_id: str) -> None:
        """Rebuild checks and metrics offline and compare them with the recorded artifacts."""
        run_dir = run_directory(self._results_dir, run_id)
        run = _load_verified(run_dir, run_id)
        try:
            recorded = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            adjudications = read_adjudications(run_dir)
        except (OSError, ValueError) as exc:
            raise RunError(f"Cannot replay run {run_id}: {exc!r}") from exc
        if run.metrics(run_id, adjudications) != recorded:
            raise RunError("Replay metrics differ from the recorded metrics.")

    def export_adjudications(self, run_id: str) -> AdjudicationExport:
        """Return outstanding review rows after cohort policy and existing human decisions."""
        run_dir = run_directory(self._results_dir, run_id)
        run = _load_verified(run_dir, run_id)
        try:
            review = run.pending_reviews(run.effective_checks(read_adjudications(run_dir)))
            return AdjudicationExport(export_csv(review, run.scenarios_by_id), len(review))
        except (OSError, ValueError) as exc:
            raise RunError(f"Cannot export run {run_id}: {exc!r}") from exc

    def import_adjudications(self, run_id: str, csv_text: str) -> AdjudicationSummary:
        """Validate the whole import before updating human decisions, metrics and report."""
        run_dir = run_directory(self._results_dir, run_id)
        run = _load_verified(run_dir, run_id)
        try:
            imported = parse_adjudications(
                csv_text, run.raw_checks, open_for=run.eligible_adjudication_keys()
            )
            adjudications = {**read_adjudications(run_dir), **imported}
        except AdjudicationError as exc:
            raise RunError(
                "Import rejected; nothing was applied:\n" + "\n".join(exc.problems)
            ) from exc
        except (OSError, ValueError) as exc:
            raise RunError(f"Cannot import into run {run_id}: {exc!r}") from exc
        metrics = run.metrics(run_id, adjudications)
        stored = "".join(
            adjudications[key].model_dump_json() + "\n" for key in sorted(adjudications)
        )
        try:
            replace_text(run_dir / ADJUDICATIONS_FILE, stored)
            replace_text(run_dir / "metrics.json", json_text(metrics))
            replace_text(run_dir / "report.md", render_report(metrics))
        except OSError as exc:
            raise RunError(f"Could not write adjudications for run {run_id}: {exc}") from exc
        return AdjudicationSummary(len(imported), len(adjudications))

    def draw_label_sample(self, run_id: str, spec: LabelSampleSpec) -> LabelSampleResult:
        """Return a complete sample from raw checks, with disjoint calibration families."""
        run = _load_verified(run_directory(self._results_dir, run_id), run_id)
        candidates = label_candidates(run.raw_checks, run.scenarios_by_id)
        try:
            sample = draw_label_sample(
                candidates,
                run_id=run_id,
                validation_size=spec.validation_size,
                calibration_size=spec.calibration_size,
                seed=spec.seed,
            )
        except ValueError as exc:
            raise RunError(f"Cannot draw label sample: {exc}") from exc
        return LabelSampleResult(sample, len(candidates))

    def prepare_labelling(self, sample: LabelSample) -> dict[str, dict[str, Any]]:
        """Return only blinded items for the sample, rejecting missing reply identifiers."""
        run = _load_verified(run_directory(self._results_dir, sample.run_id), sample.run_id)
        replies = {reply.key: reply for reply in run.replies}
        wanted = [*sample.calibration, *sample.validation]
        if missing := [reply_id for reply_id in wanted if reply_id not in replies]:
            raise RunError(
                f"The sample names replies run {sample.run_id} does not have: {missing[:3]}"
            )
        return {
            reply_id: label_item(
                replies[reply_id], run.scenarios_by_id[replies[reply_id].scenario_id], run.character
            )
            for reply_id in wanted
        }

    def render_report(self, run_id: str) -> Path:
        """Re-render the stored metrics without replaying, matching the report command."""
        run_dir = run_directory(self._results_dir, run_id)
        path = run_dir / "report.md"
        try:
            metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
            path.write_text(render_report(metrics), encoding="utf-8", newline="\n")
        except (OSError, KeyError, ValueError) as exc:
            raise RunError(f"Cannot render the report for run {run_id}: {exc!r}") from exc
        return path


def _check_inputs(inputs: dict[str, Path], hashes: dict[str, str]) -> None:
    for name, path in inputs.items():
        if sha256_input(path) != hashes[name]:
            raise RunError(f"Input {name!r} changed during generation; run was not published.")


def _publish_run(
    run_dir: Path,
    spec: RunSpec,
    order: dict[str, list[str]],
    run: ScoredRun,
    store: RecordingStore,
    inputs: dict[str, Path],
    hashes: dict[str, str],
) -> None:
    """Build all artifacts in staging before making the run directory visible."""
    staging = None
    try:
        _check_inputs(inputs, hashes)
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=f".{spec.run_id}-", dir=run_dir.parent))
        store.save(staging / "recordings.jsonl")
        write_checks(staging / "checks.jsonl", [check.row() for check in run.raw_checks])
        metrics = run.metrics(spec.run_id, {})
        write_json(staging / "metrics.json", metrics)
        (staging / "report.md").write_text(render_report(metrics), encoding="utf-8", newline="\n")
        write_json(
            staging / "run_config.json",
            {
                "run_id": spec.run_id,
                "arms": [arm.model_dump(mode="json") for arm, _ in spec.arm_prompts],
                "arm_order": order,
                "provider": spec.provider,
                **spec.provider_config,
                "model": spec.model,
                "params": spec.params,
                "semantic_review_cohort": run.cohort.model_dump(mode="json"),
                "inputs": {
                    name: {"path": portable_path(path), "sha256": hashes[name]}
                    for name, path in inputs.items()
                },
                "recordings_sha256": sha256_file(staging / "recordings.jsonl"),
            },
        )
        staging.rename(run_dir)
    except OSError as exc:
        raise RunError(f"Could not write run {spec.run_id}: {exc}") from exc
    finally:
        if staging is not None and staging.exists():
            shutil.rmtree(staging, ignore_errors=True)


def _load_verified(run_dir: Path, run_id: str) -> ScoredRun:
    """Rebuild a run from its inputs and recordings; fail unless both are unchanged.

    The rebuilt checks must equal `checks.jsonl`. Never calls a model (protocol).
    """
    try:
        config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        if config["run_id"] != run_id:
            raise RunError(f"run_config.json belongs to run {config['run_id']!r}, not {run_id!r}.")
        paths = {}
        for name, info in config["inputs"].items():
            path = Path(info["path"])
            if not path.exists() or sha256_input(path) != info["sha256"]:
                raise RunError(f"Input {name!r} changed since the run: {path}")
            paths[name] = path
        scenarios = load_scenarios(paths["scenarios"])
        character = load_character(paths["character"])
        banned = load_phrase_list(paths["banned_content"]) if "banned_content" in paths else []
        world = load_world(paths["world"]) if "world" in paths else None
        recordings_path = run_dir / "recordings.jsonl"
        arms = [Arm.model_validate(a) for a in config["arms"]]
        recordings = run_arms(
            scenarios=scenarios,
            character=character,
            templates={
                a.arm_id: paths[f"prompt:{a.arm_id}"].read_text(encoding="utf-8") for a in arms
            },
            arms=arms,
            order=config["arm_order"],
            run_id=run_id,
            model=config["model"],
            params=config["params"],
            source=ReplaySource(RecordingStore.load(recordings_path)),
        )
        if sha256_file(recordings_path) != config["recordings_sha256"]:
            raise RunError(f"Recordings changed since the run: {recordings_path}")
        recorded_checks = read_checks(run_dir / "checks.jsonl")
        declared = config.get("semantic_review_cohort")
        cohort = None if declared is None else ReviewCohort.model_validate(declared)
    except (MissingRecording, RecordingMismatch) as exc:
        raise RunError(str(exc)) from exc
    except RunError:
        raise
    except (OSError, KeyError, ValueError, TypeError, AttributeError) as exc:
        raise RunError(f"Cannot replay run {run_id}: {exc!r}") from exc

    context = ScoringContext(
        character=character,
        banned_content=banned,
        world=world,
        scenarios={s.id: s for s in scenarios},
    )
    replies = group_replies(recordings)
    raw_checks = score(replies, context)
    if [check.row() for check in raw_checks] != recorded_checks:
        raise RunError("Replay checks differ from the recorded checks.")
    return ScoredRun(scenarios, character, replies, raw_checks, cohort)
