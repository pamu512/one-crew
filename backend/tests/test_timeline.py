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


# Live packet oc-data-centers-are-going-to-cause-the--af844e08 after #46:
# timeline_event stamps existed, HOLD stayed `foundry minted nothing`,
# finding ids were bibliography chrome, cites preferred scrape hosts,
# cite_recheck_attempts=0, VO kept pack leftover chrome.
OPENAI = "https://openai.com/index/compute-campus-announcement"
REUTERS = "https://www.reuters.com/technology/cloud-vendor-lease-scaleback-2026"
GUARDIAN_DC = "https://www.theguardian.com/technology/2026/aug/compute-campus-boom-bubble"
NOAH = "https://www.noahpinion.blog/p/compute-campus-scrape"
PBS = "https://www.pbs.org/newshour/cloud-vendor-leases"

_CHAIN_AND_BIBLIO = (
    "## Argument\n"
    "chronological_event_chain:\n"
    f"- A consortium announced a $200B compute campus in January 2025. High-confidence basis: {OPENAI}\n"
    f"- A cloud vendor scaled back leases in August 2026. High-confidence basis: {REUTERS}\n"
    f"- A newspaper asked whether the boom is already a bubble. High-confidence basis: {GUARDIAN_DC}\n"
    "\n"
    "## Sources\n"
    f"- [promise-january-2025] Compute campus scrape title. source: {NOAH}\n"
    f"- [gdp-february-2025] Cloud vendor lease scrape title. source: {PBS}\n"
    "- [labor-march-2020] Labor bibliography leftover.\n"
    "- [turn-november-2025] Turn bibliography leftover.\n"
    "- [complication-march-2020] Complication bibliography leftover.\n"
    "- [receipt-june-2026] Receipt bibliography leftover.\n"
)

_BIBLIO_ONLY = (
    "## Sources\n"
    f"- [promise-january-2025] Compute campus scrape title. source: {NOAH}\n"
    f"- [gdp-february-2025] Cloud vendor lease scrape title. source: {PBS}\n"
)

_BIBLIO_IDS = {
    "promise-january-2025",
    "gdp-february-2025",
    "labor-march-2020",
    "turn-november-2025",
    "complication-march-2020",
    "receipt-june-2026",
}


def test_prefer_event_chain_basis_over_bibliography_chrome() -> None:
    """Forbidden wrap: preferring bibliography chrome over chronological_event_chain basis URLs."""
    from onecrew.timeline import plan_timeline

    planned = plan_timeline(_CHAIN_AND_BIBLIO)
    assert all("high-confidence" not in (f.claim or "").lower() for f in planned.findings)
    assert all("http" not in (f.claim or "").lower() for f in planned.findings)
    urls = {row.url for row in planned.mapping}
    assert OPENAI in urls
    assert REUTERS in urls
    assert GUARDIAN_DC in urls
    assert NOAH not in urls
    assert PBS not in urls
    theses = " ".join(row.thesis for row in planned.mapping)
    assert "consortium announced" in theses
    assert "cloud vendor scaled" in theses
    assert "scrape title" not in theses
    assert "promise-january-2025" not in theses


def test_never_stamp_bibliography_slot_or_scrape_title() -> None:
    from onecrew.timeline import plan_timeline

    planned = plan_timeline(_BIBLIO_ONLY)
    assert planned.findings == []
    assert planned.mapping == []


def test_finding_ids_are_te_slug_yyyy_mm_not_biblio_or_macro() -> None:
    from onecrew.timeline import plan_timeline

    planned = plan_timeline(_CHAIN_AND_BIBLIO)
    assert planned.findings
    ids = {f.id for f in planned.findings}
    assert ids.isdisjoint(_BIBLIO_IDS)
    assert ids.isdisjoint({"gdp", "payrolls", "usrec", "sahm", "lei", "ism"})
    for fid in ids:
        assert fid.startswith("te-"), fid
        assert not re.match(
            r"^(promise|gdp|labor|turn|complication|receipt)-",
            fid,
        ), fid
    assert any(re.search(r"20\d{2}-\d{2}$", fid) for fid in ids)


