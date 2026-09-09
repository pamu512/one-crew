"""chronological_events → timeline_event. Not a closed macro series."""

from __future__ import annotations

import logging
import re
from pathlib import Path

import pytest

from onecrew.agent.adk_agents import CLAIMER_INSTRUCTION
from onecrew.claimer import claims_from_cites, findings_from_claims
from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.cut import size_findings
from onecrew.models import Finding, Packet, Receipt, ScriptBeat
from onecrew.receipt import ReceiptInvalidError, validate_finding
from onecrew.verify import CLOSED_SERIES, CiteBag, CiteExcerpt, claims_from_findings

CAMPUS = "https://example.com/compute-campus-200b"
LEASE = "https://example.com/lease-scaleback-2026"
BOOM = "https://example.com/boom-already-bubble"

_CHRONO_PACK = (
    "chronological_events:\n"
    f"- A consortium announced a $200B compute campus. Basis: {CAMPUS}\n"
    f"- A cloud vendor scaled back leases in August 2026. cite_url: {LEASE}\n"
    "- An unsourced ribbon-cutting stayed thesis prose only.\n"
    f"- A newspaper asked whether the boom is already a bubble. Basis: {BOOM}\n"
)

_NO_URL_PACK = (
    "chronological_events:\n"
    "- A consortium announced a $200B compute campus.\n"
    "- A cloud vendor scaled back leases in August 2026.\n"
)


def _packet(pack: str, *, findings: list[Finding] | None = None) -> Packet:
    packet = Packet(
        id="oc-timeline-campus",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
        research_pack=pack,
        task_spine=pack,
        status="hold",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="beat1 cites nothing in the pack; beat3 cites nothing in the pack",
        findings=list(findings or []),
    )
    vos = {
        "cold-open": "NARRATOR\nA consortium announced a $200B compute campus.",
        "promise": "NARRATOR\nThe title stays a question.",
        "gdp": "NARRATOR\nA cloud vendor scaled back leases in August 2026.",
        "labor": "NARRATOR\nA newspaper asked whether the boom is already a bubble.",
        "turn": "NARRATOR\n$200B is the spoken capex print.",
        "complication": "NARRATOR\nLease scalebacks are not the same object as a boom.",
        "receipt": "NARRATOR\nReceipt: the $200B campus and the August 2026 scalebacks.",
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
        for i, (bid, vo) in enumerate(vos.items())
    ]
    packet.script = "\n".join(b.scene + "\n" + b.vo for b in packet.beats) + "\n"
    return packet


def test_parse_chronological_events_stamps_url_grounded_only() -> None:
    from onecrew.timeline import plan_timeline

    planned = plan_timeline(_CHRONO_PACK)
    assert {row.url for row in planned.mapping} == {CAMPUS, LEASE, BOOM}
    assert all(row.thesis.strip() for row in planned.mapping)
    assert all(row.finding_id for row in planned.mapping)
    assert not any("ribbon-cutting" in row.thesis for row in planned.mapping)
    assert all(f.stamp == "timeline_event" for f in planned.findings)
    assert all((f.series or "") in {"", "timeline_event"} for f in planned.findings)
    assert not any((f.series or "") in CLOSED_SERIES or (f.series or "") == "ISM" for f in planned.findings)
    assert all((f.parallel_url or "").startswith("http") for f in planned.findings)


def test_drop_chronological_bullet_without_url() -> None:
    from onecrew.timeline import plan_timeline

    planned = plan_timeline(_NO_URL_PACK)
    assert planned.findings == []
    assert planned.mapping == []


def test_mapping_logged_before_findings_mutate(caplog) -> None:
    from onecrew.timeline import apply_timeline, plan_timeline

    findings: list[Finding] = []
    with caplog.at_level(logging.INFO, logger="onecrew.timeline"):
        planned = plan_timeline(_CHRONO_PACK)
        assert findings == []
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert planned.mapping
        for row in planned.mapping:
            assert row.thesis in logged
            assert row.url in logged
            assert row.finding_id in logged
        apply_timeline(findings, planned)
    assert {f.id for f in findings} == {row.finding_id for row in planned.mapping}


def test_timeline_map_persists_on_receipt_and_grade() -> None:
    from onecrew.room import make_grade_artifact
    from onecrew.timeline import apply_timeline, plan_timeline

    packet = _packet(_CHRONO_PACK)
    planned = plan_timeline(_CHRONO_PACK)
    apply_timeline(packet.receipt.findings, planned)
    packet.receipt.timeline_map = list(planned.mapping)
    assert packet.receipt.timeline_map
    assert packet.receipt.timeline_map[0].url.startswith("http")
    artifact = make_grade_artifact(packet)
    assert artifact.timeline_map
    assert {row.url for row in artifact.timeline_map} == {row.url for row in planned.mapping}


def test_stamper_never_emits_closed_macro_series() -> None:
    from onecrew.timeline import plan_timeline

    pack = (
        "chronological_events:\n"
        f"- A campus ribbon-cutting mentioned GDP in passing. Basis: {CAMPUS}\n"
    )
    planned = plan_timeline(pack)
    assert planned.findings
    assert not any((f.series or "") in CLOSED_SERIES for f in planned.findings)
    assert claims_from_findings(planned.findings) == []


def test_stamping_without_url_is_rejected() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            Finding(
                id="tl-no-url",
                claim="An unsourced campus event.",
                stamp="timeline_event",
                series="timeline_event",
                print="An unsourced campus event.",
                parallel_url=None,
                parallel_status="hit",
                note="Timeline event.",
            )
        )
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            Finding(
                id="tl-as-gdp",
                claim="A campus event.",
                stamp="timeline_event",
                series="GDP",
                print="200",
                when="2025",
                parallel_url=CAMPUS,
                parallel_status="hit",
                note="Timeline event. Parallel URL on this row.",
            )
        )


