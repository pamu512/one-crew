"""Over-cite dedupe/cap, markdown headline VO, topic-restatement, mute print, RSS hub, dupe VO.

#66 closed title on_screen fallback and unique beat1…beatN. Live HOLD over-cite
still shipped a duplicated finding_id list, markdown/URL headline VO, topic
restatement chrome, all-empty on_screen, RSS hub cites, and identical VO.
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
from onecrew.timeline import MAX_CITES_PER_BEAT

HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-12"
HELIOS_FEE = "https://www.helios-wire.test/2026/01/helios-fee-0"
HELIOS_RSS = "https://www.helios-wire.test/subscribe/rss"
STAMP_TITLE = "Campus Occupancy Outlook Holds | Meridian Desk Hub"
PCT_PRINT = "12%"
FEE_PRINT = "$0/t"
TOPIC = "Have named campus occupancy prints stayed on the cited card?"
MARKDOWN_HEADLINE = (
    "# Some Analysts Are Warning Of A Tight Printed Window "
    "(http://www.helios-wire.test/2026/06/outlook)"
)
DATE_ONLY = "Then, on August 17th"
RSS_ID = "te-helios-subscribe-rss-feed"
RSS_TITLE = "Subscribe to RSS feed"

_LIVE_TOPIC = (
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
_FIXTURE = r"helios|meridian-desk|meridian desk|\b12%\b|\$0/t"
_HOLD_TOKS = (
    "cite-faithfulness",
    "thin_after_repair",
    "empty beat",
    "insufficient_cite_beats",
    "over-cite",
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
        id="oc-overcite-markdown-mute",
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


def test_repeated_finding_id_is_deduped_and_capped() -> None:
    """Same finding_id × many on one beat must ship unique and ≤ cap. Raw multi-dupe cannot."""
    from onecrew.cite_repair import _board_gate_reason

    stamp = _pct_stamp()
    dupes = [stamp.id] * 32
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = (
        "NARRATOR\nHelios occupancy printed 12% in June 2026. "
        + " ".join(f"[{stamp.id}]" for _ in range(32))
    )
    packet.beats[5].finding_ids = list(dupes)
    assert len(packet.beats[5].finding_ids) > MAX_CITES_PER_BEAT
    assert len(packet.beats[5].finding_ids) != len(set(packet.beats[5].finding_ids))

    sanitize_for_ship(packet)
    cited = [b for b in _voiced(packet) if stamp.id in b.finding_ids]
    for beat in cited:
        ids = list(beat.finding_ids)
        assert ids == list(dict.fromkeys(ids)), "asserting raw multi-dupe ship FAILS"
        assert len(ids) <= MAX_CITES_PER_BEAT, "asserting raw multi-dupe ship FAILS"
        assert ids.count(stamp.id) <= 1, "asserting raw multi-dupe ship FAILS"
        assert (beat.vo or "").count(f"[{stamp.id}]") <= 1, "asserting raw multi-dupe ship FAILS"
    if cited:
        gate = _board_gate_reason(packet)
        assert gate != "over-cite", "asserting raw multi-dupe ship FAILS"
    if _shipped_ready(packet):
        assert _reason(packet).lower().find("over-cite") < 0, "asserting raw multi-dupe ship FAILS"
        assert cited, "asserting raw multi-dupe ship FAILS"


def test_markdown_url_headline_vo_cannot_ship() -> None:
    """VO that is `# Title Case… (http…)` must drop/rewrite. Markdown headline cannot ship."""
    from onecrew.script import is_thin_title_read_vo, is_title_read_vo

    empty = _finding(
        fid="te-helios-hub-2026-06",
        claim=STAMP_TITLE,
        url="https://www.helios-wire.test/hub/campus-occupancy",
        printed="",
        title=STAMP_TITLE,
        note="Title-only hub row. Parallel URL on this row.",
    )
    assert is_title_read_vo(MARKDOWN_HEADLINE, [empty]) is True, "asserting markdown headline VO ship FAILS"
    assert is_thin_title_read_vo(MARKDOWN_HEADLINE, [empty]) is True, (
        "asserting markdown headline VO ship FAILS"
    )

    packet = _packet(_pack((empty.claim, empty.parallel_url or "")), [empty])
    packet.beats[5].vo = f"NARRATOR\n{MARKDOWN_HEADLINE}"
    packet.beats[5].finding_ids = [empty.id]
    _run_sanitize_repair(packet)
    spoken = _spoken(packet)
    bodies = _vo_bodies(packet)
    assert MARKDOWN_HEADLINE not in spoken, "asserting markdown headline VO ship FAILS"
    assert "#" not in spoken, "asserting markdown headline VO ship FAILS"
    assert not re.search(r"https?://", spoken), "asserting markdown headline VO ship FAILS"
    assert not any(_speech_norm(MARKDOWN_HEADLINE) == _speech_norm(b) for b in bodies), (
        "asserting markdown headline VO ship FAILS"
    )
    assert not any(b.lstrip().startswith("#") for b in bodies), (
        "asserting markdown headline VO ship FAILS"
    )
    if _shipped_ready(packet):
        assert "Some Analysts Are Warning" not in spoken, (
            "asserting markdown headline VO ship FAILS"
        )
    else:
        assert any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), (
            "asserting markdown headline VO ship FAILS"
        )
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_topic_restatement_chrome_cannot_ship() -> None:
    """The question was whether / This cut asks / ACTION topic paste cannot ship."""
    from onecrew.script import is_topic_question_vo, is_unverified_meta_vo

    stamp = _pct_stamp()
    whether = f"The question was whether {TOPIC}"
    asks = f"This cut asks {TOPIC}"
    action = f"ACTION: {TOPIC}"
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    assert is_topic_question_vo(whether, packet) is True, "asserting topic-restatement ship FAILS"
    assert is_topic_question_vo(asks, packet) is True, "asserting topic-restatement ship FAILS"
    assert is_unverified_meta_vo(whether) is True or is_topic_question_vo(whether, packet)

    for vo in (whether, asks, action):
        pkt = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
        pkt.beats[5].vo = f"NARRATOR\n{vo}" if not vo.startswith("ACTION:") else vo
        pkt.beats[5].finding_ids = [stamp.id]
        if vo.startswith("ACTION:"):
            pkt.beats[5].frame = TOPIC
        _run_sanitize_repair(pkt)
        spoken = _spoken(pkt)
        bodies = _vo_bodies(pkt)
        blob = f"{spoken} {pkt.script or ''}"
        assert "the question was whether" not in blob.lower(), (
            "asserting topic-restatement ship FAILS"
        )
        assert "this cut asks" not in blob.lower(), "asserting topic-restatement ship FAILS"
        assert _speech_norm(TOPIC) not in _speech_norm(spoken), (
            "asserting topic-restatement ship FAILS"
        )
        assert not any(_speech_norm(TOPIC) == _speech_norm(b) for b in bodies), (
            "asserting topic-restatement ship FAILS"
        )
        assert not any(TOPIC in (b.frame or "") for b in _voiced(pkt)), (
            "asserting topic-restatement ship FAILS"
        )
        if _shipped_ready(pkt):
            assert not re.search(r"\b(?:have|did)\b.+\?", spoken, re.I), (
                "asserting topic-restatement ship FAILS"
            )
        else:
            assert any(tok in _reason(pkt).lower() for tok in _HOLD_TOKS), (
                "asserting topic-restatement ship FAILS"
            )


def test_empty_on_screen_fills_print_or_drops_beat() -> None:
    """Covering stamp with a numeric print cannot ship a full cut of empty on_screen."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list

    stamp = _pct_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 12% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    for beat in packet.beats:
        beat.frame = ""
    sanitize_for_ship(packet)
    cited = [b for b in _voiced(packet) if stamp.id in b.finding_ids and _speech_norm(b.vo)]
    if cited:
        assert any(PCT_PRINT in (b.frame or "") for b in cited), (
            "asserting all-empty ship FAILS"
        )
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = packet.frames or write_shot_list(packet)
    screens = [(s.on_screen or "").strip() for s in shots]
    if cited and _shipped_ready(packet):
        assert any(PCT_PRINT in (s or "") for s in screens), "asserting all-empty ship FAILS"
        assert not all(not (s or "").strip() for s in screens), "asserting all-empty ship FAILS"
        hit = next(s for s in shots if PCT_PRINT in (s.on_screen or ""))
        beat = next(b for b in cited if b.id == hit.beat_id)
        assert mute_test_shows_stamp(hit, [stamp], beat) is True
    else:
        assert cited == [] or any(tok in _reason(packet).lower() for tok in _HOLD_TOKS), (
            "asserting all-empty ship FAILS"
        )


