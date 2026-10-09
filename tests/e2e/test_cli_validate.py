import yaml
from typer.testing import CliRunner

from npcbench.cli import app
from tests.factories import character_data, families_data, suite_data, world_data

runner = CliRunner()


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _content(root, scenarios):
    world = world_data()
    _write(root / "world" / "story_points.yaml", world["story_points"])
    _write(root / "world" / "facts.yaml", world["facts"])
    _write(root / "world" / "entities.yaml", world["entities"])
    _write(root / "characters" / "C.yaml", character_data())
    for scenario in scenarios:
        _write(root / "scenarios" / scenario["split"] / f"{scenario['id']}.yaml", scenario)
    for split, review in families_data(scenarios).items():
        _write(root / "scenarios" / split / "families.yaml", review)


def _validate(root, *extra):
    return runner.invoke(
        app,
        [
            "validate",
            "--world",
            str(root / "world"),
            "--characters",
            str(root / "characters"),
            "--scenarios",
            str(root / "scenarios"),
            *extra,
        ],
    )


def test_valid_v01_suite_passes(tmp_path):
    _content(tmp_path, suite_data())
    result = _validate(tmp_path)
    assert result.exit_code == 0, result.output
    assert "50 scenarios" in result.output
    assert "hash" in result.output


def test_broken_suite_lists_issues_and_fails(tmp_path):
    scenarios = suite_data()
    scenarios[0]["story_point"] = "act-9"
    _content(tmp_path, scenarios)
    result = _validate(tmp_path)
    assert result.exit_code == 1
    assert "unknown_story_point" in result.output
    assert scenarios[0]["id"] in result.output


def test_profile_none_skips_count_rules(tmp_path):
    _content(tmp_path, suite_data()[:3])
    assert _validate(tmp_path).exit_code == 1
    assert _validate(tmp_path, "--profile", "none").exit_code == 0


def test_missing_family_review_fails(tmp_path):
    _content(tmp_path, suite_data())
    (tmp_path / "scenarios" / "test" / "families.yaml").unlink()
    result = _validate(tmp_path)
    assert result.exit_code == 1
    assert "family_unregistered" in result.output


def test_unreadable_world_fails_cleanly(tmp_path):
    _content(tmp_path, suite_data())
    (tmp_path / "world" / "facts.yaml").write_text("- id: [unclosed", encoding="utf-8")
    result = _validate(tmp_path)
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
