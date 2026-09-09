"""Cite-faithfulness: named-entity ALL-cover, chrome VO, print skew, repair loop.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2%). Production
code must stay free of these names and of live office-vacancy topic strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, RoomGrade, ScriptBeat, TimelineMapRow
from onecrew.room import grade_room, make_grade_artifact, run_room_loop

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
MERIDIAN_DESK = "https://www.meridian-desk.test/insights/campus-power-2026"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"

_LIVE_TOPIC = (
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b"


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


def _meridian_survey() -> Finding:
    return _finding(
        fid="te-meridian-campus-survey",
        claim="A campus-power survey tracked buildout and inflation.",
        url=MERIDIAN_DESK,
        printed="A campus-power survey tracked buildout and inflation.",
        title="Campus power survey",
        when="2026",
    )


def _helios_print_stamp() -> Finding:
    return _finding(
        fid="te-helios-occupancy-2026-06",
        claim="Helios occupancy printed 14.2% in June 2026.",
        url=HELIOS_PRINT,
        printed="14.2%",
        title="Helios occupancy 14.2%",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-cite-faithful-cover",
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


def test_host_match_cannot_soft_cover_a_second_named_org() -> None:
    """VO names Helios + Meridian Desk; meridian-desk host alone is not cover."""
    from onecrew.script import _assemble
    from onecrew.timeline import stamp_covers_vo, vo_proper_names

    vo = "Meridian Desk says Helios paused campus leases."
    names = vo_proper_names(vo)
    assert "helios" in names
    assert "meridian" in names
    cover = _meridian_survey()
    match = _helios_stamp()
    assert stamp_covers_vo(vo, cover) is False
    assert stamp_covers_vo(vo, match) is False
    packet = _packet(
        _pack(
            (match.claim, HELIOS_WIRE),
            (cover.claim, MERIDIAN_DESK),
        ),
        [cover, match],
    )
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": vo,
                    "eyes": "card",
                    "finding_ids": [cover.id],
                }
            }
        ),
    )
    beat = next(b for b in written.beats if b.id == "turn")
    assert cover.id not in beat.finding_ids
    assert not re.search(r"helios", beat.vo, re.I)


def test_chrome_narrator_vo_must_speak_stamp_or_drop_beat() -> None:
    """Pack/slot chrome may not ship while the frame asserts a concrete print."""
    from onecrew.script import _assemble

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "The named print stays on the card.",
                    "eyes": "Helios occupancy printed 14.2% in June 2026.",
                    "finding_ids": [stamp.id],
                }
            }
        ),
    )
    spoken = written.script + "".join(f"{b.vo} {b.frame}" for b in written.beats)
    assert not re.search(r"named print stays on the card", spoken, re.I)
    turn = next((b for b in written.beats if b.id == "turn"), None)
    if turn is None:
        return
    body = f"{turn.vo} {turn.frame}"
    assert not re.search(r"named print stays on the card", body, re.I)
    if stamp.id in turn.finding_ids:
        assert re.search(r"14\.2|helios", turn.vo, re.I)


def test_print_skew_reattaches_or_drops_unsupported_number() -> None:
    """Spoken 14.2% June cannot stay on a Helios stamp that does not carry that print."""
    from onecrew.script import _assemble

    lease = _helios_stamp()
    printed = _helios_print_stamp()
    packet = _packet(
        _pack((lease.claim, HELIOS_WIRE), (printed.claim, HELIOS_PRINT)),
        [lease, printed],
    )
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "Helios printed 14.2% in June 2026.",
                    "eyes": "14.2% June on the card.",
                    "finding_ids": [lease.id],
                }
            }
        ),
    )
    beat = next(b for b in written.beats if b.id == "turn")
    spoken = f"{beat.vo} {beat.frame}"
    if re.search(r"14\.2", spoken):
        cited = [f for f in written.receipt.findings if f.id in beat.finding_ids]
        blobs = " ".join(f"{f.claim} {f.print} {f.note} {f.when}" for f in cited)
        assert "14.2" in blobs
        assert lease.id not in beat.finding_ids or "14.2" in f"{lease.claim} {lease.print} {lease.note}"
    else:
        assert lease.id not in beat.finding_ids or not re.search(r"14\.2", spoken)


def test_room_flags_soft_cover_and_print_skew_as_cite_faithfulness() -> None:
    cover = _meridian_survey()
    packet = _packet(_pack((cover.claim, MERIDIAN_DESK)), [cover])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5 — turn\n"
        "00:80–01:00\n"
        "ACTION: Helios occupancy printed 14.2% in June 2026.\n"
        "NARRATOR\n"
        f"Meridian Desk says Helios paused campus leases. [{cover.id}]\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nMeridian Desk says Helios paused campus leases. [{cover.id}]"
    )
    packet.beats[4].frame = "Helios occupancy printed 14.2% in June 2026."
    packet.beats[4].finding_ids = [cover.id]
    artifact = make_grade_artifact(packet)
    grade = grade_room(artifact, grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert "cite-faithfulness" in (grade.recut_detail or "").lower()


def test_cite_repair_runs_on_named_entity_and_chrome_holes() -> None:
    cover = _meridian_survey()
    packet = _packet(_pack((cover.claim, MERIDIAN_DESK)), [cover])
    packet.beats[4].vo = "NARRATOR\nMeridian Desk says Helios paused campus leases."
    packet.beats[4].finding_ids = [cover.id]
    packet.beats[2].vo = "NARRATOR\nThe named print stays on the card."
    packet.beats[2].frame = "Helios occupancy printed 14.2% in June 2026."
    packet.beats[2].finding_ids = [cover.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"

    def _no_search(**_k):
        return SimpleNamespace(results=[])

    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    turn = next((b for b in packet.beats if b.id == "turn"), None)
    if turn is not None:
        assert cover.id not in turn.finding_ids or not re.search(r"helios", turn.vo, re.I)
        assert not re.search(r"helios", turn.vo, re.I)
    spoken = "".join(f"{b.vo} {b.frame}" for b in packet.beats)
    assert not re.search(r"named print stays on the card", spoken, re.I)
    if not result.ok:
        reason = (packet.receipt.hold_reason or "").lower()
        assert "cite-repair loop exhausted" in reason or "empty beat" in reason
        assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS


def test_room_cite_faithfulness_hold_must_run_cite_repair(monkeypatch) -> None:
    """Room recut other:cite-faithfulness cannot finish with cite_recheck_attempts=0."""
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.cite_repair import run_cite_recheck_loop as real_repair
    from onecrew.models import Rails
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    cover = _meridian_survey()
    pack = _pack((cover.claim, MERIDIAN_DESK))
    repair_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = pack
        packet.task_spine = pack
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="READY",
            findings=[cover],
            timeline_map=[
                TimelineMapRow(thesis=cover.claim, url=MERIDIAN_DESK, finding_id=cover.id)
            ],
        )
        return receipt, [], [], pack

    def tracking_repair(packet, **kwargs):
        repair_calls["n"] += 1
        kwargs.setdefault("search_fn", lambda **_k: SimpleNamespace(results=[]))
        return real_repair(packet, **kwargs)

    eight = (
        '[{"id":"cold-open","vo":"The title stays a question.","eyes":"card","finding_ids":[]},'
        '{"id":"promise","vo":"The title stays a question.","eyes":"pack","finding_ids":[]},'
        '{"id":"gdp","vo":"The named print stays on the card.","eyes":"Helios occupancy printed 14.2% in June 2026.","finding_ids":["te-meridian-campus-survey"]},'
        '{"id":"labor","vo":"Near is not a switch.","eyes":"card","finding_ids":[]},'
        '{"id":"turn","vo":"Meridian Desk says Helios paused campus leases.","eyes":"card","finding_ids":["te-meridian-campus-survey"]},'
        '{"id":"complication","vo":"Those are not the same object.","eyes":"gap","finding_ids":[]},'
        '{"id":"receipt","vo":"Near is not a switch.","eyes":"board","finding_ids":[]},'
        '{"id":"close","vo":"Near is not a switch.","eyes":"close","finding_ids":[]}]'
    )

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.run_cite_recheck_loop", tracking_repair)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", real_write_vo)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", lambda _p: eight)
    monkeypatch.setattr(
        "onecrew.room.run_adk_room",
        lambda _a: RoomGrade(vote="recut", recut_reason="other", recut_detail="cite-faithfulness"),
    )
    monkeypatch.setattr("onecrew.agent.shift._board", lambda p, _r: p.frames)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    shift = open_shift(
        "Named-entity cover must sit on the attached stamp",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited prints",
        tone="On the cited print",
        topic="Named-entity cover must sit on the attached stamp",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=False)
    packet = run_live_packet(shift)
    assert repair_calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    if packet.receipt and packet.receipt.disposition == "HOLD":
        reason = (packet.receipt.hold_reason or "").lower()
        assert packet.cite_recheck_attempts >= 1


def test_room_loop_cite_faithfulness_still_holds_without_inventing() -> None:
    cover = _meridian_survey()
    packet = _packet(_pack((cover.claim, MERIDIAN_DESK)), [cover])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5 — turn\n"
        "NARRATOR\n"
        f"Meridian Desk says Helios paused campus leases. [{cover.id}]\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nMeridian Desk says Helios paused campus leases. [{cover.id}]"
    )
    packet.beats[4].finding_ids = [cover.id]
    loop = run_room_loop(
        packet,
        research=lambda _ask=None: None,
        rewrite=lambda: None,
        grader=lambda _a: RoomGrade(vote="ship"),
        parallel_already=1,
    )
    assert loop.disposition == "HOLD"
    assert "cite-faithfulness" in (loop.hold_reason or "").lower()


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
