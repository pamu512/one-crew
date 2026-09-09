"""Cite-faithful speech: no tone chrome, no title-read, mute-test frames.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2%). Production
code must stay free of these names and of live topic strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, RoomGrade, ScriptBeat, TimelineMapRow
from onecrew.room import grade_room, make_grade_artifact, run_room_loop

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
MERIDIAN_DESK = "https://www.meridian-desk.test/insights/campus-power-2026"

HELIOS_TITLE = "Helios campus leases – Outlook 2026 – Analysis - Meridian Desk"

_LIVE_TOPIC = (
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b|"
    r"\blithium\b|\biea\b|heat.?pump|data.?center"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b"

_TONE_CHROME = (
    r"question the decision that put this on the air|"
    r"from the news desk\.|"
    r"think past the headline\.|"
    r"personal take:"
)
_META_FRAME = (
    r"cited events? on (?:screen|later cards)|"
    r"cited print on screen|"
    r"new art from the cited print"
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
        title=HELIOS_TITLE,
    )


def _helios_print_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 14.2% in June 2026.",
        url=HELIOS_PRINT,
        printed="14.2%",
        title="Helios occupancy 14.2%",
    )


def _meridian_survey() -> Finding:
    return _finding(
        fid="te-meridian-campus-survey",
        claim="A campus-power survey tracked buildout and inflation.",
        url=MERIDIAN_DESK,
        printed="A campus-power survey tracked buildout and inflation.",
        title="Campus power survey",
        when="2026",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-cite-faithful-vo-frame",
        topic="Named-entity cover must sit on the attached stamp",
        hook="Named-entity cover must sit on the attached stamp",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited prints",
        tone="Question the decisions",
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


def _eight_units(overrides: dict[str, dict]) -> list[dict]:
    units = [
        {"id": "cold-open", "vo": "The title stays a question.", "eyes": "card", "finding_ids": []},
        {"id": "promise", "vo": "The title stays a question.", "eyes": "pack", "finding_ids": []},
        {"id": "gdp", "vo": "Those are not the same object.", "eyes": "card", "finding_ids": []},
        {"id": "labor", "vo": "Near is not a switch.", "eyes": "card", "finding_ids": []},
        {"id": "turn", "vo": "The title stays a question.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "Near is not a switch.", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    by_id = {u["id"]: u for u in units}
    for bid, patch in overrides.items():
        by_id[bid].update(patch)
    return units


def _no_search(**_k):
    return SimpleNamespace(results=[])


def test_tone_chrome_is_not_spoken_as_vo() -> None:
    """Tone is writer stance. Narrator must speak the stamp, not the tone line."""
    from onecrew.script import _assemble

    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "Question the decision that put this on the air.",
                    "eyes": "Helios paused campus leases in June 2026.",
                    "finding_ids": [stamp.id],
                }
            }
        ),
    )
    turn = next(b for b in written.beats if b.id == "turn")
    spoken = f"{turn.vo} {written.script}"
    assert not re.search(_TONE_CHROME, spoken, re.I)
    if stamp.id in turn.finding_ids:
        assert re.search(r"helios|paused campus leases", turn.vo, re.I)


def test_title_read_vo_speaks_stamp_print_not_article_title() -> None:
    """Article title is not a cite-faithful print. Speak note/claim/print instead."""
    from onecrew.script import _assemble

    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": HELIOS_TITLE,
                    "eyes": "Helios paused campus leases in June 2026.",
                    "finding_ids": [stamp.id],
                }
            }
        ),
    )
    turn = next(b for b in written.beats if b.id == "turn")
    spoken_all = "".join(f"{b.vo} {b.frame or ''}" for b in written.beats)
    assert HELIOS_TITLE not in spoken_all
    assert HELIOS_TITLE not in turn.vo
    assert stamp.id in turn.finding_ids
    assert re.search(r"paused campus leases|june 2026", turn.vo, re.I)


def test_meta_frame_shows_named_print_not_chrome() -> None:
    """Mute-test: frame must show the stamp object, not production meta."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Cited event on screen.",
                    "finding_ids": [stamp.id],
                },
                "promise": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Cited events on later cards.",
                    "finding_ids": [stamp.id],
                },
                "gdp": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "New art from the cited print.",
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    frames = " ".join((b.frame or "") for b in written.beats)
    assert not re.search(_META_FRAME, frames, re.I)
    shown = [b for b in written.beats if b.id in {"cold-open", "promise", "gdp"}]
    for beat in shown:
        if stamp.id in beat.finding_ids:
            assert re.search(r"14\.2|helios occupancy", beat.frame or "", re.I)


