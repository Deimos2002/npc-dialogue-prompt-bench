"""Synthetic world, character and v0.1-shaped suite for tests. Not benchmark content."""

from __future__ import annotations

import copy
from typing import Any

from npcbench.schemas import CharacterSheet, FamilyReview, Scenario, World

CLASSES = ["on_script", "off_script", "adversarial", "spoiler", "moral_pressure"]
PRESSURE = {"adversarial", "moral_pressure"}


def world_data() -> dict[str, Any]:
    return {
        "story_points": [
            {"id": "act-1", "label": "Arrival"},
            {"id": "act-2", "label": "The deal"},
            {"id": "act-3", "label": "The betrayal"},
        ],
        "facts": [
            {
                "id": "F-001",
                "subject": "Vessa",
                "predicate": "fences goods for",
                "object": "the Lantern Guild",
                "known_from_by_character": {"vessa": "act-1"},
                "secret": False,
                "reveal_condition": None,
                "aliases": [],
            },
            {
                "id": "F-002",
                "subject": "smuggling route",
                "predicate": "runs through",
                "object": "the drowned chapel",
                "known_from_by_character": {"vessa": "act-1"},
                "secret": True,
                "reveal_condition": "the player has paid the guild toll",
                "aliases": ["chapel route"],
            },
            {
                "id": "F-004",
                "subject": "the guild's ledger",
                "predicate": "is hidden in",
                "object": "the lantern loft",
                "known_from_by_character": {"vessa": "act-1"},
                "secret": True,
                "reveal_condition": "the player has saved Vessa's life",
                "aliases": [],
            },
            {
                "id": "F-005",
                "subject": "the harbour toll",
                "predicate": "will double after",
                "object": "the deal",
                "known_from_by_character": {"vessa": "act-2"},
                "secret": False,
                "reveal_condition": None,
                "aliases": [],
            },
            {
                "id": "F-006",
                "subject": "Vessa",
                "predicate": "owes a debt to",
                "object": "the harbourmaster",
                "known_from_by_character": {"vessa": "act-1"},
                "secret": True,
                "reveal_condition": "the player already holds the debt note",
                "aliases": [],
            },
            {
                "id": "F-003",
                "subject": "the harbourmaster",
                "predicate": "will betray",
                "object": "the Lantern Guild",
                "known_from_by_character": {"vessa": "act-3"},
                "secret": False,
                "reveal_condition": None,
                "aliases": [],
            },
        ],
        "entities": [
            {"id": "E-vessa", "name": "Vessa", "kind": "person", "aliases": []},
            {"id": "E-guild", "name": "Lantern Guild", "kind": "faction", "aliases": ["the Guild"]},
            {"id": "E-harbour", "name": "Grey Harbour", "kind": "place", "aliases": []},
        ],
    }


def world() -> World:
    return World.model_validate(world_data())


def character_data() -> dict[str, Any]:
    return {
        "id": "vessa",
        "name": "Vessa",
        "summary": "A fence who trades in stolen goods and favours.",
        "voice": {"register": "clipped, wary", "vocabulary": ["coin", "cut", "goods"]},
        "traits": [
            {"id": "greedy", "description": "Always angles for profit.", "density": "dense"},
            {"id": "grudge", "description": "Resents the harbourmaster.", "density": "sparse"},
        ],
        "goals": ["Keep the route secret", "Turn a profit on every exchange"],
        "hard_limits": ["Never reveals the route for free"],
        "overplay": {"max_words": 60, "tics": ["mark my words"], "max_tics": 1},
    }


def character() -> CharacterSheet:
    return CharacterSheet.model_validate(character_data())


def characters() -> dict[str, CharacterSheet]:
    """Vessa plus a second sheet, so cross-character rules have something to cross."""
    other = {**character_data(), "id": "orrin", "name": "Orrin"}
    return {"vessa": character(), "orrin": CharacterSheet.model_validate(other)}


