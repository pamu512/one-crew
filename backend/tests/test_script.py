import copy
import re

from onecrew.models import MISSING, SCRIPT_LEANS, Packet, Receipt
from onecrew.script import write_script
from onecrew.seed import seed_findings, seed_first_open, seed_links

_RECEIPT_JARGON = (
    "on the receipt",
    "hold on this card",
    "receipt card for",
    "tagged fringe",
    "propaganda yes",
    "independent on that row",
    "do not add a fact that is not on the row",
    "straight read",
    "right-leaning read",
    "left-leaning read",
    "source lean",
    "not a source",
)


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
        tell="Narrator-led global overview of the US and Iran",
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
    left_jcpoa = next(b.vo for b in left.beats if b.id == "jcpoa-2018")
    right_jcpoa = next(b.vo for b in right.beats if b.id == "jcpoa-2018")
    assert left_jcpoa != right_jcpoa
    assert "[jcpoa-2018]" in left_jcpoa and "[jcpoa-2018]" in right_jcpoa
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
    assert "ACT 1" in episode.script
    assert "00:" in tiktok.script
    assert "ACT 1" not in tiktok.script


def test_every_script_beat_cites_an_existing_finding() -> None:
    packet = seed_first_open()
    write_script(packet)
    ids = {f.id for f in packet.receipt.findings}
    assert packet.beats
    for beat in packet.beats:
        assert beat.finding_ids
        assert set(beat.finding_ids) <= ids
        if beat.kind == "vo":
            for fid in beat.finding_ids:
                assert f"[{fid}]" in beat.vo
                assert f"[{fid}]" in packet.script


def test_unhinged_and_centered_cannot_hide_fringe_or_propaganda() -> None:
    for lean in ("unhinged_fringe", "centered_independent"):
        packet = _packet(platform="youtube", cut="one_time_short_episode", lean=lean)
        assert "[secret-closure]" in packet.script
        assert "mined shut" in packet.script.lower() or "hidden navy" in packet.script.lower()
        assert "[hormuz-share]" in packet.script
        assert "hormuz" in packet.script.lower()
        missing = next(f for f in packet.receipt.findings if f.id == "oil-panic")
        assert missing.lean == MISSING
        assert missing.stamp == "mainstream"


def test_vo_has_no_receipt_jargon() -> None:
    combos = (
        ("tiktok", "tiktok-length", "right"),
        ("youtube", "one_time_short_episode", "centered_independent"),
        ("youtube", "full_length_documentary", "left"),
        ("tiktok", "tiktok-length", "unhinged_fringe"),
    )
    for platform, cut, lean in combos:
        packet = _packet(platform=platform, cut=cut, lean=lean)
        blob = packet.script.lower()
        for beat in packet.beats:
            blob += "\n" + beat.vo.lower()
        for banned in _RECEIPT_JARGON:
            assert banned not in blob, f"{banned!r} in {platform}/{cut}/{lean}"
    seed = seed_first_open()
    seed_blob = seed.script.lower() + "\n" + "\n".join(b.vo.lower() for b in seed.beats)
    for banned in _RECEIPT_JARGON:
        assert banned not in seed_blob


def test_right_tiktok_and_left_doc_are_not_a_wrapper() -> None:
    right = _packet(platform="tiktok", cut="tiktok-length", lean="right")
    left = _packet(platform="youtube", cut="full_length_documentary", lean="left")
    r = next(b for b in right.beats if b.id == "jcpoa-2018")
    l = next(b for b in left.beats if b.id == "jcpoa-2018")
    r_body = re.sub(r"\s*\[[^\]]+\]", "", r.vo).strip()
    l_body = re.sub(r"\s*\[[^\]]+\]", "", l.vo).strip()
    assert r_body != l_body
    claim = next(f.claim for f in right.receipt.findings if f.id == "jcpoa-2018")
    assert r_body != f"In 2018, on the receipt: {claim}."
    assert l_body != f"In 2018, the public file, not the talking-point version: {claim}."
    assert len(left.script) > len(right.script)
    assert len(left.beats) > len(right.beats)
    for lean in SCRIPT_LEANS:
        packet = _packet(platform="youtube", cut="one_time_short_episode", lean=lean)
        stamps = [(f.id, f.stamp, f.propaganda) for f in packet.receipt.findings]
        assert stamps == [(f.id, f.stamp, f.propaganda) for f in right.receipt.findings]


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