def test_room_flags_tone_title_and_meta_as_cite_faithfulness() -> None:
    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5 — turn\n"
        "00:80–01:00\n"
        "ACTION: Cited event on screen.\n"
        "NARRATOR\n"
        f"Question the decision that put this on the air. {stamp.claim} [{stamp.id}]\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nQuestion the decision that put this on the air. {stamp.claim} [{stamp.id}]"
    )
    packet.beats[4].frame = "Cited event on screen."
    packet.beats[4].finding_ids = [stamp.id]
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert "cite-faithfulness" in (grade.recut_detail or "").lower()


def test_repair_strips_tone_title_meta_or_holds() -> None:
    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    packet.beats[4].vo = (
        f"NARRATOR\nQuestion the decision that put this on the air. {HELIOS_TITLE}"
    )
    packet.beats[4].frame = "Cited event on screen."
    packet.beats[4].finding_ids = [stamp.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"

    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    spoken = "".join(f"{b.vo} {b.frame or ''}" for b in packet.beats)
    assert result.ok
    assert packet.receipt is not None
    assert packet.receipt.disposition == "READY"
    assert not re.search(_TONE_CHROME, spoken, re.I)
    assert HELIOS_TITLE not in spoken
    assert not re.search(_META_FRAME, spoken, re.I)
    assert re.search(r"paused campus leases|june 2026", spoken, re.I)


def test_ready_cannot_keep_recut_cite_faithfulness_smell() -> None:
    """Disposition READY with lingering room recut cite-faithfulness is a ship smell."""
    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5 — turn\n"
        "00:80–01:00\n"
        "ACTION: Helios paused campus leases in June 2026.\n"
        "NARRATOR\n"
        f"Helios paused campus leases in June 2026. [{stamp.id}]\n"
    )
    packet.beats[4].vo = f"NARRATOR\nHelios paused campus leases in June 2026. [{stamp.id}]"
    packet.beats[4].frame = "Helios paused campus leases in June 2026."
    packet.beats[4].finding_ids = [stamp.id]
    loop = run_room_loop(
        packet,
        research=lambda _ask=None: None,
        rewrite=lambda: None,
        grader=lambda _a: RoomGrade(
            vote="recut", recut_reason="other", recut_detail="cite-faithfulness"
        ),
        parallel_already=1,
    )
    assert loop.disposition == "READY"
    assert loop.grade.vote == "ship"
    assert "cite-faithfulness" not in (loop.grade.recut_detail or "").lower()


def test_room_loop_holds_unclean_tone_title_meta() -> None:
    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5 — turn\n"
        "ACTION: Cited event on screen.\n"
        "NARRATOR\n"
        f"Question the decision that put this on the air. {stamp.claim} [{stamp.id}]\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nQuestion the decision that put this on the air. {stamp.claim} [{stamp.id}]"
    )
    packet.beats[4].frame = "Cited event on screen."
    packet.beats[4].finding_ids = [stamp.id]
    loop = run_room_loop(
        packet,
        research=lambda _ask=None: None,
        rewrite=lambda: None,
        grader=lambda _a: RoomGrade(vote="ship"),
        parallel_already=1,
    )
    assert loop.disposition == "HOLD"
    assert "cite-faithfulness" in (loop.hold_reason or "").lower()


def test_extract_overwrites_series_token_title() -> None:
    """Parallel article title must replace the timeline_event series token."""
    from onecrew.agent.shift import _apply_extract

    stamp = _helios_stamp()
    stamp.title = "timeline_event"
    extracted = SimpleNamespace(
        results=[
            SimpleNamespace(
                url=HELIOS_WIRE,
                title=HELIOS_TITLE,
                excerpts=["Helios paused campus leases in June 2026."],
            )
        ],
        errors=[],
    )
    _apply_extract([stamp], extracted)
    assert stamp.title == HELIOS_TITLE


def test_faithful_claim_is_not_title_read() -> None:
    from onecrew.script import is_title_read_vo

    stamp = _finding(
        fid="te-helios-paused-2026-06",
        claim="Helios paused campus leases in June 2026.",
        url=HELIOS_WIRE,
        title="Helios paused campus leases in June 2026 – Outlook 2026 – Analysis",
    )
    assert is_title_read_vo(stamp.claim, [stamp]) is False
    assert is_title_read_vo(stamp.title, [stamp]) is True


def test_repair_does_not_undo_named_entity_align() -> None:
    """Tone strip must not restore a pre-align VO that names an uncovered org."""
    cover = _meridian_survey()
    packet = _packet(_pack((cover.claim, MERIDIAN_DESK)), [cover])
    packet.beats[4].vo = (
        "NARRATOR\nQuestion the decision that put this on the air. "
        "Meridian Desk says Helios paused campus leases."
    )
    packet.beats[4].finding_ids = [cover.id]
    run_cite_recheck_loop(packet, search_fn=_no_search)
    turn = next((b for b in packet.beats if b.id == "turn"), None)
    spoken = turn.vo if turn is not None else ""
    assert not re.search(r"helios", spoken, re.I)
    assert not re.search(_TONE_CHROME, spoken, re.I)


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