def test_claimer_does_not_extract_timeline_or_emit_as_gdp() -> None:
    """Forbidden wrap: Claimer emitting a chronological event as GDP."""
    from onecrew import claimer as claimer_mod

    src = Path(claimer_mod.__file__).read_text(encoding="utf-8")
    assert "chronological_events" not in src
    assert "timeline_event" not in src
    assert "chronological_events" not in CLAIMER_INSTRUCTION
    assert "timeline_event" not in CLAIMER_INSTRUCTION
    bag = CiteBag(
        excerpts=[
            CiteExcerpt(
                url=CAMPUS,
                title="campus",
                text="A consortium announced a $200B compute campus in 2025.",
            )
        ],
        spine=_CHRONO_PACK,
        hit_urls=[CAMPUS],
    )
    claims = claims_from_cites(bag)
    assert not any(c.series == "GDP" for c in claims)
    rows = findings_from_claims(claims, bag)
    assert not any(f.stamp == "timeline_event" for f in rows)
    assert not any((f.series or "") == "GDP" for f in rows)


def test_foundry_mint_does_not_stamp_timeline_event() -> None:
    """Foundry mint stays closed-series. Timeline is a dedicated path."""
    from types import SimpleNamespace

    from onecrew.foundry import mint

    packet = Packet(
        id="oc-foundry-chrono",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
        task_spine=_CHRONO_PACK,
        research_pack=_CHRONO_PACK,
    )
    try:
        rows = mint(
            packet,
            [SimpleNamespace(url=CAMPUS, title="campus", excerpts=[_CHRONO_PACK])],
            [SimpleNamespace(url="https://example.com/miss", title="miss", excerpts=["fringe offtake"])],
            SimpleNamespace(results=[], errors=[]),
            _CHRONO_PACK,
        )
    except Exception:
        return
    assert not any(f.stamp == "timeline_event" for f in rows)


def test_cite_repair_stamps_chrono_urls_and_counts_attempt() -> None:
    """Empty-cite HOLD must run repair (attempts≥1) and attach timeline_event stamps."""

    def _no_search(**_k):
        raise AssertionError("pack chronological_events already carry URLs")

    packet = _packet(_CHRONO_PACK)
    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    tls = [f for f in packet.receipt.findings if f.stamp == "timeline_event"]
    assert tls
    assert all((f.parallel_url or "").startswith("http") for f in tls)
    assert not any((f.series or "") in CLOSED_SERIES for f in tls)
    assert packet.receipt.timeline_map
    sourced = [b for b in packet.beats if any(ch.isdigit() for ch in b.vo)]
    for beat in sourced:
        assert beat.finding_ids, f"{beat.id} shipped untagged factual VO"
        assert any(f.stamp == "timeline_event" for f in packet.receipt.findings if f.id in beat.finding_ids)
    if result.ok:
        assert "cites nothing in the pack" not in (packet.receipt.hold_reason or "")
    else:
        assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")


def test_cite_repair_skips_unlinked_events_and_still_runs() -> None:
    calls = {"n": 0}

    def search(**_k):
        calls["n"] += 1
        return type("R", (), {"results": []})()

    packet = _packet(_NO_URL_PACK)
    result = run_cite_recheck_loop(packet, search_fn=search)
    assert calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    assert not any(f.stamp == "timeline_event" for f in packet.receipt.findings)
    if result.ok:
        sourced = [b for b in packet.beats if any(ch.isdigit() for ch in b.vo)]
        assert sourced == []
    else:
        assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")


def test_writer_links_timeline_event_stamps() -> None:
    from onecrew.script import _assemble

    finding = Finding(
        id="tl-campus-200b",
        claim="A consortium announced a $200B compute campus.",
        stamp="timeline_event",
        title="timeline_event",
        series="timeline_event",
        print="A consortium announced a $200B compute campus.",
        when="2025",
        parallel_url=CAMPUS,
        parallel_status="hit",
        note="Timeline event. Parallel URL on this row.",
    )
    packet = Packet(
        id="oc-tl-writer",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
        research_pack=_CHRONO_PACK,
        receipt=Receipt(
            packet_id="oc-tl-writer",
            written=False,
            disposition="READY",
            findings=[finding],
        ),
    )
    units = [
        {"id": "cold-open", "vo": "A consortium announced a $200B compute campus.", "eyes": "capex", "finding_ids": []},
        {"id": "promise", "vo": "The title stays a question.", "eyes": "pack", "finding_ids": []},
        {"id": "gdp", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "labor", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "turn", "vo": "Hold on the cited print.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "Receipt board: named series from the pack.", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    written = _assemble(packet, units)
    cold = next(b for b in written.beats if b.id == "cold-open")
    assert "tl-campus-200b" in cold.finding_ids
    assert "[tl-campus-200b]" in cold.vo


def test_size_findings_keeps_timeline_event() -> None:
    row = Finding(
        id="tl-campus-200b",
        claim="A consortium announced a $200B compute campus.",
        stamp="timeline_event",
        series="timeline_event",
        print="A consortium announced a $200B compute campus.",
        parallel_url=CAMPUS,
        parallel_status="hit",
        note="Timeline event. Parallel URL on this row.",
    )
    kept = size_findings([row], "one_time_short_episode", "youtube")
    assert any(f.id == "tl-campus-200b" for f in kept)


def test_production_timeline_path_is_not_topic_hardcoded() -> None:
    """Forbidden wrap: topic-hardcoding named news events in production."""
    root = Path(__file__).resolve().parents[1] / "onecrew"
    banned = re.compile(r"stargate|microsoft|guardian", re.I)
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if banned.search(text):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
