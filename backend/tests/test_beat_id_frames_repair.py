"""Packet beat ids, covering cites, frames, and cite-repair on HOLD.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2% / 8.6%).
Production code and this file must stay free of live topic strings.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, rebuild_timed_vo, run_cite_recheck_loop
from onecrew.models import (
    CollisionRow,
    Finding,
    Packet,
    Receipt,
    RoomGrade,
    ScriptBeat,
    ShotFrame,
    TimelineMapRow,
)
from onecrew.receipt import attach_frames
from onecrew.room import run_room_loop

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
MERIDIAN_DESK = "https://www.meridian-desk.test/insights/campus-power-2026"
CHROME_URL = "https://www.meridian-desk.test/insights/last-verified-2026-06"

_PACK_SLOT_VOCAB = frozenset(
    {"cold-open", "promise", "gdp", "labor", "turn", "complication", "receipt", "close"}
)

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
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b|\b8\.6\b"


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
        title="Helios occupancy 14.2%",
    )


def _last_verified_chrome() -> Finding:
    return _finding(
        fid="te-last-verified-2026-06",
        claim="Last verified June 2026.",
        url=CHROME_URL,
        printed="Last verified June 2026",
        title="Last verified June 2026",
        note="Index chrome. Parallel URL on this row.",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-beat-id-frames-repair",
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


def _no_search(**_k):
    return SimpleNamespace(results=[])


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").lower()


def _voiced(packet: Packet) -> list[ScriptBeat]:
    return [b for b in packet.beats if (b.kind or "vo") != "heading"]


def test_sanitize_rewrites_packet_beat_ids_not_just_script_headers() -> None:
    """Script-header-only rewrite while ids stay gdp/labor must fail."""
    from onecrew.script import sanitize_for_ship

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.frames = [
        ShotFrame(
            id=f"shot-001-{packet.beats[2].id}",
            shot="14.2% June on the card.",
            beat_id=packet.beats[2].id,
            duration_s=20,
            on_screen="",
        )
    ]
    packet.collisions = [
        CollisionRow(beat_id=packet.beats[3].id, collision="missing"),
    ]
    sanitize_for_ship(packet)
    ids = [b.id for b in _voiced(packet)]
    assert ids
    assert not (_PACK_SLOT_VOCAB & set(ids))
    assert all(re.fullmatch(r"beat\d+", bid) for bid in ids)
    assert [b.scene for b in _voiced(packet)] == [f"BEAT {i}" for i in range(1, 9)]
    assert all(re.fullmatch(r"beat\d+", f.beat_id) for f in packet.frames)
    assert not (_PACK_SLOT_VOCAB & {f.beat_id for f in packet.frames})
    assert all(re.fullmatch(r"beat\d+", row.beat_id) for row in packet.collisions)
    assert not (_PACK_SLOT_VOCAB & {row.beat_id for row in packet.collisions})


def test_rebuild_timed_vo_rewrites_ids_not_only_headers() -> None:
    """rebuild_timed_vo currently rewrites BEAT n headers while leftover ids stay."""
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.frames = [
        ShotFrame(id="shot-gdp", shot="card", beat_id="gdp", duration_s=20),
    ]
    rebuild_timed_vo(packet)
    ids = [b.id for b in _voiced(packet)]
    assert all(re.fullmatch(r"beat\d+", bid) for bid in ids)
    assert not (_PACK_SLOT_VOCAB & set(ids))
    assert all(re.fullmatch(r"beat\d+", f.beat_id) for f in packet.frames)


def test_spoken_print_reattaches_covering_stamp_not_last_verified_chrome() -> None:
    """Spoken 14.2% cannot soft-cover on te-last-verified chrome when a covering stamp exists."""
    from onecrew.script import _assemble, sanitize_for_ship

    chrome = _last_verified_chrome()
    covering = _helios_print_stamp()
    packet = _packet(
        _pack((chrome.claim, CHROME_URL), (covering.claim, HELIOS_PRINT)),
        [chrome, covering],
    )
    written = _assemble(
        packet,
        _eight_units(
            {
                "complication": {
                    "vo": "The print fell 14.2% in June 2026.",
                    "eyes": "14.2% June on the card.",
                    "finding_ids": [chrome.id],
                }
            }
        ),
    )
    sanitize_for_ship(written)
    beat = next(
        b
        for b in _voiced(written)
        if re.search(r"14\.2|helios occupancy", f"{b.vo} {b.frame or ''}", re.I)
        or chrome.id in b.finding_ids
        or covering.id in b.finding_ids
    )
    spoken = f"{beat.vo} {beat.frame or ''}"
    if re.search(r"14\.2", spoken):
        cited = [f for f in written.receipt.findings if f.id in beat.finding_ids]
        blobs = " ".join(f"{f.claim} {f.print} {f.title} {f.note}" for f in cited)
        assert "14.2" in blobs
        assert chrome.id not in beat.finding_ids
        assert covering.id in beat.finding_ids
    else:
        assert chrome.id not in beat.finding_ids
        assert covering.id not in beat.finding_ids or not re.search(r"14\.2", spoken)


def test_wrong_cover_is_cite_faithfulness_not_cites_nothing() -> None:
    """finding_ids present but wrong must not mint 'cites nothing'."""
    from onecrew.script import _assemble, sanitize_for_ship

    chrome = _last_verified_chrome()
    covering = _helios_print_stamp()
    packet = _packet(
        _pack((chrome.claim, CHROME_URL), (covering.claim, HELIOS_PRINT)),
        [chrome, covering],
    )
    written = _assemble(
        packet,
        _eight_units(
            {
                "complication": {
                    "vo": "The print fell 14.2% in June 2026.",
                    "eyes": "14.2% June on the card.",
                    "finding_ids": [chrome.id],
                }
            }
        ),
    )
    sanitize_for_ship(written)
    reason = _reason(written)
    sourced = [
        b
        for b in _voiced(written)
        if chrome.id in b.finding_ids or covering.id in b.finding_ids or re.search(r"14\.2", b.vo)
    ]
    assert sourced
    assert any(b.finding_ids for b in sourced)
    assert "cites nothing" not in reason
    if written.receipt and written.receipt.disposition == "HOLD":
        assert "cite-faithfulness" in reason


def test_empty_frames_on_hold_packet_materialize_stamp_print() -> None:
    """Empty frames array on a HOLD packet with beats is a defect."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list
    from onecrew.models import Rails
    from onecrew.script import sanitize_for_ship

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = ""
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 6\n"
        "ACTION: Helios occupancy printed 14.2% in June 2026.\n"
        "NARRATOR\n"
        f"Helios occupancy printed 14.2% in June 2026. [{stamp.id}]\n"
    )
    packet.frames = []
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    assert packet.frames, "HOLD packet with beats cannot ship an empty frames array"
    assert any(f.on_screen or f.shot for f in packet.frames)
    shots = packet.frames or write_shot_list(packet)
    cited = next(b for b in _voiced(packet) if stamp.id in b.finding_ids)
    shown = " ".join(f"{f.on_screen} {f.shot}" for f in shots if f.beat_id == cited.id) or (
        cited.frame or ""
    )
    assert re.search(r"14\.2|helios occupancy", shown, re.I)
    first = next(f for f in shots if f.beat_id == cited.id)
    assert mute_test_shows_stamp(first, [stamp], cited) is True
    assert first.footage != "sourced" or (first.footage_url or "").startswith("http")


