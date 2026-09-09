"""Refuse 1-beat collapse, wrong/soft cover, title-chrome on_screen, dropped axis.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2% / $0/t / −18%).
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
HELIOS_LANE = "https://www.helios-wire.test/2026/06/helios-lane-18"
CHROME_2023 = "https://www.helios-wire.test/2023/04/helios-lease-chrome"

FEE_PRINT = "$0/t"
STAMP_TITLE = "Helios Occupancy Print – June 2026 – Analysis - U.S"
TITLE_CHROME = "# Helios Occupancy Print – Analysis - Desk"
CHROME_TITLE = "Helios Lease Chrome 2023 – Outlook – Analysis"
TWO_AXIS_TOPIC = "Did Helios occupancy and lane rates both hold the cited prints?"

_LIVE_TOPIC = (
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
    r"\$0/t|0 \$/t|−18%"
)
_THIN_HOLD = r"thin_after_repair|insufficient_cite_beats"


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


def _helios_lane_stamp() -> Finding:
    return _finding(
        fid="te-helios-lane-18",
        claim="Helios lane rates printed −18% in June 2026.",
        url=HELIOS_LANE,
        printed="−18%",
        title="Helios lane rates −18%",
    )


def _chrome_2023_title_only() -> Finding:
    return _finding(
        fid="te-helios-lease-chrome-2023",
        claim="Helios lease chrome hit in 2023.",
        url=CHROME_2023,
        printed=CHROME_TITLE,
        title=CHROME_TITLE,
        when="2023",
        note="Title-only chrome. Parallel URL on this row.",
    )


def _packet(
    pack: str,
    findings: list[Finding],
    vos: dict[str, str] | None = None,
    *,
    topic: str = "Named-entity cover must sit on the attached stamp",
) -> Packet:
    packet = Packet(
        id="oc-multibeat-cover-onscreen",
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


def _no_search(**_k):
    return SimpleNamespace(results=[])


def _voiced(packet: Packet) -> list[ScriptBeat]:
    return [b for b in packet.beats if (b.kind or "vo") != "heading"]


def _cite_faithful(packet: Packet) -> list[ScriptBeat]:
    from onecrew.script import _speech_norm

    out: list[ScriptBeat] = []
    for beat in _voiced(packet):
        if not beat.finding_ids:
            continue
        if not _speech_norm(beat.vo):
            continue
        out.append(beat)
    return out


def _reason(packet: Packet) -> str:
    return ((packet.receipt.hold_reason or "") if packet.receipt else "").lower()


def _shipped_ready(packet: Packet) -> bool:
    return bool(packet.receipt and packet.receipt.disposition == "READY")


def _run_sanitize_repair(packet: Packet) -> None:
    run_cite_recheck_loop(packet, search_fn=_no_search)
    sanitize_for_ship(packet)


def test_three_stamps_cannot_silently_ship_one_beat() -> None:
    """Pack with ≥3 grounded stamps must keep ≥3 cite-faithful beats or HOLD thin."""
    paused = _helios_stamp()
    occupancy = _helios_print_stamp()
    fee = _helios_fee_stamp()
    packet = _packet(
        _pack(
            (paused.claim, HELIOS_WIRE),
            (occupancy.claim, HELIOS_PRINT),
            (fee.claim, HELIOS_FEE),
        ),
        [paused, occupancy, fee],
    )
    packet.beats[5].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{occupancy.id}]"
    packet.beats[5].finding_ids = [occupancy.id]
    packet.beats[5].frame = "14.2%"
    _run_sanitize_repair(packet)
    beats_n = len(_cite_faithful(packet))
    reason = _reason(packet)
    if _shipped_ready(packet):
        assert beats_n >= 3, "asserting silent 1-beat ship FAILS"
    else:
        assert re.search(_THIN_HOLD, reason), "asserting silent 1-beat ship FAILS"
        assert beats_n < 3
    assert getattr(packet, "cite_recheck_attempts", 0) <= MAX_CITE_RECHECKS


def _assert_dated_print_not_soft_covered(packet: Packet, *, cover_id: str | None, wrong_id: str, vo: str) -> None:
    from onecrew.timeline import stamp_supports_prints

    spoken = " ".join(f"{b.vo} {b.frame or ''}" for b in _voiced(packet))
    dated = bool(re.search(r"\$0/t|0 \$/t|january 2026", spoken, re.I))
    cited = [fid for b in _voiced(packet) for fid in b.finding_ids]
    by_id = {f.id: f for f in (packet.receipt.findings if packet.receipt else [])}
    if dated and _shipped_ready(packet):
        assert wrong_id not in cited, "asserting soft-wrong ship FAILS"
        if cover_id:
            assert cover_id in cited, "asserting soft-wrong ship FAILS"
        rows = [by_id[fid] for fid in cited if fid in by_id]
        assert rows and all(stamp_supports_prints(vo, f) for f in rows), "asserting soft-wrong ship FAILS"
        return
    if dated:
        reason = _reason(packet)
        assert any(
            tok in reason
            for tok in (
                "cite-faithfulness",
                "soft-wrong",
                "covering",
                "thin_after_repair",
                "empty beat",
            )
        ), "asserting soft-wrong ship FAILS"
        assert wrong_id not in cited or (cover_id and cover_id in cited)
        return
    assert wrong_id not in cited or not _shipped_ready(packet)


def test_wrong_year_title_only_stamp_is_not_soft_cover() -> None:
    """Dated spoken print cannot stay on a title-only / wrong-year stamp."""
    wrong = _chrome_2023_title_only()
    cover = _helios_fee_stamp()
    vo = "Helios fee printed $0/t in January 2026."

    both = _packet(
        _pack((wrong.claim, CHROME_2023), (cover.claim, HELIOS_FEE)),
        [wrong, cover],
    )
    both.beats[5].vo = f"NARRATOR\n{vo} [{wrong.id}]"
    both.beats[5].finding_ids = [wrong.id]
    both.beats[5].frame = FEE_PRINT
    _run_sanitize_repair(both)
    _assert_dated_print_not_soft_covered(both, cover_id=cover.id, wrong_id=wrong.id, vo=vo)

    lone = _packet(_pack((wrong.claim, CHROME_2023)), [wrong])
    lone.beats[5].vo = f"NARRATOR\n{vo} [{wrong.id}]"
    lone.beats[5].finding_ids = [wrong.id]
    lone.beats[5].frame = FEE_PRINT
    _run_sanitize_repair(lone)
    _assert_dated_print_not_soft_covered(lone, cover_id=None, wrong_id=wrong.id, vo=vo)


def test_on_screen_uses_stamp_print_not_title_chrome() -> None:
    """Mute-test on_screen is the numeric print, not article-title / # chrome."""
    from onecrew.board import mute_test_shows_stamp, write_shot_list
    from onecrew.script import _speech_norm

    stamp = _helios_fee_stamp()
    packet = _packet(_pack((stamp.claim, HELIOS_FEE)), [stamp])
    packet.beats[5].vo = f"NARRATOR\nHelios fee printed $0/t in January 2026. [{stamp.id}]"
    packet.beats[5].finding_ids = [stamp.id]
    packet.beats[5].frame = TITLE_CHROME
    sanitize_for_ship(packet)
    attach_frames(packet, [], rails=Rails(parallel=False, vertex=False, imagen=False))
    shots = packet.frames or write_shot_list(packet)
    cited = next(b for b in _voiced(packet) if stamp.id in b.finding_ids)
    first = next(f for f in shots if f.beat_id == cited.id)
    shown = f"{first.on_screen} {cited.frame or ''}"
    assert _speech_norm(TITLE_CHROME) not in _speech_norm(shown), (
        "asserting title chrome on_screen FAILS"
    )
    assert _speech_norm(STAMP_TITLE) not in _speech_norm(first.on_screen), (
        "asserting title chrome on_screen FAILS"
    )
    assert not first.on_screen.strip().startswith("#"), "asserting title chrome on_screen FAILS"
    assert re.search(r"\$0/t|0 \$/t", first.on_screen), "asserting title chrome on_screen FAILS"
    assert mute_test_shows_stamp(first, [stamp], cited) is True


