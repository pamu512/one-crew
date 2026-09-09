"""Mute-fill on_screen, topic-Q clause refuse, hanging opener, non-digit finding_ids.

Live HOLD: numeric VO + covering stamps still shipped empty on_screen; topic
question + answer stayed; `with average …` fragments shipped; finding_ids were
bare indexes. Gates must run on the live board/receipt path, not unit-only.
Fixtures use invented orgs/prints (Helios / Meridian Desk). Production code
and this file must stay free of live topic strings. No second Parallel/Vertex
mint theater. Do not live POST.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, Rails, ScriptBeat, TimelineMapRow
from onecrew.receipt import attach_frames
from onecrew.script import sanitize_for_ship

HELIOS_A = "https://www.helios-wire.test/2026/06/helios-card-a-151"
HELIOS_B = "https://www.meridian-desk.test/2026/01/helios-card-b-376"
HELIOS_C = "https://www.north-campus.test/2026/06/helios-card-c-12"
HELIOS_HUB = "https://www.helios-wire.test/hub/campus-occupancy"
HELIOS_RSS = "https://www.helios-wire.test/subscribe/rss"
TITLE_A = "Campus Occupancy Outlook Holds | Meridian Desk Hub"
TITLE_B = "Named Fee Card Outlook Holds | Meridian Desk Hub"
TITLE_C = "Lane Print Outlook Holds | Meridian Desk Hub"
HEADLINE = "Campus Occupancy Outlook Holds Through June"
PRINT_A = "$1.51"
PRINT_B = "$3.76"
PRINT_C = "12%"
TOPIC = "Have named campus occupancy prints stayed on the cited card?"
TOPIC_DID = "Did named campus occupancy prints ease on the cited card?"
RSS_ID = "te-helios-subscribe-rss-feed"
RSS_TITLE = "Subscribe to RSS feed"
HANGING = "with average occupancy printed at 12% on the cited card"

_LIVE_TOPIC = (
    r"\bdwell\b|east[- ]coast|"
    r"soybean|\bcrush\b|"
    r"diesel|crack[- ]spreads?|"
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
    r"\blithium\b|"
    r"\boag\b|atlanta|fort lauderdale|airfare|"
    r"grocery|power[- ]grid|interconnection|"
    r"airline[- ]ticket|us[- ]airline|"
    r"home[- ]insurance|cnbc|cotality|\bmatic\b"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\$1\.51|\$3\.76|\b12%"
_HOLD_TOKS = (
    "cite-faithfulness",
    "thin_after_repair",
    "empty beat",
    "insufficient_cite_beats",
    "opaque_finding_id",
)


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


def _print_stamp(*, fid: str, claim: str, url: str, printed: str, title: str, when: str = "June 2026") -> Finding:
    return _finding(fid=fid, claim=title, url=url, printed=printed, title=title, when=when)


def _stamp_a(*, fid: str = "te-helios-card-a-151") -> Finding:
    return _print_stamp(fid=fid, claim=TITLE_A, url=HELIOS_A, printed=PRINT_A, title=TITLE_A)


def _stamp_b(*, fid: str = "te-helios-card-b-376") -> Finding:
    return _print_stamp(
        fid=fid, claim=TITLE_B, url=HELIOS_B, printed=PRINT_B, title=TITLE_B, when="January 2026"
    )


def _stamp_c(*, fid: str = "te-helios-card-c-12") -> Finding:
    return _print_stamp(fid=fid, claim=TITLE_C, url=HELIOS_C, printed=PRINT_C, title=TITLE_C)


def _title_only_stamp() -> Finding:
    return _finding(
        fid="te-helios-hub-2026-06",
        claim=TITLE_A,
        url=HELIOS_HUB,
        printed="",
        title=TITLE_A,
        note="Title-only hub row. Parallel URL on this row.",
    )


def _rss_stamp() -> Finding:
    return _finding(
        fid=RSS_ID,
        claim="Subscribe to the Helios occupancy desk.",
        url=HELIOS_RSS,
        printed="",
        title=RSS_TITLE,
        note="Subscribe RSS feed hub. Not a covering stamp.",
    )


def _packet(
    pack: str,
    findings: list[Finding],
    vos: dict[str, str] | None = None,
    *,
    topic: str = TOPIC,
) -> Packet:
    packet = Packet(
        id="oc-mute-fill-topicq-hanging-ids",
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


def _cite_faithful_count(packet: Packet) -> int:
    from onecrew.script import _cite_faithful_beats

    return len(_cite_faithful_beats(packet))


def _live_board_receipt(packet: Packet) -> None:
    """Live shift path: cite-repair → room sanitize/disposition → write_board → attach_frames."""
    from onecrew.board import write_board
    from onecrew.room import RoomGrade, _sanitize_disposition

    run_cite_recheck_loop(packet, search_fn=_no_search)
    rails = Rails(parallel=False, vertex=False, imagen=False)
    _sanitize_disposition(packet, RoomGrade(vote="ship"), 1, ready=True)
    frames = write_board(packet, rails)
    attach_frames(packet, frames, rails=rails)


def _shots(packet: Packet):
    from onecrew.board import write_shot_list

    return packet.frames or write_shot_list(packet)


def _three_print_pack() -> tuple[Packet, Finding, Finding, Finding]:
    a, b, c = _stamp_a(), _stamp_b(), _stamp_c()
    pack = _pack((a.claim, HELIOS_A), (b.claim, HELIOS_B), (c.claim, HELIOS_C))
    packet = _packet(pack, [a, b, c], topic="Named campus occupancy prints on the cited card")
    packet.beats[2].vo = f"NARRATOR\n{TITLE_A}"
    packet.beats[2].finding_ids = [a.id]
    packet.beats[3].vo = f"NARRATOR\n{TITLE_B}"
    packet.beats[3].finding_ids = [b.id]
    packet.beats[5].vo = f"NARRATOR\n{TITLE_C}"
    packet.beats[5].finding_ids = [c.id]
    return packet, a, b, c


def test_numeric_vo_covering_print_fills_on_screen_via_board_receipt() -> None:
    """Spoken covering number must land on on_screen. Empty mute-test FAILS."""
    from onecrew.board import mute_test_shows_stamp
    from onecrew.script import is_digit_finding_id

    slug = _stamp_a()
    indexed = _stamp_a(fid="5")
    for stamp, fids, vo in (
        (
            slug,
            [slug.id],
            f"NARRATOR\nThe cited card printed $1.51 in June 2026. [{slug.id}]",
        ),
        (
            indexed,
            ["5"],
            "NARRATOR\nThe cited card printed $1.51 in June 2026. [5]",
        ),
        (
            slug,
            ["5"],
            f"NARRATOR\nThe cited card printed $1.51 in June 2026. [{slug.id}]",
        ),
    ):
        packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
        packet.beats[5].vo = vo
        packet.beats[5].finding_ids = list(fids)
        packet.beats[5].frame = ""
        for beat in packet.beats:
            if beat is not packet.beats[5]:
                beat.frame = ""
        _live_board_receipt(packet)
        shots = _shots(packet)
        cited = [b for b in _voiced(packet) if b.finding_ids and _speech_norm(b.vo)]
        numeric = [b for b in cited if re.search(r"\$1\.51|1\.51", f"{b.vo} {b.frame or ''}")]
        assert numeric, "asserting empty on_screen with numeric VO FAILS"
        hit = [s for s in shots if s.beat_id in {b.id for b in numeric}]
        assert hit, "asserting empty on_screen with numeric VO FAILS"
        assert all((s.on_screen or "").strip() for s in hit), (
            "asserting empty on_screen with numeric VO FAILS"
        )
        assert all((s.on_screen or "").strip() == PRINT_A for s in hit), (
            "asserting empty on_screen with numeric VO FAILS"
        )
        for shot in hit:
            beat = next(b for b in numeric if b.id == shot.beat_id)
            rows = [f for f in (packet.receipt.findings if packet.receipt else []) if f.id in beat.finding_ids]
            assert mute_test_shows_stamp(shot, rows or [stamp], beat) is True
            assert not any(is_digit_finding_id(fid) for fid in beat.finding_ids), (
                "asserting empty on_screen with numeric VO FAILS"
            )
        if _shipped_ready(packet):
            assert any(PRINT_A in (s.on_screen or "") for s in hit), (
                "asserting empty on_screen with numeric VO FAILS"
            )
        else:
            assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), (
                "asserting empty on_screen with numeric VO FAILS"
            )


def test_topic_question_clause_with_answer_cannot_ship() -> None:
    """Did/Have topic restatement stays refused even when an answer clause follows."""
    from onecrew.script import is_topic_question_vo

    stamp = _stamp_a()
    answered = f"{TOPIC} The cited card printed $1.51 in June 2026."
    did_answered = f"{TOPIC_DID} The cited card printed $1.51 in June 2026."
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp], topic=TOPIC)
    assert is_topic_question_vo(TOPIC, packet) is True, "asserting topic-question ship FAILS"
    assert is_topic_question_vo(answered, packet) is True, "asserting topic-question ship FAILS"
    did_pkt = _packet(_pack((stamp.claim, HELIOS_A)), [stamp], topic=TOPIC_DID)
    assert is_topic_question_vo(did_answered, did_pkt) is True, "asserting topic-question ship FAILS"

    for topic, vo in (
        (TOPIC, answered),
        (TOPIC_DID, did_answered),
        (TOPIC, f"Did named campus occupancy prints stay on the cited card? {PRINT_A}."),
    ):
        row = _stamp_a()
        pkt = _packet(_pack((row.claim, HELIOS_A)), [row], topic=topic)
        pkt.beats[5].vo = f"NARRATOR\n{vo}"
        pkt.beats[5].finding_ids = [row.id]
        _live_board_receipt(pkt)
        spoken = _spoken(pkt)
        bodies = _vo_bodies(pkt)
        assert "?" not in spoken, "asserting topic-question ship FAILS"
        assert not any("?" in b for b in bodies), "asserting topic-question ship FAILS"
        assert not re.search(r"\b(?:have|did)\b.+\?", spoken, re.I), (
            "asserting topic-question ship FAILS"
        )
        assert _speech_norm(topic) not in _speech_norm(spoken), (
            "asserting topic-question ship FAILS"
        )
        if _shipped_ready(pkt):
            assert re.search(r"\$1\.51|1\.51", spoken), "asserting topic-question ship FAILS"
        else:
            assert any(tok in _reason(pkt).lower() for tok in _HOLD_TOKS), (
                "asserting topic-question ship FAILS"
            )


def test_hanging_with_average_opener_cannot_ship() -> None:
    """VO that opens with a dangling connector must drop/rewrite to a full print sentence."""
    from onecrew.script import is_hanging_clause_vo, is_incomplete_vo

    stamp = _stamp_c()
    assert is_hanging_clause_vo(HANGING) is True, "asserting hanging ship FAILS"
    assert is_incomplete_vo(HANGING) is True, "asserting hanging ship FAILS"

    packet = _packet(_pack((stamp.claim, HELIOS_C)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{HANGING}"
    packet.beats[5].finding_ids = [stamp.id]
    _live_board_receipt(packet)
    spoken = _spoken(packet)
    bodies = _vo_bodies(packet)
    assert not any(re.match(r"^(with|and|but)\b", b, re.I) for b in bodies), (
        "asserting hanging ship FAILS"
    )
    assert not re.search(r"(?:^|\n)\s*with average\b", spoken, re.I), (
        "asserting hanging ship FAILS"
    )
    if _shipped_ready(packet):
        assert re.search(r"12\s*%", spoken), "asserting hanging ship FAILS"
        assert any(_speech_norm(b) and not re.match(r"^(with|and|but)\b", b, re.I) for b in bodies)
    else:
        assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), (
            "asserting hanging ship FAILS"
        )


def test_digit_finding_ids_rewrite_to_slug_or_hold() -> None:
    """Bare integer finding_ids cannot ship. Map to a url-stem/series slug or HOLD."""
    from onecrew.script import is_digit_finding_id

    stamp = _stamp_a(fid="5")
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    packet.beats[5].vo = "NARRATOR\nThe cited card printed $1.51 in June 2026. [5]"
    packet.beats[5].finding_ids = ["5"]
    assert all(is_digit_finding_id(fid) for fid in packet.beats[5].finding_ids)
    assert is_digit_finding_id(stamp.id)

    _live_board_receipt(packet)
    cited = [b for b in _voiced(packet) if b.finding_ids and _speech_norm(b.vo)]
    leftover = [
        fid
        for beat in cited
        for fid in beat.finding_ids
        if is_digit_finding_id(fid)
    ]
    finding_digits = [
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if is_digit_finding_id(f.id)
    ]
    if _shipped_ready(packet):
        assert cited, "asserting pure-digit finding_id ship FAILS"
        assert leftover == [], "asserting pure-digit finding_id ship FAILS"
        assert finding_digits == [], "asserting pure-digit finding_id ship FAILS"
        assert any(re.search(r"helios-card-a-151|te-", fid) for b in cited for fid in b.finding_ids), (
            "asserting pure-digit finding_id ship FAILS"
        )
    else:
        assert leftover or finding_digits or any(
            tok in _reason(packet).lower() for tok in _HOLD_TOKS
        ), "asserting pure-digit finding_id ship FAILS"
        assert "5" not in leftover or any(
            tok in _reason(packet).lower() for tok in _HOLD_TOKS
        ), "asserting pure-digit finding_id ship FAILS"


def test_multibeat_kept_when_prints_exist() -> None:
    """Pack with ≥3 numeric-print stamps must keep ≥3 print beats after the live path."""
    packet, a, b, c = _three_print_pack()
    _live_board_receipt(packet)
    spoken = _spoken(packet)
    faithful = _cite_faithful_count(packet)
    assert faithful >= 3, "asserting 1-beat ship FAILS"
    assert re.search(r"\$1\.51|1\.51", spoken), "asserting 1-beat ship FAILS"
    assert re.search(r"\$3\.76|3\.76", spoken), "asserting 1-beat ship FAILS"
    assert re.search(r"12\s*%", spoken), "asserting 1-beat ship FAILS"
    if _shipped_ready(packet):
        assert faithful >= 3, "asserting 1-beat ship FAILS"
    else:
        reason = _reason(packet).lower()
        assert "thin_after_repair" not in reason, "asserting 1-beat ship FAILS"
        assert "insufficient_cite_beats" not in reason, "asserting 1-beat ship FAILS"
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_rss_and_title_only_still_drop() -> None:
    """True title-only / empty print / RSS hub cites still drop. Regression."""
    from onecrew.script import _stamp_can_cover, is_thin_title_read_vo, is_title_read_vo
    from onecrew.timeline import is_chrome_cover_stamp

    empty = _title_only_stamp()
    assert is_title_read_vo(TITLE_A, [empty]) is True, "asserting title-only drop FAILS"
    assert is_thin_title_read_vo(TITLE_A, [empty]) is True, "asserting title-only drop FAILS"
    assert _stamp_can_cover(empty) is False, "asserting title-only drop FAILS"

    title_pkt = _packet(_pack((empty.claim, HELIOS_HUB)), [empty])
    title_pkt.beats[5].vo = f"NARRATOR\n{TITLE_A}"
    title_pkt.beats[5].finding_ids = [empty.id]
    run_cite_recheck_loop(title_pkt, search_fn=_no_search)
    sanitize_for_ship(title_pkt)
    title_cited = [
        beat
        for beat in _voiced(title_pkt)
        if empty.id in beat.finding_ids and _speech_norm(beat.vo)
    ]
    assert title_cited == [], "asserting title-only drop FAILS"
    assert TITLE_A not in _spoken(title_pkt), "asserting title-only drop FAILS"

    headline_pkt = _packet(_pack((empty.claim, HELIOS_HUB)), [empty])
    headline_pkt.beats[5].vo = f"NARRATOR\n{HEADLINE}"
    headline_pkt.beats[5].finding_ids = [empty.id]
    run_cite_recheck_loop(headline_pkt, search_fn=_no_search)
    sanitize_for_ship(headline_pkt)
    assert HEADLINE not in _spoken(headline_pkt), "asserting title-only drop FAILS"

    hub = _rss_stamp()
    pct = _stamp_c()
    assert is_chrome_cover_stamp(hub) is True or _stamp_can_cover(hub) is False, (
        "asserting RSS drop FAILS"
    )
    assert _stamp_can_cover(hub) is False, "asserting RSS drop FAILS"
    rss_pkt = _packet(_pack((hub.claim, HELIOS_RSS), (pct.claim, HELIOS_C)), [hub, pct])
    rss_pkt.beats[5].vo = f"NARRATOR\n{RSS_TITLE}"
    rss_pkt.beats[5].finding_ids = [hub.id]
    run_cite_recheck_loop(rss_pkt, search_fn=_no_search)
    sanitize_for_ship(rss_pkt)
    assert RSS_ID not in _spoken(rss_pkt), "asserting RSS drop FAILS"
    assert RSS_TITLE not in _spoken(rss_pkt), "asserting RSS drop FAILS"
    assert not any(
        hub.id in beat.finding_ids and _speech_norm(beat.vo) for beat in _voiced(rss_pkt)
    ), "asserting RSS drop FAILS"
    assert getattr(rss_pkt, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
