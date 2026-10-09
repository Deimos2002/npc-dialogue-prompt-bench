"""Run scenarios through a strategy arm, live or from recordings (protocol)."""

from __future__ import annotations

from typing import Any, Protocol

from npcbench.prompts import ArmPrompt, plan_messages, render_arm_prompt, reply_system
from npcbench.providers.base import AttemptFailure, ChatClient, Clock
from npcbench.recorder import RecordingMismatch, RecordingStore, request_key
from npcbench.replies import plan_usable
from npcbench.schemas import (
    Arm,
    CharacterSheet,
    ChatRequest,
    FailureKind,
    Message,
    Recording,
    Scenario,
    Timings,
    Usage,
)

# Both plan strategies share this plan-token cap, so they differ in what they plan, not in
# how much (protocol).
PLAN_TOKEN_CAP = 150
# Only these failures are retried, once (ADR 0002); parse failures and truncation are
# measured model behaviour, and retrying them would hide it.
RETRYABLE: frozenset[FailureKind] = frozenset({"timeout", "transport"})
MAX_ATTEMPTS = 2


class Source(Protocol):
    def fetch(self, *, key: str, request: ChatRequest, meta: dict[str, Any]) -> Recording: ...


class LiveSource:
    """Calls a client and times the first visible token and the full attempt.

    A retry first waits `backoff_ms`, recorded on the retry so latency can include it.
    """

    def __init__(self, client: ChatClient, clock: Clock, backoff_ms: float = 1000.0) -> None:
        self._client = client
        self._clock = clock
        self._backoff_ms = backoff_ms

    def fetch(self, *, key: str, request: ChatRequest, meta: dict[str, Any]) -> Recording:
        backoff_ms = 0.0
        if meta["attempt"] > 0:
            waited_from = self._clock.now_ms()
            self._clock.sleep_ms(self._backoff_ms)
            backoff_ms = self._clock.now_ms() - waited_from
        start = self._clock.now_ms()
        ttft_ms: float | None = None
        parts: list[str] = []
        usage = Usage()
        model_version: str | None = None
        failure = None
        try:
            for piece in self._client.stream(request):
                if piece.text:
                    if ttft_ms is None and piece.text.strip():
                        ttft_ms = self._clock.now_ms() - start
                    parts.append(piece.text)
                if piece.usage is not None:
                    usage = piece.usage
                if piece.model_version is not None:
                    model_version = piece.model_version
        except AttemptFailure as exc:
            failure = exc.kind
        total_ms = self._clock.now_ms() - start
        return Recording(
            key=key,
            **meta,
            request=request,
            response_text="".join(parts),
            failure=failure,
            backoff_ms=backoff_ms,
            model_version=model_version,
            timings=Timings(ttft_ms=ttft_ms, total_ms=total_ms),
            usage=usage,
        )


class ReplaySource:
    """Serves recorded replies only.

    A missing key raises MissingRecording; a recording made for a different request or plan
    slot raises RecordingMismatch.
    """

    def __init__(self, store: RecordingStore) -> None:
        self._store = store

    def fetch(self, *, key: str, request: ChatRequest, meta: dict[str, Any]) -> Recording:
        recording = self._store.get(key)
        mismatched = [name for name, value in meta.items() if getattr(recording, name) != value]
        if recording.key != key or recording.request != request:
            mismatched.append("request")
        if mismatched:
            raise RecordingMismatch(
                f"Recording {key} does not match the replayed request ({', '.join(mismatched)})."
            )
        return recording


def _call(
    source: Source, request: ChatRequest, call: dict[str, Any], meta: dict[str, Any]
) -> list[Recording]:
    """Every attempt of one call: a retry follows only a retryable failure (ADR 0002)."""
    attempts: list[Recording] = []
    for attempt in range(MAX_ATTEMPTS):
        slot = {**call, "attempt": attempt}
        recording = source.fetch(
            key=request_key(request, slot=slot), request=request, meta={**meta, **slot}
        )
        attempts.append(recording)
        if recording.failure not in RETRYABLE:
            break
    return attempts


