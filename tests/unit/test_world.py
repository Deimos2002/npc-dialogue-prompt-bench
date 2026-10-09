import pytest
from pydantic import ValidationError

from npcbench.schemas import CharacterSheet, World
from tests.factories import character_data, world_data


def test_valid_world_orders_story_points():
    world = World.model_validate(world_data())
    assert world.story_index("act-1") < world.story_index("act-3")
    assert world.fact("F-002").secret


def test_known_from_must_name_a_story_point():
    data = world_data()
    data["facts"][0]["known_from_by_character"]["vessa"] = "act-9"
    with pytest.raises(ValidationError, match="act-9"):
        World.model_validate(data)


def test_secret_fact_needs_a_reveal_condition():
    data = world_data()
    data["facts"][1]["reveal_condition"] = None
    with pytest.raises(ValidationError, match="reveal_condition"):
        World.model_validate(data)


def test_fact_ids_are_unique():
    data = world_data()
    data["facts"][1]["id"] = "F-001"
    with pytest.raises(ValidationError, match="F-001"):
        World.model_validate(data)


def test_entity_names_and_aliases_are_unique_ignoring_case():
    data = world_data()
    data["entities"][2]["aliases"] = ["the guild"]
    with pytest.raises(ValidationError, match="the guild"):
        World.model_validate(data)


def test_character_needs_a_dense_trait():
    data = character_data()
    for trait in data["traits"]:
        trait["density"] = "sparse"
    with pytest.raises(ValidationError, match="dense"):
        CharacterSheet.model_validate(data)


def test_misspelt_keys_are_rejected():
    data = world_data()
    data["facts"][1]["secert"] = True
    with pytest.raises(ValidationError, match="secert"):
        World.model_validate(data)
    sheet = character_data()
    sheet["hard_limit"] = ["typo"]
    with pytest.raises(ValidationError, match="hard_limit"):
        CharacterSheet.model_validate(sheet)


def test_validation_errors_do_not_echo_field_values():
    data = world_data()
    data["facts"][0]["secret"] = "SENSITIVE-VALUE"
    with pytest.raises(ValidationError) as excinfo:
        World.model_validate(data)
    assert "SENSITIVE-VALUE" not in str(excinfo.value)


def test_character_trait_ids_are_unique():
    data = character_data()
    data["traits"][1]["id"] = "greedy"
    with pytest.raises(ValidationError, match="greedy"):
        CharacterSheet.model_validate(data)
