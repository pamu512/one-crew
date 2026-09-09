"""Empty-beat collapse, host reuse cap, thin comparative VO.

Fixtures use invented orgs/prints (Helios / Meridian Desk / 14.2%). Production
code must stay free of these names and of live heat-pump / office-vacancy strings.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.foundry import complete_print
from onecrew.models import Finding, Packet, Receipt, RoomGrade, ScriptBeat, TimelineMapRow
from onecrew.room import grade_room, make_grade_artifact
from onecrew.timeline import cap_url_reuse, url_host

HELIOS_WIRE = "https://www.helios-wire.test/2026/06/helios-paused-leases"
HELIOS_PRINT = "https://www.helios-wire.test/2026/06/helios-occupancy-14-2"
MERIDIAN_A = "https://www.meridian-desk.test/insights/campus-power-2026"
MERIDIAN_B = "https://www.meridian-desk.test/insights/campus-leases-2026"
MERIDIAN_C = "https://www.meridian-desk.test/insights/campus-survey-q2"
MERIDIAN_D = "https://www.meridian-desk.test/insights/campus-survey-q3"

_LIVE_TOPIC = (
    r"office[- ]vacancy|cushman|yardi|\baxios\b|\bamazon\b|"
    r"data[- ]centers?|stargate|\bmicrosoft\b|\bguardian\b|"
    r"heat[- ]pumps?|\bboilers?\b|\beciu\b"
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


def _meridian(fid: str, url: str, claim: str) -> Finding:
    return _finding(fid=fid, claim=claim, url=url, title="Campus power survey", when="2026")


def _packet(pack: str, findings: list[Finding], vos: dict[str, str] | None = None) -> Packet:
    packet = Packet(
        id="oc-empty-beat-host-print",
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


def test_uncited_titled_beats_drop_or_hold_before_room() -> None:
    """promise/gdp/labor/receipt empty + uncited cannot remain on a READY spine."""
    from onecrew.script import _assemble

    helios = _helios_stamp()
    printed = _helios_print_stamp()
    pack = _pack((helios.claim, HELIOS_WIRE), (printed.claim, HELIOS_PRINT))
    packet = _packet(pack, [helios, printed])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios paused campus leases in June 2026.",
                    "eyes": "card",
                    "finding_ids": [helios.id],
                },
                "turn": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "card",
                    "finding_ids": [printed.id],
                },
                "complication": {
                    "vo": "Helios paused campus leases in June 2026.",
                    "eyes": "gap",
                    "finding_ids": [helios.id],
                },
                "close": {
                    "vo": "Helios occupancy printed 14.2% in June 2026.",
                    "eyes": "close",
                    "finding_ids": [printed.id],
                },
            }
        ),
    )
    result = run_cite_recheck_loop(written, search_fn=_no_search)
    assert written.cite_recheck_attempts <= MAX_CITE_RECHECKS
    assert result.hold_reason != "cite-repair loop exhausted" or written.cite_recheck_attempts > 3
    uncited = [b.id for b in written.beats if (b.kind or "vo") != "heading" and not b.finding_ids]
    if written.receipt and written.receipt.disposition == "READY":
        assert uncited == []
        assert written.beats
        assert "chrome" not in (written.script or "").lower()
    else:
        reason = (written.receipt.hold_reason or "").lower() if written.receipt else ""
        assert written.status == "hold"
        assert any(
            tok in reason
            for tok in ("empty beat", "cites nothing", "no pack finding")
        )
        assert "cite-repair loop exhausted" not in reason or written.cite_recheck_attempts > 3


def test_room_flags_uncited_titled_beat_as_cite_faithfulness() -> None:
    helios = _helios_stamp()
    packet = _packet(_pack((helios.claim, HELIOS_WIRE)), [helios])
    packet.script = (
        "Timed VO · youtube · one_time_short_episode\n\n"
        "BEAT 2 — promise\n"
        "00:20–00:40\n"
        "NARRATOR\n"
        "\n"
        "BEAT 5 — turn\n"
        "00:80–01:00\n"
        "NARRATOR\n"
        f"Helios paused campus leases in June 2026. [{helios.id}]\n"
    )
    packet.beats[1].vo = "NARRATOR\n"
    packet.beats[1].finding_ids = []
    packet.beats[4].vo = f"NARRATOR\nHelios paused campus leases in June 2026. [{helios.id}]"
    packet.beats[4].finding_ids = [helios.id]
    grade = grade_room(make_grade_artifact(packet), grader=lambda _a: RoomGrade(vote="ship"))
    assert grade.vote == "recut"
    assert "cite-faithfulness" in (grade.recut_detail or "").lower()


def test_same_survey_host_cannot_cover_half_the_cut() -> None:
    rows = [
        _meridian(f"te-meridian-survey-{i}", url, f"A campus-power survey row {i} tracked buildout.")
        for i, url in enumerate((MERIDIAN_A, MERIDIAN_B, MERIDIAN_C, MERIDIAN_D), start=1)
    ]
    kept = cap_url_reuse(rows, pairs=[])
    hosts = Counter(url_host(f.parallel_url or "") for f in kept if f.stamp == "timeline_event")
    assert hosts.get("meridian-desk.test", 0) <= 2


def test_attach_prefers_unused_host_over_survey_reuse() -> None:
    from onecrew.script import _assemble

    helios = _helios_stamp()
    surveys = [
        _meridian(f"te-meridian-survey-{i}", url, "A campus-power survey tracked buildout and inflation.")
        for i, url in enumerate((MERIDIAN_A, MERIDIAN_B, MERIDIAN_C), start=1)
    ]
    pack = _pack(
        (helios.claim, HELIOS_WIRE),
        *[(f.claim, f.parallel_url or "") for f in surveys],
    )
    packet = _packet(pack, [helios, *surveys])
    written = _assemble(
        packet,
        _eight_units(
            {
                "cold-open": {
                    "vo": "Helios paused campus leases in June 2026.",
                    "eyes": "card",
                    "finding_ids": [surveys[0].id],
                },
                "turn": {
                    "vo": "Helios paused campus leases in June 2026.",
                    "eyes": "card",
                    "finding_ids": [surveys[1].id],
                },
                "close": {
                    "vo": "Helios paused campus leases in June 2026.",
                    "eyes": "close",
                    "finding_ids": [surveys[2].id],
                },
            }
        ),
    )
    run_cite_recheck_loop(written, search_fn=_no_search)
    tls = [f for f in written.receipt.findings if f.stamp == "timeline_event"]
    hosts = Counter(url_host(f.parallel_url or "") for f in tls if (f.parallel_url or "").strip())
    assert hosts.get("meridian-desk.test", 0) <= 2
    spoken = [
        b
        for b in written.beats
        if re.search(r"helios", b.vo, re.I)
    ]
    for beat in spoken:
        cited = [f for f in written.receipt.findings if f.id in beat.finding_ids]
        assert cited
        assert any(url_host(f.parallel_url or "") == "helios-wire.test" for f in cited)


def test_thin_comparative_vo_needs_print_bearing_stamp_or_drops() -> None:
    from onecrew.script import _assemble
    from onecrew.timeline import _event_nums, stamp_text

    printed = _helios_print_stamp()
    pack = _pack((printed.claim, HELIOS_PRINT))
    packet = _packet(pack, [printed])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "A slowdown from percent growth.",
                    "eyes": "card",
                    "finding_ids": [],
                }
            }
        ),
    )
    result = run_cite_recheck_loop(written, search_fn=_no_search)
    turn = next((b for b in written.beats if b.id == "turn"), None)
    spoken_all = "".join(f"{b.vo} {b.frame or ''}" for b in written.beats)
    if turn is None:
        assert not re.search(r"slowdown from percent growth", spoken_all, re.I)
        return
    cited = [f for f in written.receipt.findings if f.id in turn.finding_ids]
    if cited and any(_event_nums(stamp_text(f)) for f in cited):
        return
    reason = ((written.receipt.hold_reason or "") if written.receipt else "").lower()
    assert written.status == "hold" or not result.ok
    assert any(tok in reason for tok in ("empty beat", "cites nothing", "no pack finding"))
    assert "cite-repair loop exhausted" not in reason or written.cite_recheck_attempts > 3


def test_thin_comparative_vo_does_not_use_year_only_stamp() -> None:
    """A June 2026 lease row is not a magnitude print for 'percent growth'."""
    from onecrew.script import _assemble

    lease = _helios_stamp()
    pack = _pack((lease.claim, HELIOS_WIRE))
    packet = _packet(pack, [lease])
    written = _assemble(
        packet,
        _eight_units(
            {
                "turn": {
                    "vo": "A slowdown from percent growth.",
                    "eyes": "card",
                    "finding_ids": [],
                }
            }
        ),
    )
    run_cite_recheck_loop(written, search_fn=_no_search)
    turn = next((b for b in written.beats if b.id == "turn"), None)
    if turn is None:
        return
    spoken = f"{turn.vo} {turn.frame or ''}"
    assert lease.id not in turn.finding_ids
    assert not re.search(r"slowdown from percent growth", spoken, re.I)


def test_production_grep_stays_clear_of_fixtures_and_live_topic() -> None:
    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(_LIVE_TOPIC, text, re.I) or re.search(_FIXTURE, text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
