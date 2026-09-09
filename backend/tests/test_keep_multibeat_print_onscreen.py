"""Keep ≥3 print beats after repair; fill on_screen from spoken covering prints.

Sanitizers were dropping title-adjacent VO even when stamps had usable
numeric prints, collapsing one_time_short_episode to 1 beat (or HOLD
thin_after_repair) and leaving empty on_screen on numeric VO. Rewrite VO
to the covering print before drop. Fixtures use invented orgs/prints
(Helios / Meridian Desk). Production code and this file must stay free of
live topic strings. No second Parallel/Vertex mint theater. Do not live POST.
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
RSS_ID = "te-helios-subscribe-rss-feed"
RSS_TITLE = "Subscribe to RSS feed"

_LIVE_TOPIC = (
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
    # Title-shaped claim == title so speak_stamp_fact used to return a bare print
    # token, which drop_thin then rejected. Rewrite-before-drop must keep the beat.
    return _finding(fid=fid, claim=title, url=url, printed=printed, title=title, when=when)


def _stamp_a() -> Finding:
    return _print_stamp(
        fid="te-helios-card-a-151",
        claim=TITLE_A,
        url=HELIOS_A,
        printed=PRINT_A,
        title=TITLE_A,
    )


def _stamp_b() -> Finding:
    return _print_stamp(
        fid="te-helios-card-b-376",
        claim=TITLE_B,
        url=HELIOS_B,
        printed=PRINT_B,
        title=TITLE_B,
        when="January 2026",
    )


def _stamp_c() -> Finding:
    return _print_stamp(
        fid="te-helios-card-c-12",
        claim=TITLE_C,
        url=HELIOS_C,
        printed=PRINT_C,
        title=TITLE_C,
    )


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
        id="oc-keep-multibeat-print-onscreen",
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


def test_three_print_stamps_do_not_collapse_to_one_beat() -> None:
    """Pack with ≥3 numeric-print stamps + title-like VO must keep ≥3 print beats."""
    from onecrew.script import is_thin_title_read_vo, is_title_read_vo

    packet, a, b, c = _three_print_pack()
    assert is_title_read_vo(TITLE_A, [a]) is True, "asserting 1-beat ship FAILS"
    assert is_thin_title_read_vo(TITLE_A, [a]) is True, "asserting 1-beat ship FAILS"
    assert is_title_read_vo(TITLE_B, [b]) is True, "asserting 1-beat ship FAILS"
    assert is_title_read_vo(TITLE_C, [c]) is True, "asserting 1-beat ship FAILS"

    _run_sanitize_repair(packet)
    spoken = _spoken(packet)
    faithful = _cite_faithful_count(packet)
    assert faithful >= 3, "asserting 1-beat ship FAILS"
    assert faithful != 1, "asserting 1-beat ship FAILS"
    assert re.search(r"\$1\.51|1\.51", spoken), "asserting 1-beat ship FAILS"
    assert re.search(r"\$3\.76|3\.76", spoken), "asserting 1-beat ship FAILS"
    assert re.search(r"12\s*%", spoken), "asserting 1-beat ship FAILS"
    if _shipped_ready(packet):
        assert faithful >= 3, "asserting 1-beat ship FAILS"
        assert "thin_after_repair" not in _reason(packet).lower()
    else:
        reason = _reason(packet).lower()
        assert "thin_after_repair" not in reason, "asserting 1-beat ship FAILS"
        assert "insufficient_cite_beats" not in reason, "asserting 1-beat ship FAILS"
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    from onecrew.board import write_shot_list

    shots = packet.frames or write_shot_list(packet)
    cited = [beat for beat in _voiced(packet) if beat.finding_ids and _speech_norm(beat.vo)]
    assert len(cited) >= 3, "asserting 1-beat ship FAILS"
    for beat in cited:
        shot = next((s for s in shots if s.beat_id == beat.id), None)
        if not re.search(r"\$1\.51|\$3\.76|1\.51|3\.76|12\s*%", beat.vo):
            continue
        assert shot is not None and (shot.on_screen or "").strip(), (
            "asserting empty on_screen with numeric VO FAILS"
        )
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_numeric_vo_fills_on_screen_from_covering_print() -> None:
    """Spoken covering number must appear on on_screen. Empty mute frame FAILS."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list

    stamp = _stamp_a()
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nThe cited card printed $1.51 in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = ""
    for beat in packet.beats:
        if beat is not packet.beats[5]:
            beat.frame = ""
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    cited = [b for b in _voiced(packet) if stamp.id in b.finding_ids and _speech_norm(b.vo)]
    assert cited, "asserting empty on_screen with numeric VO FAILS"
    assert any(re.search(r"\$1\.51|1\.51", b.vo) for b in cited), (
        "asserting empty on_screen with numeric VO FAILS"
    )
    shots = packet.frames or write_shot_list(packet)
    screens = [(s.on_screen or "").strip() for s in shots]
    numeric_cited = [
        b
        for b in cited
        if re.search(r"\$1\.51|1\.51", f"{b.vo} {b.frame or ''}")
    ]
    assert numeric_cited, "asserting empty on_screen with numeric VO FAILS"
    hit_shots = [s for s in shots if s.beat_id in {b.id for b in numeric_cited}]
    assert hit_shots, "asserting empty on_screen with numeric VO FAILS"
    assert all((s.on_screen or "").strip() for s in hit_shots), (
        "asserting empty on_screen with numeric VO FAILS"
    )
    assert any(PRINT_A in (s.on_screen or "") for s in hit_shots), (
        "asserting empty on_screen with numeric VO FAILS"
    )
    for shot in hit_shots:
        assert (shot.on_screen or "").strip() == PRINT_A, (
            "asserting empty on_screen with numeric VO FAILS"
        )
        beat = next(b for b in numeric_cited if b.id == shot.beat_id)
        assert mute_test_shows_stamp(shot, [stamp], beat) is True
    if _shipped_ready(packet):
        assert not all(not (s or "").strip() for s in screens), (
            "asserting empty on_screen with numeric VO FAILS"
        )

    worded = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    worded.beats[5].vo = f"NARRATOR\nThe cited card printed 1.51 dollars in June 2026. [{stamp.id}]"
    worded.beats[5].finding_ids = [stamp.id]
    worded.beats[5].frame = ""
    sanitize_for_ship(worded)
    attach_frames(worded, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    worded_cited = [b for b in _voiced(worded) if stamp.id in b.finding_ids and _speech_norm(b.vo)]
    worded_shots = worded.frames or write_shot_list(worded)
    assert worded_cited, "asserting empty on_screen with numeric VO FAILS"
    worded_hit = [s for s in worded_shots if s.beat_id in {b.id for b in worded_cited}]
    assert any(PRINT_A in (s.on_screen or "") for s in worded_hit), (
        "asserting empty on_screen with numeric VO FAILS"
    )
    assert all((s.on_screen or "").strip() for s in worded_hit), (
        "asserting empty on_screen with numeric VO FAILS"
    )


def test_title_like_vo_rewrites_to_print_instead_of_mass_drop() -> None:
    """Title-like VO + usable stamp print rewrites to the print. Mass-drop FAILS."""
    from onecrew.script import is_title_read_vo

    packet, a, b, c = _three_print_pack()
    assert is_title_read_vo(TITLE_A, [a]) is True, "asserting mass-drop when prints exist FAILS"
    _run_sanitize_repair(packet)
    spoken = _spoken(packet)
    bodies = _vo_bodies(packet)
    faithful = _cite_faithful_count(packet)
    assert faithful >= 3, "asserting mass-drop when prints exist FAILS"
    assert TITLE_A not in spoken or PRINT_A in spoken, "asserting mass-drop when prints exist FAILS"
    assert not any(_speech_norm(TITLE_A) == _speech_norm(body) for body in bodies), (
        "asserting mass-drop when prints exist FAILS"
    )
    assert re.search(r"\$1\.51|1\.51", spoken), "asserting mass-drop when prints exist FAILS"
    assert re.search(r"\$3\.76|3\.76", spoken), "asserting mass-drop when prints exist FAILS"
    assert re.search(r"12\s*%", spoken), "asserting mass-drop when prints exist FAILS"
    reason = _reason(packet).lower()
    assert "thin_after_repair" not in reason, "asserting mass-drop when prints exist FAILS"
    assert "insufficient_cite_beats" not in reason, "asserting mass-drop when prints exist FAILS"
    kept_a = [beat for beat in _voiced(packet) if a.id in beat.finding_ids and _speech_norm(beat.vo)]
    assert kept_a, "asserting mass-drop when prints exist FAILS"
    assert any(re.search(r"\$1\.51|1\.51", beat.vo) for beat in kept_a), (
        "asserting mass-drop when prints exist FAILS"
    )


def test_title_only_no_print_and_rss_still_drop() -> None:
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
    _run_sanitize_repair(title_pkt)
    title_cited = [
        beat
        for beat in _voiced(title_pkt)
        if empty.id in beat.finding_ids and _speech_norm(beat.vo)
    ]
    assert title_cited == [], "asserting title-only drop FAILS"
    assert TITLE_A not in _spoken(title_pkt), "asserting title-only drop FAILS"
    if _shipped_ready(title_pkt):
        assert not any(_speech_norm(TITLE_A) == _speech_norm(body) for body in _vo_bodies(title_pkt))
    else:
        assert any(tok in _reason(title_pkt).lower() for tok in _HOLD_TOKS)

    headline_pkt = _packet(_pack((empty.claim, HELIOS_HUB)), [empty])
    headline_pkt.beats[5].vo = f"NARRATOR\n{HEADLINE}"
    headline_pkt.beats[5].finding_ids = [empty.id]
    _run_sanitize_repair(headline_pkt)
    assert HEADLINE not in _spoken(headline_pkt), "asserting title-only drop FAILS"
    assert not any(
        empty.id in beat.finding_ids and _speech_norm(beat.vo) for beat in _voiced(headline_pkt)
    ), "asserting title-only drop FAILS"

    hub = _rss_stamp()
    pct = _stamp_c()
    assert is_chrome_cover_stamp(hub) is True or _stamp_can_cover(hub) is False, (
        "asserting RSS drop FAILS"
    )
    assert _stamp_can_cover(hub) is False, "asserting RSS drop FAILS"
    rss_pkt = _packet(_pack((hub.claim, HELIOS_RSS), (pct.claim, HELIOS_C)), [hub, pct])
    rss_pkt.beats[5].vo = f"NARRATOR\n{RSS_TITLE}"
    rss_pkt.beats[5].finding_ids = [hub.id]
    _run_sanitize_repair(rss_pkt)
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
