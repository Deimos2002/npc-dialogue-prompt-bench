"""Optional quota pacing between attempts, outside measured provider latency."""

from __future__ import annotations

from typing import Any

from npcbench.providers.base import Clock
from npcbench.runner import Source
from npcbench.schemas import ChatRequest, Recording


class PacedSource:
    def __init__(self, source: Source, clock: Clock, interval_ms: float) -> None:
        self._source = source
        self._clock = clock
        self._interval_ms = interval_ms
        self._last_finished: float | None = None

    def fetch(self, *, key: str, request: ChatRequest, meta: dict[str, Any]) -> Recording:
        if self._last_finished is not None:
            remaining = self._last_finished + self._interval_ms - self._clock.now_ms()
            if remaining > 0:
                self._clock.sleep_ms(remaining)
        try:
            return self._source.fetch(key=key, request=request, meta=meta)
        finally:
            self._last_finished = self._clock.now_ms()
