import pytest

from npcbench.schemas import FamilyReview, World
from npcbench.suite import V0_1, expected_target_status, suite_hash, validate_suite
from tests.factories import (
    characters,
    families,
    families_data,
    find,
    mutated,
    suite,
    world,
    world_data,
)


def _codes(scenarios, profile=V0_1, reviews=None):
    reviews = families() if reviews is None else reviews
    issues = validate_suite(scenarios, world(), characters(), profile, families=reviews)
    return {issue.code for issue in issues}


def test_valid_v01_suite_has_no_issues():
    assert validate_suite(suite(), world(), characters(), V0_1, families=families()) == []


def _drop_one_test_on_script(data):
    data.remove(find(data, **{"class": "on_script", "split": "test"}))


def _short_pressure_script(data):
    s = find(data, **{"class": "adversarial", "split": "test"})
    s["turns"] = s["turns"][:2]


def _long_pressure_script(data):
    s = find(data, **{"class": "moral_pressure", "split": "test"})
    s["turns"] = [{"player": "again"}] * 7


def _multi_turn_on_script(data):
    find(data, **{"class": "on_script"})["turns"].append({"player": "and?"})


def _one_false_premise(data):
    find(data, subtype="false_premise")["subtype"] = "authority_challenge"


def _adversarial_without_subtype(data):
    find(data, **{"class": "adversarial", "subtype": "authority_challenge"})["subtype"] = None


def _unsafe_content_in_moral_pressure(data):
    find(data, **{"class": "moral_pressure"})["subtype"] = "unsafe_content"


def _pair_with_two_compliance_probes(data):
    find(data, probe="awareness", split="test")["probe"] = "compliance"


def _pair_with_two_targets(data):
    member = find(data, probe="awareness", split="test", target_fact="F-002")
    member["target_fact"] = "F-003"
    member["target_fact_status"] = "not_yet_known"
    member["context_exposure"] = {"F-003": "provided_but_forbidden"}
    member["expected"]["forbidden_facts"] = ["F-003"]


def _family_across_splits(data):
    find(data, probe="awareness", split="test")["split"] = "dev"


def _unknown_story_point(data):
    data[0]["story_point"] = "act-9"


def _unknown_forbidden_fact(data):
    data[0]["expected"]["forbidden_facts"] = ["F-404"]
    data[0]["context_exposure"] = {"F-404": "withheld"}


def _forbidden_fact_without_exposure(data):
    data[0]["expected"]["forbidden_facts"] = ["F-001"]


def _wrong_target_status(data):
    find(data, target_fact="F-003", probe="awareness", split="test")["target_fact_status"] = (
        "secret"
    )


def _freely_known_target(data):
    for member in data:
        if member.get("target_fact") == "F-003" and member["split"] == "test":
            member["target_fact"] = "F-001"
            member["context_exposure"] = {"F-001": "provided_but_forbidden"}
            member["expected"]["forbidden_facts"] = ["F-001"]


def _probe_outside_spoiler(data):
    find(data, **{"class": "on_script"})["probe"] = "awareness"


def _spoiler_without_probe(data):
    find(data, probe="compliance", split="test")["probe"] = None


def _target_not_forbidden(data):
    find(data, probe="compliance", split="test")["expected"]["forbidden_facts"] = []


def _unknown_entity(data):
    data[0]["expected"]["allowances"]["allowed_entities"] = ["E-nobody"]


def _unknown_character(data):
    data[0]["character"] = "Z"


def _family_across_characters(data):
    find(data, **{"class": "on_script", "split": "test"})["character"] = "orrin"
    second = find(data, **{"class": "off_script", "split": "test"})
    second["family_id"] = find(data, **{"class": "on_script", "split": "test"})["family_id"]


def _same_target_in_two_families(data):
    for member in data:
        if member.get("pair_id") == "test-spoiler-pair-02":
            member["target_fact"] = "F-002"
            member["context_exposure"] = {"F-002": "provided_but_forbidden"}
            member["expected"]["forbidden_facts"] = ["F-002"]


def _spoiler_without_protected_proposition(data):
    find(data, probe="compliance", split="test")["protected_proposition"] = None


