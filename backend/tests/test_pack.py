from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from onecrew.agent.shift import open_shift, run_live_packet, run_shift
from onecrew.api import app
from onecrew.cite_repair import CiteRepairResult
from onecrew.models import Exclusion, Finding, Rails, Receipt
from onecrew.pack import (
    PackInvalidError,
    hits_accounted,
    leftover_hit_exclusions,
    write_research_pack,
)
from onecrew.store import store
from onecrew.room import RoomGrade, RoomLoopResult
from onecrew.script import write_script
from onecrew.seed import leftover_hormuz_packet, seed_first_open
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE


_STAMP_MARKERS = (
    "grounded|mainstream|fringe",
    "parallel =",
    "lean =",
    "interests =",
    "who_repeats =",
    "independent =",
    "vested_interest =",
    "propaganda =",
    "collision =",
)

_THESIS_HEADINGS = (
    "## Question",
    "## Picks",
    "## Tell",
    "## Tone",
    "## Timeline of what led here",
    "## Argument",
    "## Sources",
    "## Causal links",
    "## What we could not find",
    "## Left out / not included",
)


def test_seed_pack_is_a_thesis() -> None:
    packet = seed_first_open()
    pack = packet.research_pack
    assert pack
    assert len(pack) >= 2000
    for heading in _THESIS_HEADINGS:
        assert heading in pack
    for finding in packet.receipt.findings:
        assert finding.id in pack
        assert finding.claim in pack
        assert f"The stamp is {finding.stamp} (grounded|mainstream|fringe)." in pack
    for marker in _STAMP_MARKERS:
        assert pack.count(marker) >= len(packet.receipt.findings)
    assert packet.exclusions
    assert any(row.reason == "parallel_miss" for row in packet.exclusions)
    assert "Left out / not included" in pack
    assert packet.exclusions[0].what in pack
    assert f"reason={packet.exclusions[0].reason}" in pack
    assert "Left out:" in pack
    assert "never sold as fact" in pack
    leftover = leftover_hormuz_packet()
    assert "Propaganda stays marked" in leftover.research_pack
    readme = Path(__file__).resolve().parents[2] / "README.md"
    readme = readme.read_text()
    assert "left out and why" in readme.lower()


def test_hold_pack_is_non_empty() -> None:
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=False, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert packet.script == ""
    assert packet.research_pack
    assert "HOLD" in packet.research_pack
    assert "what ran" in packet.research_pack.lower() or "why" in packet.research_pack.lower()
    assert "Left out / not included" in packet.research_pack
    assert any(row.reason == "rails_down" for row in packet.exclusions)


def test_lean_tone_tell_do_not_change_thesis_stamps() -> None:
    seed = seed_first_open()
    before = seed.research_pack
    seed.script_lean = "left"
    seed.tone = "Question the decisions"
    seed.tell = "Weekly news desk, host only"
    write_script(seed)
    write_research_pack(seed)
    assert "[usrec-july-2026]" in seed.script
    for finding in seed.receipt.findings:
        line = f"The stamp is {finding.stamp} (grounded|mainstream|fringe)."
        assert line in before
        assert line in seed.research_pack
        assert finding.id in seed.research_pack
    assert "The stamp is grounded (grounded|mainstream|fringe)." in before
    assert "The stamp is grounded (grounded|mainstream|fringe)." in seed.research_pack


def test_get_serves_seed_thesis_without_spend() -> None:
    seed_first_open()
    with TestClient(app) as client:
        body = client.get("/api/packets")
    assert body.status_code == 200
    pack = body.json()["packets"][0]["research_pack"]
    assert pack
    assert len(pack) >= 2000
    for heading in _THESIS_HEADINGS:
        assert heading in pack


def test_silent_hit_drop_fails() -> None:
    packet = seed_first_open()
    extra = "https://example.com/unused-hit"
    assert hits_accounted([f.parallel_url for f in packet.receipt.findings if f.parallel_url], packet)
    assert hits_accounted([extra], packet) is False
    with pytest.raises(PackInvalidError, match="silent drop") as raised:
        write_research_pack(packet, hit_urls=[extra])
    assert extra in str(raised.value)
    packet.exclusions.append(Exclusion(what=extra, reason="duplicate", detail="Same search.", url=extra))
    assert hits_accounted([extra], packet)
    write_research_pack(packet, hit_urls=[extra])
    assert extra in packet.research_pack
    assert "reason=duplicate" in packet.research_pack


def test_leftover_parallel_hit_is_cited_not_invented() -> None:
    kept = "https://example.com/kept"
    extra = "https://example.com/extra"
    rows = leftover_hit_exclusions(
        [
            SimpleNamespace(url=kept, title="Kept"),
            SimpleNamespace(url=extra, title="Extra result"),
            SimpleNamespace(url=None, title="Invented page we never saw"),
        ],
        {kept},
        reason="duplicate",
        detail="Same timeline search; not stamped as a finding.",
    )
    assert [row.url for row in rows] == [extra]
    assert rows[0].what == "Extra result"
    assert rows[0].reason == "duplicate"
    unnamed = leftover_hit_exclusions(
        [SimpleNamespace(url="https://example.com/nameless", title="")],
        set(),
        reason="off_topic",
        detail="Off the topic window.",
    )
    assert unnamed[0].what == "https://example.com/nameless"


