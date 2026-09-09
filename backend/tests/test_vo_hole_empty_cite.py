"""VO print-holes and false empty-cite HOLD.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2% / 9.4).
Production must stay free of these names and of live topic strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, RoomGrade, ScriptBeat, TimelineMapRow
from onecrew.room import grade_room, make_grade_artifact

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
MERIDIAN_DESK = "https://www.meridian-desk.test/insights/campus-power-2026"

_LIVE_TOPIC = (
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b|"
    r"interconnection|\blbnl\b|lawrence berkeley|\brmi\b|"
    r"terawatts?|power[- ]grid|queue[- ]cut"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b|\b9\.4\b"
_HOLE = r"\bBy,|\bover\s+points\b"


def _finding(
    *,
    fid: str,
    claim: str,
    url: str,
    printed: str | None = None,
    when: str = "June 2026",
    title: str = "timeline_event",
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
        note="Timeline event. Parallel URL on this row.",
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
        title="Helios occupancy 14.2%",
    )


def _packet(pack: str, findings: list[Finding]) -> Packet:
    packet = Packet(
        id="oc-vo-hole-empty-cite",
        topic="Named-entity cover must sit on the attached stamp",
        hook="Named-entity cover must sit on the attached stamp",
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
        ],
    )
    lines = {
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


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").lower()


def test_covering_finding_ids_do_not_hold_as_cites_nothing() -> None:
    """Frame chrome must not empty a beat that already has covering pack ids."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "On screen: 'Meridian Queue Report",
                    "finding_ids": [stamp.id],
                },
                "promise": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "On screen: 'Hel",
                    "finding_ids": [stamp.id],
                },
                "complication": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "On screen: 'U.S",
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    # Frame chrome must not empty covering ids at mint. Repair is not a second chance.
    assert "cites nothing" not in _reason(written)
    for bid in ("cold-open", "promise", "complication"):
        beat = next(b for b in written.beats if b.id == bid)
        assert stamp.id in beat.finding_ids
        assert f"[{stamp.id}]" in beat.vo
    result = run_cite_recheck_loop(written, search_fn=_no_search)
    assert written.cite_recheck_attempts <= MAX_CITE_RECHECKS
    assert result.hold_reason != "cite-repair loop exhausted" or written.cite_recheck_attempts > 3
    reason = _reason(written)
    assert "cites nothing" not in reason
    assert "empty beat" not in reason
    covered = [b for b in written.beats if stamp.id in b.finding_ids]
    assert len(covered) >= 3
    for beat in covered:
        assert f"[{stamp.id}]" in beat.vo
        assert re.search(r"14\.2|helios occupancy", beat.vo, re.I)
        assert not re.search(_HOLE, f"{beat.vo} {beat.frame or ''}")


def test_unsupported_print_strip_rewrites_or_drops_clause() -> None:
    """Stripping an uncovered number must not leave 'By,' / 'over points' holes."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "By 9.4, Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "card",
                    "finding_ids": [stamp.id],
                },
                "promise": {
                    "vo": "Helios occupancy printed over 9.4 points.",
                    "eyes": "card",
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    result = run_cite_recheck_loop(written, search_fn=_no_search)
    assert written.cite_recheck_attempts <= MAX_CITE_RECHECKS
    spoken = "".join(f"{b.vo} {b.frame or ''}" for b in written.beats)
    assert not re.search(_HOLE, spoken)
    assert "9.4" not in spoken
    for bid in ("cold-open", "promise"):
        beat = next((b for b in written.beats if b.id == bid), None)
        if beat is None:
            continue
        if stamp.id in beat.finding_ids:
            assert re.search(r"14\.2|helios occupancy|paused campus leases", beat.vo, re.I)
            assert f"[{stamp.id}]" in beat.vo
    if written.receipt and written.receipt.disposition == "HOLD":
        reason = _reason(written)
        assert "cites nothing" not in reason
        assert result.hold_reason != "cite-repair loop exhausted" or written.cite_recheck_attempts > 3


def test_truncated_frame_shows_attached_stamp_print() -> None:
    """Mute-test: leftover screen chrome is replaced by the attached stamp print."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "On screen: 'Hel",
                    "finding_ids": [stamp.id],
                }
            }
        ),
    )
    turn = next(b for b in written.beats if b.id == "turn")
    assert stamp.id in turn.finding_ids
    assert re.search(r"14\.2|helios occupancy", turn.frame or "", re.I)
    assert not re.search(r"^on screen\b", turn.frame or "", re.I)
    assert "'" not in (turn.frame or "") or (turn.frame or "").count("'") % 2 == 0


def test_stripped_cite_tags_reattach_when_ids_cover() -> None:
    """Repair must re-pin [fid] when finding_ids already cover the spoken claim."""
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[4].vo = "NARRATOR\nHelios occupancy printed 14.2% in June 2026."
    packet.beats[4].frame = "On screen: 'Hel"
    packet.beats[4].finding_ids = [stamp.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "beat5 cites nothing in the pack"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    turn = next((b for b in packet.beats if stamp.id in b.finding_ids and "14.2" in (b.vo or "")), None)
    assert turn is not None
    assert stamp.id in turn.finding_ids
    assert f"[{stamp.id}]" in turn.vo
    assert "cites nothing" not in _reason(packet)
    assert result.hold_reason != "cite-repair loop exhausted" or packet.cite_recheck_attempts > 3
    if packet.script:
        assert f"[{stamp.id}]" in packet.script


def test_room_does_not_empty_cite_covered_ids_without_tags() -> None:
    """Script tag lag is not an empty-cite miss when the beat already carries covering ids."""
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[4].vo = "NARRATOR\nHelios occupancy printed 14.2% in June 2026."
    packet.beats[4].finding_ids = [stamp.id]
    packet.beats[4].frame = "Helios occupancy printed 14.2% in June 2026."
    run_cite_recheck_loop(packet, search_fn=_no_search)
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    if grade.vote == "recut":
        assert "cite-faithfulness" not in (grade.recut_detail or "").lower() or f"[{stamp.id}]" in (
            packet.script or ""
        )
    else:
        assert grade.vote == "ship"


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
