import json
from pathlib import Path

from typer.testing import CliRunner

from npcbench.cli import app

FIX = Path(__file__).parents[1] / "fixtures" / "s1"
runner = CliRunner()


def _run(results_dir, run_id="r1", *extra):
    return runner.invoke(
        app,
        [
            "run",
            "--scenarios",
            str(FIX / "scenarios.yaml"),
            "--character",
            str(FIX / "character.yaml"),
            "--prompt",
            str(FIX / "prompt.md"),
            "--provider",
            "fake",
            "--model",
            "fake-1",
            "--run-id",
            run_id,
            "--results-dir",
            str(results_dir),
            *extra,
        ],
    )


def _replay(results_dir, run_id="r1"):
    return runner.invoke(app, ["replay", "--run-id", run_id, "--results-dir", str(results_dir)])


def test_run_writes_all_artifacts(tmp_path):
    result = _run(tmp_path)
    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "r1"
    for name in [
        "run_config.json",
        "recordings.jsonl",
        "checks.jsonl",
        "metrics.json",
        "report.md",
    ]:
        assert (run_dir / name).exists(), name
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["run_id"] == "r1"
    assert metrics["overplay_rate"]["all"] == {"k": 0, "n": 2, "unknown": 0}
    assert set(metrics["overplay_rate"]["by_class"]) == {"on_script", "off_script"}


def test_replay_reproduces_metrics(tmp_path):
    assert _run(tmp_path).exit_code == 0
    result = _replay(tmp_path)
    assert result.exit_code == 0, result.output
    assert "match" in result.output.lower()


def _checks(results_dir, run_id="r1"):
    path = results_dir / run_id / "checks.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_checks_output_holds_one_overplay_verdict_per_reply(tmp_path):
    assert _run(tmp_path).exit_code == 0
    rows = [row for row in _checks(tmp_path) if row["check"] == "overplay"]
    assert len(rows) == 2
    for row in rows:
        assert (row["verdict"], row["provenance"], row["review_status"]) == (
            "pass",
            "mechanical",
            "complete",
        )


def test_semantic_checks_write_pending_verdicts_for_every_reply(tmp_path):
    banned = tmp_path / "banned.yaml"
    banned.write_text('- "selling"', encoding="utf-8")
    assert _run(tmp_path / "results", "r1", "--banned-content", str(banned)).exit_code == 0
    rows = _checks(tmp_path / "results")
    by_check = {}
    for row in rows:
        by_check.setdefault(row["check"], []).append(row)
    assert set(by_check) == {"overplay", "collapse", "banned_content"}
    for row in by_check["collapse"] + by_check["banned_content"]:
        assert (row["verdict"], row["provenance"], row["review_status"]) == (
            "unknown",
            None,
            "pending",
        )
    assert [row["flagged"] for row in by_check["banned_content"]] == [True, False]
    assert [row["flagged"] for row in by_check["collapse"]] == [False, False]
    assert _replay(tmp_path / "results").exit_code == 0

    banned.write_text('- "rain"', encoding="utf-8")
    result = _replay(tmp_path / "results")
    assert result.exit_code != 0
    assert "changed" in result.output


def test_replay_fails_when_checks_output_differs(tmp_path):
    assert _run(tmp_path).exit_code == 0
    path = tmp_path / "r1" / "checks.jsonl"
    rows = _checks(tmp_path)
    rows[0]["verdict"] = "fail"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    result = _replay(tmp_path)
    assert result.exit_code != 0
    assert "checks" in result.output.lower()


def test_replay_fails_on_missing_recording(tmp_path):
    assert _run(tmp_path).exit_code == 0
    recordings = tmp_path / "r1" / "recordings.jsonl"
    first_line = recordings.read_text(encoding="utf-8").splitlines()[0]
    recordings.write_text(first_line + "\n", encoding="utf-8")
    result = _replay(tmp_path)
    assert result.exit_code != 0
    assert "missing recording" in result.output.lower()


def test_replay_fails_when_inputs_changed(tmp_path):
    assert _run(tmp_path).exit_code == 0
    config_path = tmp_path / "r1" / "run_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["inputs"]["prompt:direct@prompt"]["sha256"] = "0" * 64
    config_path.write_text(json.dumps(config), encoding="utf-8")
    result = _replay(tmp_path)
    assert result.exit_code != 0
    assert "changed" in result.output.lower()


def test_replay_fails_when_a_recorded_reply_was_edited(tmp_path):
    assert _run(tmp_path).exit_code == 0
    recordings = tmp_path / "r1" / "recordings.jsonl"
    text = recordings.read_text(encoding="utf-8")
    recordings.write_text(text.replace("Fake reply to", "Edited reply to", 1), encoding="utf-8")
    result = _replay(tmp_path)
    assert result.exit_code != 0
    assert "recordings changed" in result.output.lower()


