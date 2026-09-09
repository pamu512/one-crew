"""Refuse title-read VO, meta-question chrome, headline on_screen; neutralize narrative ids.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2%).
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

HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
STAMP_TITLE = "Helios Occupancy Print – June 2026 – Analysis - U.S"
SERIES_PAGE = "Helios Occupancy Print - Historical Data & Trends"
SERIES_SOURCE = "Helios Occupancy Series - Desk Source"
TRUNCATED_AND = "Helios occupancy and"
ARTICLE_HEADLINE = "Desk Wire: Campus Occupancy Outlook Holds"
TOPIC = "Did named campus occupancy stall after the printed pause?"
META_MINDS = (
    "The question on many minds is whether named campus occupancy "
    "stalled after the printed pause."
)
META_COMMON = "A common question is whether occupancy stalled."
NARRATIVE_ID = "precursor_explanation"

_LIVE_TOPIC = (
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
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b"
_META_QUESTION = (
    r"the question on (?:many|most) minds|"
    r"(?:a |the )?common question"
)
_BEAT_N = re.compile(r"^beat\d+$")


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


def _helios_print_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 14.2% in June 2026.",
        url=HELIOS_PRINT,
        printed="14.2%",
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
        id="oc-title-read-meta-numeric-onscreen",
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

    return [re.sub(r"\[[^\]]+\]", "", _vo_lines(b.vo)).strip() for b in _voiced(packet) if _vo_lines(b.vo).strip()]


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").strip()


def _shipped_ready(packet: Packet) -> bool:
    return bool(packet.receipt and packet.receipt.disposition == "READY")


def _run_sanitize_repair(packet: Packet) -> None:
    run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)


def test_title_read_series_page_vo_cannot_ship() -> None:
    """Page/chart/series title VO must drop or expand with the stamp print."""
    from onecrew.script import is_thin_title_read_vo, is_title_read_vo

    stamp = _helios_print_stamp()
    assert is_title_read_vo(SERIES_PAGE, [stamp]) is True, "asserting title-read ship FAILS"
    assert is_thin_title_read_vo(SERIES_PAGE, [stamp]) is True, "asserting title-read ship FAILS"
    assert is_title_read_vo(SERIES_SOURCE, [stamp]) is True, "asserting title-read ship FAILS"
    from onecrew.script import is_incomplete_vo

    assert is_incomplete_vo(TRUNCATED_AND) is True, "asserting title-read ship FAILS"
    assert is_title_read_vo(stamp.claim, [stamp]) is False

    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{SERIES_PAGE}"
    packet.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(packet)
    bodies = _vo_bodies(packet)
    spoken = _spoken(packet)
    assert SERIES_PAGE not in spoken, "asserting title-read ship FAILS"
    assert SERIES_PAGE not in bodies, "asserting title-read ship FAILS"
    assert not any(_speech_norm(SERIES_PAGE) == _speech_norm(b) for b in bodies), (
        "asserting title-read ship FAILS"
    )
    if _shipped_ready(packet):
        assert re.search(r"14\.2|helios occupancy printed", spoken, re.I), (
            "asserting title-read ship FAILS"
        )
    else:
        assert any(
            tok in _reason(packet).lower()
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat")
        ), "asserting title-read ship FAILS"
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS

    src = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    src.beats[5].vo = f"NARRATOR\n{SERIES_SOURCE}"
    src.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(src)
    assert SERIES_SOURCE not in _spoken(src), "asserting title-read ship FAILS"
    if _shipped_ready(src):
        assert re.search(r"14\.2|helios occupancy printed", _spoken(src), re.I)

    hung = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    hung.beats[5].vo = f"NARRATOR\n{TRUNCATED_AND}"
    hung.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(hung)
    hung_bodies = _vo_bodies(hung)
    assert not any(re.search(r"\band\s*$", b, re.I) for b in hung_bodies), (
        "asserting title-read ship FAILS"
    )
    assert TRUNCATED_AND not in _spoken(hung), "asserting title-read ship FAILS"


def test_meta_question_chrome_cannot_ship() -> None:
    """Narrator question chrome restating the topic must strip/drop without a print."""
    from onecrew.script import is_unverified_meta_vo

    stamp = _helios_print_stamp()
    assert is_unverified_meta_vo(META_MINDS) is True, "asserting ship FAILS"
    assert is_unverified_meta_vo(META_COMMON) is True, "asserting ship FAILS"

    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{META_MINDS}"
    packet.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(packet)
    spoken = _spoken(packet)
    assert not re.search(_META_QUESTION, spoken, re.I), "asserting ship FAILS"
    if _shipped_ready(packet):
        assert re.search(r"14\.2|helios occupancy printed", spoken, re.I), "asserting ship FAILS"
    else:
        assert any(
            tok in _reason(packet).lower()
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat")
        ), "asserting ship FAILS"

    common = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    common.beats[5].vo = f"NARRATOR\n{META_COMMON}"
    common.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(common)
    assert not re.search(_META_QUESTION, _spoken(common), re.I), "asserting ship FAILS"

    restated = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    restated.beats[5].vo = f"NARRATOR\n{TOPIC}"
    restated.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(restated)
    restated_bodies = _vo_bodies(restated)
    assert not any(_speech_norm(TOPIC) == _speech_norm(b) for b in restated_bodies), (
        "asserting ship FAILS"
    )
    if _shipped_ready(restated):
        assert re.search(r"14\.2|helios occupancy printed", _spoken(restated), re.I), (
            "asserting ship FAILS"
        )


def test_on_screen_uses_numeric_print_not_article_headline() -> None:
    """Mute-test on_screen is the attached print, not an article/series headline."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list
    from onecrew.script import is_title_chrome_frame

    stamp = _helios_print_stamp()
    assert is_title_chrome_frame(ARTICLE_HEADLINE, [stamp.id], [stamp]) is True, (
        "asserting headline on_screen FAILS"
    )
    assert is_title_chrome_frame(SERIES_PAGE, [stamp.id], [stamp]) is True, (
        "asserting headline on_screen FAILS"
    )

    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = ARTICLE_HEADLINE
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = packet.frames or write_shot_list(packet)
    cited = next(b for b in _voiced(packet) if stamp.id in b.finding_ids)
    first = next(f for f in shots if f.beat_id == cited.id)
    shown = first.on_screen or ""
    assert _speech_norm(ARTICLE_HEADLINE) not in _speech_norm(shown), (
        "asserting headline on_screen FAILS"
    )
    assert _speech_norm(STAMP_TITLE) not in _speech_norm(shown), (
        "asserting headline on_screen FAILS"
    )
    assert "14.2%" in shown, "asserting headline on_screen FAILS"
    assert mute_test_shows_stamp(first, [stamp], cited) is True

    series_pkt = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    series_pkt.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    series_pkt.beats[5].finding_ids = [stamp.id]
    series_pkt.beats[5].frame = SERIES_SOURCE
    sanitize_for_ship(series_pkt)
    attach_frames(series_pkt, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    series_shots = series_pkt.frames or write_shot_list(series_pkt)
    series_cited = next(b for b in _voiced(series_pkt) if stamp.id in b.finding_ids)
    series_first = next(f for f in series_shots if f.beat_id == series_cited.id)
    assert _speech_norm(SERIES_SOURCE) not in _speech_norm(series_first.on_screen), (
        "asserting headline on_screen FAILS"
    )
    assert "14.2%" in series_first.on_screen, "asserting headline on_screen FAILS"


def test_narrative_beat_ids_rewritten_to_beatn() -> None:
    """Leftover narrative labels cannot ship. Room grades packet beat ids."""
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].id = NARRATIVE_ID
    packet.beats[5].scene = f"BEAT 6 — {NARRATIVE_ID}"
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[2].id = "follow_up_context"
    packet.beats[2].scene = "BEAT 3 — follow_up_context"
    sanitize_for_ship(packet)
    ids = [b.id for b in _voiced(packet)]
    assert ids, "asserting leftover narrative id ship FAILS"
    assert NARRATIVE_ID not in ids, "asserting leftover narrative id ship FAILS"
    assert "follow_up_context" not in ids, "asserting leftover narrative id ship FAILS"
    assert all(_BEAT_N.fullmatch(bid) for bid in ids), "asserting leftover narrative id ship FAILS"
    assert [b.scene for b in _voiced(packet)] == [f"BEAT {i}" for i in range(1, len(ids) + 1)]


def _speech_norm(text: str) -> str:
    from onecrew.script import _speech_norm as norm

    return norm(text)


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
