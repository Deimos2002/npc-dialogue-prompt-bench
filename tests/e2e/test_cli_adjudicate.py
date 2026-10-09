import csv
import io
import json
from pathlib import Path

from typer.testing import CliRunner

from npcbench.cli import app

FIX = Path(__file__).parents[1] / "fixtures" / "s1"
runner = CliRunner()


def _run(tmp_path):
    banned = tmp_path / "banned.yaml"
    banned.write_text('- "selling"', encoding="utf-8")
    args = [
        "run",
        "--scenarios",
        str(FIX / "scenarios.yaml"),
        "--character",
        str(FIX / "character.yaml"),
        "--prompt",
        str(FIX / "prompt.md"),
        "--model",
        "fake-1",
        "--run-id",
        "r1",
        "--results-dir",
        str(tmp_path / "results"),
        "--banned-content",
        str(banned),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output


def _adjudicate(tmp_path, action, path):
    flag = "--out" if action == "export" else "--file"
    args = ["adjudicate", action, "--run-id", "r1", "--results-dir", str(tmp_path / "results")]
    return runner.invoke(app, [*args, flag, str(path)])


def _read(path):
    return list(csv.DictReader(io.StringIO(path.read_text(encoding="utf-8"))))


def _write(path, rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=list(rows[0]), lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    path.write_text(out.getvalue(), encoding="utf-8")


def _metrics(tmp_path):
    return json.loads((tmp_path / "results" / "r1" / "metrics.json").read_text(encoding="utf-8"))


def test_export_import_round_trip_completes_pending_verdicts(tmp_path):
    _run(tmp_path)
    sheet = tmp_path / "pending.csv"
    assert _adjudicate(tmp_path, "export", sheet).exit_code == 0
    rows = _read(sheet)
    # The flagged reply, reviewed whole, plus the audit sample: the unflagged reply.
    assert sorted((r["check"], r["flagged"]) for r in rows) == [
        ("banned_content", "no"),
        ("banned_content", "yes"),
        ("collapse", "no"),
        ("collapse", "no"),
    ]

    flagged = next(r for r in rows if r["flagged"] == "yes")
    flagged["verdict"] = "pass"
    flagged["notes"] = "selling is fine here"
    _write(sheet, rows)
    result = _adjudicate(tmp_path, "import", sheet)
    assert result.exit_code == 0, result.output
    assert "1 adjudication" in result.output

    again = tmp_path / "pending-2.csv"
    assert _adjudicate(tmp_path, "export", again).exit_code == 0
    assert len(_read(again)) == 3

    # Replay applies the stored adjudications and still matches.
    replay = runner.invoke(
        app, ["replay", "--run-id", "r1", "--results-dir", str(tmp_path / "results")]
    )
    assert replay.exit_code == 0, replay.output


def test_adjudicating_a_mechanical_verdict_updates_metrics_and_report(tmp_path):
    _run(tmp_path)
    assert _metrics(tmp_path)["overplay_rate"]["all"] == {"k": 0, "n": 2, "unknown": 0}
    checks = (tmp_path / "results" / "r1" / "checks.jsonl").read_text(encoding="utf-8")
    key = json.loads(checks.splitlines()[0])["key"]
    sheet = tmp_path / "overplay.csv"
    sheet.write_text(f"reply_id,check,verdict\n{key},overplay,fail\n", encoding="utf-8")
    assert _adjudicate(tmp_path, "import", sheet).exit_code == 0
    assert _metrics(tmp_path)["overplay_rate"]["all"] == {"k": 1, "n": 2, "unknown": 0}
    report = (tmp_path / "results" / "r1" / "report.md").read_text(encoding="utf-8")
    assert "1/2 (50.0%)" in report

    # Re-importing the same file changes nothing.
    before = sorted(p.read_bytes() for p in (tmp_path / "results" / "r1").iterdir())
    assert _adjudicate(tmp_path, "import", sheet).exit_code == 0
    after = sorted(p.read_bytes() for p in (tmp_path / "results" / "r1").iterdir())
    assert before == after


def test_a_bad_import_names_each_row_and_changes_nothing(tmp_path):
    _run(tmp_path)
    run_dir = tmp_path / "results" / "r1"
    before = {p.name: p.read_bytes() for p in run_dir.iterdir()}
    sheet = tmp_path / "bad.csv"
    sheet.write_text("reply_id,check,verdict\nnope,collapse,pass\n", encoding="utf-8")
    result = _adjudicate(tmp_path, "import", sheet)
    assert result.exit_code == 1
    assert "row 2: unrecognised reply id 'nope'" in result.output
    assert {p.name: p.read_bytes() for p in run_dir.iterdir()} == before


def test_the_review_cohort_is_declared_and_reported(tmp_path):
    _run(tmp_path)
    run_dir = tmp_path / "results" / "r1"
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert config["semantic_review_cohort"] == {
        "replicates": [0],
        "audit_fraction": 0.1,
        "audit_seed": 0,
    }
    metrics = _metrics(tmp_path)
    assert metrics["audit"]["coverage"] == {"k": 1, "n": 1}
    # The flagged and the audited reply await review; nothing is decided yet.
    assert metrics["detected_semantic_error_rate"]["banned_content"]["all"] == {
        "k": 0,
        "n": 0,
        "unknown": 2,
    }
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "Detected semantic error rate" in report
    assert "audited miss rate" in report