def test_rss_hub_stamp_is_not_a_covering_cite() -> None:
    """Subscribe / RSS feed hub ids and titles are not covering stamps."""
    from onecrew.script import _stamp_can_cover
    from onecrew.timeline import is_chrome_cover_stamp

    hub = _rss_stamp()
    pct = _pct_stamp()
    assert is_chrome_cover_stamp(hub) is True or _stamp_can_cover(hub) is False, (
        "asserting RSS-cite ship FAILS"
    )
    assert _stamp_can_cover(hub) is False, "asserting RSS-cite ship FAILS"

    packet = _packet(
        _pack((hub.claim, HELIOS_RSS), (pct.claim, HELIOS_PRINT)),
        [hub, pct],
    )
    packet.beats[5].vo = f"NARRATOR\n{RSS_TITLE}"
    packet.beats[5].finding_ids = [hub.id]
    _run_sanitize_repair(packet)
    spoken = _spoken(packet)
    cited_hub = [b for b in _voiced(packet) if hub.id in b.finding_ids and _speech_norm(b.vo)]
    assert cited_hub == [], "asserting RSS-cite ship FAILS"
    assert RSS_ID not in spoken, "asserting RSS-cite ship FAILS"
    assert RSS_TITLE not in spoken, "asserting RSS-cite ship FAILS"
    if _shipped_ready(packet):
        assert not any(hub.id in b.finding_ids for b in _voiced(packet) if _speech_norm(b.vo)), (
            "asserting RSS-cite ship FAILS"
        )


