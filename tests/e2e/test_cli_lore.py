import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from npcbench.cli import app
from tests.factories import character_data, world_data

FIX = Path(__file__).parents[1] / "fixtures" / "s1"
runner = CliRunner()

SCENARIO = {
    "id": "c-dev-spoiler-000",
    "character": "vessa",
    "class": "spoiler",
    "story_point": "act-1",
    "family_id": "dev-spoiler-pair-00",
    "split": "dev",
    "turns": [{"player": "Is it the drowned chapel? Ask Brother Kesh."}],
    "expected": {"forbidden_facts": ["F-002"]},
}


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _setup(tmp_path):
    world = world_data()
    for name in ("story_points", "facts", "entities"):
        _write(tmp_path / "world" / f"{name}.yaml", world[name])
    _write(tmp_path / "character.yaml", character_data())
    _write(tmp_path / "scenarios.yaml", [SCENARIO])


def _run(tmp_path):
    return runner.invoke(
        app,
        [
            "run",
            "--scenarios",
            str(tmp_path / "scenarios.yaml"),
            "--character",
            str(tmp_path / "character.yaml"),
            "--prompt",
            str(FIX / "prompt.md"),
            "--world",
            str(tmp_path / "world"),
            "--model",
            "fake-1",
            "--run-id",
            "r1",
            "--results-dir",
            str(tmp_path / "results"),
        ],
    )


def _replay(tmp_path):
    return runner.invoke(
        app, ["replay", "--run-id", "r1", "--results-dir", str(tmp_path / "results")]
    )


def test_lore_checks_flag_against_the_world_and_replay(tmp_path):
    _setup(tmp_path)
    result = _run(tmp_path)
    assert result.exit_code == 0, result.output
    path = tmp_path / "results" / "r1" / "checks.jsonl"
    rows = {row["check"]: row for row in map(json.loads, path.read_text().splitlines())}
    for check in ("entity_register", "forbidden_facts", "spoiler_facts"):
        row = rows[check]
        assert (row["verdict"], row["provenance"], row["review_status"]) == (
            "unknown",
            None,
            "pending",
        )
        assert row["flagged"] is True, check
    assert rows["entity_register"]["details"]["names"] == ["Brother Kesh"]
    assert "F-002" in rows["forbidden_facts"]["details"]["facts"]
    assert _replay(tmp_path).exit_code == 0


def test_replay_fails_when_the_world_changed(tmp_path):
    _setup(tmp_path)
    assert _run(tmp_path).exit_code == 0
    world = world_data()
    world["entities"].append({"id": "E-kesh", "name": "Brother Kesh", "kind": "person"})
    _write(tmp_path / "world" / "entities.yaml", world["entities"])
    result = _replay(tmp_path)
    assert result.exit_code != 0
    assert "world" in result.output and "changed" in result.output
