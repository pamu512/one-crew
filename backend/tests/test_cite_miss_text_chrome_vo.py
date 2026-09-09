"""Refuse cite-miss attach, thin/hanging VO, Text: on_screen chrome, strip-only HOLD.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2% / 41 Bcf).
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

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
HELIOS_FEE = "https://www.helios-wire.test/2026/01/helios-fee-0"
HELIOS_FLOW = "https://www.helios-wire.test/2026/06/helios-flow-41"

FEE_PRINT = "$0/t"
FLOW_PRINT = "41 Bcf"
STAMP_TITLE = "Helios Occupancy Print – June 2026 – Analysis - U.S"
TITLE_CHROME = "# Helios Occupancy Print – Analysis - Desk"
TEXT_CHROME = "Text: 'Helios Occupancy Print – Analysis'"

_LIVE_TOPIC = (
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
_FIXTURE = (
    r"helios|meridian-desk|meridian desk|\b14\.2\b|"
    r"\$0/t|0 \$/t|41 bcf"
)
_PLACEHOLDER_FID = re.compile(r"cite-miss|\bmissing\b|^$|frame-miss", re.I)
_BARE_ACCORDING = re.compile(
    r"according to (?:the )?[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s*$",
    re.I,
)
_HANGING_DATE = re.compile(
    r"(?:the following week,?\s+)?ending\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?\s*$",
    re.I,
)
_SPLIT_PERCENT = re.compile(r"\d,\s+\d+\s*(?:percent|%)", re.I)
_STRIP_ONLY = "pack slot token stripped from VO"
_SLOT_LEFTOVER = re.compile(
    r"chronological_events|executive_summary|missing_causal_links|excerpts\[\d+\]",
    re.I,
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


def _helios_stamp() -> Finding:
    return _finding(
        fid="te-helios-paused-2026-06",
        claim="Helios paused campus leases in June 2026.",
        url=HELIOS_WIRE,
        title="Helios paused campus leases",
    )


def _helios_print_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 14.2% in June 2026.",
        url=HELIOS_PRINT,
        printed="14.2%",
        title=STAMP_TITLE,
    )


def _helios_fee_stamp() -> Finding:
    return _finding(
        fid="te-helios-fee-2026-01",
        claim="Helios fee printed $0/t in January 2026.",
        url=HELIOS_FEE,
        printed=FEE_PRINT,
        title="Helios fee $0/t January 2026",
        when="January 2026",
    )


def _helios_flow_stamp() -> Finding:
    return _finding(
        fid="te-helios-flow-2026-06",
        claim="Helios flow printed 41 Bcf in June 2026.",
        url=HELIOS_FLOW,
        printed=FLOW_PRINT,
        title="Helios flow 41 Bcf",
    )


def _fringe_miss(*, fid: str = "cite-miss") -> Finding:
    return Finding(
        id=fid,
        claim="Unsourced fringe claim about campus occupancy.",
        stamp="fringe",
        parallel_status="miss",
        note="Parallel miss. Included and tagged fringe. Never sold as fact.",
    )


def _packet(
    pack: str,
    findings: list[Finding],
    vos: dict[str, str] | None = None,
    *,
    topic: str = "Named-entity cover must sit on the attached stamp",
) -> Packet:
    packet = Packet(
        id="oc-cite-miss-text-chrome-vo",
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
        "promise": "NARRATOR\n",
        "gdp": "NARRATOR\n",
        "labor": "NARRATOR\n",
        "turn": "NARRATOR\nThe title stays a question.",
        "complication": "NARRATOR\nThose are not the same object.",
        "receipt": "NARRATOR\n",
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


def _eight_units(overrides: dict[str, dict]) -> list[dict]:
    units = [
        {"id": "cold-open", "vo": "The title stays a question.", "eyes": "card", "finding_ids": []},
        {"id": "promise", "vo": "", "eyes": "pack", "finding_ids": []},
        {"id": "gdp", "vo": "", "eyes": "card", "finding_ids": []},
        {"id": "labor", "vo": "", "eyes": "card", "finding_ids": []},
        {"id": "turn", "vo": "The title stays a question.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    by_id = {u["id"]: u for u in units}
    for bid, patch in overrides.items():
        by_id[bid].update(patch)
    return units


def _no_search(**_k):
    return SimpleNamespace(results=[])


def _voiced(packet: Packet) -> list[ScriptBeat]:
    return [b for b in packet.beats if (b.kind or "vo") != "heading"]


def _spoken(packet: Packet) -> str:
    return " ".join(f"{b.vo} {b.frame or ''}" for b in _voiced(packet))


def _cited(packet: Packet) -> list[str]:
    return [fid for b in _voiced(packet) for fid in b.finding_ids]


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").strip()


def _shipped_ready(packet: Packet) -> bool:
    return bool(packet.receipt and packet.receipt.disposition == "READY")


def _hold_clauses(reason: str) -> list[str]:
    return [p.strip() for p in (reason or "").replace("\n", ";").split(";") if p.strip()]


def _run_sanitize_repair(packet: Packet) -> None:
    run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)


def test_cite_miss_placeholder_ids_cannot_attach_or_ship() -> None:
    """Literal cite-miss / missing / empty tokens are not covering stamps."""
    stamp = _helios_print_stamp()
    miss = _fringe_miss()
    empty_miss = _fringe_miss(fid="missing")
    packet = _packet(
        _pack((stamp.claim, HELIOS_PRINT)),
        [stamp, miss, empty_miss],
    )
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{miss.id}]"
    packet.beats[5].finding_ids = [miss.id]
    packet.beats[5].frame = "14.2%"
    packet.beats[2].vo = "NARRATOR\nUnsourced fringe claim about campus occupancy. [missing]"
    packet.beats[2].finding_ids = ["missing", ""]
    _run_sanitize_repair(packet)
    cited = _cited(packet)
    spoken = _spoken(packet)
    assert not any(_PLACEHOLDER_FID.search(fid or "") for fid in cited), (
        "asserting cite-miss attach FAILS"
    )
    assert "[cite-miss]" not in spoken
    assert "[missing]" not in spoken
    if _shipped_ready(packet):
        assert stamp.id in cited
        assert not re.search(r"\[cite-miss(?:-\d+)?\]", spoken)
    else:
        reason = _reason(packet).lower()
        assert any(
            tok in reason
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat", "covering")
        ), "asserting cite-miss attach FAILS"
        assert "cite-miss" not in reason or "faithfulness" in reason
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def _vo_bodies(packet: Packet) -> str:
    from onecrew.script import _vo_lines

    return " ".join(_vo_lines(b.vo) for b in _voiced(packet))


def _beat_vos(packet: Packet) -> list[str]:
    from onecrew.script import _vo_lines

    return [re.sub(r"\[[^\]]+\]", "", _vo_lines(b.vo)).strip() for b in _voiced(packet)]


def test_bare_according_to_and_hanging_date_cannot_ship() -> None:
    """Mid-attribution / hanging date with no print must drop, rewrite, or HOLD."""
    covered = _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 14.2% in June 2026 according to the Meridian Desk.",
        url=HELIOS_PRINT,
        printed="14.2%",
        title="Meridian Desk occupancy print",
    )
    attrib = _packet(_pack((covered.claim, HELIOS_PRINT)), [covered])
    attrib.beats[5].vo = (
        "NARRATOR\nHelios occupancy printed 14.2% in June 2026. According to the Meridian Desk"
    )
    attrib.beats[5].finding_ids = [covered.id]
    _run_sanitize_repair(attrib)
    attrib_vo = re.sub(r"\[[^\]]+\]", "", _vo_bodies(attrib))
    assert not any(_BARE_ACCORDING.search(vo) for vo in _beat_vos(attrib) if vo), (
        "asserting ship FAILS"
    )
    if _shipped_ready(attrib):
        assert re.search(r"14\.2|helios occupancy printed", attrib_vo, re.I)
    else:
        assert any(
            tok in _reason(attrib).lower()
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat")
        ), "asserting ship FAILS"
    assert getattr(attrib, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS
    assert "cite-repair loop exhausted" not in _reason(attrib).lower() or (
        getattr(attrib, "cite_recheck_attempts", 0) > MAX_CITE_RECHECKS
    )

    hung = _packet(_pack((covered.claim, HELIOS_PRINT)), [covered])
    hung.beats[5].vo = "NARRATOR\nThe following week, ending June 21st"
    hung.beats[5].finding_ids = [covered.id]
    _run_sanitize_repair(hung)
    hung_vo = re.sub(r"\[[^\]]+\]", "", _vo_bodies(hung))
    assert not any(_HANGING_DATE.search(vo) for vo in _beat_vos(hung) if vo), (
        "asserting ship FAILS"
    )
    if _shipped_ready(hung):
        assert re.search(r"14\.2|helios occupancy printed", hung_vo, re.I)
    else:
        assert any(
            tok in _reason(hung).lower()
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat")
        ), "asserting ship FAILS"
    assert getattr(hung, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_split_percent_print_hole_cannot_ship_on_sanitize() -> None:
    """Sanitize path must rewrite or drop split-percent / By, / over-points holes."""
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = "NARRATOR\nHelios occupancy printed 1, 3 percent."
    packet.beats[5].finding_ids = [stamp.id]
    _run_sanitize_repair(packet)
    spoken = re.sub(r"\[[^\]]+\]", "", _vo_bodies(packet))
    assert not _SPLIT_PERCENT.search(spoken), "asserting hole ship FAILS"
    if _shipped_ready(packet):
        assert re.search(r"14\.2|helios occupancy printed", spoken, re.I)
        assert stamp.id in _cited(packet)
    else:
        assert any(
            tok in _reason(packet).lower()
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat")
        ), "asserting hole ship FAILS"


def test_split_percent_print_hole_cannot_ship() -> None:
    """Incomplete number splits rewrite from the stamp or drop. Hole ship FAILS."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios occupancy printed 1, 3 percent.",
                    "eyes": "card",
                    "finding_ids": [stamp.id],
                },
                "promise": {
                    "vo": "By,",
                    "eyes": "card",
                    "finding_ids": [stamp.id],
                },
                "complication": {
                    "vo": "Occupancy moved over points.",
                    "eyes": "gap",
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    run_cite_recheck_loop(written, search_fn=_no_search)
    sanitize_for_ship(written)
    spoken = _spoken(written)
    assert not _SPLIT_PERCENT.search(spoken), "asserting hole ship FAILS"
    assert not re.search(r"\bBy,|\bover\s+points\b", spoken), "asserting hole ship FAILS"
    if _shipped_ready(written):
        assert re.search(r"14\.2|helios occupancy printed", spoken, re.I)
        assert stamp.id in _cited(written)
    else:
        reason = _reason(written).lower()
        assert any(
            tok in reason
            for tok in ("cite-faithfulness", "thin_after_repair", "empty beat")
        ), "asserting hole ship FAILS"
    assert getattr(written, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def test_on_screen_uses_stamp_print_not_text_or_headline_chrome() -> None:
    """Mute-test on_screen is the attached print, not Text:/# wrappers."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list
    from onecrew.script import _speech_norm

    occupancy = _helios_print_stamp()
    fee = _helios_fee_stamp()
    flow = _helios_flow_stamp()

    text_pkt = _packet(_pack((occupancy.claim, HELIOS_PRINT)), [occupancy])
    text_pkt.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{occupancy.id}]"
    text_pkt.beats[5].finding_ids = [occupancy.id]
    text_pkt.beats[5].frame = TEXT_CHROME
    sanitize_for_ship(text_pkt)
    attach_frames(text_pkt, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = text_pkt.frames or write_shot_list(text_pkt)
    cited = next(b for b in _voiced(text_pkt) if occupancy.id in b.finding_ids)
    first = next(f for f in shots if f.beat_id == cited.id)
    shown = first.on_screen or ""
    assert not shown.strip().lower().startswith("text:"), "asserting Text:/headline chrome FAILS"
    assert not shown.strip().startswith("#"), "asserting Text:/headline chrome FAILS"
    assert _speech_norm(TEXT_CHROME) not in _speech_norm(shown), (
        "asserting Text:/headline chrome FAILS"
    )
    assert "14.2%" in shown, "asserting Text:/headline chrome FAILS"
    assert mute_test_shows_stamp(first, [occupancy], cited) is True

    hash_pkt = _packet(_pack((fee.claim, HELIOS_FEE)), [fee])
    hash_pkt.beats[5].vo = f"NARRATOR\nHelios fee printed $0/t in January 2026. [{fee.id}]"
    hash_pkt.beats[5].finding_ids = [fee.id]
    hash_pkt.beats[5].frame = TITLE_CHROME
    sanitize_for_ship(hash_pkt)
    attach_frames(hash_pkt, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    fee_shots = hash_pkt.frames or write_shot_list(hash_pkt)
    fee_cited = next(b for b in _voiced(hash_pkt) if fee.id in b.finding_ids)
    fee_first = next(f for f in fee_shots if f.beat_id == fee_cited.id)
    assert not fee_first.on_screen.strip().startswith("#"), "asserting Text:/headline chrome FAILS"
    assert re.search(r"\$0/t|0 \$/t", fee_first.on_screen), "asserting Text:/headline chrome FAILS"

    flow_pkt = _packet(_pack((flow.claim, HELIOS_FLOW)), [flow])
    flow_pkt.beats[5].vo = f"NARRATOR\nHelios flow printed 41 Bcf in June 2026. [{flow.id}]"
    flow_pkt.beats[5].finding_ids = [flow.id]
    flow_pkt.beats[5].frame = "Text: 'Helios Flow Print – Analysis'"
    sanitize_for_ship(flow_pkt)
    attach_frames(flow_pkt, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    flow_shots = flow_pkt.frames or write_shot_list(flow_pkt)
    flow_cited = next(b for b in _voiced(flow_pkt) if flow.id in b.finding_ids)
    flow_first = next(f for f in flow_shots if f.beat_id == flow_cited.id)
    assert not flow_first.on_screen.strip().lower().startswith("text:"), (
        "asserting Text:/headline chrome FAILS"
    )
    assert FLOW_PRINT in flow_first.on_screen, "asserting Text:/headline chrome FAILS"


def test_successful_pack_slot_strip_is_not_sole_hold() -> None:
    """Clean VO after strip must not stay HOLD solely for the strip nit."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": (
                        "Helios occupancy printed 14.2% in June 2026. "
                        "[chronological_events[7]] [executive_summary]"
                    ),
                    "eyes": "card",
                    "finding_ids": [stamp.id],
                },
                "promise": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "card",
                    "finding_ids": [stamp.id],
                },
                "complication": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "gap",
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    sanitize_for_ship(written)
    spoken = _spoken(written)
    leftover = bool(_SLOT_LEFTOVER.search(spoken))
    if leftover:
        assert not _shipped_ready(written), "leftover pack-slot tokens must HOLD"
        return
    clauses = _hold_clauses(_reason(written))
    sole = clauses == [_STRIP_ONLY] or (
        _reason(written).lower() == _STRIP_ONLY.lower()
    )
    assert not sole, "asserting strip-only HOLD FAILS"
    if _shipped_ready(written):
        assert stamp.id in _cited(written)
        assert re.search(r"14\.2|helios occupancy printed", spoken, re.I)

    held = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    held.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    held.beats[5].finding_ids = [stamp.id]
    held.beats[5].frame = "14.2%"
    held.receipt.disposition = "HOLD"
    held.receipt.hold_reason = _STRIP_ONLY
    held.status = "hold"
    sanitize_for_ship(held)
    held_spoken = _spoken(held)
    assert not _SLOT_LEFTOVER.search(held_spoken)
    held_clauses = _hold_clauses(_reason(held))
    assert held_clauses != [_STRIP_ONLY], "asserting strip-only HOLD FAILS"
    if held.receipt and held.receipt.disposition == "HOLD":
        assert _STRIP_ONLY.lower() not in _reason(held).lower() or len(held_clauses) > 1, (
            "asserting strip-only HOLD FAILS"
        )


def test_leftover_pack_slot_token_in_vo_holds() -> None:
    """If a pack-slot token remains in VO after sanitize, HOLD."""
    from onecrew.foundry import is_pack_slot_id

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = (
        "NARRATOR\nHelios occupancy printed 14.2% in June 2026. [chronological_events[7]]"
    )
    packet.beats[5].finding_ids = [stamp.id]
    sanitize_for_ship(packet)
    spoken = _spoken(packet)
    leftover = bool(_SLOT_LEFTOVER.search(spoken)) or any(
        is_pack_slot_id(fid) for fid in _cited(packet)
    )
    if leftover:
        assert not _shipped_ready(packet)
        assert _STRIP_ONLY.lower() in _reason(packet).lower() or "cite-faithfulness" in (
            _reason(packet).lower()
        )
    else:
        clauses = _hold_clauses(_reason(packet))
        assert clauses != [_STRIP_ONLY], "asserting strip-only HOLD FAILS"


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
