"""Cite-repair must fire on HOLD receipt; refuse meta VO, title-reads, hanging clauses.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2%).
Production code and this file must stay free of live topic strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, Rails, RoomGrade, ScriptBeat, TimelineMapRow
from onecrew.receipt import attach_frames
from onecrew.script import sanitize_for_ship

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
MERIDIAN_DESK = "https://www.meridian-desk.test/insights/campus-power-2026"

STAMP_TITLE = "Helios Occupancy Print – June 2026 – Analysis - U.S"
TOPIC = "Did named campus occupancy stall after the printed pause?"

_LIVE_TOPIC = (
    r"home[- ]insurance|cnbc|cotality|\bmatic\b|premiums|"
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b|"
    r"\blithium\b|\biea\b|"
    r"red[- ]sea|xeneta|freightos|"
    r"\boag\b|atlanta|fort lauderdale|airfare|"
    r"grocery|power[- ]grid|interconnection|"
    r"airline[- ]ticket|us[- ]airline"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b"

_META_VO = (
    r"cannot be verified|our research indicates|common question circulating"
)
_HANGING = r"for instance\s*$"


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


def _fringe_miss() -> Finding:
    return Finding(
        id="cite-miss",
        claim="Unsourced fringe claim about campus occupancy.",
        stamp="fringe",
        parallel_status="miss",
        note="Parallel miss. Included and tagged fringe. Never sold as fact.",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-repair-fire-meta-onscreen",
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


def _spoken(packet: Packet) -> str:
    return " ".join(f"{b.vo} {b.frame or ''}" for b in packet.beats)


def _voiced(packet: Packet) -> list[ScriptBeat]:
    return [b for b in packet.beats if (b.kind or "vo") != "heading"]


def test_cite_faithfulness_hold_persists_receipt_attempts_on_shift_path(monkeypatch) -> None:
    """Room recut other:cite-faithfulness must increment the stored receipt, not only a helper."""
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.cite_repair import run_cite_recheck_loop as real_repair
    from onecrew.script_writer import write_vo_from_pack as real_write_vo
    from onecrew.store import store

    stamp = _helios_print_stamp()
    miss = _fringe_miss()
    pack = _pack((stamp.claim, HELIOS_PRINT))

    def research(packet, rails, depth, **_k):
        packet.research_pack = pack
        packet.task_spine = pack
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="READY",
            findings=[stamp, miss],
            timeline_map=[
                TimelineMapRow(thesis=stamp.claim, url=HELIOS_PRINT, finding_id=stamp.id)
            ],
        )
        return receipt, [], [], pack

    def tracking_repair(packet, **kwargs):
        kwargs.setdefault("search_fn", _no_search)
        return real_repair(packet, **kwargs)

    eight = (
        '[{"id":"cold-open","vo":"The title stays a question.","eyes":"card","finding_ids":[]},'
        '{"id":"promise","vo":"The title stays a question.","eyes":"pack","finding_ids":[]},'
        '{"id":"gdp","vo":"Those are not the same object.","eyes":"card","finding_ids":[]},'
        '{"id":"labor","vo":"Near is not a switch.","eyes":"card","finding_ids":[]},'
        '{"id":"turn","vo":"The title stays a question.","eyes":"hold","finding_ids":[]},'
        '{"id":"complication","vo":"The print fell 14.2% in June 2026.","eyes":"14.2% June on the card.","finding_ids":["te-helios-occupancy-2026-06"]},'
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
    monkeypatch.setattr(
        "onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[])
    )
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    shift = open_shift(
        TOPIC,
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited prints",
        tone="On the cited print",
        topic=TOPIC,
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=False)
    packet = run_live_packet(shift)
    dumped = packet.model_dump()
    stored = store.get_packet(packet.id)
    assert stored is not None
    stored_dump = stored.model_dump()
    for blob in (dumped, stored_dump):
        receipt = blob.get("receipt") or {}
        attempts = int(receipt.get("cite_recheck_attempts") or 0)
        assert attempts >= 1, "asserting 0 FAILS — receipt the API returns must count the repair"
        assert attempts <= MAX_CITE_RECHECKS
    assert packet.receipt is not None
    assert getattr(packet.receipt, "cite_recheck_attempts", 0) >= 1
    assert stored.receipt is not None
    assert getattr(stored.receipt, "cite_recheck_attempts", 0) >= 1
    if packet.receipt.disposition == "HOLD":
        reason = (packet.receipt.hold_reason or "").lower()
        assert "cite-repair loop exhausted" not in reason or packet.cite_recheck_attempts > 3


def test_unverified_meta_vo_cannot_ship() -> None:
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = (
        "NARRATOR\nThe premise cannot be verified. Our research indicates "
        "a common question circulating."
    )
    packet.beats[5].finding_ids = [stamp.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)
    spoken = _spoken(packet)
    assert not re.search(_META_VO, spoken, re.I), "asserting ship FAILS"
    assert result.ok or getattr(packet.receipt, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS
    if packet.receipt and packet.receipt.disposition == "READY":
        assert not re.search(_META_VO, spoken, re.I)


def test_thin_headline_paste_vo_cannot_ship() -> None:
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\n{STAMP_TITLE}"
    packet.beats[5].finding_ids = [stamp.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"
    run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)
    spoken = _spoken(packet)
    assert STAMP_TITLE not in spoken, "asserting ship FAILS"
    if re.search(r"14\.2|helios occupancy printed", spoken, re.I):
        assert not re.search(r"\s-\s+u\.s\s*$", spoken.strip(), re.I)


def test_hanging_for_instance_cannot_ship() -> None:
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = "NARRATOR\nHelios occupancy printed 14.2% in June 2026. For instance"
    packet.beats[5].finding_ids = [stamp.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"
    run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)
    spoken = _spoken(packet)
    assert not re.search(_HANGING, spoken, re.I), "asserting ship FAILS"


def test_on_screen_uses_stamp_print_not_topic_question() -> None:
    from onecrew.board import mute_test_shows_stamp, write_shot_list

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = TOPIC
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = packet.frames or write_shot_list(packet)
    cited = next(b for b in _voiced(packet) if stamp.id in b.finding_ids)
    shown = " ".join(f"{f.on_screen} {f.shot}" for f in shots if f.beat_id == cited.id) or (
        cited.frame or ""
    )
    assert _speech_norm(TOPIC) not in _speech_norm(shown), "asserting topic-question on_screen FAILS"
    assert re.search(r"14\.2|helios occupancy", shown, re.I)
    first = next(f for f in shots if f.beat_id == cited.id)
    assert mute_test_shows_stamp(first, [stamp], cited) is True


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
