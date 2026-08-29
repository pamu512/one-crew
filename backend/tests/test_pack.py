import pytest

from onecrew.agent.shift import open_shift, run_live_packet
from onecrew.models import Exclusion, Rails
from onecrew.pack import PackInvalidError, hits_accounted, write_research_pack
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
)


def test_seed_pack_is_a_thesis() -> None:
    packet = seed_first_open()
    pack = packet.research_pack
    assert pack
    assert len(pack) >= 2000
    for heading in (
        "## Question",
        "## Picks",
        "## Timeline of what led here",
        "## Sources",
        "## Causal links",
        "## What we could not find",
        "## Left out / not included",
    ):
        assert heading in pack
    for finding in packet.receipt.findings:
        assert finding.id in pack
        assert finding.claim in pack
    for marker in _STAMP_MARKERS:
        assert pack.count(marker) >= len(packet.receipt.findings)
    assert packet.exclusions
    assert any(row.reason == "parallel_miss" for row in packet.exclusions)
    assert "Left out / not included" in pack
    assert packet.exclusions[0].what in pack


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
        assert f"grounded|mainstream|fringe = {finding.stamp}" in seed.research_pack
        assert finding.id in seed.research_pack
    assert "stamps: grounded|mainstream|fringe = grounded" in before
    assert "stamps: grounded|mainstream|fringe = grounded" in seed.research_pack


def test_silent_hit_drop_fails() -> None:
    packet = seed_first_open()
    extra = "https://example.com/unused-hit"
    assert hits_accounted([f.parallel_url for f in packet.receipt.findings if f.parallel_url], packet)
    assert hits_accounted([extra], packet) is False
    packet.exclusions.append(Exclusion(what=extra, reason="duplicate", detail="Same search.", url=extra))
    assert hits_accounted([extra], packet)


def test_invented_exclusion_title_fails() -> None:
    packet = seed_first_open()
    packet.exclusions.append(
        Exclusion(what="AP exclusive Hormuz minefield tape", reason="other", detail="made up")
    )
    with pytest.raises(PackInvalidError, match="invented exclusion"):
        write_research_pack(packet)