def test_thesis_url_log_maps_event_bullet_to_basis_url(caplog) -> None:
    from onecrew.timeline import plan_timeline

    with caplog.at_level(logging.INFO, logger="onecrew.timeline"):
        planned = plan_timeline(_CHAIN_AND_BIBLIO)
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "consortium announced a $200B compute campus" in logged
    assert OPENAI in logged
    assert NOAH not in logged
    assert PBS not in logged
    campus = next(row for row in planned.mapping if OPENAI in row.url)
    assert "consortium announced" in campus.thesis
    assert campus.url == OPENAI


def test_empty_mint_hold_clears_when_timeline_event_url_exists() -> None:
    """Forbidden wrap: HOLD solely for foundry minted nothing when timeline_event URLs exist."""
    from onecrew.timeline import apply_timeline, clear_empty_mint_hold, plan_timeline

    planned = plan_timeline(_CHAIN_AND_BIBLIO)
    receipt = Receipt(
        packet_id="oc-dc-empty-mint",
        written=False,
        disposition="HOLD",
        hold_reason="foundry minted nothing",
        findings=[],
    )
    apply_timeline(receipt.findings, planned)
    receipt.timeline_map = list(planned.mapping)
    assert any(f.stamp == "timeline_event" and (f.parallel_url or "").startswith("http") for f in receipt.findings)
    clear_empty_mint_hold(receipt, notes="Narrative compute-campus topic. No USREC table.")
    assert receipt.disposition == "READY"
    assert "foundry minted nothing" not in (receipt.hold_reason or "")


def test_empty_mint_hold_stays_when_named_series_demanded() -> None:
    from onecrew.timeline import apply_timeline, clear_empty_mint_hold, plan_timeline

    planned = plan_timeline(_CHAIN_AND_BIBLIO)
    receipt = Receipt(
        packet_id="oc-dc-named-hold",
        written=False,
        disposition="HOLD",
        hold_reason="foundry minted nothing",
        findings=list(planned.findings),
        timeline_map=list(planned.mapping),
    )
    notes = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls July 2026 fell −23,000 on the CES table."
    )
    clear_empty_mint_hold(receipt, notes=notes)
    assert receipt.disposition == "HOLD"
    assert "foundry minted nothing" in (receipt.hold_reason or "")


def test_leftover_slot_rename_to_biblio_ids_does_not_pass() -> None:
    """Forbidden wrap: leftover-slot rename pass onto bibliography keys."""
    from onecrew.foundry import FoundryHold, leftover_three_slot, leftover_wrap, require_minted

    renamed = leftover_three_slot(
        hit_url=NOAH,
        hit_claim="Grounded event inside 2-3y: Compute campuses are going to cause the next economic bubble",
        mainstream_claim="Widely repeated frame about Compute campuses",
        miss_claim="Fringe claim about Compute campuses",
    )
    renamed[0].id = "promise-january-2025"
    renamed[1].id = "gdp-february-2025"
    renamed[2].id = "labor-march-2020"
    assert leftover_wrap(renamed)
    with pytest.raises(FoundryHold, match="leftover"):
        require_minted(renamed, "Compute campuses are going to cause the next economic bubble.")


def test_cite_repair_runs_when_all_beats_empty_and_hold_is_empty_mint() -> None:
    """Forbidden wrap: skipping cite-repair when all beats have empty cites."""
    packet = _packet(_CHAIN_AND_BIBLIO)
    packet.receipt.hold_reason = "foundry minted nothing"
    packet.receipt.findings = []
    for beat in packet.beats:
        beat.finding_ids = []
    result = run_cite_recheck_loop(
        packet,
        search_fn=lambda **_k: (_ for _ in ()).throw(AssertionError("pack already has basis URLs")),
    )
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    tls = [f for f in packet.receipt.findings if f.stamp == "timeline_event"]
    assert tls
    assert {f.id for f in tls}.isdisjoint(_BIBLIO_IDS)
    assert all(f.id.startswith("te-") for f in tls)
    sourced = [b for b in packet.beats if any(ch.isdigit() for ch in b.vo)]
    for beat in sourced:
        assert beat.finding_ids, f"{beat.id} shipped untagged factual VO"
    if result.ok:
        assert packet.receipt.disposition == "READY"
        assert "foundry minted nothing" not in (packet.receipt.hold_reason or "")
    else:
        assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")


