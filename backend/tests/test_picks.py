from fastapi.testclient import TestClient

import pytest

from onecrew.agent.shift import open_shift, run_live_packet
from onecrew.api import app
from onecrew.models import MISSING
from onecrew.picks import (
    PlatformRequiredError,
    ScriptLeanRequiredError,
    TopicRequiredError,
    require_picks,
    require_topic,
)
from onecrew.tell import SEED_TELL, TellRequiredError
from onecrew.tone import SEED_TONE, ToneRequiredError
from onecrew.script import write_script
from onecrew.seed import leftover_hormuz_packet, seed_first_open
from onecrew.spend import ledger


def _all(**overrides):
    body = {
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "decade",
        "script_lean": "centered_independent",
        "tell": SEED_TELL,
        "tone": SEED_TONE,
    }
    body.update(overrides)
    return body


def test_no_run_without_all_six_picks(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent without all six picks")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    with TestClient(app) as client:
        headers = {"X-Shift-Token": "correct-horse"}
        empty_topic = client.post("/api/shifts", json=_all(topic=""), headers=headers)
        assert empty_topic.status_code == 400
        assert "topic" in empty_topic.json()["detail"].lower()
        whitespace = client.post("/api/shifts", json=_all(topic="   "), headers=headers)
        assert whitespace.status_code == 400
        assert "topic" in whitespace.json()["detail"].lower()
        omitted = {k: v for k, v in _all().items() if k != "topic"}
        missing_topic = client.post("/api/shifts", json=omitted, headers=headers)
        assert missing_topic.status_code == 400
        assert "topic" in missing_topic.json()["detail"].lower()
        missing_platform = client.post("/api/shifts", json=_all(platform=None), headers=headers)
        assert missing_platform.status_code == 400
        assert "platform" in missing_platform.json()["detail"].lower()
        missing_cut = client.post("/api/shifts", json=_all(cut=None), headers=headers)
        assert missing_cut.status_code == 400
        assert "cut" in missing_cut.json()["detail"].lower()
        missing_depth = client.post("/api/shifts", json=_all(depth=None), headers=headers)
        assert missing_depth.status_code == 400
        assert "depth" in missing_depth.json()["detail"].lower()
        missing_lean = client.post("/api/shifts", json=_all(script_lean=None), headers=headers)
        assert missing_lean.status_code == 400
        assert "lean" in missing_lean.json()["detail"].lower()
        missing_tell = client.post("/api/shifts", json=_all(tell=None), headers=headers)
        assert missing_tell.status_code == 400
        assert "tell" in missing_tell.json()["detail"].lower()
        empty_tell = client.post("/api/shifts", json=_all(tell=""), headers=headers)
        assert empty_tell.status_code == 400
        omitted_tell = {k: v for k, v in _all().items() if k != "tell"}
        missing_omitted = client.post("/api/shifts", json=omitted_tell, headers=headers)
        assert missing_omitted.status_code == 400
        assert "tell" in missing_omitted.json()["detail"].lower()
        missing_tone = client.post("/api/shifts", json=_all(tone=None), headers=headers)
        assert missing_tone.status_code == 400
        assert "tone" in missing_tone.json()["detail"].lower()
        empty_tone = client.post("/api/shifts", json=_all(tone="   "), headers=headers)
        assert empty_tone.status_code == 400
        omitted_tone = {k: v for k, v in _all().items() if k != "tone"}
        missing_tone_omit = client.post("/api/shifts", json=omitted_tone, headers=headers)
        assert missing_tone_omit.status_code == 400
        assert "tone" in missing_tone_omit.json()["detail"].lower()
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0
    with pytest.raises(TopicRequiredError, match="No topic chosen"):
        require_topic("")
    with pytest.raises(TopicRequiredError, match="No topic chosen"):
        require_topic("   ")
    assert require_topic("  Hormuz  ") == "Hormuz"
    with pytest.raises(TopicRequiredError, match="No topic chosen"):
        require_picks(None, "youtube", "one_time_short_episode", "decade", "left", SEED_TELL)
    with pytest.raises(PlatformRequiredError):
        require_picks("Hormuz", None, "one_time_short_episode", "decade", "left", SEED_TELL)
    with pytest.raises(ScriptLeanRequiredError):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", None, SEED_TELL)
    with pytest.raises(TellRequiredError, match="No tell chosen"):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", "left", None)
    with pytest.raises(TellRequiredError, match="No tell chosen"):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", "left", "   ")
    with pytest.raises(ToneRequiredError, match="No tone chosen"):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", "left", SEED_TELL, None)
    with pytest.raises(ToneRequiredError, match="No tone chosen"):
        require_picks("Hormuz", "youtube", "full_length_documentary", "decade", "left", SEED_TELL, "")


def test_script_lean_cannot_change_a_source_stamp() -> None:
    packet = leftover_hormuz_packet()
    before = [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent, f.interests)
        for f in packet.receipt.findings
    ]
    fringe = next(f for f in packet.receipt.findings if f.stamp == "fringe")
    house = next(f for f in packet.receipt.findings if f.propaganda == "yes")
    missing_lean = next(f for f in packet.receipt.findings if f.lean == MISSING)
    for voice in ("unhinged_fringe", "far_right", "far_left", "centered_independent"):
        packet.script_lean = voice
        write_script(packet)
        after = [
            (f.id, f.stamp, f.propaganda, f.lean, f.independent, f.interests)
            for f in packet.receipt.findings
        ]
        assert after == before
        assert fringe.stamp == "fringe"
        assert house.stamp == "grounded"
        assert house.propaganda == "yes"
        assert missing_lean.lean == MISSING
        assert packet.script.strip()
        assert len([b for b in packet.beats if b.kind == "vo"]) == 8


def test_unhinged_lean_still_fail_closed_on_missing_parallel() -> None:
    shift = open_shift(
        "Hormuz",
        platform="tiktok",
        cut="tiktok-length",
        depth="decade",
        script_lean="unhinged_fringe",
        tell="Thriller on a tanker crossing Hormuz that might get hit",
        tone=SEED_TONE,
        topic="Hormuz",
    )
    packet = run_live_packet(shift)
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert packet.receipt.findings == []
    assert packet.receipt.invented_source is False
    assert packet.receipt.invented_stamp is False
    assert packet.script == ""
    assert packet.script_lean == "unhinged_fringe"
