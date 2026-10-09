"""Suite validation (protocol, §6). Reports every issue instead of stopping early."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass

from npcbench.loaders import FAMILIES_FILE
from npcbench.schemas import CharacterSheet, FamilyReview, Scenario, World

CLASSES = ("on_script", "off_script", "adversarial", "spoiler", "moral_pressure")
PRESSURE_CLASSES = frozenset({"adversarial", "moral_pressure"})
PRESSURE_TURNS = (3, 6)
ADVERSARIAL_ONLY_SUBTYPES = frozenset({"false_premise", "unsafe_content", "prompt_extraction"})
# Metrics key on these names (§6.3 rule 8, §8), so a misspelling must fail. Extend deliberately.
ADVERSARIAL_SUBTYPES = ADVERSARIAL_ONLY_SUBTYPES | {
    "authority_challenge",
    "economic_exploit",
    "emotional_manipulation",
}
WITHHELD_EXPOSURES = frozenset({"provided_but_forbidden", "withheld"})


@dataclass(frozen=True)
class Issue:
    code: str
    scenario_id: str | None
    message: str


@dataclass(frozen=True)
class Profile:
    """Release-specific counts (protocol). General rules apply without a profile."""

    name: str
    per_class: dict[str, int]
    single_turn_classes: frozenset[str]
    min_false_premise_test: int
    min_unsafe_content_test: int
    spoiler_pairs: dict[str, int]


V0_1 = Profile(
    name="v0.1",
    per_class={"test": 8, "dev": 2},
    single_turn_classes=frozenset({"on_script", "off_script", "spoiler"}),
    min_false_premise_test=2,
    min_unsafe_content_test=1,
    spoiler_pairs={"test": 4, "dev": 1},
)
PROFILES = {"v0.1": V0_1}


def expected_target_status(world: World, scenario: Scenario) -> str | None:
    """`not_yet_known` before the character may know the fact, `secret` when known but withheld.

    None means the character may state the fact freely, so it cannot be a spoiler target.
    """
    fact = world.fact(scenario.target_fact)
    known_from = fact.known_from_by_character.get(scenario.character)
    if known_from is None or world.story_index(scenario.story_point) < world.story_index(
        known_from
    ):
        return "not_yet_known"
    return "secret" if fact.secret else None


def validate_suite(
    scenarios: list[Scenario],
    world: World,
    characters: dict[str, CharacterSheet],
    profile: Profile | None,
    *,
    families: list[FamilyReview],
) -> list[Issue]:
    issues: list[Issue] = []

    def add(code: str, scenario_id: str | None, message: str) -> None:
        issues.append(Issue(code, scenario_id, message))

    seen: set[str] = set()
    for s in scenarios:
        if s.id in seen:
            add("duplicate_id", s.id, f"scenario id {s.id} is used more than once")
        seen.add(s.id)

    for fact in world.facts:
        for char in sorted(set(fact.known_from_by_character) - set(characters)):
            add("unknown_fact_character", None, f"fact {fact.id} names unknown character {char}")

    points = {p.id for p in world.story_points}
    for s in scenarios:
        _check_scenario(s, world, characters, points, profile, add)

    _check_families_and_pairs(scenarios, add)
    _check_family_review(scenarios, families, add)
    if profile is not None:
        _check_profile(scenarios, profile, add)
    return issues


def _check_scenario(s, world, characters, points, profile, add) -> None:
    if s.character not in characters:
        add("unknown_character", s.id, f"character {s.character} has no sheet")
    if s.story_point not in points:
        add("unknown_story_point", s.id, f"story point {s.story_point} is not in the world")

    low, high = PRESSURE_TURNS
    if s.class_ in PRESSURE_CLASSES and not low <= len(s.turns) <= high:
        add("pressure_turns", s.id, f"{s.class_} needs {low}-{high} turns, has {len(s.turns)}")
    if profile and s.class_ in profile.single_turn_classes and len(s.turns) != 1:
        add("single_turn", s.id, f"{s.class_} is single-turn in {profile.name}")

    if s.class_ == "adversarial" and not s.subtype:
        add("missing_subtype", s.id, "adversarial scenarios need a subtype")
    elif s.class_ == "adversarial" and s.subtype not in ADVERSARIAL_SUBTYPES:
        add("unknown_subtype", s.id, f"subtype {s.subtype} not in {sorted(ADVERSARIAL_SUBTYPES)}")
    if s.subtype in ADVERSARIAL_ONLY_SUBTYPES and s.class_ != "adversarial":
        add("subtype_class", s.id, f"subtype {s.subtype} belongs to the adversarial class")

    referenced = set(s.expected.forbidden_facts) | set(s.context_exposure)
    if s.target_fact:
        referenced.add(s.target_fact)
    for fact_id in sorted(referenced):
        if not world.has_fact(fact_id):
            add("unknown_fact", s.id, f"fact {fact_id} is not in the world")
    targeted = set(s.expected.forbidden_facts) | ({s.target_fact} if s.target_fact else set())
    for fact_id in sorted(targeted):
        exposure = s.context_exposure.get(fact_id)
        if exposure is None:
            add("missing_context_exposure", s.id, f"targeted fact {fact_id} has no exposure")
        elif exposure not in WITHHELD_EXPOSURES:
            add("exposure_role", s.id, f"targeted fact {fact_id} cannot be exposed as {exposure}")
    for fact_id, exposure in sorted(s.context_exposure.items()):
        if exposure == "provided_but_forbidden" and fact_id not in targeted:
            add("exposure_role", s.id, f"{fact_id} is provided_but_forbidden but not forbidden")
    for entity_id in s.expected.allowances.allowed_entities:
        if not world.has_entity(entity_id):
            add("unknown_entity", s.id, f"entity {entity_id} is not in the register")

    spoiler_fields = (
        s.pair_id,
        s.probe,
        s.target_fact,
        s.target_fact_status,
        s.protected_proposition,
    )
    if s.class_ != "spoiler":
        if any(value is not None for value in spoiler_fields):
            add("probe_outside_spoiler", s.id, "only spoiler scenarios carry probe fields")
        return
    if any(value is None or value == "" for value in spoiler_fields):
        add(
            "spoiler_fields",
            s.id,
            "spoiler scenarios need pair_id, probe, target_fact, status and protected_proposition",
        )
        return
    if s.target_fact not in s.expected.forbidden_facts:
        add("target_not_forbidden", s.id, f"target fact {s.target_fact} must be forbidden")
    if world.has_fact(s.target_fact) and s.story_point in points:
        expected = expected_target_status(world, s)
        if expected != s.target_fact_status:
            add(
                "target_status",
                s.id,
                f"{s.target_fact} at {s.story_point} is "
                f"{expected or 'freely known'}, not {s.target_fact_status}",
            )


def _check_families_and_pairs(scenarios, add) -> None:
    splits = defaultdict(set)
    characters = defaultdict(set)
    for s in scenarios:
        splits[s.family_id].add(s.split)
        characters[s.family_id].add(s.character)
    for family, family_splits in sorted(splits.items()):
        if len(family_splits) > 1:
            add("family_split", None, f"family {family} spans splits {sorted(family_splits)}")
    for family, family_characters in sorted(characters.items()):
        if len(family_characters) > 1:
            add(
                "family_character",
                None,
                f"family {family} spans characters {sorted(family_characters)}",
            )

    # GLOSSARY: Family. A shared target fact makes scenarios dependent, within one character.
    families_by_target = defaultdict(set)
    for s in scenarios:
        if s.target_fact:
            families_by_target[(s.character, s.target_fact)].add(s.family_id)
    for (character, fact), families in sorted(families_by_target.items()):
        if len(families) > 1:
            add(
                "target_family",
                None,
                f"{character} scenarios targeting {fact} span families {sorted(families)}",
            )

    pairs = defaultdict(list)
    for s in scenarios:
        if s.class_ == "spoiler" and s.pair_id:
            pairs[s.pair_id].append(s)
    for pair_id, members in sorted(pairs.items()):
        if len(members) != 2:
            add("pair_size", None, f"pair {pair_id} has {len(members)} members, needs 2")
            continue
        if sorted(m.probe or "" for m in members) != ["awareness", "compliance"]:
            add("pair_roles", None, f"pair {pair_id} needs one awareness and one compliance probe")
        if len({(m.target_fact, m.target_fact_status) for m in members}) != 1:
            add("pair_target", None, f"pair {pair_id} members target different facts or statuses")
        if len({m.family_id for m in members}) != 1:
            add("pair_family", None, f"pair {pair_id} members belong to different families")
        if len({(m.character, m.story_point) for m in members}) != 1:
            add("pair_context", None, f"pair {pair_id} members differ in character or story point")

    # protocol: each spoiler pair is its own independent family.
    pair_ids_by_family = defaultdict(set)
    for pair_id, members in pairs.items():
        for m in members:
            pair_ids_by_family[m.family_id].add(pair_id)
    for family, pair_ids in sorted(pair_ids_by_family.items()):
        if len(pair_ids) > 1:
            add("shared_pair_family", None, f"family {family} holds pairs {sorted(pair_ids)}")


def _check_family_review(scenarios, reviews: list[FamilyReview], add) -> None:
    """Every family is registered once with a rationale; separations are recorded once."""
    entries = [family for review in reviews for family in review.families]
    registered = {f.id for f in entries}
    seen: set[str] = set()
    for family in entries:
        if family.id in seen:
            add("duplicate_family_id", None, f"family {family.id} is registered more than once")
        seen.add(family.id)
    used = {s.family_id for s in scenarios}
    for family in sorted(used - registered):
        add("family_unregistered", None, f"family {family} has no entry in {FAMILIES_FILE}")
    for family in sorted(registered - used):
        add("family_unused", None, f"family {family} is registered but no scenario uses it")

    pairs: set[frozenset[str]] = set()
    for family in entries:
        for separation in family.kept_apart_from:
            other = separation.family
            if other == family.id:
                add("separation_self", None, f"family {family.id} is kept apart from itself")
                continue
            if other not in registered:
                add("separation_unknown", None, f"family {family.id} names unknown family {other}")
                continue
            pair = frozenset({family.id, other})
            if pair in pairs:
                add(
                    "separation_duplicate",
                    None,
                    f"separation of {family.id} and {other} is recorded more than once",
                )
            pairs.add(pair)


def _check_profile(scenarios, profile: Profile, add) -> None:
    for split, expected in profile.per_class.items():
        for cls in CLASSES:
            count = sum(1 for s in scenarios if s.split == split and s.class_ == cls)
            if count != expected:
                add("class_count", None, f"{split}/{cls} has {count} scenarios, needs {expected}")
    false_premise = sum(
        1
        for s in scenarios
        if s.split == "test" and s.class_ == "adversarial" and s.subtype == "false_premise"
    )
    if false_premise < profile.min_false_premise_test:
        add(
            "false_premise_count",
            None,
            f"test has {false_premise} false-premise scripts, needs "
            f"{profile.min_false_premise_test}",
        )
    unsafe = sum(1 for s in scenarios if s.split == "test" and s.subtype == "unsafe_content")
    if unsafe < profile.min_unsafe_content_test:
        add(
            "unsafe_content_count",
            None,
            f"test has {unsafe} unsafe_content scenarios, needs {profile.min_unsafe_content_test}",
        )
    for split, expected in profile.spoiler_pairs.items():
        found = {s.pair_id for s in scenarios if s.split == split and s.pair_id}
        if len(found) != expected:
            add("spoiler_pairs", None, f"{split} has {len(found)} spoiler pairs, needs {expected}")


def suite_hash(scenarios: list[Scenario], families: list[FamilyReview]) -> str:
    """Version identity of a scenario set and its family review, independent of file layout and
    order (§6.3 rule 4)."""
    records = sorted(
        (s.model_dump(mode="json", by_alias=True) for s in scenarios), key=lambda r: r["id"]
    )
    reviews = sorted(
        (r.model_dump(mode="json") for r in families),
        key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False),
    )
    canonical = json.dumps(
        {"scenarios": records, "families": reviews},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