def test_cite_faithfulness_hold_increments_attempts() -> None:
    """cite-faithfulness / cites-nothing HOLD cannot finish with attempts=0."""
    chrome = _last_verified_chrome()
    covering = _helios_print_stamp()
    packet = _packet(
        _pack((chrome.claim, CHROME_URL), (covering.claim, HELIOS_PRINT)),
        [chrome, covering],
    )
    packet.beats[5].vo = "NARRATOR\nThe print fell 14.2% in June 2026."
    packet.beats[5].finding_ids = [chrome.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "complication cites nothing in the pack"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    if result.ok and packet.receipt and packet.receipt.disposition == "READY":
        assert "cites nothing" not in _reason(packet)
    else:
        reason = _reason(packet)
        assert "cite-repair loop exhausted" in reason or "cite-faithfulness" in reason
        assert "cite-repair loop exhausted" not in reason or packet.cite_recheck_attempts > 3


def test_room_cites_nothing_hold_fires_cite_repair(monkeypatch) -> None:
    """Room HOLD 'cites nothing' / covering miss must run cite-repair (attempts>=1)."""
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.cite_repair import run_cite_recheck_loop as real_repair
    from onecrew.models import Rails
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    chrome = _last_verified_chrome()
    covering = _helios_print_stamp()
    pack = _pack((chrome.claim, CHROME_URL), (covering.claim, HELIOS_PRINT))
    repair_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = pack
        packet.task_spine = pack
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="READY",
            findings=[chrome, covering],
            timeline_map=[
                TimelineMapRow(thesis=chrome.claim, url=CHROME_URL, finding_id=chrome.id),
                TimelineMapRow(thesis=covering.claim, url=HELIOS_PRINT, finding_id=covering.id),
            ],
        )
        return receipt, [], [], pack

    def tracking_repair(packet, **kwargs):
        repair_calls["n"] += 1
        kwargs.setdefault("search_fn", _no_search)
        return real_repair(packet, **kwargs)

    eight = (
        '[{"id":"cold-open","vo":"The title stays a question.","eyes":"card","finding_ids":[]},'
        '{"id":"promise","vo":"The title stays a question.","eyes":"pack","finding_ids":[]},'
        '{"id":"gdp","vo":"Those are not the same object.","eyes":"card","finding_ids":[]},'
        '{"id":"labor","vo":"Near is not a switch.","eyes":"card","finding_ids":[]},'
        '{"id":"turn","vo":"The title stays a question.","eyes":"hold","finding_ids":[]},'
        '{"id":"complication","vo":"The print fell 14.2% in June 2026.","eyes":"14.2% June on the card.","finding_ids":["te-last-verified-2026-06"]},'
        '{"id":"receipt","vo":"Near is not a switch.","eyes":"board","finding_ids":[]},'
        '{"id":"close","vo":"Near is not a switch.","eyes":"close","finding_ids":[]}]'
    )

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.run_cite_recheck_loop", tracking_repair)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", real_write_vo)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", lambda _p: eight)
    monkeypatch.setattr(
        "onecrew.room.run_adk_room",
        lambda _a: RoomGrade(
            vote="recut", recut_reason="other", recut_detail="complication cites nothing"
        ),
    )
    monkeypatch.setattr("onecrew.agent.shift._board", lambda p, _r: p.frames)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr(
        "onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[])
    )
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
    ids = [b.id for b in _voiced(packet)]
    if ids:
        assert not (_PACK_SLOT_VOCAB & set(ids))
    if packet.beats:
        assert packet.frames, "HOLD/ship packet with beats cannot keep empty frames"


def test_room_loop_hold_sanitizes_leftover_ids() -> None:
    """HOLD persist must rewrite leftover beat ids, not only BEAT n headers."""
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 6\n"
        "NARRATOR\n"
        f"Helios occupancy printed 14.2% in June 2026. [{stamp.id}]\n"
    )
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    loop = run_room_loop(
        packet,
        research=lambda _ask=None: None,
        rewrite=lambda: None,
        grader=lambda _a: RoomGrade(
            vote="recut", recut_reason="other", recut_detail="complication cites nothing"
        ),
        parallel_already=1,
    )
    assert loop.disposition == "HOLD"
    ids = [b.id for b in _voiced(packet)]
    assert ids
    assert not (_PACK_SLOT_VOCAB & set(ids))
    assert all(re.fullmatch(r"beat\d+", bid) for bid in ids)


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
