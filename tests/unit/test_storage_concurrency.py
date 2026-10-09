"""Regression coverage for concurrent local review requests and artifact replacement."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

import pytest

from npcbench._run_storage import replace_text
from npcbench.review.labelling import LabelError, LabelRecord, append_label, read_labels


def test_concurrent_duplicate_labels_accept_exactly_one(tmp_path):
    path = tmp_path / "labels.jsonl"
    record = LabelRecord(reply_id="reply", rater="human", answers={"voice": "yes"})
    barrier = Barrier(8)

    def submit(_):
        barrier.wait()
        try:
            append_label(path, record, {"reply": ["voice"]})
            return True
        except LabelError:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert sum(pool.map(submit, range(8))) == 1
    assert read_labels(path) == [record]


def test_failed_replace_preserves_original_and_removes_staging(tmp_path, monkeypatch):
    path = tmp_path / "metrics.json"
    path.write_text("original", encoding="utf-8")

    def fail(*args):
        raise OSError("disk error")

    monkeypatch.setattr(Path, "replace", fail)
    with pytest.raises(OSError, match="disk error"):
        replace_text(path, "new")
    assert path.read_text(encoding="utf-8") == "original"
    assert list(tmp_path.iterdir()) == [path]


def test_concurrent_replacements_publish_a_complete_file(tmp_path):
    path = tmp_path / "metrics.json"
    values = [str(n) * 10000 for n in range(8)]
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda value: replace_text(path, value), values))
    assert path.read_text(encoding="utf-8") in values
    assert list(tmp_path.iterdir()) == [path]