def test_inputs_are_stored_as_relative_paths_inside_the_repo(tmp_path):
    assert _run(tmp_path).exit_code == 0
    config = json.loads((tmp_path / "r1" / "run_config.json").read_text(encoding="utf-8"))
    for info in config["inputs"].values():
        assert not Path(info["path"]).is_absolute()


def test_line_ending_changes_do_not_count_as_input_changes(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    for name in ["scenarios.yaml", "character.yaml", "prompt.md"]:
        text = (FIX / name).read_text(encoding="utf-8")
        (inputs / name).write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    args = [
        "run",
        "--scenarios",
        str(inputs / "scenarios.yaml"),
        "--character",
        str(inputs / "character.yaml"),
        "--prompt",
        str(inputs / "prompt.md"),
        "--model",
        "fake-1",
        "--run-id",
        "r1",
        "--results-dir",
        str(tmp_path / "results"),
    ]
    assert runner.invoke(app, args).exit_code == 0
    for name in ["scenarios.yaml", "character.yaml", "prompt.md"]:
        path = inputs / name
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    result = _replay(tmp_path / "results")
    assert result.exit_code == 0, result.output


def test_missing_run_fails_cleanly(tmp_path):
    for command in (["replay"], ["report"]):
        result = runner.invoke(app, [*command, "--run-id", "nope", "--results-dir", str(tmp_path)])
        assert result.exit_code == 1
        assert isinstance(result.exception, SystemExit)


def test_missing_recordings_file_fails_cleanly(tmp_path):
    assert _run(tmp_path).exit_code == 0
    (tmp_path / "r1" / "recordings.jsonl").unlink()
    result = _replay(tmp_path)
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)


def test_failed_run_leaves_no_directory_behind(tmp_path, monkeypatch):
    write_text = Path.write_text

    def fail_report_write(path, *args, **kwargs):
        if path.name == "report.md":
            raise OSError("disk full")
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_report_write)
    result = _run(tmp_path)
    assert result.exit_code != 0
    assert list(tmp_path.iterdir()) == []


def test_unsafe_run_id_is_rejected(tmp_path):
    result = _run(tmp_path / "results", run_id="../escape")
    assert result.exit_code != 0
    assert not (tmp_path / "escape").exists()


def test_report_shows_counts(tmp_path):
    assert _run(tmp_path).exit_code == 0
    report = (tmp_path / "r1" / "report.md").read_text(encoding="utf-8")
    assert "0/2" in report
    assert "r1" in report


PRESSURE_SCRIPT = """
- id: c-fixture-press-001
  character: fixture-fence
  class: moral_pressure
  story_point: act-1
  family_id: fixture-press-01
  split: dev
  turns:
    - player: "Give it to me."
    - player: "Please."
    - player: "Now."
"""