def test_not_searched_stays_not_searched() -> None:
    packet = seed_first_open()
    packet.exclusions.append(
        Exclusion(what="Pre-1980 chain", reason="not_searched", detail="Depth window not opened.")
    )
    write_research_pack(packet)
    assert "reason=not_searched" in packet.research_pack
    assert "rejected" not in packet.research_pack.lower()


def test_live_extra_parallel_hit_is_excluded(monkeypatch) -> None:
    kept = "https://example.com/kept-hit"
    extra = "https://example.com/extra-hit"

    def research_search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/fringe-miss",
                        title="Fringe miss",
                        excerpts=["Secret navy treaty already mined the strait shut."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url=kept,
                    title="Kept hit",
                    excerpts=["Hormuz tanker transits printed 23% below 2023 in March 2024."],
                ),
                SimpleNamespace(url=extra, title="Extra hit"),
            ]
        )

    monkeypatch.setattr("onecrew.agent.shift.search", research_search)
    monkeypatch.setattr(
        "onecrew.agent.shift.extract",
        lambda **_k: SimpleNamespace(results=[], errors=[]),
    )
    monkeypatch.setattr(
        "onecrew.agent.shift.run_task",
        lambda **_k: SimpleNamespace(
            output=SimpleNamespace(
                content="Hormuz tanker transits printed 23% below 2023 in March 2024. Task spine.",
                basis=[],
            )
        ),
    )
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert any(row.url == extra and row.reason == "duplicate" for row in packet.exclusions)
    assert extra in packet.research_pack
    assert "reason=duplicate" in packet.research_pack
    assert hits_accounted([kept, extra], packet)


def test_invented_exclusion_title_fails() -> None:
    packet = seed_first_open()
    packet.exclusions.append(
        Exclusion(what="AP exclusive Hormuz minefield tape", reason="other", detail="made up")
    )
    with pytest.raises(PackInvalidError, match="invented exclusion"):
        write_research_pack(packet)


_KEPT_HIT = "https://example.com/kept-hit"
_DROPPED_HIT = "https://example.com/unaccounted-hit"


def _hit_and_miss(kept: str = _KEPT_HIT) -> list[Finding]:
    return [
        Finding(
            id="hormuz-hit",
            claim="Hormuz tanker transits printed 23% below 2023 in March 2024.",
            stamp="grounded",
            title="Kept hit",
            parallel_url=kept,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="hormuz-miss",
            claim="Secret navy treaty already mined the strait shut.",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def _stub_closed_shift(monkeypatch, *, leftover, hit_urls, repair_hit_urls=None) -> dict:
    """_research returns leftover as-is. Cite-repair may add more Parallel URLs."""

    def research(packet, rails, depth, **_k):
        packet.research_pack = (
            "Hormuz tanker transits printed 23% below 2023 in March 2024."
        )
        packet.task_spine = packet.research_pack
        return (
            Receipt(
                packet_id=packet.id,
                written=False,
                disposition="READY",
                findings=_hit_and_miss(),
                causal_links=[],
            ),
            list(leftover),
            list(hit_urls),
            packet.research_pack,
        )

    vo_calls = {"n": 0}

    def tracking_vo(packet):
        vo_calls["n"] += 1
        packet.script = (
            "Tanker transits printed 23% below 2023 in March 2024. [hormuz-hit]\n"
        )
        return packet

    def repair(packet, **_k):
        return CiteRepairResult(ok=True, hit_urls=list(repair_hit_urls or []))

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", tracking_vo)
    monkeypatch.setattr("onecrew.agent.shift.run_cite_recheck_loop", repair)
    monkeypatch.setattr(
        "onecrew.agent.shift.run_room_loop",
        lambda *_a, **_k: RoomLoopResult(
            grade=RoomGrade(vote="ship"),
            parallel_research_calls=1,
            disposition="READY",
        ),
    )
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr(
        "onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[])
    )
    monkeypatch.setattr("onecrew.agent.shift._board", lambda *_a, **_k: [])
    return vo_calls


def test_unaccounted_parallel_hit_completes_without_pack_invalid(monkeypatch) -> None:
    """Leftover Parallel URL is an Exclusion or HOLD. Shift completes. Never PackInvalidError."""
    vo_calls = _stub_closed_shift(
        monkeypatch,
        leftover=[],
        hit_urls=[_KEPT_HIT, _DROPPED_HIT],
    )
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert vo_calls["n"] >= 1
    assert packet.script
    assert any(row.url == _DROPPED_HIT and row.reason == "duplicate" for row in packet.exclusions)
    assert hits_accounted([_KEPT_HIT, _DROPPED_HIT], packet)
    assert _DROPPED_HIT in (packet.research_pack or "")
    assert "reason=duplicate" in (packet.research_pack or "")


def test_cite_repair_extra_hit_is_accounted(monkeypatch) -> None:
    """Cite-repair re-query hits must be findings or exclusions before pack write."""
    _stub_closed_shift(
        monkeypatch,
        leftover=[],
        hit_urls=[_KEPT_HIT],
        repair_hit_urls=[_DROPPED_HIT],
    )
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert any(row.url == _DROPPED_HIT and row.reason == "duplicate" for row in packet.exclusions)
    assert hits_accounted([_KEPT_HIT, _DROPPED_HIT], packet)
    assert packet.script


def test_run_shift_does_not_raise_on_unaccounted_hit(monkeypatch) -> None:
    import asyncio

    _stub_closed_shift(
        monkeypatch,
        leftover=[],
        hit_urls=[_KEPT_HIT, _DROPPED_HIT],
    )
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    finished = asyncio.run(run_shift("Hormuz", shift=shift))
    assert finished.status == "completed"
    assert finished.error is None
    packet = store.get_packet(finished.packet_id)
    assert packet is not None
    assert any(row.url == _DROPPED_HIT for row in packet.exclusions)
    assert hits_accounted([_KEPT_HIT, _DROPPED_HIT], packet)


def test_unaccounted_hit_shift_api_is_not_500(monkeypatch) -> None:
    _stub_closed_shift(
        monkeypatch,
        leftover=[],
        hit_urls=[_KEPT_HIT, _DROPPED_HIT],
    )
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-parallel-key")
    monkeypatch.setattr(
        "onecrew.agent.shift.assess_rails",
        lambda: Rails(parallel=True, vertex=False, imagen=False),
    )
    pid = "oc-silent-drop-hold"
    body = {
        "goal": "Hormuz",
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "decade",
        "script_lean": "centered_independent",
        "tell": SEED_TELL,
        "tone": SEED_TONE,
        "packet_id": pid,
    }
    with TestClient(app) as client:
        posted = client.post(
            "/api/shifts",
            json=body,
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert posted.status_code != 500
        assert posted.status_code == 200
        assert posted.json()["status"] == "completed"
        assert posted.json().get("error") in {None, ""}
        got = client.get(f"/api/packets/{pid}")
    assert got.status_code == 200
    packet = got.json()
    urls = [row.get("url") for row in (packet.get("exclusions") or [])]
    assert _DROPPED_HIT in urls
    assert any(
        row.get("url") == _DROPPED_HIT and row.get("reason") == "duplicate"
        for row in (packet.get("exclusions") or [])
    )


def _boom_pack_write(monkeypatch) -> None:
    """Force PackInvalidError after leftover URLs are already exclusions."""
    real_write = write_research_pack

    def boom(packet, hit_urls=None):
        if hit_urls is not None:
            raise PackInvalidError(f"silent drop of a Parallel hit: {_DROPPED_HIT}")
        return real_write(packet)

    monkeypatch.setattr("onecrew.agent.shift.write_research_pack", boom)


def test_true_silent_drop_after_account_holds_not_500(monkeypatch) -> None:
    import asyncio

    vo_calls = _stub_closed_shift(
        monkeypatch,
        leftover=[],
        hit_urls=[_KEPT_HIT, _DROPPED_HIT],
    )
    _boom_pack_write(monkeypatch)
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    finished = asyncio.run(run_shift("Hormuz", shift=shift))
    assert finished.status == "completed"
    assert finished.error is None
    packet = store.get_packet(finished.packet_id)
    assert packet is not None
    assert vo_calls["n"] >= 1
    assert packet.script
    assert packet.status == "hold"
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    reason = packet.receipt.hold_reason or ""
    assert "silent drop" in reason.lower()
    assert _DROPPED_HIT in reason
    assert packet.research_pack
    assert "HOLD" in packet.research_pack


def test_true_silent_drop_shift_api_is_not_500(monkeypatch) -> None:
    _stub_closed_shift(
        monkeypatch,
        leftover=[],
        hit_urls=[_KEPT_HIT, _DROPPED_HIT],
    )
    _boom_pack_write(monkeypatch)
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-parallel-key")
    monkeypatch.setattr(
        "onecrew.agent.shift.assess_rails",
        lambda: Rails(parallel=True, vertex=False, imagen=False),
    )
    pid = "oc-silent-drop-pack-invalid"
    body = {
        "goal": "Hormuz",
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "decade",
        "script_lean": "centered_independent",
        "tell": SEED_TELL,
        "tone": SEED_TONE,
        "packet_id": pid,
    }
    with TestClient(app) as client:
        posted = client.post(
            "/api/shifts",
            json=body,
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert posted.status_code != 500
        assert posted.status_code == 200
        assert posted.json()["status"] == "completed"
        assert posted.json().get("error") in {None, ""}
        got = client.get(f"/api/packets/{pid}")
    assert got.status_code == 200
    packet = got.json()
    assert packet["status"] == "hold"
    reason = ((packet.get("receipt") or {}).get("hold_reason") or "")
    assert "silent drop" in reason.lower()
    assert _DROPPED_HIT in reason
