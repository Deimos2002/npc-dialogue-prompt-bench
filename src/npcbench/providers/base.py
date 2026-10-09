"""Provider interface: every client streams pieces so the runner can time the first token."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Protocol

from pydantic import BaseModel

from npcbench.schemas import ChatRequest, FailureKind, Usage


class StreamPiece(BaseModel):
    """A chunk of visible text, or the final usage report of a stream."""

    text: str = ""
    usage: Usage | None = None
    model_version: str | None = None


class AttemptFailure(Exception):
    """Raised by a client when an attempt yields no usable output."""

    def __init__(self, kind: FailureKind) -> None:
        super().__init__(kind)
        self.kind: FailureKind = kind


class ProviderConfigError(RuntimeError):
    """A request the provider can never serve as configured; it stops the run, unrecorded."""


class Clock(Protocol):
    def now_ms(self) -> float: ...

    def sleep_ms(self, ms: float) -> None: ...


class ChatClient(Protocol):
    def stream(self, request: ChatRequest) -> Iterator[StreamPiece]: ...


class MonotonicClock:
    def now_ms(self) -> float:
        return time.perf_counter() * 1000.0

    def sleep_ms(self, ms: float) -> None:
        time.sleep(ms / 1000.0)