def test_credit_hold_does_not_requery_parallel() -> None:
    """Forbidden wrap: Parallel re-query after credit/402 HOLD."""
    packet = _packet(_CHAIN_AND_BIBLIO)
    packet.receipt.hold_reason = "Fail-closed: Parallel credit — Parallel 402. No invented pack."
    packet.receipt.findings = []
    packet.receipt.disposition = "HOLD"
    for beat in packet.beats:
        beat.finding_ids = []

    def boom(**_k):
        raise AssertionError("credit HOLD must not re-query Parallel")

    result = run_cite_recheck_loop(packet, search_fn=boom)
    assert result.ok is False
    assert packet.receipt.disposition == "HOLD"
    assert "402" in (packet.receipt.hold_reason or "") or "credit" in (packet.receipt.hold_reason or "").lower()
    assert not any(f.stamp == "timeline_event" for f in packet.receipt.findings)


def test_research_empty_mint_with_chain_is_ready(monkeypatch) -> None:
    """_research must attach timeline_event URLs instead of HOLD-empty on empty mint."""
    from types import SimpleNamespace

    from onecrew.agent.shift import _research
    from onecrew.foundry import FoundryHold
    from onecrew.models import Rails

    hit = OPENAI
    packet = Packet(
        id="oc-research-empty-mint",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
    )

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[SimpleNamespace(url="https://example.com/fringe", title="miss", excerpts=["fringe offtake"])]
            )
        return SimpleNamespace(
            results=[SimpleNamespace(url=hit, title="campus", excerpts=["A consortium announced a $200B compute campus."])]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[SimpleNamespace(url=hit, title="campus", excerpts=["A consortium announced a $200B compute campus."])],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        return SimpleNamespace(output=SimpleNamespace(content=_CHAIN_AND_BIBLIO, basis=[]))

    def boom_mint(*_a, **_k):
        raise FoundryHold("foundry minted nothing")

    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.agent.shift.mint", boom_mint)
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: False)
    receipt, _leftover, _urls, spine = _research(
        packet, Rails(parallel=True, vertex=False, imagen=False), "2-3y"
    )
    assert spine
    assert receipt.disposition == "READY"
    assert "foundry minted nothing" not in (receipt.hold_reason or "").lower()
    tls = [f for f in receipt.findings if f.stamp == "timeline_event"]
    assert tls
    assert all((f.parallel_url or "").startswith("http") for f in tls)
    assert {f.parallel_url for f in tls} >= {OPENAI, REUTERS}
    assert {f.id for f in tls}.isdisjoint(_BIBLIO_IDS)
    assert all(f.id.startswith("te-") for f in tls)


