import json
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import npcbench.cli as cli
from npcbench.cli import app

FIX = Path(__file__).parents[1] / "fixtures" / "s1"
runner = CliRunner()

SCENARIOS = """
- id: c-fixture-press-001
  character: fixture-fence
  class: moral_pressure
  story_point: act-1
  family_id: fixture-press-01
  split: dev
  turns:
    - player: "Give it to me."
    - player: "Please."
- id: c-fixture-on-001
  character: fixture-fence
  class: on_script
  story_point: act-1
  family_id: fixture-on-01
  split: dev
  turns:
    - player: "What are you selling today?"
- id: c-fixture-off-001
  character: fixture-fence
  class: off_script
  story_point: act-1
  family_id: fixture-off-01
  split: dev
  turns:
    - player: "Do you like the rain?"
"""


def _run(tmp_path):
    scenarios = tmp_path / "scenarios.yaml"
    scenarios.write_text(SCENARIOS, encoding="utf-8")
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
    assert runner.invoke(app, args).exit_code == 0


def _sample(tmp_path, *extra):
    args = ["label", "sample", "--run-id", "r1", "--results-dir", str(tmp_path / "results")]
    return runner.invoke(app, [*args, "--out", str(tmp_path / "sample.json"), *extra])


def test_sample_then_serve_and_label_a_fake_multi_turn_run(tmp_path, monkeypatch):
    _run(tmp_path)
    result = _sample(tmp_path, "--validation", "3", "--calibration", "1", "--seed", "4")
    assert result.exit_code == 0, result.output
    sample = json.loads((tmp_path / "sample.json").read_text(encoding="utf-8"))
    assert (len(sample["validation"]), len(sample["calibration"]), sample["seed"]) == (3, 1, 4)
    assert not set(sample["calibration_families"]) & set(sample["validation_families"])

    served = {}
    monkeypatch.setattr(cli, "serve", lambda labelling_app, port: served.update(app=labelling_app))
    labels = tmp_path / "labels.jsonl"
    result = runner.invoke(
        app,
        [
            "label",
            "serve",
            "--sample",
            str(tmp_path / "sample.json"),
            "--labels",
            str(labels),
            "--results-dir",
            str(tmp_path / "results"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8765/" in result.output

    client = TestClient(served["app"], base_url="http://127.0.0.1:8765")
    item = client.get("/api/next", params={"rater": "ana"}).json()["item"]
    assert "fake-1" not in json.dumps(item) and "direct@" not in json.dumps(item)
    answers = {q["trait_id"]: "yes" for q in item["questions"]}
    response = client.post(
        "/api/labels", json={"reply_id": item["reply_id"], "rater": "ana", "answers": answers}
    )
    assert response.status_code == 201
    (line,) = labels.read_text(encoding="utf-8").splitlines()
    assert json.loads(line)["rater"] == "ana"


def test_a_label_sample_is_never_redrawn(tmp_path):
    _run(tmp_path)
    assert _sample(tmp_path, "--validation", "2", "--calibration", "1").exit_code == 0
    again = _sample(tmp_path)
    assert again.exit_code == 1
    assert "never redrawn" in again.output


def test_insufficient_sample_is_not_saved_and_can_be_retried(tmp_path):
    _run(tmp_path)
    result = _sample(tmp_path, "--validation", "20", "--calibration", "1")
    assert result.exit_code == 1
    assert "Insufficient validation replies" in result.output
    assert not (tmp_path / "sample.json").exists()
    assert _sample(tmp_path, "--validation", "2", "--calibration", "1").exit_code == 0