def test_two_axis_topic_cannot_silently_drop_one_axis() -> None:
    """Topic AND + stamps for both axes → speak both with covering ids, or HOLD the gap."""
    occupancy = _helios_print_stamp()
    lane = _helios_lane_stamp()
    packet = _packet(
        _pack((occupancy.claim, HELIOS_PRINT), (lane.claim, HELIOS_LANE)),
        [occupancy, lane],
        topic=TWO_AXIS_TOPIC,
    )
    packet.beats[5].vo = (
        f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. [{occupancy.id}]"
    )
    packet.beats[5].finding_ids = [occupancy.id]
    packet.beats[5].frame = "14.2%"
    _run_sanitize_repair(packet)
    spoken = " ".join(b.vo for b in _voiced(packet))
    cited = {fid for b in _voiced(packet) for fid in b.finding_ids}
    occ_ok = bool(re.search(r"14\.2|occupancy", spoken, re.I)) and occupancy.id in cited
    lane_ok = bool(re.search(r"−18%|-18%|lane rates", spoken, re.I)) and lane.id in cited
    if _shipped_ready(packet):
        assert occ_ok and lane_ok, "asserting silent single-axis ship FAILS"
    else:
        reason = _reason(packet)
        assert re.search(r"lane rates|missing.{0,24}axis|cannot cover", reason, re.I), (
            "asserting silent single-axis ship FAILS"
        )


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []


