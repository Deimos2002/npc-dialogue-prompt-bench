"""The local blind labelling screen (protocol), served in-process."""

from fastapi.testclient import TestClient

from npcbench.review import app as review_app
from npcbench.review.app import STATIC, create_labelling_app, serve


def _item(reply_id, reply):
    return {
        "reply_id": reply_id,
        "reply": reply,
        "conversation": [{"speaker": "Player", "text": "Sell me a knife."}],
        "player": "And a cloak?",
        "scenario": {"class": "on_script", "story_point": "act-1"},
        "character": {"name": "Vessa", "summary": "A fence.", "voice": "clipped", "traits": []},
        "questions": [{"trait_id": "greedy", "text": "Greedy? Answer yes or no."}],
    }


ITEMS = {
    "x1": _item("x1", "<script>alert(1)</script> Coin first."),
    "x2": _item("x2", "No."),
}


def _client(tmp_path):
    app = create_labelling_app(ITEMS, labels_path=tmp_path / "labels.jsonl", seed=0)
    return TestClient(app, base_url="http://127.0.0.1:8765"), tmp_path / "labels.jsonl"


def test_the_page_renders_text_never_html_and_sets_a_strict_policy(tmp_path):
    client, _ = _client(tmp_path)
    page = client.get("/")
    assert page.status_code == 200
    assert "script-src 'self'" in page.headers["content-security-policy"]
    assert page.headers["x-content-type-options"] == "nosniff"
    assert client.get("/static/label.js").status_code == 200
    script = (STATIC / "label.js").read_text(encoding="utf-8")
    assert "textContent" in script
    for unsafe in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
        assert unsafe not in script
    assert page.text.count("<script") == 1  # only the external script, never inline


def test_a_rater_labels_every_item_once_then_is_done(tmp_path):
    client, path = _client(tmp_path)
    seen = []
    for _ in ITEMS:
        response = client.get("/api/next", params={"rater": "ana"}).json()
        assert response["remaining"] == len(ITEMS) - len(seen)
        seen.append(response["item"]["reply_id"])
        posted = client.post(
            "/api/labels",
            json={"reply_id": seen[-1], "rater": "ana", "answers": {"greedy": "yes"}},
        )
        assert posted.status_code == 201, posted.text
    assert sorted(seen) == sorted(ITEMS)
    assert client.get("/api/next", params={"rater": "ana"}).json() == {"done": True}
    assert len(path.read_text(encoding="utf-8").splitlines()) == 2
    # Another rater starts afresh.
    assert "item" in client.get("/api/next", params={"rater": "ben"}).json()


def test_reply_text_is_returned_as_json_data(tmp_path):
    client, _ = _client(tmp_path)
    response = client.get("/api/next", params={"rater": "ana"})
    assert response.headers["content-type"].startswith("application/json")


def test_bad_labels_are_rejected_without_writing(tmp_path):
    client, path = _client(tmp_path)
    for body in (
        {"reply_id": "nope", "rater": "ana", "answers": {"greedy": "yes"}},
        {"reply_id": "x1", "rater": "ana", "answers": {"greedy": "maybe"}},
        {"reply_id": "x1", "rater": "", "answers": {"greedy": "yes"}},
    ):
        assert client.post("/api/labels", json=body).status_code in (400, 422)
    assert not path.exists()
    assert client.get("/api/next", params={"rater": "a b"}).status_code == 422


def test_requests_for_another_host_are_refused(tmp_path):
    # A DNS-rebinding page reaches the screen under its own host name.
    app = create_labelling_app(ITEMS, labels_path=tmp_path / "labels.jsonl", seed=0)
    client = TestClient(app, base_url="http://attacker.example")
    assert client.get("/api/next", params={"rater": "ana"}).status_code == 400


def test_the_screen_binds_to_loopback_only(monkeypatch):
    calls = {}
    monkeypatch.setattr(review_app.uvicorn, "run", lambda app, **kw: calls.update(kw))
    serve(object(), port=8765)
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8765
