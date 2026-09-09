import copy
import re

from onecrew.models import MISSING, SCRIPT_LEANS, Packet, Receipt
from onecrew.script import write_script
from onecrew.seed import leftover_hormuz_findings, leftover_hormuz_links, seed_first_open

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
        topic="How a decade of decisions around the Strait of Hormuz still sets the price of oil",
        hook="How a decade of decisions around the Strait of Hormuz still sets the price of oil",
        script="",
        platform=platform,
        cut=cut,
        depth="decade",
        script_lean=lean,
        tell="Narrator-led global overview of the US and Iran",
    )
    receipt = Receipt(
        packet_id=packet.id,
        findings=copy.deepcopy(leftover_hormuz_findings()),
        causal_links=copy.deepcopy(leftover_hormuz_links()),
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
    left_open = next(b.vo for b in left.beats if b.id == "cold-open")
    right_open = next(b.vo for b in right.beats if b.id == "cold-open")
    assert left_open != right_open
    assert left.beats[0].id == "cold-open"
    assert "Right-leaning read." not in right.script
    assert "Left-leaning read." not in left.script
    assert "Straight read." not in left.script


def test_tiktok_vo_is_short_episode_has_running_timecodes() -> None:
    tiktok = _packet(platform="tiktok", cut="tiktok-length", lean="centered_independent")
    episode = _packet(
        platform="youtube", cut="one_time_short_episode", lean="centered_independent"
    )
    assert len(tiktok.script) < len(episode.script)
    assert sum(b.duration_s for b in tiktok.beats) < 60
    assert 6 * 60 <= sum(b.duration_s for b in episode.beats) <= 12 * 60
    assert re.search(r"\d{2}:\d{2}:\d{2}", episode.script)
    assert "ACT 1" in episode.script
    assert "00:" in tiktok.script
    assert "ACT 1" not in tiktok.script
    assert len([b for b in episode.beats if b.kind == "vo"]) == 8


def test_every_script_beat_cites_an_existing_finding() -> None:
    packet = seed_first_open()
    write_script(packet)
    ids = {f.id for f in packet.receipt.findings}
    assert packet.beats
    for beat in packet.beats:
        assert beat.finding_ids
        assert set(beat.finding_ids) <= ids
        if beat.kind == "vo" and beat.finding_ids:
            assert any(f"[{fid}]" in beat.vo for fid in beat.finding_ids)


def test_unhinged_and_centered_cannot_hide_fringe_or_propaganda() -> None:
    for lean in ("unhinged_fringe", "centered_independent"):
        packet = _packet(platform="youtube", cut="one_time_short_episode", lean=lean)
        fringe = next(f for f in packet.receipt.findings if f.stamp == "fringe")
        house = next(f for f in packet.receipt.findings if f.propaganda == "yes")
        assert fringe.stamp == "fringe"
        assert house.propaganda == "yes"
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
    r = next(b for b in right.beats if b.id == "cold-open")
    l = next(b for b in left.beats if b.id == "cold-open")
    r_body = re.sub(r"\s*\[[^\]]+\]", "", r.vo).strip()
    l_body = re.sub(r"\s*\[[^\]]+\]", "", l.vo).strip()
    assert r_body != l_body
    assert "on the receipt" not in r_body.lower()
    assert len(left.script) > len(right.script)
    for lean in SCRIPT_LEANS:
        packet = _packet(platform="youtube", cut="one_time_short_episode", lean=lean)
        stamps = [(f.id, f.stamp, f.propaganda) for f in packet.receipt.findings]
        assert stamps == [(f.id, f.stamp, f.propaganda) for f in right.receipt.findings]


def test_independent_months_no_smash_mint_holes_skip_mixed() -> None:
    """Script must not mint smash mixed months from observation-month mismatch alone."""
    from onecrew.models import Finding

    packet = Packet(
        id="oc-independent-months",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        research_pack="Independent USREC and payrolls observations. No smash stamp.",
        task_spine="Independent USREC and payrolls observations. No smash stamp.",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-june-2026",
                claim="USREC=0 (June 2026).",
                stamp="grounded",
                title="USREC",
                series="USREC",
                print="0",
                when="June 2026",
                parallel_url="https://fred.stlouisfed.org/series/USREC",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-august-2026",
                claim="Nonfarm payrolls increased by 10,000 in August 2026.",
                stamp="grounded",
                title="BLS payrolls",
                series="BLS payrolls",
                print="+10,000",
                when="August 2026",
                parallel_url="https://www.bls.gov/news.release/empsit.nr0.htm",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
        ],
    )
    write_script(packet)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert not re.search(r"smash(?:ed)?\s+into", spoken, re.I)
    reason = (packet.receipt.hold_reason or "").lower()
    assert "smash mixed months" not in reason


def test_claimed_smash_in_spine_mints_smash_mixed_months() -> None:
    """VO/spine smash with conflicting months HOLDs even when the pipe is missing."""
    from onecrew.models import Finding

    packet = Packet(
        id="oc-claimed-smash",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        research_pack="No payrolls-month pipe cell.",
        task_spine="USREC=0 (June 2026) smashed into payrolls.",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-june-2026",
                claim="USREC=0 (June 2026).",
                stamp="grounded",
                title="USREC",
                series="USREC",
                print="0",
                when="June 2026",
                parallel_url="https://fred.stlouisfed.org/series/USREC",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-august-2026",
                claim="Nonfarm payrolls increased by 10,000 in August 2026.",
                stamp="grounded",
                title="BLS payrolls",
                series="BLS payrolls",
                print="+10,000",
                when="August 2026",
                parallel_url="https://www.bls.gov/news.release/empsit.nr0.htm",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
        ],
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "").lower()
    assert "smash mixed months" in reason


