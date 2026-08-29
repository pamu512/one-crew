import copy
import re

from onecrew.models import MISSING, Packet, Receipt
from onecrew.script import write_script
from onecrew.seed import seed_findings, seed_first_open, seed_links


def _packet(*, platform: str, cut: str, lean: str) -> Packet:
    packet = Packet(
        id="oc-vo",
        topic="Explain what's going on with the Hormuz strait",
        hook="Explain what's going on with the Hormuz strait",
        script="",
        platform=platform,
        cut=cut,
        depth="decade",
        script_lean=lean,
    )
    receipt = Receipt(
        packet_id=packet.id,
        findings=copy.deepcopy(seed_findings()),
        causal_links=copy.deepcopy(seed_links()),
        disposition="READY",
        written=True,
    )
    packet.receipt = receipt
    return write_script(packet)


def test_right_and_left_vo_wording_differs_stamps_identical() -> None:
    left = _packet(platform="youtube", cut="one_time_short_episode", lean="left")
    right = _packet(platform="youtube", cut="one_time_short_episode", lean="right")
    left_stamps = [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in left.receipt.findings
    ]
    right_stamps = [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in right.receipt.findings
    ]
    assert left_stamps == right_stamps
    assert left.script != right.script
    assert "public file" in left.script.lower()
    assert "state-file" in right.script.lower()
    assert "Right-leaning read." not in right.script
    assert "Left-leaning read." not in left.script
    assert "Straight read." not in left.script


def test_tiktok_vo_is_short_episode_has_running_timecodes() -> None:
    tiktok = _packet(platform="tiktok", cut="tiktok-length", lean="centered_independent")
    episode = _packet(
        platform="youtube", cut="one_time_short_episode", lean="centered_independent"
    )
    assert len(tiktok.script) < len(episode.script)
    assert len(tiktok.beats) < len(episode.beats)
    assert sum(b.duration_s for b in tiktok.beats) < 60
    assert sum(b.duration_s for b in episode.beats) >= 40 * 60
    assert re.search(r"\d{2}:\d{2}:\d{2}", episode.script)
    assert "ACT" in episode.script
    assert "00:" in tiktok.script
    assert "ACT" not in tiktok.script


def test_every_script_beat_cites_an_existing_finding() -> None:
    packet = seed_first_open()
    write_script(packet)
    ids = {f.id for f in packet.receipt.findings}
    assert packet.beats
    for beat in packet.beats:
        assert beat.finding_ids
        assert set(beat.finding_ids) <= ids
        for fid in beat.finding_ids:
            assert f"[{fid}]" in beat.vo
            assert f"[{fid}]" in packet.script


def test_unhinged_and_centered_cannot_hide_fringe_or_propaganda() -> None:
    for lean in ("unhinged_fringe", "centered_independent"):
        packet = _packet(platform="youtube", cut="one_time_short_episode", lean=lean)
        assert "[secret-closure]" in packet.script
        assert "fringe" in packet.script.lower()
        assert "[hormuz-share]" in packet.script
        assert "propaganda" in packet.script.lower()
        assert "opec" in packet.script.lower()
        missing = next(f for f in packet.receipt.findings if f.lean == MISSING)
        assert missing.lean == MISSING


def test_hold_receipt_writes_empty_script() -> None:
    packet = Packet(
        id="oc-hold",
        hook="hook",
        script="should clear",
        platform="tiktok",
        cut="tiktok-length",
        depth="decade",
        script_lean="unhinged_fringe",
    )
    packet.receipt = Receipt(
        packet_id=packet.id, disposition="HOLD", findings=[], written=True
    )
    write_script(packet)
    assert packet.script == ""
    assert packet.beats == []
