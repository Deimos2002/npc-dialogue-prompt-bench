"""Recording store and request keys (protocol–11.2).

Replay looks every call up by key and never falls back to a live call: a missing recording
is an error.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from npcbench.schemas import ChatRequest, Recording


def request_key(request: ChatRequest, *, slot: dict[str, Any] | None = None) -> str:
    """Stable hash of a request and its place in the run plan.

    The slot (scenario, arm, turn, replicate, call kind, attempt) keeps identical requests in
    different places of the plan, such as two replicates, from sharing one recording.
    """
    payload = {"request": request.model_dump(mode="json"), "slot": slot or {}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class MissingRecording(LookupError):
    def __init__(self, key: str):
        super().__init__(
            f"Missing recording for request {key}; replay never makes a model call "
            "(protocol)."
        )
        self.key = key


class RecordingMismatch(LookupError):
    """A stored recording does not belong to the request it is served for."""


class RecordingStore:
    def __init__(self) -> None:
        self._by_key: dict[str, Recording] = {}

    def add(self, recording: Recording) -> None:
        if recording.key in self._by_key:
            raise ValueError(f"Duplicate recording key {recording.key}")
        self._by_key[recording.key] = recording

    def get(self, key: str) -> Recording:
        try:
            return self._by_key[key]
        except KeyError:
            raise MissingRecording(key) from None

    def __iter__(self) -> Iterator[Recording]:
        return iter(self._by_key.values())

    def __len__(self) -> int:
        return len(self._by_key)

    def save(self, path: Path) -> None:
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for recording in self._by_key.values():
                f.write(recording.model_dump_json() + "\n")

    @classmethod
    def load(cls, path: Path) -> RecordingStore:
        store = cls()
        with path.open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    store.add(Recording.model_validate_json(line))
        return store
