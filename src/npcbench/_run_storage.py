"""Private file-format and publication helpers for run workflows."""

from __future__ import annotations

import json
import re
import tempfile
import threading
from pathlib import Path
from typing import Any

from npcbench.adjudication import Adjudication

ADJUDICATIONS_FILE = "adjudications.jsonl"
_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
_REPLACE_LOCK = threading.Lock()


class RunError(ValueError):
    """A run operation could not complete; safe to show directly to a caller."""


def run_directory(results_dir: Path, run_id: str) -> Path:
    """Validate the identifier before resolving it beneath the results directory."""
    if not _RUN_ID.fullmatch(run_id) or ".." in run_id:
        raise RunError(f"Invalid run id {run_id!r}: use letters, digits, '.', '_' or '-' (max 64).")
    base = results_dir.resolve()
    run_dir = (base / run_id).resolve()
    if run_dir.parent != base:
        raise RunError(f"Run id {run_id!r} escapes the results directory.")
    return run_dir


def portable_path(path: Path) -> str:
    """Use checkout-relative paths where possible, preserving portable replay."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(resolved)


def json_text(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_json(path: Path, data: Any) -> None:
    path.write_text(json_text(data), encoding="utf-8", newline="\n")


def write_checks(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def read_checks(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def read_adjudications(run_dir: Path) -> dict[tuple[str, str], Adjudication]:
    path = run_dir / ADJUDICATIONS_FILE
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as stream:
        items = [Adjudication.model_validate_json(line) for line in stream if line.strip()]
    return {(item.reply_id, item.check): item for item in items}


def replace_text(path: Path, text: str) -> None:
    """Swap one complete file into place; this is not a multi-file transaction."""
    staging = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}-", suffix=".tmp", delete=False,
        ) as stream:
            staging = Path(stream.name)
            stream.write(text)
        # Windows can reject overlapping replacement operations on the same target.
        with _REPLACE_LOCK:
            staging.replace(path)
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
