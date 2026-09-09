"""Mute print must survive board/receipt serialize; pack-slot ids/VO cannot ship.

#69 filled ShotFrame.on_screen in-memory; live packet JSON still shipped empty
beat.on_screen. Pack-slot finding_ids and [[n]] chrome still held after a
successful strip. Gates run on write_board → attach_frames → model_dump.
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

HELIOS_A = "https://www.helios-wire.test/2026/06/helios-card-a-418"
HELIOS_B = "https://www.meridian-desk.test/2026/01/helios-card-b-703"
TITLE_A = "Campus Occupancy Outlook Holds | Meridian Desk Hub"
PRINT_A = "$4.18"
PRINT_B = "$7.03"
TOPIC = "Named campus occupancy prints on the cited card"

_STRIP_ONLY = "pack slot token stripped from VO"
_SLOT_FID = (
    "subsequent_events_chronologically[4]",
    "first_trigger_identified[0]",
    "claim_id_EX007",
)
_SLOT_FID_RE = re.compile(
    r"subsequent_events_chronologically\[\d+\]|first_trigger_identified\[\d+\]|"
    r"claim_id_EX\d+",
    re.I,
)
_SLOT_VO = re.compile(
    r"\[\[\d+\]\]|subsequent_events_chronologically|first_trigger_identified|"
    r"claim_id_EX\d+|chronological_events|executive_summary|excerpts\[\d+\]",
    re.I,
)
_LIVE_TOPIC = (
    r"\bfertilizer\b|\bdap\b|\burea\b|anhydrous|\bmidwest\b|"
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
_FIXTURE = r"helios|meridian-desk|meridian desk|\$4\.18|\$7\.03"
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


def _stamp_a(*, fid: str = "te-helios-card-a-418") -> Finding:
    return _finding(
        fid=fid,
        claim=TITLE_A,
        url=HELIOS_A,
        printed=PRINT_A,
        title=TITLE_A,
    )


def _stamp_b(*, fid: str = "te-helios-card-b-703") -> Finding:
    return _finding(
        fid=fid,
        claim="Named Fee Card Outlook Holds | Meridian Desk Hub",
        url=HELIOS_B,
        printed=PRINT_B,
        title="Named Fee Card Outlook Holds | Meridian Desk Hub",
        when="January 2026",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-mute-persist-packslot-strip",
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
    return " ".join(f"{b.vo} {b.frame or ''} {getattr(b, 'on_screen', '') or ''}" for b in _voiced(packet))


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").strip()


def _shipped_ready(packet: Packet) -> bool:
    return bool(packet.receipt and packet.receipt.disposition == "READY")


def _hold_clauses(reason: str) -> list[str]:
    return [part.strip() for part in (reason or "").replace("\n", ";").split(";") if part.strip()]


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


def test_numeric_vo_on_screen_survives_board_receipt_roundtrip() -> None:
    """Spoken covering number must land on packet beat.on_screen after serialize."""
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
    numeric = [b for b in cited if re.search(r"\$4\.18|4\.18", f"{b.vo} {b.frame or ''}")]
    assert numeric, "asserting empty on_screen with numeric VO FAILS"
    for beat in numeric:
        shown = (getattr(beat, "on_screen", None) or "").strip()
        assert shown, "asserting empty on_screen with numeric VO FAILS"
        assert shown == PRINT_A, "asserting empty on_screen with numeric VO FAILS"
    payload = loaded.model_dump()
    hit = [
        row
        for row in payload.get("beats") or []
        if row.get("finding_ids") and re.search(r"\$4\.18|4\.18", row.get("vo") or "")
    ]
    assert hit, "asserting empty on_screen with numeric VO FAILS"
    assert all((row.get("on_screen") or "").strip() == PRINT_A for row in hit), (
        "asserting empty on_screen with numeric VO FAILS"
    )
    frames = payload.get("frames") or []
    frame_hit = [
        row
        for row in frames
        if row.get("beat_id") in {b.id for b in numeric}
    ]
    if frame_hit:
        assert all((row.get("on_screen") or "").strip() == PRINT_A for row in frame_hit), (
            "asserting empty on_screen with numeric VO FAILS"
        )
    if _shipped_ready(loaded):
        assert any((getattr(b, "on_screen", None) or "") == PRINT_A for b in numeric)
    else:
        assert any(tok in _reason(loaded).lower() for tok in _HOLD_TOKS), (
            "asserting empty on_screen with numeric VO FAILS"
        )
    assert getattr(loaded, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_pack_slot_finding_ids_remap_or_drop() -> None:
    """Schema/index/claim_id_EX* finding_ids cannot ship. Remap to te- slug or drop."""
    for chrome in _SLOT_FID:
        row = _stamp_a(fid=chrome)
        packet = _packet(_pack((row.claim, HELIOS_A)), [row])
        packet.beats[5].vo = f"NARRATOR\nThe cited card printed {PRINT_A} in June 2026. [{chrome}]"
        packet.beats[5].finding_ids = [chrome]
        _live_board_receipt(packet)
        loaded = _api_round_trip(packet)
        leftover = [
            fid
            for beat in _voiced(loaded)
            for fid in beat.finding_ids
            if _SLOT_FID_RE.search(fid)
        ]
        finding_chrome = [
            f.id
            for f in (loaded.receipt.findings if loaded.receipt else [])
            if _SLOT_FID_RE.search(f.id)
        ]
        assert leftover == [], "asserting pack-slot finding_id ship FAILS"
        assert finding_chrome == [], "asserting pack-slot finding_id ship FAILS"
        cited = [b for b in _voiced(loaded) if b.finding_ids and _speech_norm(b.vo)]
        if cited:
            assert all(
                not _SLOT_FID_RE.search(fid)
                for b in cited
                for fid in b.finding_ids
            ), "asserting pack-slot finding_id ship FAILS"
            assert any(fid.startswith("te-") for b in cited for fid in b.finding_ids) or not cited
        spoken = _spoken(loaded)
        assert not _SLOT_FID_RE.search(spoken), "asserting pack-slot finding_id ship FAILS"
        payload = loaded.model_dump()
        dumped_ids = [
            fid
            for beat in payload.get("beats") or []
            for fid in beat.get("finding_ids") or []
        ] + [
            f.get("id") or ""
            for f in ((payload.get("receipt") or {}).get("findings") or [])
        ]
        assert not any(_SLOT_FID_RE.search(fid) for fid in dumped_ids), (
            "asserting pack-slot finding_id ship FAILS"
        )


def test_vo_double_bracket_and_pack_slot_tokens_strip() -> None:
    """[[n]] / pack-slot tokens must leave VO. Leftover FAILS."""
    stamp = _stamp_a(fid="subsequent_events_chronologically[4]")
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    packet.beats[5].vo = (
        f"NARRATOR\nThe cited card printed {PRINT_A} in June 2026. "
        f"[[4]] [subsequent_events_chronologically[4]]"
    )
    packet.beats[5].finding_ids = ["subsequent_events_chronologically[4]"]
    _live_board_receipt(packet)
    loaded = _api_round_trip(packet)
    spoken = _spoken(loaded)
    assert "[[4]]" not in spoken, "asserting leftover pack-slot VO FAILS"
    assert not _SLOT_VO.search(spoken), "asserting leftover pack-slot VO FAILS"
    for beat in _voiced(loaded):
        assert "[[4]]" not in (beat.vo or ""), "asserting leftover pack-slot VO FAILS"
        assert not _SLOT_VO.search(beat.vo or ""), "asserting leftover pack-slot VO FAILS"


def test_successful_pack_slot_strip_alone_is_not_hold() -> None:
    """Successful strip of pack-slot chrome is cleaned, not a sole HOLD reason."""
    stamp = _stamp_a(fid="first_trigger_identified[0]")
    packet = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    packet.beats[5].vo = (
        f"NARRATOR\nThe cited card printed {PRINT_A} in June 2026. "
        f"[chronological_events[7]] [[4]] [first_trigger_identified[0]]"
    )
    packet.beats[5].finding_ids = ["first_trigger_identified[0]"]
    packet.beats[5].frame = PRINT_A
    _live_board_receipt(packet)
    loaded = _api_round_trip(packet)
    spoken = _spoken(loaded)
    leftover = bool(_SLOT_VO.search(spoken))
    clauses = _hold_clauses(_reason(loaded))
    sole = clauses == [_STRIP_ONLY] or _reason(loaded).lower() == _STRIP_ONLY.lower()
    assert not sole, "asserting strip-only HOLD FAILS"
    if leftover:
        assert not _shipped_ready(loaded), "leftover pack-slot tokens must HOLD"
        assert _STRIP_ONLY.lower() in _reason(loaded).lower() or "cite-faithfulness" in (
            _reason(loaded).lower()
        )
    else:
        assert clauses != [_STRIP_ONLY], "asserting strip-only HOLD FAILS"
        if loaded.receipt and loaded.receipt.disposition == "HOLD":
            assert _STRIP_ONLY.lower() not in _reason(loaded).lower() or len(clauses) > 1, (
                "asserting strip-only HOLD FAILS"
            )
        if _shipped_ready(loaded):
            assert re.search(r"\$4\.18|4\.18", spoken)

    seeded = _packet(_pack((stamp.claim, HELIOS_A)), [stamp])
    seeded.beats[5].vo = f"NARRATOR\nThe cited card printed {PRINT_A} in June 2026. [{stamp.id}]"
    seeded.beats[5].finding_ids = [stamp.id]
    seeded.beats[5].frame = PRINT_A
    seeded.receipt.disposition = "HOLD"
    seeded.receipt.hold_reason = _STRIP_ONLY
    seeded.status = "hold"
    sanitize_for_ship(seeded)
    seeded_clauses = _hold_clauses(_reason(seeded))
    assert seeded_clauses != [_STRIP_ONLY], "asserting strip-only HOLD FAILS"
    if seeded.receipt and seeded.receipt.disposition == "HOLD":
        assert _STRIP_ONLY.lower() not in _reason(seeded).lower() or len(seeded_clauses) > 1, (
            "asserting strip-only HOLD FAILS"
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
