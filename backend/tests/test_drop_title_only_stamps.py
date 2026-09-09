"""Drop title-only stamps; refuse topic-Q VO; never headline on_screen.

#65 only expands / forces numeric on_screen when stamp.print is clearly numeric.
PR/page-title stamps with empty or non-numeric print still shipped as
headline-paste VO + headline on_screen. Fixtures use invented orgs/prints
(Helios / Meridian Desk). Production code and this file must stay free of
live topic strings. No second Parallel/Vertex mint theater.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import MISSING, Finding, Packet, Receipt, Rails, ScriptBeat, TimelineMapRow
from onecrew.receipt import attach_frames
from onecrew.script import sanitize_for_ship

HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-12"
HELIOS_FEE = "https://www.helios-wire.test/2026/01/helios-fee-0"
HELIOS_LANE = "https://www.helios-wire.test/2026/06/helios-lane-18"
HELIOS_HUB = "https://www.helios-wire.test/hub/campus-occupancy"
STAMP_TITLE = "Campus Occupancy Outlook Holds | Meridian Desk Hub"
SITE_NAME = "Meridian Desk Wire"
HEADLINE = "Campus Occupancy Outlook Holds Through June"
HUB_TITLE = "Meridian Desk Hub"
PCT_PRINT = "12%"
FEE_PRINT = "$0/t"
LANE_PRINT = "−18%"
TOPIC = "Have named campus occupancy prints stayed on the cited card?"
TOPIC_DID = "Did named campus occupancy stall after the printed pause?"
UNCITED = "Campus occupancy jumped 47% overnight."

_LIVE_TOPIC = (
    r"\blumber\b|softwood|random[- ]lengths|"
    r"container(?:ized)?|\bteu\b|west[- ]coast|"
    r"railroad|class[- ]i[- ]rail|carloads?|\baar\b|\bstb\b|surface transportation|"
    r"natural[- ]gas|natgas|storage[- ]injection|"
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
_FIXTURE = r"helios|meridian-desk|meridian desk|\b12%\b|\$0/t|−18%|\b47%"
_HOLD_TOKS = ("cite-faithfulness", "thin_after_repair", "empty beat", "insufficient_cite_beats")


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


def _title_only_stamp(*, printed: str | None = "", title: str = STAMP_TITLE) -> Finding:
    return _finding(
        fid="te-helios-hub-2026-06",
        claim=title,
        url=HELIOS_HUB,
        printed=printed if printed is not None else "",
        title=title,
        note="Title-only hub row. Parallel URL on this row.",
    )


def _pct_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 12% in June 2026.",
        url=HELIOS_PRINT,
        printed=PCT_PRINT,
        title=STAMP_TITLE,
    )


def _fee_stamp() -> Finding:
    return _finding(
        fid="te-helios-fee-2026-01",
        claim="Helios fee printed $0/t in January 2026.",
        url=HELIOS_FEE,
        printed=FEE_PRINT,
        title="Helios fee $0/t January 2026",
        when="January 2026",
    )


def _lane_stamp() -> Finding:
    return _finding(
        fid="te-helios-lane-18",
        claim="Helios lane rates printed −18% in June 2026.",
        url=HELIOS_LANE,
        printed=LANE_PRINT,
        title="Helios lane rates −18%",
    )


def _packet(
    pack: str,
    findings: list[Finding],
    vos: dict[str, str] | None = None,
    *,
    topic: str = TOPIC,
) -> Packet:
    packet = Packet(
        id="oc-drop-title-only-stamps",
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


def _cite_faithful_count(packet: Packet) -> int:
    from onecrew.script import _cite_faithful_beats

    return len(_cite_faithful_beats(packet))


def test_empty_print_title_like_vo_is_dropped_not_shipped() -> None:
    """Empty / non-numeric print + title-like VO must drop. Title paste cannot ship."""
    from onecrew.script import is_thin_title_read_vo, is_title_read_vo

    empty = _title_only_stamp(printed="")
    missing = _title_only_stamp(printed=MISSING)
    hub = _title_only_stamp(printed=STAMP_TITLE, title=STAMP_TITLE)
    site = _title_only_stamp(printed=SITE_NAME, title=SITE_NAME)

    for stamp, paste in (
        (empty, STAMP_TITLE),
        (missing, HEADLINE),
        (hub, STAMP_TITLE),
        (site, SITE_NAME),
    ):
        assert is_title_read_vo(paste, [stamp]) is True, "asserting ship FAILS"
        assert is_thin_title_read_vo(paste, [stamp]) is True, "asserting ship FAILS"

        packet = _packet(_pack((stamp.claim, stamp.parallel_url or HELIOS_HUB)), [stamp])
        packet.beats[5].vo = f"NARRATOR\n{paste}"
        packet.beats[5].finding_ids = [stamp.id]
        _run_sanitize_repair(packet)
        bodies = _vo_bodies(packet)
        spoken = _spoken(packet)
        assert paste not in spoken, "asserting ship FAILS"
        assert paste not in bodies, "asserting ship FAILS"
        assert not any(_speech_norm(paste) == _speech_norm(b) for b in bodies), (
            "asserting ship FAILS"
        )
        cited = [b for b in _voiced(packet) if stamp.id in b.finding_ids and _speech_norm(b.vo)]
        assert cited == [], "asserting ship FAILS"
        if _shipped_ready(packet):
            assert not any(_speech_norm(paste) == _speech_norm(b) for b in bodies), (
                "asserting ship FAILS"
            )
        else:
            assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), (
                "asserting ship FAILS"
            )
        assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_topic_question_vo_is_dropped_or_stripped() -> None:
    """Have/Did topic restatement, with or without a trailing opinion, cannot ship."""
    from onecrew.script import is_topic_question_vo

    stamp = _title_only_stamp(printed="")
    packet = _packet(_pack((stamp.claim, HELIOS_HUB)), [stamp], topic=TOPIC)
    assert is_topic_question_vo(TOPIC, packet) is True, "asserting ship FAILS"
    opinion = f"{TOPIC} The printed pause still looks tight."
    assert is_topic_question_vo(opinion, packet) is True, "asserting ship FAILS"
    did_pkt = _packet(_pack((stamp.claim, HELIOS_HUB)), [stamp], topic=TOPIC_DID)
    assert is_topic_question_vo(TOPIC_DID, did_pkt) is True, "asserting ship FAILS"

    for topic, vo in (
        (TOPIC, TOPIC),
        (TOPIC, opinion),
        (TOPIC_DID, TOPIC_DID),
        (TOPIC_DID, f"{TOPIC_DID} Markets still look tight."),
    ):
        row = _title_only_stamp(printed="")
        pkt = _packet(_pack((row.claim, HELIOS_HUB)), [row], topic=topic)
        pkt.beats[5].vo = f"NARRATOR\n{vo}"
        pkt.beats[5].finding_ids = [row.id]
        _run_sanitize_repair(pkt)
        spoken = _spoken(pkt)
        bodies = _vo_bodies(pkt)
        assert "?" not in spoken, "asserting ship FAILS"
        assert not any("?" in b for b in bodies), "asserting ship FAILS"
        assert _speech_norm(topic) not in _speech_norm(spoken), "asserting ship FAILS"
        assert not any(_speech_norm(topic) == _speech_norm(b) for b in bodies), (
            "asserting ship FAILS"
        )
        assert STAMP_TITLE not in spoken, "asserting ship FAILS"
        if _shipped_ready(pkt):
            assert not re.search(r"\b(?:have|did)\b.+\?", spoken, re.I), "asserting ship FAILS"
        else:
            assert any(tok in _reason(pkt).lower() for tok in _HOLD_TOKS), (
                "asserting ship FAILS"
            )


def test_on_screen_title_when_print_empty_cannot_remain() -> None:
    """Empty/non-numeric print must not put stamp.title / headline on on_screen."""
    from onecrew.board import write_shot_list
    from onecrew.script import is_title_chrome_frame

    stamp = _title_only_stamp(printed="")
    assert is_title_chrome_frame(STAMP_TITLE, [stamp.id], [stamp]) is True, (
        "asserting title on_screen FAILS"
    )
    assert is_title_chrome_frame(HEADLINE, [stamp.id], [stamp]) is True, (
        "asserting title on_screen FAILS"
    )
    assert is_title_chrome_frame(HUB_TITLE, [stamp.id], [stamp]) is True, (
        "asserting title on_screen FAILS"
    )

    packet = _packet(_pack((stamp.claim, HELIOS_HUB)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{STAMP_TITLE}"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = STAMP_TITLE
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = packet.frames or write_shot_list(packet)
    shown = " ".join(f"{f.on_screen} {f.shot}" for f in shots) + " " + " ".join(
        b.frame or "" for b in _voiced(packet)
    )
    assert _speech_norm(STAMP_TITLE) not in _speech_norm(shown), (
        "asserting title on_screen FAILS"
    )
    assert _speech_norm(HEADLINE) not in _speech_norm(shown), (
        "asserting title on_screen FAILS"
    )
    assert _speech_norm(HUB_TITLE) not in _speech_norm(shown), (
        "asserting title on_screen FAILS"
    )
    for shot in shots:
        screen = shot.on_screen or ""
        assert _speech_norm(STAMP_TITLE) not in _speech_norm(screen), (
            "asserting title on_screen FAILS"
        )
        assert _speech_norm(stamp.title) not in _speech_norm(screen), (
            "asserting title on_screen FAILS"
        )
    if _shipped_ready(packet):
        assert all(not (f.on_screen or "").strip() or PCT_PRINT in (f.on_screen or "") for f in shots)
    else:
        assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), (
            "asserting title on_screen FAILS"
        )


def test_uncited_claim_without_covering_ids_cannot_ship() -> None:
    """VO claim with no covering finding_ids / print must drop or HOLD cite-faithfulness."""
    stamp = _pct_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{UNCITED}"
    packet.beats[5].finding_ids = []
    _run_sanitize_repair(packet)
    spoken = _spoken(packet)
    bodies = _vo_bodies(packet)
    assert UNCITED not in spoken, "asserting uncited-claim ship FAILS"
    assert "47%" not in spoken, "asserting uncited-claim ship FAILS"
    assert not any("47" in b for b in bodies), "asserting uncited-claim ship FAILS"
    if _shipped_ready(packet):
        assert "47%" not in spoken, "asserting uncited-claim ship FAILS"
    else:
        reason = _reason(packet).lower()
        assert "47%" not in spoken, "asserting uncited-claim ship FAILS"
        assert "uncited claim" not in reason or "cite-faithfulness" in reason


def test_three_numeric_print_stamps_still_ship_three_beats() -> None:
    """Pack with ≥3 numeric-print stamps must still be able to ship ≥3 beats."""
    pct, fee, lane = _pct_stamp(), _fee_stamp(), _lane_stamp()
    pack = _pack(
        (pct.claim, HELIOS_PRINT),
        (fee.claim, HELIOS_FEE),
        (lane.claim, HELIOS_LANE),
    )
    packet = _packet(
        pack,
        [pct, fee, lane],
        topic="Named campus occupancy prints on the cited card",
    )
    packet.beats[2].vo = f"NARRATOR\nHelios occupancy printed 12% in June 2026. [{pct.id}]"
    packet.beats[2].finding_ids = [pct.id]
    packet.beats[3].vo = f"NARRATOR\nHelios fee printed $0/t in January 2026. [{fee.id}]"
    packet.beats[3].finding_ids = [fee.id]
    packet.beats[5].vo = f"NARRATOR\nHelios lane rates printed −18% in June 2026. [{lane.id}]"
    packet.beats[5].finding_ids = [lane.id]
    sanitize_for_ship(packet)
    spoken = _spoken(packet)
    assert _cite_faithful_count(packet) >= 3, "asserting over-drop FAILS"
    assert re.search(r"12\s*%", spoken), "asserting over-drop FAILS"
    assert re.search(r"\$0/t|0 \$/t", spoken), "asserting over-drop FAILS"
    assert re.search(r"−18%|-18%", spoken), "asserting over-drop FAILS"
    if not _shipped_ready(packet):
        reason = _reason(packet).lower()
        assert "thin_after_repair" not in reason
        assert "insufficient_cite_beats" not in reason
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
