import os

import pytest
import yaml

from npcbench.loaders import load_families, load_scenarios
from tests.factories import families_data, suite_data


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def test_directory_loading_accepts_mappings_lists_and_upper_case_suffixes(tmp_path):
    data = suite_data()
    _write(tmp_path / "a.yaml", data[0])
    _write(tmp_path / "nested" / "b.YAML", data[1:3])
    (tmp_path / "folder.yaml").mkdir()
    assert [s.id for s in load_scenarios(tmp_path)] == [d["id"] for d in data[:3]]


def test_family_reviews_load_separately_from_scenarios(tmp_path):
    data = suite_data()
    _write(tmp_path / "test" / "a.yaml", data[0])
    _write(tmp_path / "test" / "families.yaml", families_data(data[:1])["test"])
    assert [s.id for s in load_scenarios(tmp_path)] == [data[0]["id"]]
    reviews = load_families(tmp_path)
    assert [f.id for r in reviews for f in r.families] == [data[0]["family_id"]]
    assert load_families(tmp_path / "test" / "a.yaml") == []


def test_links_leaving_the_content_directory_are_ignored(tmp_path):
    outside = tmp_path / "outside.yaml"
    _write(outside, suite_data()[0])
    content = tmp_path / "content"
    _write(content / "own.yaml", suite_data()[1])
    try:
        os.symlink(outside, content / "link.yaml")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks need extra privileges on this system")
    assert [s.id for s in load_scenarios(content)] == [suite_data()[1]["id"]]


def test_errors_name_the_file_without_echoing_values(tmp_path):
    bad = suite_data()[0]
    bad["split"] = "SENSITIVE-VALUE"
    _write(tmp_path / "broken.yaml", bad)
    with pytest.raises(ValueError) as excinfo:
        load_scenarios(tmp_path)
    assert "broken.yaml" in str(excinfo.value)
    assert "SENSITIVE-VALUE" not in str(excinfo.value)
