"""Run operations through their public interface, using real files and a fake provider."""

import csv
import io
import json
from dataclasses import replace
from pathlib import Path

import pytest

from npcbench.providers.fake import FakeClient, FakeClock, echo_reply
from npcbench.runner import LiveSource
from npcbench.runs import LabelSampleSpec, RunError, RunSpec, RunWorkflows
from npcbench.schemas import Arm

FIX = Path(__file__).parents[1] / "fixtures" / "s1"


@pytest.fixture
def spec(tmp_path):
    banned = tmp_path / "banned.yaml"
    banned.write_text('- "selling"', encoding="utf-8")
    return RunSpec(
        run_id="r1",
        scenarios=FIX / "scenarios.yaml",
        character=FIX / "character.yaml",
        arm_prompts=[(Arm.of("direct", "prompt"), FIX / "prompt.md")],
        model="fake-1",
        provider="fake",
        banned_content=banned,
    )


class OfflineSource:
    """An injected real LiveSource with a call counter and an explicit offline switch."""

    def __init__(self):
        clock = FakeClock()
        self.live = LiveSource(FakeClient(reply=echo_reply, clock=clock), clock)
        self.calls = 0
        self.allow_calls = True

    def fetch(self, **kwargs):
        assert self.allow_calls, "An offline operation called the generation source"
        self.calls += 1
        return self.live.fetch(**kwargs)


@pytest.fixture
def source():
    return OfflineSource()


@pytest.fixture
def runs(tmp_path):
    return RunWorkflows(tmp_path / "results")


def _csv_text(rows):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def _artifacts(run_dir):
    return {path.name: path.read_bytes() for path in run_dir.iterdir()}


def test_create_verify_export_import_and_report_without_the_cli(runs, spec, source):
    summary = runs.create(spec, source=source)
    assert (summary.reply_count, summary.attempt_count, source.calls) == (2, 2, 2)
    assert set(_artifacts(summary.run_dir)) == {
        "recordings.jsonl",
        "checks.jsonl",
        "metrics.json",
        "report.md",
        "run_config.json",
    }
    source.allow_calls = False
    runs.verify(spec.run_id)

    exported = runs.export_adjudications(spec.run_id)
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert exported.pending_count == len(rows) == 4
    flagged = next(row for row in rows if row["flagged"] == "yes")
    flagged["verdict"] = "pass"
    flagged["notes"] = "selling is fine here"
    imported = runs.import_adjudications(spec.run_id, _csv_text(rows))
    assert (imported.imported_count, imported.stored_count) == (1, 1)
    remaining = list(csv.DictReader(io.StringIO(runs.export_adjudications(spec.run_id).text)))
    assert len(remaining) == 3
    assert (flagged["reply_id"], flagged["check"]) not in {
        (row["reply_id"], row["check"]) for row in remaining
    }
    runs.verify(spec.run_id)
    assert runs.render_report(spec.run_id) == summary.run_dir / "report.md"
    assert source.calls == 2


def test_input_changed_by_source_is_not_published(runs, spec, source, tmp_path):
    prompt = tmp_path / "prompt.md"
    prompt.write_text(spec.arm_prompts[0][1].read_text(encoding="utf-8"), encoding="utf-8")
    spec = replace(spec, arm_prompts=[(spec.arm_prompts[0][0], prompt)])

    class EditingSource:
        def fetch(self, **kwargs):
            recording = source.fetch(**kwargs)
            prompt.write_text("Edited during generation", encoding="utf-8")
            return recording

    with pytest.raises(RunError, match="changed during generation"):
        runs.create(spec, source=EditingSource())
    assert not (tmp_path / "results" / spec.run_id).exists()


@pytest.mark.parametrize("field", ["run_id", "arms", "arm_order", "provider", "inputs"])
def test_metadata_cannot_override_provenance(runs, spec, source, field):
    with pytest.raises(RunError, match="cannot override"):
        runs.create(replace(spec, provider_config={field: "override"}), source=source)
    assert source.calls == 0


def test_human_decisions_override_mechanical_checks_and_reimport_is_idempotent(runs, spec, source):
    summary = runs.create(spec, source=source)
    checks = [
        json.loads(line) for line in (summary.run_dir / "checks.jsonl").read_text().splitlines()
    ]
    reply_id = checks[0]["key"]
    text = f"reply_id,check,verdict\n{reply_id},overplay,fail\n"
    runs.import_adjudications(spec.run_id, text)
    metrics = json.loads((summary.run_dir / "metrics.json").read_text())
    assert metrics["overplay_rate"]["all"] == {"k": 1, "n": 2, "unknown": 0}
    assert "1/2 (50.0%)" in (summary.run_dir / "report.md").read_text(encoding="utf-8")
    before = _artifacts(summary.run_dir)
    runs.import_adjudications(spec.run_id, text)
    assert _artifacts(summary.run_dir) == before
    runs.verify(spec.run_id)


