"""Pack-slot ids, ACTION chrome VO, thin title-reads, soft close, ACTION-only mute.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2% / 9.1%).
Production code and this file must stay free of live topic strings.
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
HELIOS_CAMPUS = "https://www.helios-wire.test/2026/06/helios-north-campus-14-2"
NATIONAL_PRINT = "https://www.meridian-desk.test/insights/national-occupancy-2026"
MERIDIAN_DESK = "https://www.meridian-desk.test/insights/campus-power-2026"

STAMP_TITLE = "Helios Occupancy Print – June 2026 – Analysis"
ACTION_CARD = "June 2026: Campus occupancy 14.2% (Desk)"
TITLE_CARD = "Campus vs. National Print"

_PACK_SLOT_VOCAB = frozenset(
    {"cold-open", "promise", "gdp", "labor", "turn", "complication", "receipt", "close"}
)

_LIVE_TOPIC = (
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b|"
    r"\blithium\b|\biea\b|"
    r"red[- ]sea|xeneta|freightos|"
    r"\boag\b|atlanta|fort lauderdale|airfare|"
    r"grocery|power[- ]grid|interconnection|"
    r"airline[- ]ticket|us[- ]airline"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b|\b9\.1\b"


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


def _helios_campus_stamp() -> Finding:
    return _finding(
        fid="te-helios-north-campus-14-2",
        claim="Helios north campus occupancy printed 14.2% in June 2026.",
        url=HELIOS_CAMPUS,
        printed="14.2%",
        title="Helios north campus occupancy 14.2%",
        note="Local campus print. Parallel URL on this row.",
    )


def _national_occupancy_stamp() -> Finding:
    return _finding(
        fid="te-national-occupancy-2026-06",
        claim="National occupancy printed 9.1% in June 2026.",
        url=NATIONAL_PRINT,
        printed="9.1%",
        title="National occupancy 9.1%",
        note="Nationwide aggregate print. Parallel URL on this row.",
    )


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-slot-chrome-mute-close",
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


def _leftover_in_labels(packet: Packet) -> list[str]:
    blob = " ".join(
        [
            packet.script or "",
            *(f"{b.id} {b.scene}" for b in packet.beats),
            *(getattr(f, "beat_id", "") for f in packet.frames),
        ]
    ).lower()
    return [tok for tok in sorted(_PACK_SLOT_VOCAB) if re.search(rf"\b{re.escape(tok)}\b", blob)]


def test_leftover_pack_slot_beat_ids_rewritten_before_ship() -> None:
    """Leftover recession-slot ids cannot ship as beat labels on a non-matching topic."""
    from onecrew.script import _assemble, sanitize_for_ship

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Helios occupancy printed 14.2% in June 2026.",
                    "finding_ids": [stamp.id],
                },
                "gdp": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Helios occupancy printed 14.2% in June 2026.",
                    "finding_ids": [stamp.id],
                },
                "labor": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Helios occupancy printed 14.2% in June 2026.",
                    "finding_ids": [stamp.id],
                },
                "promise": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Helios occupancy printed 14.2% in June 2026.",
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    sanitize_for_ship(written)
    leftover = _leftover_in_labels(written)
    assert leftover == []
    ids = [b.id for b in written.beats if (b.kind or "vo") != "heading"]
    assert ids
    assert not (_PACK_SLOT_VOCAB & set(ids))
    assert all(re.fullmatch(r"beat\d+", bid) or bid not in _PACK_SLOT_VOCAB for bid in ids)
    for beat in written.beats:
        assert not re.search(
            r"BEAT\s+\d+\s+—\s+(?:cold-open|promise|gdp|labor|turn|complication|receipt|close)\b",
            beat.scene or "",
            re.I,
        )


def test_renaming_leftover_slots_to_other_leftover_vocab_fails() -> None:
    """gdp→labor / promise→close is still leftover pack-slot vocabulary."""
    from onecrew.script import sanitize_for_ship

    stamp = _helios_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_WIRE)), [stamp])
    packet.beats[2].id = "labor"
    packet.beats[2].scene = "BEAT 3 — labor"
    packet.beats[3].id = "receipt"
    packet.beats[3].scene = "BEAT 4 — receipt"
    sanitize_for_ship(packet)
    assert _leftover_in_labels(packet) == []
    assert not (_PACK_SLOT_VOCAB & {b.id for b in packet.beats})


def test_action_chrome_and_source_tag_stripped_from_vo() -> None:
    """ACTION / (Source) / title-card after the cite stay off the narrator line."""
    from onecrew.script import _assemble, _vo_lines

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": (
                        "Helios occupancy printed 14.2% in June 2026. "
                        f"{ACTION_CARD}. {TITLE_CARD}."
                    ),
                    "eyes": ACTION_CARD,
                    "finding_ids": [stamp.id],
                }
            }
        ),
    )
    turn = written.beats[4]
    spoken = _vo_lines(turn.vo)
    assert ACTION_CARD not in spoken
    assert TITLE_CARD not in spoken
    assert not re.search(r"\(Desk\)|\(Source\)", spoken, re.I)
    assert stamp.id in turn.finding_ids
    assert re.search(r"14\.2|helios occupancy", spoken, re.I)
    assert ACTION_CARD in (turn.frame or "")


def test_room_refuses_action_chrome_left_in_vo() -> None:
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5\n"
        "00:80–01:00\n"
        f"ACTION: {ACTION_CARD}\n"
        "NARRATOR\n"
        f"Helios occupancy printed 14.2% in June 2026. [{stamp.id}] "
        f"{ACTION_CARD}. {TITLE_CARD}.\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}] "
        f"{ACTION_CARD}. {TITLE_CARD}."
    )
    packet.beats[4].frame = ACTION_CARD
    packet.beats[4].finding_ids = [stamp.id]
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert "cite-faithfulness" in (grade.recut_detail or "").lower()


def test_thin_title_read_beat_dropped_or_expanded() -> None:
    """Mute-off VO cannot ship as a verbatim stamp-title read."""
    from onecrew.script import _assemble, _vo_lines

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "Helios occupancy printed 14.2% in June 2026.",
                    "finding_ids": [stamp.id],
                },
                "turn": {
                    "vo": STAMP_TITLE,
                    "eyes": STAMP_TITLE,
                    "finding_ids": [stamp.id],
                },
            }
        ),
    )
    result = run_cite_recheck_loop(written, search_fn=_no_search)
    assert written.cite_recheck_attempts <= MAX_CITE_RECHECKS
    spoken_mid = [
        _vo_lines(b.vo)
        for b in written.beats
        if (b.kind or "vo") != "heading" and b is not written.beats[0]
    ]
    assert STAMP_TITLE not in spoken_mid
    remaining = [b for b in written.beats if (b.kind or "vo") != "heading"]
    assert remaining
    mid = [
        re.sub(r"\s+", " ", re.sub(r"\[[^\]]+\]", "", _vo_lines(b.vo))).strip()
        for b in remaining[1:]
    ]
    assert STAMP_TITLE not in mid
    if result.ok and written.receipt and written.receipt.disposition == "READY":
        for body in mid:
            assert body != STAMP_TITLE
            assert len(body.split()) >= 6 or not body


def test_verbatim_stamp_title_vo_cannot_ship() -> None:
    from onecrew.script import is_thin_title_read_vo

    stamp = _helios_print_stamp()
    assert is_thin_title_read_vo(STAMP_TITLE, [stamp]) is True
    assert is_thin_title_read_vo(stamp.claim, [stamp]) is False


def test_broad_conclusion_attaches_covering_stamp_not_narrow() -> None:
    """Nationwide/aggregate close cannot soft-cover on a local stamp when a covering row exists."""
    from onecrew.script import _assemble

    narrow = _helios_campus_stamp()
    covering = _national_occupancy_stamp()
    packet = _packet(
        _pack((narrow.claim, HELIOS_CAMPUS), (covering.claim, NATIONAL_PRINT)),
        [narrow, covering],
    )
    written = _assemble(
        packet,
        _eight_units(
            {
                "close": {
                    "vo": "In aggregate, occupancy did not fall across the country.",
                    "eyes": "In aggregate, occupancy did not fall across the country.",
                    "finding_ids": [narrow.id],
                }
            }
        ),
    )
    close = written.beats[-1]
    if written.receipt and written.receipt.disposition == "READY":
        assert covering.id in close.finding_ids
        assert narrow.id not in close.finding_ids
    else:
        reason = ((written.receipt.hold_reason if written.receipt else "") or "").lower()
        assert "cite-faithfulness" in reason or "empty beat" in reason


def test_narrow_soft_cover_on_broad_close_cannot_pass_room() -> None:
    narrow = _helios_campus_stamp()
    covering = _national_occupancy_stamp()
    packet = _packet(
        _pack((narrow.claim, HELIOS_CAMPUS), (covering.claim, NATIONAL_PRINT)),
        [narrow, covering],
    )
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 8\n"
        "NARRATOR\n"
        f"In aggregate, occupancy did not fall across the country. [{narrow.id}]\n"
    )
    packet.beats[-1].vo = (
        f"NARRATOR\nIn aggregate, occupancy did not fall across the country. [{narrow.id}]"
    )
    packet.beats[-1].finding_ids = [narrow.id]
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert "cite-faithfulness" in (grade.recut_detail or "").lower()


def test_repair_reattaches_covering_stamp_for_broad_close() -> None:
    narrow = _helios_campus_stamp()
    covering = _national_occupancy_stamp()
    packet = _packet(
        _pack((narrow.claim, HELIOS_CAMPUS), (covering.claim, NATIONAL_PRINT)),
        [narrow, covering],
    )
    packet.beats[-1].vo = (
        "NARRATOR\nIn aggregate, occupancy did not fall across the country."
    )
    packet.beats[-1].finding_ids = [narrow.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: cite-faithfulness"
    packet.status = "hold"
    run_cite_recheck_loop(packet, search_fn=_no_search)
    close = packet.beats[-1] if packet.beats else None
    if packet.receipt and packet.receipt.disposition == "READY" and close is not None:
        assert covering.id in close.finding_ids
        assert narrow.id not in close.finding_ids
    else:
        reason = ((packet.receipt.hold_reason if packet.receipt else "") or "").lower()
        assert "cite-faithfulness" in reason or "empty beat" in reason


def test_mute_test_requires_on_screen_or_frame_not_action_shot() -> None:
    """Mute-test is the stamp print on on_screen/frame, not invented ACTION chrome."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list
    from onecrew.models import ShotFrame

    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.beats[0].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]"
    packet.beats[0].finding_ids = [stamp.id]
    packet.beats[0].frame = ""
    fake = ShotFrame(
        id="shot-001-x",
        shot=ACTION_CARD,
        source_refs=[stamp.parallel_url or ""],
        beat_id=packet.beats[0].id,
        kind="infographic",
        footage="missing",
        on_screen="",
    )
    assert mute_test_shows_stamp(fake, [stamp], packet.beats[0]) is False
    shots = write_shot_list(packet)
    first = shots[0]
    assert first.footage == "missing"
    shown = f"{getattr(first, 'on_screen', '')} {packet.beats[0].frame or ''}"
    assert re.search(r"14\.2|helios occupancy", shown, re.I)
    assert mute_test_shows_stamp(first, [stamp], packet.beats[0]) is True
    assert first.footage != "sourced" or (first.footage_url or "").startswith("http")


def test_action_only_mute_pass_is_refused() -> None:
    from onecrew.board import mute_test_shows_stamp
    from onecrew.models import ShotFrame

    stamp = _helios_print_stamp()
    beat = ScriptBeat(
        id="beat1",
        start="00:00",
        duration_s=20,
        vo=f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}]",
        finding_ids=[stamp.id],
        frame="",
    )
    shot = ShotFrame(
        id="shot-001-beat1",
        shot="14.2% June on the card.",
        source_refs=[],
        beat_id="beat1",
        kind="infographic",
        footage="missing",
        on_screen="",
    )
    assert mute_test_shows_stamp(shot, [stamp], beat) is False


def test_room_loop_holds_unclean_action_chrome() -> None:
    stamp = _helios_print_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_PRINT)), [stamp])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5\n"
        f"ACTION: {ACTION_CARD}\n"
        "NARRATOR\n"
        f"Helios occupancy printed 14.2% in June 2026. [{stamp.id}] {TITLE_CARD}.\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{stamp.id}] {TITLE_CARD}."
    )
    packet.beats[4].frame = ACTION_CARD
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


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