def _protected_proposition_outside_spoiler(data):
    find(data, **{"class": "on_script"})["protected_proposition"] = "the route"


def _duplicate_id(data):
    data[1]["id"] = data[0]["id"]


def _forbidden_fact_marked_provided(data):
    data[0]["expected"]["forbidden_facts"] = ["F-001"]
    data[0]["context_exposure"] = {"F-001": "provided"}


def _forbidden_exposure_without_forbidden_fact(data):
    data[0]["context_exposure"] = {"F-001": "provided_but_forbidden"}


def _misspelt_adversarial_subtype(data):
    find(data, subtype="unsafe_content")["subtype"] = "unsafe-content"


def _no_unsafe_content_in_test(data):
    find(data, subtype="unsafe_content")["subtype"] = "authority_challenge"


def _pair_with_one_member(data):
    data.remove(find(data, probe="awareness", split="test"))


def _pair_members_in_two_families(data):
    find(data, probe="awareness", split="test")["family_id"] = "test-elsewhere"


def _two_pairs_in_one_family(data):
    first = find(data, probe="awareness", split="test")["family_id"]
    for member in data:
        if member["split"] == "test" and member.get("pair_id") == "test-spoiler-pair-01":
            member["family_id"] = first


def _pair_at_two_story_points(data):
    find(data, probe="compliance", split="test", target_fact="F-002")["story_point"] = "act-2"


def _test_pair_moved_to_dev(data):
    for member in data:
        if member.get("pair_id") == "test-spoiler-pair-03":
            member["split"] = "dev"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (_drop_one_test_on_script, "class_count"),
        (_short_pressure_script, "pressure_turns"),
        (_long_pressure_script, "pressure_turns"),
        (_multi_turn_on_script, "single_turn"),
        (_one_false_premise, "false_premise_count"),
        (_adversarial_without_subtype, "missing_subtype"),
        (_unsafe_content_in_moral_pressure, "subtype_class"),
        (_pair_with_two_compliance_probes, "pair_roles"),
        (_pair_with_two_targets, "pair_target"),
        (_family_across_splits, "family_split"),
        (_unknown_story_point, "unknown_story_point"),
        (_unknown_forbidden_fact, "unknown_fact"),
        (_forbidden_fact_without_exposure, "missing_context_exposure"),
        (_wrong_target_status, "target_status"),
        (_freely_known_target, "target_status"),
        (_probe_outside_spoiler, "probe_outside_spoiler"),
        (_spoiler_without_probe, "spoiler_fields"),
        (_target_not_forbidden, "target_not_forbidden"),
        (_unknown_entity, "unknown_entity"),
        (_unknown_character, "unknown_character"),
        (_family_across_characters, "family_character"),
        (_same_target_in_two_families, "target_family"),
        (_spoiler_without_protected_proposition, "spoiler_fields"),
        (_protected_proposition_outside_spoiler, "probe_outside_spoiler"),
        (_duplicate_id, "duplicate_id"),
        (_forbidden_fact_marked_provided, "exposure_role"),
        (_forbidden_exposure_without_forbidden_fact, "exposure_role"),
        (_misspelt_adversarial_subtype, "unknown_subtype"),
        (_no_unsafe_content_in_test, "unsafe_content_count"),
        (_pair_with_one_member, "pair_size"),
        (_pair_members_in_two_families, "pair_family"),
        (_two_pairs_in_one_family, "shared_pair_family"),
        (_pair_at_two_story_points, "pair_context"),
        (_test_pair_moved_to_dev, "spoiler_pairs"),
    ],
)
def test_each_broken_rule_is_reported(change, code):
    assert code in _codes(mutated(change))


def test_fact_knowledge_keys_must_name_characters():
    data = world_data()
    data["facts"][1]["known_from_by_character"] = {"c": "act-1"}
    issues = validate_suite(
        suite(), World.model_validate(data), characters(), V0_1, families=families()
    )
    assert "unknown_fact_character" in {i.code for i in issues}


