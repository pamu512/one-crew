from fastapi.testclient import TestClient

import pytest

from onecrew.agent.shift import open_shift, run_live_packet
from onecrew.api import app
from onecrew.models import MISSING
from onecrew.picks import (
    GenreRequiredError,
    PlatformRequiredError,
    ScriptLeanRequiredError,
    TopicRequiredError,
    VantageRequiredError,
    require_picks,
    require_topic,
)
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.spend import ledger


def _all(**overrides):
    body = {
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "decade",
        "script_lean": "centered_independent",
        "genre": "nonfiction",
        "vantage": "global_overview",
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
        missing_genre = client.post("/api/shifts", json=_all(genre=None), headers=headers)
        assert missing_genre.status_code == 400
        assert "genre" in missing_genre.json()["detail"].lower()
        empty_genre = client.post("/api/shifts", json=_all(genre=""), headers=headers)
        assert empty_genre.status_code == 400
        omitted_tell = {k: v for k, v in _all().items() if k not in {"genre", "vantage"}}
        missing_vantage = client.post("/api/shifts", json={**omitted_tell, "genre": "drama"}, headers=headers)
        assert missing_vantage.status_code == 400
        assert "vantage" in missing_vantage.json()["detail"].lower()
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0
    with pytest.raises(TopicRequiredError, match="No topic chosen"):
        require_topic("")
    with pytest.raises(TopicRequiredError, match="No topic chosen"):
        require_topic("   ")
    assert require_topic("  Hormuz  ") == "Hormuz"
    with pytest.raises(TopicRequiredError, match="No topic chosen"):
        require_picks(None, "youtube", "one_time_short_episode", "decade", "left", "nonfiction", "global_overview")
    with pytest.raises(PlatformRequiredError):
        require_picks("Hormuz", None, "one_time_short_episode", "decade", "left", "nonfiction", "global_overview")
    with pytest.raises(ScriptLeanRequiredError):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", None, "nonfiction", "global_overview")
    with pytest.raises(GenreRequiredError, match="No genre chosen"):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", "left", None, "global_overview")
    with pytest.raises(VantageRequiredError, match="No vantage chosen"):
        require_picks("Hormuz", "youtube", "one_time_short_episode", "decade", "left", "drama", "")


def test_script_lean_cannot_change_a_source_stamp() -> None:
    packet = seed_first_open()
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
        assert f"[{fringe.id}]" in packet.script
        assert f"[{house.id}]" in packet.script


def test_unhinged_lean_still_fail_closed_on_missing_parallel() -> None:
    shift = open_shift(
        "Hormuz",
        platform="tiktok",
        cut="tiktok-length",
        depth="decade",
        script_lean="unhinged_fringe",
        genre="thriller",
        vantage="one_ship",
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