def test_pipe_remap_miss_still_mints_smash_mixed_months() -> None:
    """Pipe 0/1 on the payrolls month with a different USREC when is still a smash hole."""
    from onecrew.models import Finding

    pack = (
        "observation_date,USREC\n2026-05-01,0\n2026-06-01,0\n2026-08-01,0\n"
        "Payrolls printed in August 2026."
    )
    packet = Packet(
        id="oc-pipe-remap-miss",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        research_pack=pack,
        task_spine=pack,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-june-2026",
                claim="USREC=0 (June 2026).",
                stamp="grounded",
                title="USREC",
                series="USREC",
                print="0",
                when="June 2026",
                parallel_url="https://fred.stlouisfed.org/series/USREC",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-august-2026",
                claim="Nonfarm payrolls increased by 10,000 in August 2026.",
                stamp="grounded",
                title="BLS payrolls",
                series="BLS payrolls",
                print="+10,000",
                when="August 2026",
                parallel_url="https://www.bls.gov/news.release/empsit.nr0.htm",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
        ],
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "").lower()
    assert "smash mixed months" in reason


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


_HOLD_META_BANNED = (
    "gdp hole named",
    "no matching url",
    "spine chart stays",
    "hold. the spine",
    "hold on the pack number",
)


def _live_sahm_packet() -> Packet:
    """Live dd25387b shape: USREC+payrolls+Sahm stamped. GDP 0.5 already rejected."""
    from onecrew.models import Finding

    pack = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls fell −23,000 in July 2026. "
        "Sahm is −0.03 vs the 0.50 trigger."
    )
    packet = Packet(
        id="oc-are-we-near-recession-dd25387b",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        research_pack=pack,
        task_spine=pack,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-july-2026",
                claim="USREC=0 (July 2026).",
                stamp="grounded",
                title="USREC",
                series="USREC",
                print="0",
                when="July 2026",
                parallel_url="https://fred.stlouisfed.org/series/USREC",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-july-2026",
                claim="Nonfarm payrolls fell −23,000.",
                stamp="grounded",
                title="BLS payrolls",
                series="BLS payrolls",
                print="−23,000",
                when="July 2026",
                parallel_url="https://www.bls.gov/news.release/empsit.nr0.htm",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="sahm-july-2026",
                claim="Sahm is −0.03 vs the 0.50 trigger.",
                stamp="grounded",
                title="Sahm rule",
                series="SAHMREALTIME",
                print="−0.03",
                when="July 2026",
                parallel_url="https://fred.stlouisfed.org/series/SAHMREALTIME",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
        ],
    )
    return packet


def _narrator_blob(packet: Packet) -> str:
    return (packet.script or "") + "\n" + "\n".join(b.vo for b in packet.beats)


def test_local_eight_beat_never_speaks_hold_meta_and_voices_stamped_sahm() -> None:
    packet = _live_sahm_packet()
    write_script(packet)
    spoken = _narrator_blob(packet)
    low = spoken.lower()
    for banned in _HOLD_META_BANNED:
        assert banned not in low, banned
    assert re.search(r"\bhold\.", low) is None
    assert "−0.03" in spoken or "-0.03" in spoken
    assert "0.50" in spoken
    assert "pack numbers missing from VO" not in ((packet.receipt.hold_reason or "") if packet.receipt else "")
    assert packet.status == "ready"
    assert len([b for b in packet.beats if b.kind == "vo"]) == 8
    from onecrew.board import write_shot_list

    frames = write_shot_list(packet)
    assert len(frames) == 8


def test_vertex_hold_meta_stripped_stamped_sahm_spoken_not_hold(monkeypatch) -> None:
    """ADK leftover production notes must not stay in NARRATOR or silent-drop Sahm."""
    dirty = (
        '[{"id":"cold-open","vo":"USREC=0 (July 2026). Labor: payrolls −23,000. Named BLS. '
        '[usrec-july-2026] [payrolls-july-2026]",'
        '"eyes":"cards","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"promise","vo":"Three objects from the pack. [usrec-july-2026]",'
        '"eyes":"pack","finding_ids":["usrec-july-2026"]},'
        '{"id":"gdp","vo":"GDP hole named. No matching URL. Hold.",'
        '"eyes":"GDP hole named. No matching URL.","finding_ids":[]},'
        '{"id":"labor","vo":"Labor: payrolls −23,000. Named BLS. [payrolls-july-2026]",'
        '"eyes":"ces","finding_ids":["payrolls-july-2026"]},'
        '{"id":"turn","vo":"Hold. The spine chart stays.",'
        '"eyes":"Hold. Chart stays.","finding_ids":[]},'
        '{"id":"complication","vo":"Those are not the same object. Near is the gap. [usrec-july-2026]",'
        '"eyes":"gap","finding_ids":["usrec-july-2026"]},'
        '{"id":"receipt","vo":"Receipt board: named series NBER, FRED, BLS. '
        '[usrec-july-2026] [payrolls-july-2026]",'
        '"eyes":"board","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-july-2026]",'
        '"eyes":"close","finding_ids":["usrec-july-2026"]}]'
    )
    packet = _live_sahm_packet()
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda *_a, **_k: dirty)
    write_script(packet)
    spoken = _narrator_blob(packet)
    low = spoken.lower()
    for banned in _HOLD_META_BANNED:
        assert banned not in low, banned
    assert re.search(r"\bhold\.", low) is None
    assert "−0.03" in spoken or "-0.03" in spoken
    reason = (packet.receipt.hold_reason or "") if packet.receipt else ""
    assert "pack numbers missing from VO" not in reason
    assert packet.status == "ready"
    assert packet.script
    assert len(packet.beats) == 8
    from onecrew.board import write_shot_list

    frames = write_shot_list(packet)
    assert len(frames) == 8