def arm_order(scenario_ids: list[str], arm_ids: list[str]) -> dict[str, list[str]]:
    """Predeclared, counterbalanced arm order: scenario i runs the arms rotated by i.

    Over every block of len(arm_ids) scenarios each arm runs first, second, ... once, so no
    arm systematically runs first (protocol).
    """
    k = len(arm_ids)
    return {sid: arm_ids[i % k :] + arm_ids[: i % k] for i, sid in enumerate(scenario_ids)}


def _run_scenario(
    *,
    scenario: Scenario,
    prompt: ArmPrompt,
    arm: Arm,
    run_id: str,
    model: str,
    params: dict[str, Any],
    source: Source,
    replicate: int,
) -> list[Recording]:
    """Every turn of one scenario under one arm; an execution failure ends the script.

    A plan arm makes a plan call capped at PLAN_TOKEN_CAP, then a reply call that sees the
    plan. Only visible replies enter later turns' history (protocol).
    """
    meta = {"run_id": run_id, "strategy": arm.strategy, "prompt_version": arm.prompt_version}
    history: list[Message] = []
    recordings: list[Recording] = []
    for turn_index, turn in enumerate(scenario.turns):
        history.append(Message(role="user", content=turn.player))
        call = {
            "scenario_id": scenario.id,
            "arm_id": arm.arm_id,
            "turn_index": turn_index,
            "replicate": replicate,
        }
        plan: str | None = None
        if prompt.plan_instruction is not None:
            plan_request = ChatRequest(
                model=model,
                messages=plan_messages(prompt, history),
                params={**params, "max_tokens": PLAN_TOKEN_CAP},
            )
            attempts = _call(source, plan_request, {**call, "call_kind": "plan"}, meta)
            recordings.extend(attempts)
            if not plan_usable(attempts[-1]):
                break
            plan = attempts[-1].response_text
        reply_request = ChatRequest(
            model=model,
            messages=[Message(role="system", content=reply_system(prompt, plan)), *history],
            params=dict(params),
        )
        attempts = _call(source, reply_request, {**call, "call_kind": "reply"}, meta)
        recordings.extend(attempts)
        if attempts[-1].failure is not None:
            # An execution failure ends the script: later turns are never run.
            break
        history.append(Message(role="assistant", content=attempts[-1].response_text))
    return recordings


def run_arms(
    *,
    scenarios: list[Scenario],
    character: CharacterSheet,
    templates: dict[str, str],
    arms: list[Arm],
    order: dict[str, list[str]],
    run_id: str,
    model: str,
    params: dict[str, Any],
    source: Source,
    replicate: int = 0,
) -> list[Recording]:
    """Each scenario under every arm, in the predeclared per-scenario arm order."""
    mismatched = [s.id for s in scenarios if s.character != character.id]
    if mismatched:
        raise ValueError(f"Scenarios {mismatched} do not belong to character {character.id!r}")
    by_id = {arm.arm_id: arm for arm in arms}
    prompts = {
        arm.arm_id: render_arm_prompt(templates[arm.arm_id], character, arm.strategy)
        for arm in arms
    }
    recordings: list[Recording] = []
    for scenario in scenarios:
        for arm_id in order[scenario.id]:
            recordings += _run_scenario(
                scenario=scenario,
                prompt=prompts[arm_id],
                arm=by_id[arm_id],
                run_id=run_id,
                model=model,
                params=params,
                source=source,
                replicate=replicate,
            )
    return recordings


def run_arm(
    *,
    scenarios: list[Scenario],
    character: CharacterSheet,
    template: str,
    run_id: str,
    arm: Arm,
    model: str,
    params: dict[str, Any],
    source: Source,
    replicate: int = 0,
) -> list[Recording]:
    """A run of a single arm."""
    return run_arms(
        scenarios=scenarios,
        character=character,
        templates={arm.arm_id: template},
        arms=[arm],
        order={s.id: [arm.arm_id] for s in scenarios},
        run_id=run_id,
        model=model,
        params=params,
        source=source,
        replicate=replicate,
    )