def test_identical_vo_and_date_only_clause_cannot_ship() -> None:
    """Date-only hanging VO drops. Identical VO across beats keeps one."""
    from onecrew.script import is_incomplete_vo

    stamp = _pct_stamp()
    fee = _fee_stamp()
    assert is_incomplete_vo(DATE_ONLY) is True, "asserting hanging date ship FAILS"

    hung = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    hung.beats[5].vo = f"NARRATOR\n{DATE_ONLY}"
    hung.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(hung)
    bodies = _vo_bodies(hung)
    spoken = _spoken(hung)
    assert DATE_ONLY not in spoken, "asserting hanging date ship FAILS"
    assert not any(_speech_norm(DATE_ONLY) == _speech_norm(b) for b in bodies), (
        "asserting hanging date ship FAILS"
    )
    if _shipped_ready(hung):
        assert re.search(r"12\s*%|helios occupancy printed", spoken, re.I), (
            "asserting hanging date ship FAILS"
        )
    else:
        assert any(tok in _reason(hung).lower() for tok in _HOLD_TOKS), (
            "asserting hanging date ship FAILS"
        )

    same = "Helios occupancy printed 12% in June 2026."
    packet = _packet(
        _pack((stamp.claim, HELIOS_PRINT), (fee.claim, HELIOS_FEE)),
        [stamp, fee],
    )
    packet.beats[2].vo = f"NARRATOR\n{same} [{stamp.id}]"
    packet.beats[2].finding_ids = [stamp.id]
    packet.beats[5].vo = f"NARRATOR\n{same} [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    sanitize_for_ship(packet)
    norms = [_speech_norm(b.vo) for b in _voiced(packet) if _speech_norm(b.vo)]
    assert norms.count(_speech_norm(same)) <= 1, "asserting duplicate VO ship FAILS"
    if _shipped_ready(packet):
        assert norms.count(_speech_norm(same)) == 1, "asserting duplicate VO ship FAILS"


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
