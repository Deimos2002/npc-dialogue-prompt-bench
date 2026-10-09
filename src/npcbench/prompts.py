"""Prompt rendering. Rendering is deterministic so replay keys stay stable."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from npcbench.schemas import CharacterSheet, Message, Strategy

_PLACEHOLDER = re.compile(r"\{\{\s*[\w.]+\s*\}\}")
_DENSITY = {"dense": "show in every reply", "sparse": "show only when relevant"}


def render_character_sheet(character: CharacterSheet) -> str:
    """The same structured sheet for every arm (protocol)."""
    lines = [
        f"Name: {character.name}",
        f"Summary: {character.summary.strip()}",
        f"Voice: {character.voice.tone}",
    ]
    if character.voice.vocabulary:
        lines.append(f"Vocabulary: {', '.join(character.voice.vocabulary)}")
    lines.append("Traits:")
    lines += [f"- {t.description} ({_DENSITY[t.density]})" for t in character.traits]
    for title, items in (("Goals", character.goals), ("Hard limits", character.hard_limits)):
        if items:
            lines.append(f"{title}:")
            lines += [f"- {item}" for item in items]
    return "\n".join(lines)


def render_system_prompt(template: str, character: CharacterSheet) -> str:
    rendered = template.replace("{{character_name}}", character.name).replace(
        "{{character_sheet}}", render_character_sheet(character)
    )
    leftover = _PLACEHOLDER.findall(rendered)
    if leftover:
        raise ValueError(f"Unknown prompt placeholders: {leftover}")
    return rendered


# A plan strategy's prompt file: the shared system prompt, this marker line, then the plan
# instruction. Only the plan instruction differs between arms (protocol).
PLAN_MARKER = "<!-- plan -->"
PLAN_HEADING = "Your private plan for this reply. The player never sees it:"


@dataclass(frozen=True)
class ArmPrompt:
    system: str
    plan_instruction: str | None
    transcript_context: bool = False


def render_arm_prompt(template: str, character: CharacterSheet, strategy: Strategy) -> ArmPrompt:
    shared, marker, plan = template.partition(PLAN_MARKER)
    if strategy == "direct":
        if marker:
            raise ValueError("A direct prompt has no plan section")
        return ArmPrompt(render_system_prompt(template, character).strip(), None)
    if not marker or not plan.strip():
        raise ValueError(f"A {strategy} prompt needs a plan instruction after {PLAN_MARKER}")
    directive = "<!-- plan-context: transcript -->"
    transcript = plan.strip().startswith(directive)
    instruction = plan.strip().removeprefix(directive).strip() if transcript else plan.strip()
    if not instruction:
        raise ValueError("A plan context directive needs a planning instruction")
    return ArmPrompt(render_system_prompt(shared, character).strip(), instruction, transcript)


def plan_system(prompt: ArmPrompt) -> str:
    """The system prompt of a plan call: the shared prompt and the plan instruction."""
    if prompt.plan_instruction is None:
        raise ValueError("A direct arm makes no plan call")
    return f"{prompt.system}\n\n{prompt.plan_instruction}"


def reply_system(prompt: ArmPrompt, plan: str | None) -> str:
    """The system prompt of a reply call: the shared prompt and, for plan arms, this turn's plan."""
    if plan is None:
        return prompt.system
    return f"{prompt.system}\n\n{PLAN_HEADING}\n{plan.strip()}"


def plan_messages(prompt: ArmPrompt, history: list[Message]) -> list[Message]:
    """Opt-in transcript context separates past speech from the current planning task.

    Legacy prompts retain their exact messages, preserving existing replay keys.
    Transcript prompts retain every visible turn as JSON data, not assistant speech.
    """
    system = Message(role="system", content=plan_system(prompt))
    if not prompt.transcript_context:
        return [system, *history]
    transcript = json.dumps(
        [
            {"speaker": "player" if m.role == "user" else "elder", "text": m.content}
            for m in history
        ],
        ensure_ascii=False,
    )
    return [
        system,
        Message(
            role="user",
            content=(
                "Conversation transcript (context data, including the current player turn):\n"
                + transcript
                + "\n\nNow perform the private planning task specified in the system instruction. "
                "Produce only the four note lines, not a reply to the player."
            ),
        ),
    ]