@pytest.mark.parametrize(
    ("story_point", "status"),
    [("act-1", "not_yet_known"), ("act-2", "secret"), ("act-3", "secret")],
)
def test_status_boundary_is_the_known_from_point(story_point, status):
    data = world_data()
    data["facts"][1]["known_from_by_character"] = {"vessa": "act-2"}
    scenario = next(s for s in suite() if s.target_fact == "F-002")
    scenario = scenario.model_copy(update={"story_point": story_point})
    assert expected_target_status(World.model_validate(data), scenario) == status


def test_the_same_target_for_another_character_may_be_another_family():
    def change(data):
        for member in data:
            if member.get("pair_id") == "test-spoiler-pair-02":
                member["character"] = "orrin"
                member["target_fact"] = "F-002"
                member["context_exposure"] = {"F-002": "provided_but_forbidden"}
                member["expected"]["forbidden_facts"] = ["F-002"]

    assert "target_family" not in _codes(mutated(change), profile=None)


def test_unexplained_allowance_keys_are_rejected():
    with pytest.raises(ValueError):
        mutated(lambda data: data[0]["expected"]["allowances"].update(allow_invention=True))


def test_economic_exploit_is_a_known_adversarial_subtype():
    def change(data):
        find(data, **{"class": "adversarial", "subtype": "authority_challenge"})["subtype"] = (
            "economic_exploit"
        )

    assert "unknown_subtype" not in _codes(mutated(change))


def test_counts_are_not_enforced_without_a_profile():
    small = suite()[:3]
    assert "class_count" not in _codes(small, profile=None)


def test_issues_name_the_scenario():
    issues = validate_suite(
        mutated(_unknown_story_point), world(), characters(), V0_1, families=families()
    )
    issue = next(i for i in issues if i.code == "unknown_story_point")
    assert issue.scenario_id == suite()[0].id
    assert "act-9" in issue.message


def test_suite_hash_ignores_order_but_not_content():
    scenarios = suite()
    assert suite_hash(scenarios, families()) == suite_hash(list(reversed(scenarios)), families())
    changed = mutated(lambda data: data[0]["turns"][0].update(player="different words"))
    assert suite_hash(changed, families()) != suite_hash(scenarios, families())


def test_suite_hash_covers_the_family_review():
    reviews = families_data()
    reviews["test"]["families"][0]["rationale"] = "a different reason"
    edited = [FamilyReview.model_validate(r) for r in reviews.values()]
    assert suite_hash(suite(), edited) != suite_hash(suite(), families())
    assert suite_hash(suite(), families()) == suite_hash(suite(), list(reversed(families())))


def _reviews(change):
    reviews = families_data()
    change(reviews)
    return [FamilyReview.model_validate(r) for r in reviews.values()]


def _separate(reviews, first, second, reason="different player goals"):
    entry = next(f for r in reviews.values() for f in r["families"] if f["id"] == first)
    entry.setdefault("kept_apart_from", []).append({"family": second, "reason": reason})


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (lambda r: r["test"]["families"].pop(0), "family_unregistered"),
        (
            lambda r: r["dev"]["families"].append({"id": "ghost", "rationale": "unused"}),
            "family_unused",
        ),
        (
            lambda r: r["dev"]["families"].append(dict(r["test"]["families"][0])),
            "duplicate_family_id",
        ),
        (lambda r: _separate(r, "test-on_script-000", "nowhere"), "separation_unknown"),
        (lambda r: _separate(r, "test-on_script-000", "test-on_script-000"), "separation_self"),
        (
            lambda r: (
                _separate(r, "test-on_script-000", "test-on_script-001"),
                _separate(r, "test-on_script-001", "test-on_script-000"),
            ),
            "separation_duplicate",
        ),
    ],
)
def test_each_broken_family_rule_is_reported(change, code):
    assert code in _codes(suite(), reviews=_reviews(change))


def test_a_recorded_separation_is_valid():
    reviews = _reviews(lambda r: _separate(r, "test-on_script-000", "test-on_script-001"))
    assert _codes(suite(), reviews=reviews) == set()


def test_family_entries_need_a_rationale_and_reviewer():
    with pytest.raises(ValueError):
        _reviews(lambda r: r["test"]["families"][0].update(rationale=" "))
    with pytest.raises(ValueError):
        _reviews(lambda r: r["test"]["review"].update(reviewer=""))