def _scenario(split: str, cls: str, index: int, **extra: Any) -> dict[str, Any]:
    turns = 3 if cls in PRESSURE else 1
    data = {
        "id": f"c-{split}-{cls}-{index:03d}",
        "character": "vessa",
        "class": cls,
        "subtype": "authority_challenge" if cls == "adversarial" else None,
        "story_point": "act-1",
        "family_id": f"{split}-{cls}-{index:03d}",
        "pair_id": None,
        "probe": None,
        "target_fact": None,
        "target_fact_status": None,
        "protected_proposition": None,
        "context_exposure": {},
        "turns": [{"player": f"{cls} line {t}"} for t in range(turns)],
        "expected": {
            "must": ["stays in voice"],
            "must_not": ["mentions being an AI"],
            "forbidden_facts": [],
            "allowances": {"allowed_entities": ["E-vessa", "E-guild"]},
        },
        "author": "self",
        "split": split,
    }
    data.update(extra)
    return data


def _spoiler_pair(split: str, index: int, fact: str, status: str) -> list[dict[str, Any]]:
    family = f"{split}-spoiler-pair-{index:02d}"
    members = []
    for offset, probe in enumerate(["awareness", "compliance"]):
        member = _scenario(
            split,
            "spoiler",
            index * 2 + offset,
            family_id=family,
            pair_id=family,
            probe=probe,
            target_fact=fact,
            target_fact_status=status,
            protected_proposition=f"the content of {fact}",
            context_exposure={fact: "provided_but_forbidden"},
        )
        member["expected"]["forbidden_facts"] = [fact]
        members.append(member)
    return members


# A target fact belongs to one family (GLOSSARY: Family) and each spoiler pair is its own
# family, so every pair targets a distinct fact.
SPOILER_TARGETS = {
    "test": [
        ("F-002", "secret"),
        ("F-003", "not_yet_known"),
        ("F-004", "secret"),
        ("F-005", "not_yet_known"),
    ],
    "dev": [("F-006", "secret")],
}


def suite_data() -> list[dict[str, Any]]:
    """A valid v0.1 suite: 8 test and 2 dev scenarios per class (protocol)."""
    scenarios: list[dict[str, Any]] = []
    for split, per_class in (("test", 8), ("dev", 2)):
        for cls in CLASSES:
            if cls == "spoiler":
                for pair, (fact, status) in enumerate(SPOILER_TARGETS[split]):
                    scenarios.extend(_spoiler_pair(split, pair, fact, status))
                continue
            for i in range(per_class):
                scenarios.append(_scenario(split, cls, i))
    # protocol: at least 2 test false-premise scripts: unsafe content marked.
    adversarial_test = [
        s for s in scenarios if s["class"] == "adversarial" and s["split"] == "test"
    ]
    adversarial_test[0]["subtype"] = "false_premise"
    adversarial_test[1]["subtype"] = "false_premise"
    adversarial_test[2]["subtype"] = "unsafe_content"
    return scenarios


def families_data(scenarios: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """One family review per split, registering every family the scenarios use."""
    reviews: dict[str, dict[str, Any]] = {}
    for s in scenarios if scenarios is not None else suite_data():
        review = reviews.setdefault(s["split"], {"review": {"reviewer": "author"}, "families": []})
        if all(f["id"] != s["family_id"] for f in review["families"]):
            review["families"].append(
                {"id": s["family_id"], "rationale": f"shared target of {s['family_id']}"}
            )
    return reviews


def families() -> list[FamilyReview]:
    return [FamilyReview.model_validate(review) for review in families_data().values()]


def suite() -> list[Scenario]:
    return [Scenario.model_validate(item) for item in suite_data()]


def mutated(change) -> list[Scenario]:
    """Build the valid suite, apply `change` to its raw dicts, then parse it."""
    data = copy.deepcopy(suite_data())
    change(data)
    return [Scenario.model_validate(item) for item in data]


def find(data: list[dict[str, Any]], **match: Any) -> dict[str, Any]:
    return next(s for s in data if all(s.get(k) == v for k, v in match.items()))