def test_invalid_import_applies_no_rows(runs, spec, source):
    summary = runs.create(spec, source=source)
    rows = list(csv.DictReader(io.StringIO(runs.export_adjudications(spec.run_id).text)))
    rows[0]["verdict"] = "pass"
    rows[1]["reply_id"] = "nope"
    rows[1]["verdict"] = "fail"
    before = _artifacts(summary.run_dir)
    with pytest.raises(RunError, match="Import rejected; nothing was applied"):
        runs.import_adjudications(spec.run_id, _csv_text(rows))
    assert _artifacts(summary.run_dir) == before


def test_existing_run_is_rejected_before_generation(runs, spec, source):
    summary = runs.create(spec, source=source)
    before = _artifacts(summary.run_dir)
    source.allow_calls = False
    with pytest.raises(RunError, match="results are never overwritten"):
        runs.create(spec, source=source)
    assert _artifacts(summary.run_dir) == before


@pytest.mark.parametrize("run_id", ["../escape", "bad/id", "..", ""])
def test_unsafe_run_ids_are_rejected_before_generation(runs, spec, source, run_id):
    source.allow_calls = False
    with pytest.raises(RunError, match="Invalid run id"):
        runs.create(replace(spec, run_id=run_id), source=source)
    with pytest.raises(RunError, match="Invalid run id"):
        runs.export_adjudications(run_id)


@pytest.mark.parametrize("artifact", ["input", "recordings.jsonl", "checks.jsonl", "metrics.json"])
def test_verify_rejects_changed_evidence_and_metrics(runs, spec, source, artifact):
    summary = runs.create(spec, source=source)
    source.allow_calls = False
    if artifact == "input":
        spec.banned_content.write_text('- "rain"', encoding="utf-8")
    elif artifact == "recordings.jsonl":
        path = summary.run_dir / artifact
        path.write_text(path.read_text().replace("Fake reply to", "Edited reply to", 1))
    elif artifact == "checks.jsonl":
        path = summary.run_dir / artifact
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["verdict"] = "fail"
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    else:
        path = summary.run_dir / artifact
        metrics = json.loads(path.read_text())
        metrics["run_id"] = "changed"
        path.write_text(json.dumps(metrics))
    with pytest.raises(RunError, match="changed|differ"):
        runs.verify(spec.run_id)
    if artifact != "metrics.json":
        with pytest.raises(RunError, match="changed|differ"):
            runs.export_adjudications(spec.run_id)


def test_missing_recording_has_no_live_fallback(runs, spec, source):
    summary = runs.create(spec, source=source)
    path = summary.run_dir / "recordings.jsonl"
    path.write_text(path.read_text().splitlines()[0] + "\n")
    source.allow_calls = False
    with pytest.raises(RunError, match="[Mm]issing recording"):
        runs.verify(spec.run_id)
    with pytest.raises(RunError, match="[Mm]issing recording"):
        runs.export_adjudications(spec.run_id)
    assert source.calls == 2


def test_sample_is_deterministic_disjoint_and_blinded(runs, spec, source):
    runs.create(spec, source=source)
    source.allow_calls = False
    request = LabelSampleSpec(validation_size=1, calibration_size=1, seed=4)
    result = runs.draw_label_sample(spec.run_id, request)
    assert result == runs.draw_label_sample(spec.run_id, request)
    assert result.candidate_count == 2
    assert not set(result.sample.calibration_families) & set(result.sample.validation_families)
    items = runs.prepare_labelling(result.sample)
    assert set(items) == set(result.sample.calibration + result.sample.validation)
    for item in items.values():
        assert set(item) == {
            "reply_id",
            "reply",
            "conversation",
            "player",
            "scenario",
            "character",
            "questions",
        }
        assert "fake-1" not in json.dumps(item)
        assert "direct@" not in json.dumps(item)
    assert source.calls == 2


def test_label_errors_leave_run_artifacts_unchanged(runs, spec, source):
    summary = runs.create(spec, source=source)
    before = _artifacts(summary.run_dir)
    with pytest.raises(RunError, match="Insufficient validation replies"):
        runs.draw_label_sample(spec.run_id, LabelSampleSpec(validation_size=20, calibration_size=1))
    result = runs.draw_label_sample(
        spec.run_id, LabelSampleSpec(validation_size=1, calibration_size=1)
    )
    missing = result.sample.model_copy(update={"validation": ["nope"]})
    with pytest.raises(RunError, match="sample names replies"):
        runs.prepare_labelling(missing)
    assert _artifacts(summary.run_dir) == before
