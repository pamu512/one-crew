"""Catch headline-paste VO, force numeric on_screen, unique sequential beat ids.

#64 matched exact stamp.title only. Publisher-pipe titles, site-name-only VO,
digitless VO on a numeric stamp, hub-title on_screen, and duplicate beatN ids
still shipped. Fixtures use invented orgs/prints (Helios / Meridian Desk).
Production code and this file must stay free of live topic strings.
No second Parallel/Vertex mint theater.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, Rails, ScriptBeat, TimelineMapRow
from onecrew.receipt import attach_frames
from onecrew.script import sanitize_for_ship

HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-12"
HELIOS_UNIT = "https://www.helios-wire.test/2026/06/helios-occupancy-1-2m"
STAMP_TITLE = "Helios Occupancy Outlook Holds | Meridian Desk Hub"
SITE_NAME = "Meridian Desk Wire"
HEADLINE = "Campus Occupancy Outlook Holds Through June"
HUB_TITLE = "Meridian Desk Hub"
LONG_HEADLINE = "Named Campus Occupancy Outlook Holds Through The Printed Pause Window Review"
PCT_PRINT = "12%"
UNIT_PRINT = "1.2M TEU"
TOPIC = "Did named campus occupancy stall after the printed pause?"

_LIVE_TOPIC = (
    r"container(?:ized)?|\bteu\b|west[- ]coast|"
    r"railroad|class[- ]i[- ]rail|carloads?|\baar\b|\bstb\b|surface transportation|"
    r"natural[- ]gas|storage[- ]injection|"
    r"copper|mine[- ]grades?|tc/?rc|"
    r"ethanol|"
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b|"
    r"red[- ]sea|xeneta|freightos|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b|"
    r"\blithium\b|\biea\b|"
    r"\boag\b|atlanta|fort lauderdale|airfare|"
    r"grocery|power[- ]grid|interconnection|"
    r"airline[- ]ticket|us[- ]airline|"
    r"home[- ]insurance|cnbc|cotality|\bmatic\b"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b12%\b|1\.2m teu"
_BEAT_N = re.compile(r"^beat\d+$")
_HOLD_TOKS = ("cite-faithfulness", "thin_after_repair", "empty beat")


def _finding(
    *,
    fid: str,
    claim: str,
    url: str,
    printed: str | None = None,
    when: str = "June 2026",
    title: str = "timeline_event",
    note: str = "Timeline event. Parallel URL on this row.",
) -> Finding:
    return Finding(
        id=fid,
        claim=claim,
        stamp="timeline_event",
        title=title,
        series="timeline_event",
        print=printed if printed is not None else claim,
        when=when,
        parallel_url=url,
        parallel_status="hit",
        note=note,
    )


def _pct_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 12% in June 2026.",
        url=HELIOS_PRINT,
        printed=PCT_PRINT,
        title=STAMP_TITLE,
    )


def _unit_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-unit-2026-06",
        claim="Helios occupancy printed 1.2M TEU in June 2026.",
        url=HELIOS_UNIT,
        printed=UNIT_PRINT,
        title=STAMP_TITLE,
    )


def _packet(
    pack: str,
    findings: list[Finding],
    vos: dict[str, str] | None = None,
    *,
    topic: str = TOPIC,
) -> Packet:
    packet = Packet(
        id="oc-headline-paste-unique-beats",
        topic=topic,
        hook=topic,
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited prints",
        tone="On the cited print",
        research_pack=pack,
        task_spine=pack,
        status="hold",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        hold_reason=None,
        findings=list(findings),
        timeline_map=[
            TimelineMapRow(thesis=f.claim, url=f.parallel_url or "", finding_id=f.id)
            for f in findings
            if (f.parallel_url or "").strip()
        ],
    )
    lines = vos or {
        "cold-open": "NARRATOR\nThe title stays a question.",
        "promise": "NARRATOR\nThe title stays a question.",
        "gdp": "NARRATOR\nThose are not the same object.",
        "labor": "NARRATOR\nNear is not a switch.",
        "turn": "NARRATOR\nThe title stays a question.",
        "complication": "NARRATOR\nThose are not the same object.",
        "receipt": "NARRATOR\nNear is not a switch.",
        "close": "NARRATOR\nNear is not a switch.",
    }
    packet.beats = [
        ScriptBeat(
            id=bid,
            start=f"00:{i * 20:02d}",
            duration_s=20,
            scene=f"BEAT {i + 1} — {bid}",
            vo=vo,
            finding_ids=[],
        )
        for i, (bid, vo) in enumerate(lines.items())
    ]
    packet.script = "\n".join(b.scene + "\n" + b.vo for b in packet.beats) + "\n"
    return packet


def _pack(*rows: tuple[str, str]) -> str:
    bullets = "\n".join(f"- {thesis}. source: {url}" for thesis, url in rows)
    return f"## Argument\nNamed-entity events need matching stamps.\n\n## Sources\n{bullets}\n"


def _no_search(**_k):
    return SimpleNamespace(results=[])


def _voiced(packet: Packet) -> list[ScriptBeat]:
    return [b for b in packet.beats if (b.kind or "vo") != "heading"]


def _spoken(packet: Packet) -> str:
    return " ".join(f"{b.vo} {b.frame or ''}" for b in _voiced(packet))


def _vo_bodies(packet: Packet) -> list[str]:
    from onecrew.script import _vo_lines

    return [
        re.sub(r"\[[^\]]+\]", "", _vo_lines(b.vo)).strip()
        for b in _voiced(packet)
        if _vo_lines(b.vo).strip()
    ]


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").strip()


def _shipped_ready(packet: Packet) -> bool:
    return bool(packet.receipt and packet.receipt.disposition == "READY")


def _speech_norm(text: str) -> str:
    from onecrew.script import _speech_norm as norm

    return norm(text)


def _run_sanitize_repair(packet: Packet) -> None:
    run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)


def _assert_paste_cannot_ship(packet: Packet, paste: str, print_pat: str) -> None:
    bodies = _vo_bodies(packet)
    spoken = _spoken(packet)
    assert paste not in spoken, "asserting ship FAILS"
    assert paste not in bodies, "asserting ship FAILS"
    assert not any(_speech_norm(paste) == _speech_norm(b) for b in bodies), "asserting ship FAILS"
    if _shipped_ready(packet):
        assert re.search(print_pat, spoken, re.I), "asserting ship FAILS"
    else:
        assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), "asserting ship FAILS"
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_stamp_title_and_publisher_pipe_vo_cannot_ship() -> None:
    """VO equal to stamp.title or Title | Publisher must drop or expand with the print."""
    from onecrew.script import is_thin_title_read_vo, is_title_read_vo

    stamp = _pct_stamp()
    assert is_title_read_vo(STAMP_TITLE, [stamp]) is True, "asserting ship FAILS"
    assert is_thin_title_read_vo(STAMP_TITLE, [stamp]) is True, "asserting ship FAILS"
    assert is_title_read_vo("Helios Occupancy Outlook Holds", [stamp]) is True, (
        "asserting ship FAILS"
    )
    assert is_title_read_vo(stamp.claim, [stamp]) is False

    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{STAMP_TITLE}"
    packet.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(packet)
    _assert_paste_cannot_ship(packet, STAMP_TITLE, r"12\s*%|12 percent|helios occupancy printed")


def test_site_name_only_vo_cannot_ship() -> None:
    """Site-name-only VO is title-read. Not a spoken print."""
    from onecrew.script import is_thin_title_read_vo, is_title_read_vo

    stamp = _pct_stamp()
    assert is_title_read_vo(SITE_NAME, [stamp]) is True, "asserting ship FAILS"
    assert is_thin_title_read_vo(SITE_NAME, [stamp]) is True, "asserting ship FAILS"

    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{SITE_NAME}"
    packet.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(packet)
    _assert_paste_cannot_ship(packet, SITE_NAME, r"12\s*%|12 percent|helios occupancy printed")


def test_digitless_vo_on_numeric_print_cannot_ship() -> None:
    """VO with no digit/print token while stamp.print is 12% / 1.2M TEU must expand or drop."""
    from onecrew.script import is_title_read_vo

    pct = _pct_stamp()
    assert is_title_read_vo(HEADLINE, [pct]) is True, "asserting ship FAILS"

    packet = _packet(_pack((pct.claim, HELIOS_PRINT)), [pct])
    packet.beats[5].vo = f"NARRATOR\n{HEADLINE}"
    packet.beats[5].finding_ids = [pct.id]
    _run_sanitize_repair(packet)
    bodies = _vo_bodies(packet)
    spoken = _spoken(packet)
    assert HEADLINE not in spoken, "asserting ship FAILS"
    assert not any(_speech_norm(HEADLINE) == _speech_norm(b) for b in bodies), (
        "asserting ship FAILS"
    )
    if _shipped_ready(packet):
        assert re.search(r"12\s*%|12 percent", spoken, re.I), "asserting ship FAILS"
        assert any(re.search(r"\d", b) for b in bodies), "asserting ship FAILS"
    else:
        assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), "asserting ship FAILS"

    unit = _unit_stamp()
    assert is_title_read_vo(HEADLINE, [unit]) is True, "asserting ship FAILS"
    unit_pkt = _packet(_pack((unit.claim, HELIOS_UNIT)), [unit])
    unit_pkt.beats[5].vo = f"NARRATOR\n{HEADLINE}"
    unit_pkt.beats[5].finding_ids = [unit.id]
    _run_sanitize_repair(unit_pkt)
    unit_spoken = _spoken(unit_pkt)
    assert HEADLINE not in unit_spoken, "asserting ship FAILS"
    if _shipped_ready(unit_pkt):
        assert re.search(r"1\.2\s*m|1\.2m", unit_spoken, re.I), "asserting ship FAILS"
    else:
        assert any(tok in _reason(unit_pkt).lower() for tok in _HOLD_TOKS), "asserting ship FAILS"


def test_on_screen_headline_must_become_numeric_print() -> None:
    """Mute-test on_screen is the attached print. Hub / article headline cannot remain."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list
    from onecrew.script import is_title_chrome_frame

    stamp = _pct_stamp()
    assert is_title_chrome_frame(HUB_TITLE, [stamp.id], [stamp]) is True, (
        "asserting headline on_screen FAILS"
    )
    assert is_title_chrome_frame(HEADLINE, [stamp.id], [stamp]) is True, (
        "asserting headline on_screen FAILS"
    )
    assert is_title_chrome_frame(LONG_HEADLINE, [stamp.id], [stamp]) is True, (
        "asserting headline on_screen FAILS"
    )

    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 12% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = LONG_HEADLINE
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = packet.frames or write_shot_list(packet)
    cited = next(b for b in _voiced(packet) if stamp.id in b.finding_ids)
    first = next(f for f in shots if f.beat_id == cited.id)
    shown = first.on_screen or ""
    assert _speech_norm(LONG_HEADLINE) not in _speech_norm(shown), (
        "asserting headline on_screen FAILS"
    )
    assert _speech_norm(HEADLINE) not in _speech_norm(shown), "asserting headline on_screen FAILS"
    assert _speech_norm(HUB_TITLE) not in _speech_norm(shown), "asserting headline on_screen FAILS"
    assert _speech_norm(STAMP_TITLE) not in _speech_norm(shown), "asserting headline on_screen FAILS"
    assert PCT_PRINT in shown, "asserting headline on_screen FAILS"
    assert _speech_norm(LONG_HEADLINE) not in _speech_norm(cited.frame or ""), (
        "asserting headline on_screen FAILS"
    )
    assert mute_test_shows_stamp(first, [stamp], cited) is True

    hub = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    hub.beats[5].vo = f"NARRATOR\nHelios occupancy printed 12% in June 2026. [{stamp.id}]"
    hub.beats[5].finding_ids = [stamp.id]
    hub.beats[5].frame = HUB_TITLE
    sanitize_for_ship(hub)
    attach_frames(hub, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    hub_shots = hub.frames or write_shot_list(hub)
    hub_cited = next(b for b in _voiced(hub) if stamp.id in b.finding_ids)
    hub_first = next(f for f in hub_shots if f.beat_id == hub_cited.id)
    assert _speech_norm(HUB_TITLE) not in _speech_norm(hub_first.on_screen), (
        "asserting headline on_screen FAILS"
    )
    assert PCT_PRINT in hub_first.on_screen, "asserting headline on_screen FAILS"


def test_duplicate_beat3_ids_renumbered_unique_sequential() -> None:
    """After neutralize, packet.beats[].id is unique beat1…beatN in order."""
    stamp = _pct_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[2].id = "beat3"
    packet.beats[2].scene = "BEAT 3 — beat3"
    packet.beats[5].id = "beat3"
    packet.beats[5].scene = "BEAT 6 — beat3"
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 12% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    sanitize_for_ship(packet)
    ids = [b.id for b in _voiced(packet)]
    assert ids, "asserting duplicate ids ship FAILS"
    assert len(ids) == len(set(ids)), "asserting duplicate ids ship FAILS"
    assert ids.count("beat3") <= 1, "asserting duplicate ids ship FAILS"
    assert all(_BEAT_N.fullmatch(bid) for bid in ids), "asserting duplicate ids ship FAILS"
    assert ids == [f"beat{i}" for i in range(1, len(ids) + 1)], "asserting duplicate ids ship FAILS"
    assert [b.scene for b in _voiced(packet)] == [f"BEAT {i}" for i in range(1, len(ids) + 1)]


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
