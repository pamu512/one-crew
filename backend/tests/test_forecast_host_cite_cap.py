"""Forecast-theater refuse, host reuse on Parallel/cite rows, per-beat cite cap.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2%). Production
must stay free of these names and of live grocery topic strings.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, RoomGrade, ScriptBeat, TimelineMapRow
from onecrew.room import grade_room, make_grade_artifact
from onecrew.timeline import cap_url_reuse, url_host

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
MERIDIAN_A = "https://www.meridian-desk.test/insights/campus-power-2026"
MERIDIAN_B = "https://www.meridian-desk.test/insights/campus-leases-2026"
MERIDIAN_C = "https://www.meridian-desk.test/insights/campus-survey-q2"
MERIDIAN_D = "https://www.meridian-desk.test/insights/campus-survey-q3"
FRED_USREC = "https://fred.stlouisfed.org/series/USREC"
FRED_SAHM = "https://fred.stlouisfed.org/series/SAHMREALTIME"

_LIVE_TOPIC = (
    r"grocery|usda|ers\.usda|food[- ]at[- ]home|"
    r"office[- ]vacancy|cushman|yardi|\baxios\b|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b"
)
_FIXTURE = r"helios|meridian-desk|meridian desk|\b14\.2\b"

_REALIZED_TELL = (
    "Host-only desk read. Cite-faithful realized prints. No forecast theater."
)


def _finding(
    *,
    fid: str,
    claim: str,
    url: str,
    stamp: str = "grounded",
    series: str = "",
    printed: str | None = None,
    when: str = "June 2026",
    title: str = "",
) -> Finding:
    return Finding(
        id=fid,
        claim=claim,
        stamp=stamp,
        title=title or claim,
        series=series or stamp,
        print=printed if printed is not None else claim,
        when=when,
        parallel_url=url,
        parallel_status="hit",
        note="Parallel URL on this row.",
    )


def _helios_print() -> Finding:
    return _finding(
        fid="helios-occupancy-2026-06",
        claim="Helios occupancy printed 14.2% in June 2026.",
        url=HELIOS_PRINT,
        printed="14.2%",
        title="Helios occupancy 14.2%",
    )


def _helios_lease() -> Finding:
    return _finding(
        fid="helios-paused-2026-06",
        claim="Helios paused campus leases in June 2026.",
        url=HELIOS_WIRE,
        title="Helios paused campus leases",
    )


def _meridian(fid: str, url: str, claim: str, printed: str | None = None) -> Finding:
    return _finding(
        fid=fid,
        claim=claim,
        url=url,
        printed=printed or claim,
        title="Campus power survey",
        when="2026",
    )


def _packet(pack: str, findings: list[Finding], *, tell: str | None = None) -> Packet:
    packet = Packet(
        id="oc-forecast-host-cite-cap",
        topic="Named-entity cover must sit on the attached stamp",
        hook="Named-entity cover must sit on the attached stamp",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell=tell or _REALIZED_TELL,
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


def test_forecast_spine_vo_drops_or_holds_when_tell_forbids_theater() -> None:
    from onecrew.script import _assemble

    printed = _helios_print()
    pack = _pack((printed.claim, HELIOS_PRINT))
    packet = _packet(pack, [printed])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": (
                        "Helios occupancy printed 14.2% in June 2026. "
                        "The June outlook forecast a 14.2% increase."
                    ),
                    "eyes": "card",
                    "finding_ids": [printed.id],
                }
            }
        ),
    )
    spoken = "".join(f"{b.vo} {b.frame or ''}" for b in written.beats)
    theater = bool(re.search(r"forecasts?\s+from|outlook\s+forecast", spoken, re.I))
    if theater:
        reason = ((written.receipt.hold_reason or "") if written.receipt else "").lower()
        assert written.status == "hold"
        assert "forecast theater" in reason
        assert "cite-repair loop exhausted" not in reason or written.cite_recheck_attempts > 3
        return
    turn = next(b for b in written.beats if b.id == "turn")
    assert printed.id in turn.finding_ids
    assert re.search(r"14\.2|printed", turn.vo, re.I)


def test_room_ship_cannot_bypass_forecast_theater() -> None:
    printed = _helios_print()
    packet = _packet(_pack((printed.claim, HELIOS_PRINT)), [printed])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 5 — turn\n"
        "00:80–01:00\n"
        "NARRATOR\n"
        f"Helios occupancy printed 14.2% in June 2026. The June outlook forecast a 14.2% increase. [{printed.id}]\n"
    )
    packet.beats[4].vo = (
        f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. The June outlook forecast a 14.2% increase. [{printed.id}]"
    )
    packet.beats[4].finding_ids = [printed.id]
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert (grade.recut_detail or "").lower() == "forecast theater"


def test_grounded_parallel_rows_obey_host_reuse_cap() -> None:
    rows = [
        _meridian(f"meridian-survey-{i}", url, f"A campus-power survey row {i} tracked buildout.")
        for i, url in enumerate((MERIDIAN_A, MERIDIAN_B, MERIDIAN_C, MERIDIAN_D), start=1)
    ]
    kept = cap_url_reuse(rows, pairs=[])
    hosts = Counter(url_host(f.parallel_url or "") for f in kept if (f.parallel_url or "").strip())
    assert hosts.get("meridian-desk.test", 0) <= 2


def test_closed_series_same_host_survives_reuse_cap() -> None:
    usrec = _finding(
        fid="usrec-july-2026",
        claim="USREC=0 (July 2026)",
        url=FRED_USREC,
        series="USREC",
        printed="0",
        when="July 2026",
        title="USREC",
    )
    sahm = _finding(
        fid="sahm-july-2026",
        claim="Sahm −0.03 in July 2026",
        url=FRED_SAHM,
        series="SAHMREALTIME",
        printed="−0.03",
        when="July 2026",
        title="SAHMREALTIME",
    )
    kept = cap_url_reuse([usrec, sahm], pairs=[])
    assert {f.id for f in kept} == {usrec.id, sahm.id}


def test_attach_prefers_covering_host_over_grounded_survey_reuse() -> None:
    from onecrew.script import _assemble

    helios = _helios_print()
    surveys = [
        _meridian(f"meridian-survey-{i}", url, "A campus-power survey tracked buildout and inflation.")
        for i, url in enumerate((MERIDIAN_A, MERIDIAN_B, MERIDIAN_C), start=1)
    ]
    pack = _pack((helios.claim, HELIOS_PRINT), *[(f.claim, f.parallel_url or "") for f in surveys])
    packet = _packet(pack, [helios, *surveys])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "card",
                    "finding_ids": [s.id for s in surveys],
                }
            }
        ),
    )
    turn = next(b for b in written.beats if b.id == "turn")
    cited = [f for f in written.receipt.findings if f.id in turn.finding_ids]
    assert cited
    assert any(url_host(f.parallel_url or "") == "helios-wire.test" for f in cited)
    assert sum(1 for f in cited if url_host(f.parallel_url or "") == "meridian-desk.test") <= 2
    assert len(turn.finding_ids) <= 2


def test_beat_cannot_attach_whole_series_bag() -> None:
    from onecrew.script import _assemble

    helios = _helios_print()
    bag = [
        _finding(
            fid=f"helios-print-{i}",
            claim=f"Helios occupancy printed 14.2% on card {i}.",
            url=f"https://www.helios-wire.test/2026/06/helios-occupancy-{i}",
            printed="14.2%",
            title=f"Helios occupancy card {i}",
        )
        for i in range(1, 11)
    ]
    pack = _pack((helios.claim, HELIOS_PRINT), *[(f.claim, f.parallel_url or "") for f in bag])
    packet = _packet(pack, [helios, *bag])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "card",
                    "finding_ids": [f.id for f in bag],
                }
            }
        ),
    )
    beat = next(b for b in written.beats if b.id == "cold-open")
    assert 1 <= len(beat.finding_ids) <= 2
    cited = [f for f in written.receipt.findings if f.id in beat.finding_ids]
    assert any("14.2" in f"{f.print} {f.claim}" for f in cited)


def test_room_ship_cannot_bypass_over_cite() -> None:
    helios = _helios_print()
    bag = [
        _finding(
            fid=f"helios-print-{i}",
            claim=f"Helios occupancy printed 14.2% on card {i}.",
            url=f"https://www.helios-wire.test/2026/06/helios-occupancy-{i}",
            printed="14.2%",
            title=f"Helios occupancy card {i}",
        )
        for i in range(1, 11)
    ]
    packet = _packet(_pack(*[(f.claim, f.parallel_url or "") for f in [helios, *bag]]), [helios, *bag])
    ids = [f.id for f in bag]
    cites = " ".join(f"[{fid}]" for fid in ids)
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 1 — cold-open\n"
        "00:00–00:20\n"
        "NARRATOR\n"
        f"Helios occupancy printed 14.2% in June 2026. {cites}\n"
    )
    packet.beats[0].vo = f"NARRATOR\nHelios occupancy printed 14.2% in June 2026. {cites}"
    packet.beats[0].finding_ids = ids
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert (grade.recut_detail or "").lower() == "over-cite"


def test_room_ship_cannot_bypass_host_overreuse() -> None:
    rows = [
        _meridian(f"meridian-survey-{i}", url, f"A campus-power survey row {i} tracked buildout.")
        for i, url in enumerate((MERIDIAN_A, MERIDIAN_B, MERIDIAN_C, MERIDIAN_D), start=1)
    ]
    packet = _packet(_pack(*[(f.claim, f.parallel_url or "") for f in rows]), rows)
    slots = (0, 4, 5, 7)
    parts = ["Timed VO · youtube · one_time_short_episode\n"]
    for i, (slot, finding) in enumerate(zip(slots, rows)):
        packet.beats[slot].vo = f"NARRATOR\n{finding.claim} [{finding.id}]"
        packet.beats[slot].finding_ids = [finding.id]
        parts.append(
            f"BEAT {i + 1} — {packet.beats[slot].id}\n"
            f"NARRATOR\n{finding.claim} [{finding.id}]\n"
        )
    packet.script = "\n".join(parts)
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert (grade.recut_detail or "").lower() == "host reuse"


def test_cite_repair_strips_forecast_theater_or_holds() -> None:
    printed = _helios_print()
    packet = _packet(_pack((printed.claim, HELIOS_PRINT)), [printed])
    packet.beats[4].vo = (
        "NARRATOR\nHelios occupancy printed 14.2% in June 2026. The June outlook forecast a 14.2% increase."
    )
    packet.beats[4].finding_ids = [printed.id]
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "room recut other: forecast theater"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    spoken = "".join(f"{b.vo} {b.frame or ''}" for b in packet.beats)
    theater = bool(re.search(r"forecasts?\s+from|outlook\s+forecast", spoken, re.I))
    if theater:
        reason = (packet.receipt.hold_reason or "").lower()
        assert packet.status == "hold"
        assert "forecast theater" in reason or "cite-faithfulness" in reason
        assert "cite-repair loop exhausted" not in reason or packet.cite_recheck_attempts > 3
        return
    assert result.ok or packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    turn = next((b for b in packet.beats if b.id == "turn"), None)
    if turn is not None:
        assert not re.search(r"forecasts?\s+from|outlook\s+forecast", turn.vo, re.I)


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
