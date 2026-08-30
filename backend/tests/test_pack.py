from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from onecrew.agent.shift import open_shift, run_live_packet
from onecrew.api import app
from onecrew.models import Exclusion, Rails
from onecrew.pack import (
    PackInvalidError,
    hits_accounted,
    leftover_hit_exclusions,
    write_research_pack,
)
from onecrew.script import write_script
from onecrew.seed import seed_first_open


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
    "## Desk card",
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
    assert "Propaganda stays marked" in pack
    readme = Path("/workspace/README.md").read_text()
    assert "left out and why" in readme.lower()


def test_hold_pack_is_non_empty() -> None:
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Narrator-led global overview of the US and Iran",
        tone="Grounded in the record",
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
    assert "[jcpoa-2018]" in seed.script
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
    with pytest.raises(PackInvalidError, match="silent drop"):
        write_research_pack(packet, hit_urls=[extra])
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
            return SimpleNamespace(results=[])
        return SimpleNamespace(
            results=[
                SimpleNamespace(url=kept, title="Kept hit"),
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
            output=SimpleNamespace(content="Task spine.", basis=[])
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
        tell="Narrator-led global overview of the US and Iran",
        tone="Grounded in the record",
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
