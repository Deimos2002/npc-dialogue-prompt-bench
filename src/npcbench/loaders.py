"""Load authored YAML content. Always `yaml.safe_load`; never execute content."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from npcbench.schemas import CharacterSheet, FamilyReview, Scenario, World

FAMILIES_FILE = "families.yaml"


def _read_yaml(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as f:
            return yaml.safe_load(f)
    except yaml.MarkedYAMLError as exc:
        # Report the problem and position only; the default message quotes file content.
        line = exc.problem_mark.line + 1 if exc.problem_mark else "?"
        raise ValueError(f"{path}: invalid YAML at line {line} ({exc.problem})") from None
    except yaml.YAMLError:
        raise ValueError(f"{path}: invalid YAML") from None


def _yaml_files(path: Path) -> list[Path]:
    """YAML files under `path`, skipping links that resolve outside it (symlinks, junctions)."""
    if not path.is_dir():
        return [path]
    root = path.resolve()
    return sorted(
        p
        for p in path.rglob("*")
        if p.suffix.lower() in {".yaml", ".yml"}
        and p.is_file()
        and p.resolve().is_relative_to(root)
    )


def _validate(model: type[BaseModel], data: Any, file: Path) -> Any:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"{file}: {exc}") from None


def load_scenarios(path: Path) -> list[Scenario]:
    """Load one file or every YAML file under a directory; each holds one scenario or a list.

    Family reviews (`families.yaml`) are skipped; `load_families` reads them.
    """
    scenarios: list[Scenario] = []
    for file in _yaml_files(path):
        if file.name.lower() == FAMILIES_FILE:
            continue
        data = _read_yaml(file)
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{file}: expected a scenario mapping")
            scenarios.append(_validate(Scenario, item, file))
    ids = [s.id for s in scenarios]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise ValueError(f"{path}: duplicate scenario ids {duplicates}")
    return scenarios


def load_families(path: Path) -> list[FamilyReview]:
    """Every `families.yaml` under a scenario directory; none for a single scenario file."""
    if not path.is_dir():
        return []
    return [
        _validate(FamilyReview, _read_yaml(file), file)
        for file in _yaml_files(path)
        if file.name.lower() == FAMILIES_FILE
    ]


def load_character(path: Path) -> CharacterSheet:
    return _validate(CharacterSheet, _read_yaml(path), path)


def load_characters(path: Path) -> dict[str, CharacterSheet]:
    characters: dict[str, CharacterSheet] = {}
    for file in _yaml_files(path):
        sheet = load_character(file)
        if sheet.id in characters:
            raise ValueError(f"{file}: duplicate character id {sheet.id}")
        characters[sheet.id] = sheet
    return characters


WORLD_FILES = ("story_points.yaml", "facts.yaml", "entities.yaml")


def load_world(directory: Path) -> World:
    data = {
        "story_points": _read_yaml(directory / "story_points.yaml"),
        "facts": _read_yaml(directory / "facts.yaml") or [],
        "entities": _read_yaml(directory / "entities.yaml") or [],
    }
    return _validate(World, data, directory)


def load_phrase_list(path: Path) -> list[str]:
    """A YAML list of non-empty phrases, such as a banned content list."""
    data = _read_yaml(path)
    if not isinstance(data, list) or not all(isinstance(p, str) and p.strip() for p in data):
        raise ValueError(f"{path}: expected a list of non-empty phrases")
    return data


def sha256_file(path: Path) -> str:
    """Content hash with line endings normalised, so a CRLF checkout matches an LF one."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def sha256_input(path: Path) -> str:
    """Hash of a run input: a file's content, or a world directory's three files together."""
    if not path.is_dir():
        return sha256_file(path)
    parts = [f"{name}:{sha256_file(path / name)}" for name in WORLD_FILES]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
