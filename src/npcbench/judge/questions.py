"""The per-trait yes/no questions shared by the judge and blind labelling (protocol).

One question per dense trait; a reply is in character when every dense trait passes. The
judge and human labellers must be asked the same questions, so both build them here.
"""

from __future__ import annotations

from dataclasses import dataclass

from npcbench.schemas import CharacterSheet


@dataclass(frozen=True)
class TraitQuestion:
    trait_id: str
    text: str


def trait_questions(character: CharacterSheet) -> list[TraitQuestion]:
    return [
        TraitQuestion(
            trait_id=trait.id,
            text=(
                f'Does this reply show {character.name}\'s trait "{trait.id}":'
                f" {trait.description.strip()} Answer yes or no."
            ),
        )
        for trait in character.dense_traits()
    ]