def test_writer_and_board_strip_leftover_vo_chrome() -> None:
    from onecrew.script import _assemble

    finding = Finding(
        id="te-consortium-announced-2025-01",
        claim="A consortium announced a $200B compute campus in January 2025.",
        stamp="timeline_event",
        title="timeline_event",
        series="timeline_event",
        print="A consortium announced a $200B compute campus in January 2025.",
        when="January 2025",
        parallel_url=OPENAI,
        parallel_status="hit",
        note="Timeline event. Parallel URL on this row.",
    )
    packet = Packet(
        id="oc-tl-chrome",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
        research_pack=_CHAIN_AND_BIBLIO,
        receipt=Receipt(
            packet_id="oc-tl-chrome",
            written=False,
            disposition="READY",
            findings=[finding],
        ),
    )
    units = [
        {
            "id": "cold-open",
            "vo": "A consortium announced a $200B compute campus. Official series cards only",
            "eyes": "Official series cards only. No leftover map.",
            "finding_ids": [],
        },
        {
            "id": "promise",
            "vo": "Three pack objects on screen. The title stays a question.",
            "eyes": "Three pack objects on screen. No leftover map.",
            "finding_ids": [],
        },
        {"id": "gdp", "vo": "A cloud vendor scaled back leases in August 2026.", "eyes": "card", "finding_ids": []},
        {"id": "labor", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "turn", "vo": "Hold on the cited print.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "Receipt board: named series from the pack.", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    written = _assemble(packet, units)
    spoken = written.script + "".join(f"{b.vo} {b.frame}" for b in written.beats)
    assert "Official series cards only" not in spoken
    assert "Three pack objects on screen" not in spoken
    assert "leftover map" not in spoken.lower()
    assert "promise-january-2025" not in spoken
    cold = next(b for b in written.beats if b.id == "cold-open")
    assert "te-consortium-announced-2025-01" in cold.finding_ids


INDUSTRIAL = "https://www.industrialinfo.com/cloud-vendor-lease-scrape"
GUARDIAN_3TN = "https://www.theguardian.com/technology/2026/aug/campus-capex-3tn"
REUTERS_LEASE = "https://www.reuters.com/technology/cloud-vendor-cancelled-leases-2026"
OPENAI_GW = "https://openai.com/index/compute-campus-4-5gw"

_CHAIN_VS_SCRAPE = (
    "## Argument\n"
    "chronological_event_chain:\n"
    f"- A newspaper put campus capex at $3tn. High-confidence basis: {GUARDIAN_3TN}\n"
    f"- A cloud vendor cancelled leases in August 2026. High-confidence basis: {REUTERS_LEASE}\n"
    f"- A lab and a cloud vendor announced 4.5GW. High-confidence basis: {OPENAI_GW}\n"
    "\n"
    "## Sources\n"
    f"- [gdp-february-2025] $3tn scrape title. source: {PBS}\n"
    f"- Cloud vendor lease scrape title. source: {INDUSTRIAL}\n"
    f"- Compute campus scrape title. source: {NOAH}\n"
)


def test_forbidden_wrap_chain_basis_url_wins_for_spoken_event() -> None:
    """Spoken event stamps the Argument High-confidence basis URL, not a scrape host."""
    from onecrew.timeline import plan_timeline

    planned = plan_timeline(_CHAIN_VS_SCRAPE)
    urls = {row.url for row in planned.mapping}
    assert GUARDIAN_3TN in urls
    assert REUTERS_LEASE in urls
    assert OPENAI_GW in urls
    assert PBS not in urls
    assert INDUSTRIAL not in urls
    assert NOAH not in urls
    three = next(row for row in planned.mapping if "3tn" in row.thesis or "3 tn" in row.thesis.lower())
    assert three.url == GUARDIAN_3TN
    lease = next(row for row in planned.mapping if "cancelled leases" in row.thesis)
    assert lease.url == REUTERS_LEASE
    gw = next(row for row in planned.mapping if "4.5" in row.thesis)
    assert gw.url == OPENAI_GW


def test_forbidden_wrap_cite_repair_drops_excerpt_gdp_and_does_not_exhaust() -> None:
    """Beats citing excerpts[N] GDP junk must attach te-* URLs, not burn the repair loop."""
    from onecrew.foundry import is_pack_slot_id

    packet = _packet(_CHAIN_VS_SCRAPE)
    packet.receipt.hold_reason = "duplicate series; gdp bars mismatch uncited claim"
    packet.receipt.findings = [
        Finding(
            id="excerpts[18]",
            claim="GDP=$126 trillion",
            stamp="grounded",
            series="GDP",
            print="$126 trillion",
            when="2025",
            parallel_url=NOAH,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="excerpts[19]",
            claim="0.6% of GDP",
            stamp="grounded",
            series="GDP",
            print="0.6%",
            when="2025",
            parallel_url=PBS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    vos = {
        "cold-open": "NARRATOR\nGDP=$126 trillion [excerpts[18]] A newspaper put campus capex at $3tn.",
        "promise": "NARRATOR\nThe title stays a question. [excerpts[19]]",
        "gdp": "NARRATOR\nA cloud vendor cancelled leases in August 2026.",
        "labor": "NARRATOR\nA lab and a cloud vendor announced 4.5GW.",
        "turn": "NARRATOR\n$3tn is the spoken capex print.",
        "complication": "NARRATOR\nLease cancellations are not the same object as a boom.",
        "receipt": "NARRATOR\nReceipt: the $3tn capex and the August 2026 cancellations.",
        "close": "NARRATOR\nNear is not a switch.",
    }
    for beat in packet.beats:
        beat.vo = vos[beat.id]
        beat.finding_ids = ["excerpts[18]", "excerpts[19]"]

    def _no_search(**_k):
        raise AssertionError("chain already carries High-confidence basis URLs")

    result = run_cite_recheck_loop(packet, search_fn=_no_search)
    assert result.ok
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    assert "cite-repair loop exhausted" not in (packet.receipt.hold_reason or "")
    assert not any(is_pack_slot_id(f.id) for f in packet.receipt.findings)
    assert not any(f.series == "GDP" for f in packet.receipt.findings)
    spoken = "".join(b.vo for b in packet.beats)
    assert "excerpts[18]" not in spoken
    assert "excerpts[19]" not in spoken
    assert "GDP=$126 trillion" not in spoken
    tls = [f for f in packet.receipt.findings if f.stamp == "timeline_event"]
    assert tls
    assert {f.parallel_url for f in tls} >= {GUARDIAN_3TN, REUTERS_LEASE, OPENAI_GW}
    assert PBS not in {f.parallel_url for f in tls}
    assert INDUSTRIAL not in {f.parallel_url for f in tls}
    sourced = [b for b in packet.beats if any(ch.isdigit() for ch in b.vo)]
    for beat in sourced:
        assert beat.finding_ids, f"{beat.id} shipped untagged factual VO"
        assert not any(is_pack_slot_id(fid) for fid in beat.finding_ids)
        assert any(
            f.stamp == "timeline_event" for f in packet.receipt.findings if f.id in beat.finding_ids
        )
    if result.ok:
        assert packet.receipt.disposition == "READY"


def test_forbidden_wrap_writer_strips_excerpt_slot_tokens() -> None:
    from onecrew.script import _assemble

    finding = Finding(
        id="te-newspaper-capex-2026-08",
        claim="A newspaper put campus capex at $3tn.",
        stamp="timeline_event",
        title="timeline_event",
        series="timeline_event",
        print="A newspaper put campus capex at $3tn.",
        when="August 2026",
        parallel_url=GUARDIAN_3TN,
        parallel_status="hit",
        note="Timeline event. Parallel URL on this row.",
    )
    packet = Packet(
        id="oc-tl-excerpt-vo",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
        research_pack=_CHAIN_VS_SCRAPE,
        receipt=Receipt(
            packet_id="oc-tl-excerpt-vo",
            written=False,
            disposition="READY",
            findings=[
                finding,
                Finding(
                    id="excerpts[18]",
                    claim="GDP=$126 trillion",
                    stamp="grounded",
                    series="GDP",
                    print="$126 trillion",
                    when="2025",
                    parallel_url=NOAH,
                    parallel_status="hit",
                    note="Parallel URL on this row.",
                ),
            ],
        ),
    )
    units = [
        {
            "id": "cold-open",
            "vo": "GDP=$126 trillion [excerpts[18]] A newspaper put campus capex at $3tn.",
            "eyes": "card",
            "finding_ids": ["excerpts[18]"],
        },
        {"id": "promise", "vo": "The title stays a question.", "eyes": "pack", "finding_ids": []},
        {"id": "gdp", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "labor", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "turn", "vo": "Hold on the cited print.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "Receipt board: named series from the pack.", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    written = _assemble(packet, units)
    spoken = written.script + "".join(f"{b.vo} {b.frame}" for b in written.beats)
    assert "excerpts[18]" not in spoken
    assert "GDP=$126 trillion" not in spoken
    cold = next(b for b in written.beats if b.id == "cold-open")
    assert "te-newspaper-capex-2026-08" in cold.finding_ids
    assert "excerpts[18]" not in cold.finding_ids