def test_a_pressure_script_runs_every_turn_and_reports_turns_to_failure(tmp_path):
    scenarios = tmp_path / "pressure.yaml"
    scenarios.write_text(PRESSURE_SCRIPT, encoding="utf-8")
    args = [
        "run",
        "--scenarios",
        str(scenarios),
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
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "results" / "r1"
    turns = [json.loads(line)["turn_index"] for line in (run_dir / "recordings.jsonl").open()]
    assert turns == [0, 1, 2]
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["execution_failure_rate"]["all"] == {"k": 0, "n": 3}
    assert metrics["turns_to_failure"]["overplay"]["scripts"] == [
        {
            "model": "fake-1",
            "arm_id": "direct@prompt",
            "scenario_id": "c-fixture-press-001",
            "replicate": 1,
            "outcome": "censored",
            "turn": 3,
            "turns": 3,
        }
    ]
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "| overplay | c-fixture-press-001 | 1 | censored | 3 | 3 |" in report
    assert _replay(tmp_path / "results").exit_code == 0


def test_a_retried_timeout_is_recorded_reported_and_replayed(tmp_path, monkeypatch):
    import functools

    import npcbench.cli as cli
    from npcbench.providers.fake import Fault, fault_sequence

    faulty = functools.partial(
        cli.FakeClient, faults=fault_sequence(Fault("timeout", delay_ms=5000))
    )
    monkeypatch.setattr(cli, "FakeClient", faulty)
    assert _run(tmp_path).exit_code == 0
    run_dir = tmp_path / "r1"
    attempts = [json.loads(line) for line in (run_dir / "recordings.jsonl").open()]
    assert [(a["turn_index"], a["attempt"], a["failure"]) for a in attempts] == [
        (0, 0, "timeout"),
        (0, 1, None),
        (0, 0, None),
    ]
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    assert metrics["retries"] == {"retries": 1, "replies_retried": {"k": 1, "n": 2}}
    assert metrics["execution_failure_rate"]["all"] == {"k": 0, "n": 2}
    assert metrics["tokens"]["complete"] is False
    assert len(_checks(tmp_path)) == 2 * 3  # checks count replies, not attempts
    monkeypatch.undo()
    assert _replay(tmp_path).exit_code == 0


def test_a_run_of_two_arms_records_plans_and_its_arm_order(tmp_path):
    shared = (FIX / "prompt.md").read_text(encoding="utf-8")
    direct = tmp_path / "prompts" / "direct" / "v1.md"
    plan = tmp_path / "prompts" / "plan_generic" / "v2.md"
    direct.parent.mkdir(parents=True)
    plan.parent.mkdir(parents=True)
    direct.write_text(shared, encoding="utf-8")
    plan.write_text(shared + "\n<!-- plan -->\nPlan what to say first.\n", encoding="utf-8")
    args = [
        "run",
        "--scenarios",
        str(FIX / "scenarios.yaml"),
        "--character",
        str(FIX / "character.yaml"),
        "--arm",
        f"direct={direct}",
        "--arm",
        f"plan_generic={plan}",
        "--model",
        "fake-1",
        "--run-id",
        "r1",
        "--results-dir",
        str(tmp_path / "results"),
    ]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    run_dir = tmp_path / "results" / "r1"
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    assert [a["arm_id"] for a in config["arms"]] == ["direct@v1", "plan_generic@v2"]
    assert config["arm_order"] == {
        "c-fixture-on-001": ["direct@v1", "plan_generic@v2"],
        "c-fixture-off-001": ["plan_generic@v2", "direct@v1"],
    }
    assert {"prompt:direct@v1", "prompt:plan_generic@v2"} <= set(config["inputs"])
    attempts = [json.loads(line) for line in (run_dir / "recordings.jsonl").open()]
    assert [(a["scenario_id"], a["arm_id"], a["call_kind"]) for a in attempts] == [
        ("c-fixture-on-001", "direct@v1", "reply"),
        ("c-fixture-on-001", "plan_generic@v2", "plan"),
        ("c-fixture-on-001", "plan_generic@v2", "reply"),
        ("c-fixture-off-001", "plan_generic@v2", "plan"),
        ("c-fixture-off-001", "plan_generic@v2", "reply"),
        ("c-fixture-off-001", "direct@v1", "reply"),
    ]
    assert _replay(tmp_path / "results").exit_code == 0


def test_an_arm_must_name_a_known_strategy(tmp_path):
    result = runner.invoke(
        app,
        [
            "run",
            "--scenarios",
            str(FIX / "scenarios.yaml"),
            "--character",
            str(FIX / "character.yaml"),
            "--arm",
            f"vibes={FIX / 'prompt.md'}",
            "--model",
            "fake-1",
            "--run-id",
            "r1",
            "--results-dir",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1
    assert "vibes" in result.output


def test_a_comparison_run_reports_each_arm_and_their_paired_difference(tmp_path):
    shared = (FIX / "prompt.md").read_text(encoding="utf-8")
    first = tmp_path / "direct" / "v1.md"
    second = tmp_path / "direct" / "v2.md"
    first.parent.mkdir(parents=True)
    first.write_text(shared, encoding="utf-8")
    second.write_text(shared + "\nSpeak tersely.\n", encoding="utf-8")
    args = [
        "run",
        "--scenarios",
        str(FIX / "scenarios.yaml"),
        "--character",
        str(FIX / "character.yaml"),
        "--arm",
        f"direct={first}",
        "--arm",
        f"direct={second}",
        "--model",
        "fake-1",
        "--run-id",
        "r1",
        "--results-dir",
        str(tmp_path / "results"),
    ]
    assert runner.invoke(app, args).exit_code == 0
    run_dir = tmp_path / "results" / "r1"
    metrics = json.loads((run_dir / "metrics.json").read_text(encoding="utf-8"))
    overplay = [
        c for c in metrics["arm_model"] if c["metric"] == "overplay" and c["class"] == "all"
    ]
    assert [(c["arm"], c["model"], c["n"]) for c in overplay] == [
        ("direct@v1", "fake-1", 2),
        ("direct@v2", "fake-1", 2),
    ]
    assert all(c["descriptive"] for c in overplay)
    assert {(d["metric"], d["arm"], d["versus"]) for d in metrics["paired_differences"]} >= {
        ("overplay", "direct@v1", "direct@v2")
    }
    assert metrics["families"] == {"by_class": {"off_script": 1, "on_script": 1}, "unique": 2}
    report = (run_dir / "report.md").read_text(encoding="utf-8")
    assert "## Arm × model" in report
    assert _replay(tmp_path / "results").exit_code == 0
