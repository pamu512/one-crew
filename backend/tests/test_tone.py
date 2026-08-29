from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.picks import require_picks
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.spend import ledger
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE, TONE_EXAMPLES


def test_documentary_without_tone_is_400_no_spend(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent without tone")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    body = {
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "full_length_documentary",
        "depth": "decade",
        "script_lean": "centered_independent",
        "tell": SEED_TELL,
    }
    with TestClient(app) as client:
        headers = {"X-Shift-Token": "correct-horse"}
        missing = client.post("/api/shifts", json=body, headers=headers)
        assert missing.status_code == 400
        assert "tone" in missing.json()["detail"].lower()
        empty = client.post("/api/shifts", json={**body, "tone": "   "}, headers=headers)
        assert empty.status_code == 400
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0


def test_feature_without_tone_still_runs() -> None:
    topic, platform, cut, depth, lean, tell, tone = require_picks(
        "Hormuz",
        "youtube",
        "feature_film",
        "decade",
        "centered_independent",
        "one retired pilot on the night watch",
        None,
    )
    assert cut == "feature_film"
    assert tell
    assert tone == ""
    packet = seed_first_open()
    packet.cut = "feature_film"
    packet.tell = tell
    packet.tone = ""
    write_script(packet)
    assert packet.script.strip()
    assert "(frame)" in packet.script


def test_two_tones_change_vo_not_stamps() -> None:
    def _with(tone: str):
        packet = seed_first_open()
        packet.tone = tone
        write_script(packet)
        return packet

    desk = _with("News desk")
    question = _with("Question the decisions")
    record = _with(SEED_TONE)
    stamps = lambda p: [(f.id, f.stamp, f.propaganda, f.lean) for f in p.receipt.findings]
    assert stamps(desk) == stamps(question) == stamps(record)
    assert desk.script != question.script
    assert "From the news desk." in desk.script
    assert "Question the decision" in question.script
    assert "From the news desk." not in record.script
    assert "Question the decision" not in record.script
    assert "[jcpoa-2018]" in desk.script
    assert "[secret-closure]" in question.script


def test_tone_examples_are_not_an_enum() -> None:
    with TestClient(app) as client:
        body = client.get("/api/tone-examples").json()
        assert body["default"] is None
        assert body["examples"] == list(TONE_EXAMPLES)
        assert SEED_TONE in body["examples"]
        assert "Grounded in the record" in body["examples"]
        assert "grounded in reality" not in " ".join(body["examples"]).lower()
