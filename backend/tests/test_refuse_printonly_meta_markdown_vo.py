"""Refuse print-only VO, process/pack chrome, leftover markdown, short digit-hyphen ids.

Live HOLD shipped bare equals-prints, pipeline-meta VO, **markdown** speech,
and opaque ids like 11-2. Gates run on write_board → attach_frames → model_dump.
Fixtures use invented orgs/prints (Helios / Meridian Desk). Production code
and this file must stay free of live topic strings. Do not live POST.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, Rails, ScriptBeat, TimelineMapRow
from onecrew.receipt import attach_frames
from onecrew.script import sanitize_for_ship

HELIOS_A = "https://www.helios-wire.test/2026/06/helios-card-a-77"
HELIOS_B = "https://www.meridian-desk.test/2026/01/helios-card-b-56m"
TITLE_A = "Campus Occupancy Outlook Holds | Meridian Desk Hub"
TITLE_B = "Named Fee Card Outlook Holds | Meridian Desk Hub"
PRINT_A = "7.7%"
PRINT_B = "56 million"
TOPIC = "Named campus occupancy prints on the cited card"
EQUALS_PRINT = "=7.7%"
MARKDOWN_PRINT = "The cited card printed **56 million** in January 2026."
META_TITLE = "The title is a question we will not answer with a forecast"
META_NEAR = "Near is not a switch"
META_PACK = "When the pack changes, the board changes"
META_OBJECT = "Those are not the same object. Near is the gap."
SHORT_FID = "11-2"

_LIVE_TOPIC = (
    r"cold[- ]storage|\bvacancy\b|\bfertilizer\b|\bdap\b|\burea\b|anhydrous|\bmidwest\b|"
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
_FIXTURE = r"helios|meridian-desk|meridian desk|\b7\.7%|\b56 million\b"
_HOLD_TOKS = (
    "cite-faithfulness",
    "thin_after_repair",
    "empty beat",
    "insufficient_cite_beats",
    "opaque_finding_id",
)
_META_LEFTOVER = re.compile(
    r"the title is a question|will not answer with a forecast|"
    r"near is not a switch|near is the gap|"
    r"those are not the same object|"
    r"when the pack changes|the board changes",
    re.I,
)
_SHORT_DIGIT_HYPHEN = re.compile(r"^\d{1,3}(?:-\d{1,3})+$")
_MD_LEFTOVER = re.compile(r"\*\*|`|^#{1,6}\s+", re.M)


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


def _stamp_a(*, fid: str = "te-helios-card-a-77") -> Finding:
    return _finding(
        fid=fid,
        claim=TITLE_A,
        url=HELIOS_A,
        printed=PRINT_A,
        title=TITLE_A,
    )


def _stamp_b(*, fid: str = "te-helios-card-b-56m") -> Finding:
    return _finding(
        fid=fid,
        claim=TITLE_B,
        url=HELIOS_B,
        printed=PRINT_B,
        title=TITLE_B,
        when="January 2026",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-refuse-printonly-meta-markdown-vo",
        topic=TOPIC,
        hook=TOPIC,
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
    return " ".join(
        f"{b.vo} {b.frame or ''} {getattr(b, 'on_screen', '') or ''}" for b in _voiced(packet)
    )


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


def _live_board_receipt(packet: Packet) -> None:
    """Live shift path: cite-repair → room sanitize/disposition → write_board → attach_frames."""
    from onecrew.board import write_board
    from onecrew.room import RoomGrade, _sanitize_disposition

    run_cite_recheck_loop(packet, search_fn=_no_search)
    rails = Rails(parallel=False, vertex=False, imagen=False)
    _sanitize_disposition(packet, RoomGrade(vote="ship"), 1, ready=True)
    frames = write_board(packet, rails)
    attach_frames(packet, frames, rails=rails)


def _api_round_trip(packet: Packet) -> Packet:
    """Same serialize path as store.upsert_packet / GET /api/packets."""
    return Packet.model_validate(packet.model_dump())


def test_print_only_vo_rewrites_or_drops() -> None:
    """Bare / equals-print VO must become a full cite-faithful sentence or drop."""
    from onecrew.script import is_print_only_vo

    assert is_print_only_vo(EQUALS_PRINT) is True, "asserting print-only ship FAILS"
    assert is_print_only_vo(PRINT_A) is True, "asserting print-only ship FAILS"
    assert is_print_only_vo(f"The cited card printed {PRINT_A} in June 2026.") is False

    for raw in (EQUALS_PRINT, PRINT_A):
        stamp = _stamp_a()
        packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
        packet.beats[5].vo = f"NARRATOR\n{raw}"
        packet.beats[5].finding_ids = [stamp.id]
        _live_board_receipt(packet)
        loaded = _api_round_trip(packet)
        bodies = _vo_bodies(loaded)
        leftover = [b for b in bodies if is_print_only_vo(b)]
        assert leftover == [], "asserting print-only ship FAILS"
        spoken = _spoken(loaded)
        assert EQUALS_PRINT not in spoken, "asserting print-only ship FAILS"
        if _shipped_ready(loaded):
            assert re.search(r"7\.7\s*%", spoken), "asserting print-only ship FAILS"
            assert any(
                re.search(r"7\.7\s*%", b) and len(re.findall(r"[A-Za-z]+", b)) >= 3 for b in bodies
            ), "asserting print-only ship FAILS"
        else:
            assert any(tok in _reason(loaded).lower() for tok in _HOLD_TOKS), (
                "asserting print-only ship FAILS"
            )
        assert getattr(loaded, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_process_meta_chrome_vo_cannot_ship() -> None:
    """Title/forecast/pack/board/object-gap chrome must drop or rewrite to a covering print."""
    from onecrew.script import is_process_chrome_vo

    for chrome in (META_TITLE, META_NEAR, META_PACK, META_OBJECT):
        assert is_process_chrome_vo(chrome) is True, "asserting meta ship FAILS"

    stamp = _stamp_a()
    for chrome in (META_TITLE, META_NEAR, META_PACK, META_OBJECT):
        packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
        packet.beats[5].vo = f"NARRATOR\n{chrome}"
        packet.beats[5].finding_ids = [stamp.id]
        _live_board_receipt(packet)
        loaded = _api_round_trip(packet)
        spoken = _spoken(loaded)
        bodies = _vo_bodies(loaded)
        assert not _META_LEFTOVER.search(spoken), "asserting meta ship FAILS"
        assert not any(_META_LEFTOVER.search(b) for b in bodies), "asserting meta ship FAILS"
        assert not any(is_process_chrome_vo(b) for b in bodies), "asserting meta ship FAILS"
        if _shipped_ready(loaded):
            assert re.search(r"7\.7\s*%", spoken), "asserting meta ship FAILS"
        else:
            assert any(tok in _reason(loaded).lower() for tok in _HOLD_TOKS), (
                "asserting meta ship FAILS"
            )


def test_markdown_emphasis_stripped_from_vo() -> None:
    """Spoken VO cannot keep **bold**, heading #, or backticks."""
    from onecrew.script import leftover_spoken_markdown, strip_spoken_markdown

    stripped = strip_spoken_markdown(MARKDOWN_PRINT)
    assert "**" not in stripped, "asserting leftover markdown FAILS"
    assert leftover_spoken_markdown(stripped) is False
    assert leftover_spoken_markdown("The cited card printed **56 million**.") is True

    stamp = _stamp_b()
    packet = _packet(_pack((stamp.claim, HELIOS_B)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{MARKDOWN_PRINT}"
    packet.beats[5].finding_ids = [stamp.id]
    _live_board_receipt(packet)
    loaded = _api_round_trip(packet)
    spoken = _spoken(loaded)
    bodies = _vo_bodies(loaded)
    assert "**" not in spoken, "asserting leftover markdown FAILS"
    assert not any("**" in b or leftover_spoken_markdown(b) for b in bodies), (
        "asserting leftover markdown FAILS"
    )
    assert not _MD_LEFTOVER.search(spoken), "asserting leftover markdown FAILS"
    if _shipped_ready(loaded):
        assert re.search(r"56\s+million", spoken, re.I), "asserting leftover markdown FAILS"
    else:
        assert any(tok in _reason(loaded).lower() for tok in _HOLD_TOKS), (
            "asserting leftover markdown FAILS"
        )


def test_short_digit_hyphen_finding_id_remaps_or_drops() -> None:
    """Ids like 11-2 cannot ship. Remap to a te- slug from URL/title or drop."""
    from onecrew.script import is_short_digit_hyphen_finding_id

    assert is_short_digit_hyphen_finding_id(SHORT_FID) is True, (
        "asserting short digit-hyphen id ship FAILS"
    )
    assert is_short_digit_hyphen_finding_id("te-helios-card-a-77") is False

    stamp = _stamp_a(fid=SHORT_FID)
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nThe cited card printed {PRINT_A} in June 2026. [{SHORT_FID}]"
    packet.beats[5].finding_ids = [SHORT_FID]
    _live_board_receipt(packet)
    loaded = _api_round_trip(packet)
    leftover = [
        fid
        for beat in _voiced(loaded)
        for fid in beat.finding_ids
        if is_short_digit_hyphen_finding_id(fid) or _SHORT_DIGIT_HYPHEN.fullmatch(fid or "")
    ]
    finding_chrome = [
        f.id
        for f in (loaded.receipt.findings if loaded.receipt else [])
        if is_short_digit_hyphen_finding_id(f.id) or _SHORT_DIGIT_HYPHEN.fullmatch(f.id or "")
    ]
    assert leftover == [], "asserting short digit-hyphen id ship FAILS"
    assert finding_chrome == [], "asserting short digit-hyphen id ship FAILS"
    cited = [b for b in _voiced(loaded) if b.finding_ids and _speech_norm(b.vo)]
    if cited:
        assert all(
            not is_short_digit_hyphen_finding_id(fid) for b in cited for fid in b.finding_ids
        ), "asserting short digit-hyphen id ship FAILS"
        assert any(fid.startswith("te-") for b in cited for fid in b.finding_ids) or not cited
    spoken = _spoken(loaded)
    assert SHORT_FID not in spoken, "asserting short digit-hyphen id ship FAILS"
    payload = loaded.model_dump()
    dumped_ids = [
        fid for beat in payload.get("beats") or [] for fid in beat.get("finding_ids") or []
    ] + [f.get("id") or "" for f in ((payload.get("receipt") or {}).get("findings") or [])]
    assert not any(_SHORT_DIGIT_HYPHEN.fullmatch(fid) for fid in dumped_ids), (
        "asserting short digit-hyphen id ship FAILS"
    )
    if _shipped_ready(loaded):
        assert cited, "asserting short digit-hyphen id ship FAILS"
    else:
        assert any(tok in _reason(loaded).lower() for tok in _HOLD_TOKS), (
            "asserting short digit-hyphen id ship FAILS"
        )


def test_mute_on_screen_still_persists_with_numeric_prints() -> None:
    """Regression: covering number still lands on beat.on_screen after serialize."""
    stamp = _stamp_a()
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nThe cited card printed {PRINT_A} in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = ""
    for beat in packet.beats:
        if beat is not packet.beats[5]:
            beat.frame = ""
    _live_board_receipt(packet)
    loaded = _api_round_trip(packet)
    cited = [b for b in _voiced(loaded) if b.finding_ids and _speech_norm(b.vo)]
    numeric = [b for b in cited if re.search(r"7\.7\s*%", f"{b.vo} {b.frame or ''}")]
    assert numeric, "asserting empty on_screen with numeric VO FAILS"
    for beat in numeric:
        shown = (getattr(beat, "on_screen", None) or "").strip()
        assert shown, "asserting empty on_screen with numeric VO FAILS"
        assert shown == PRINT_A, "asserting empty on_screen with numeric VO FAILS"
    payload = loaded.model_dump()
    hit = [
        row
        for row in payload.get("beats") or []
        if row.get("finding_ids") and re.search(r"7\.7\s*%", row.get("vo") or "")
    ]
    assert hit, "asserting empty on_screen with numeric VO FAILS"
    assert all((row.get("on_screen") or "").strip() == PRINT_A for row in hit), (
        "asserting empty on_screen with numeric VO FAILS"
    )
    if _shipped_ready(loaded):
        assert any((getattr(b, "on_screen", None) or "") == PRINT_A for b in numeric)
    else:
        assert any(tok in _reason(loaded).lower() for tok in _HOLD_TOKS), (
            "asserting empty on_screen with numeric VO FAILS"
        )
    assert getattr(loaded, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
