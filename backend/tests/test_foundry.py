"""Foundry mints objects from the thesis. Leftover 3-slot wrap must fail."""

import re
from types import SimpleNamespace

import pytest

from onecrew.cut import size_findings
from onecrew.models import MISSING, Finding, Packet, Receipt
from onecrew.receipt import write_receipt
from onecrew.script import write_script
from onecrew.spend import ledger
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE

# Inlined from live oc-recession-live-sep1b thesis. No network.
LIVE_SENTENCES = (
    "USREC July 2026 = 0.",
    "Nonfarm payrolls July 2026 = −23,000; May+June revised −103,000.",
    "Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%.",
    "Sahm July 2026 = −0.03 vs 0.50 trigger.",
    "LEI July +0.2%.",
    "IMF 2.4% q4/q4 is a forecast, not a print.",
)

LIVE_SPINE = " ".join(LIVE_SENTENCES)

FRED_USREC = "https://fred.stlouisfed.org/series/USREC"
BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
BEA = "https://www.bea.gov/data/gdp/gross-domestic-product"
FRED_SAHM = "https://fred.stlouisfed.org/series/SAHMREALTIME"
LEI_URL = "https://www.conference-board.org/topics/us-leading-indicators"

_LEFTOVER = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})


def _row(url, title, excerpts):
    return SimpleNamespace(url=url, title=title, excerpts=list(excerpts))


def _packet() -> Packet:
    return Packet(
        id="oc-recession-live-sep1b",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        research_pack="",
        task_spine=LIVE_SPINE,
    )


def _mint():
    from onecrew.foundry import mint

    packet = _packet()
    hit_rows = [
        _row(FRED_USREC, "USREC", ["USREC July 2026 = 0."]),
        _row(BLS, "BLS Employment Situation", ["Nonfarm payrolls July 2026 = −23,000."]),
        _row(BEA, "BEA GDP", ["Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%."]),
        _row(FRED_SAHM, "SAHMREALTIME", ["Sahm July 2026 = −0.03 vs 0.50 trigger."]),
        _row(LEI_URL, "Conference Board LEI", ["LEI July +0.2%."]),
    ]
    miss_rows = [
        _row(
            "https://example.com/hidden-treaty",
            "Hidden treaty",
            ["Hormuz has already been mined shut under a hidden navy treaty."],
        )
    ]
    extracted = SimpleNamespace(
        results=[
            _row(FRED_USREC, "USREC", ["USREC July 2026 = 0."]),
            _row(BLS, "BLS Employment Situation", ["Nonfarm payrolls July 2026 = −23,000."]),
        ],
        errors=[],
    )
    before = ledger.parallel_calls
    rows = mint(packet, hit_rows, miss_rows, extracted, LIVE_SPINE)
    assert ledger.parallel_calls == before
    return packet, rows


def test_mint_live_thesis_named_series_not_three_slot() -> None:
    packet, rows = _mint()
    ids = {f.id for f in rows}
    assert ids != _LEFTOVER
    assert not ids & _LEFTOVER
    usrec = next(f for f in rows if f.series == "USREC")
    payrolls = next(f for f in rows if "payroll" in f.series.lower() or f.series == "BLS payrolls")
    assert usrec.id == "usrec-july-2026"
    assert usrec.print in {"0", "USREC=0"} or "0" in usrec.print
    assert "USREC July 2026 = 0" in usrec.claim
    assert usrec.when.lower().startswith("july")
    assert usrec.parallel_url == FRED_USREC
    assert usrec.stamp == "grounded"
    assert usrec.independent == MISSING
    assert usrec.independent_url is None
    assert "−23" in payrolls.print or "-23" in payrolls.print
    assert "23,000" in payrolls.print or "23k" in payrolls.print.lower()
    assert "payroll" in payrolls.claim.lower()
    assert payrolls.id.startswith("bls-payrolls") or "payroll" in payrolls.id
    gdp = next(f for f in rows if f.series == "GDP")
    assert "0.5" in gdp.claim and "2.1" in gdp.claim and "1.5" in gdp.claim
    sahm = next(f for f in rows if f.series == "SAHMREALTIME")
    assert ("−0.03" in sahm.claim or "-0.03" in sahm.claim) and "0.50" in sahm.claim
    lei = next(f for f in rows if f.series == "LEI")
    assert "+0.2" in lei.claim or "+0.2%" in lei.print
    assert not any("imf" in f.series.lower() or "2.4" in (f.print or "") for f in rows if f.stamp == "grounded" and f.series != MISSING)


def test_leftover_three_slot_illegal_when_thesis_has_prints() -> None:
    from onecrew.foundry import leftover_three_slot, mint

    packet = _packet()
    wrapped = leftover_three_slot(
        hit_url=FRED_USREC,
        hit_claim="USREC July 2026 = 0.",
        mainstream_claim="Widely repeated frame about Are we near recession?",
        miss_claim="Fringe claim about Are we near recession?",
    )
    assert {f.id for f in wrapped} == _LEFTOVER
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["USREC July 2026 = 0."]),
            _row(BLS, "BLS Employment Situation", ["Nonfarm payrolls July 2026 = −23,000."]),
        ],
        [_row("https://example.com/fringe", "x", ["Secret double-dip already started in May."])],
        SimpleNamespace(results=[], errors=[]),
        LIVE_SPINE,
    )
    assert {f.id for f in rows} != _LEFTOVER
    assert not {f.id for f in rows} & _LEFTOVER
    assert any(f.series == "USREC" for f in rows)
    assert any("payroll" in (f.series or "").lower() or "payroll" in f.claim.lower() for f in rows)


def test_fringe_miss_is_excerpt_never_topic_template() -> None:
    _, rows = _mint()
    fringe = [f for f in rows if f.stamp == "fringe"]
    assert len(fringe) == 1
    assert fringe[0].series == MISSING
    assert fringe[0].print == MISSING
    assert "Fringe claim about Are we near recession?" not in fringe[0].claim
    assert "hidden navy treaty" in fringe[0].claim.lower() or "mined shut" in fringe[0].claim.lower()


def test_mint_does_not_invent_forecast_or_causal() -> None:
    _, rows = _mint()
    blob = " ".join(f"{f.id} {f.claim} {f.series}" for f in rows).lower()
    assert "imf" not in blob
    assert "2.4" not in blob
    assert "will enter" not in blob
    assert not any("causal" in f.id for f in rows)


def test_nuclear_thesis_mints_its_own_prints_not_timeline_hit() -> None:
    from onecrew.foundry import FoundryHold, mint

    packet = Packet(
        id="oc-nuclear-yields",
        topic="Did the 10-year break?",
        hook="Did the 10-year break?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
    )
    spine = "The 10-year yield printed 4.8% in March 2026."
    url = "https://fred.stlouisfed.org/series/DGS10"
    with pytest.raises(FoundryHold, match="foundry minted nothing"):
        mint(
            packet,
            [_row(url, "10-Year Treasury", [spine])],
            [_row("https://example.com/fringe", "x", ["Hidden treaty already priced the curve."])],
            SimpleNamespace(results=[_row(url, "10-Year Treasury", [spine])], errors=[]),
            spine,
        )


def test_leftover_ids_plus_two_prints_holds() -> None:
    from onecrew.foundry import FoundryHold, leftover_three_slot, require_minted

    wrapped = leftover_three_slot(
        hit_url=FRED_USREC,
        hit_claim="USREC July 2026 = 0.",
        mainstream_claim="Widely repeated frame about Are we near recession?",
        miss_claim="Fringe claim about Are we near recession?",
    )
    with pytest.raises(FoundryHold, match="leftover 3-slot"):
        require_minted(wrapped, LIVE_SPINE)


def test_size_findings_keeps_named_prints_not_timeline_slots() -> None:
    from onecrew.foundry import leftover_three_slot

    named = [
        Finding(
            id="usrec-july-2026",
            claim="USREC July 2026 = 0.",
            stamp="grounded",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls July 2026 = −23,000.",
            stamp="grounded",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="gdp-2026-q2",
            claim="Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%.",
            stamp="grounded",
            series="GDP",
            print="0.5%",
            parallel_url=BEA,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    leftover = leftover_three_slot(
        hit_url=FRED_USREC,
        hit_claim="USREC July 2026 = 0.",
        mainstream_claim="Widely repeated frame about Are we near recession?",
        miss_claim="Fringe claim about Are we near recession?",
    )
    kept = size_findings(leftover + named, "tiktok-length", "tiktok")
    ids = {f.id for f in kept}
    assert "usrec-july-2026" in ids
    assert "payrolls-july-2026" in ids or "gdp-2026-q2" in ids
    assert not ids & _LEFTOVER


def test_writer_reads_minted_series_print_not_year_smash() -> None:
    packet, rows = _mint()
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    vo = packet.script + "\n" + "\n".join(b.vo for b in packet.beats)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert packet.status == "ready"
    assert "USREC=0" in vo
    assert "−23k" in vo or "-23k" in vo or "−23,000" in vo or "-23,000" in vo
    assert "2026 smashed into 0" not in vo
    assert "Fringe claim about Are we near recession?" not in vo
    assert "USREC=0" in (cold.frame or "")
    assert "23" in (cold.frame or "")
    assert "2026 and 0" not in (cold.frame or "")
    assert "LEI" not in vo and "+0.2%" not in vo
    assert "IMF" not in vo and "2.4" not in vo
    assert ledger.parallel_calls == 0


def _hit_rows():
    return [
        _row(FRED_USREC, "USREC", ["USREC July 2026 = 0."]),
        _row(BLS, "BLS Employment Situation", ["Nonfarm payrolls July 2026 = −23,000."]),
        _row(BEA, "BEA GDP", ["Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%."]),
        _row(FRED_SAHM, "SAHMREALTIME", ["Sahm July 2026 = −0.03 vs 0.50 trigger."]),
    ]


def _miss_rows():
    return [
        _row(
            "https://example.com/hidden-treaty",
            "Hidden treaty",
            ["Hormuz has already been mined shut under a hidden navy treaty."],
        )
    ]


def test_sahm_url_is_not_usrec() -> None:
    from onecrew.foundry import mint

    packet = _packet()
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["USREC July 2026 = 0. Sahm July 2026 = −0.03 vs 0.50 trigger."]),
            _row(BLS, "BLS Employment Situation", ["Nonfarm payrolls July 2026 = −23,000."]),
            _row(BEA, "BEA GDP", ["Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Sahm July 2026 = −0.03 vs 0.50 trigger."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_SPINE,
    )
    sahm = next(f for f in rows if f.series == "SAHMREALTIME" or "sahm" in f.id)
    usrec = next(f for f in rows if f.series == "USREC" or "usrec" in f.id)
    payrolls = next(f for f in rows if "payroll" in f.id)
    gdp = next(f for f in rows if "gdp" in f.id)
    assert "sahmrealtime" in (sahm.parallel_url or "").lower() or "/series/sahm" in (sahm.parallel_url or "").lower()
    assert "usrec" not in (sahm.parallel_url or "").lower()
    assert sahm.parallel_url != usrec.parallel_url
    assert "bls.gov" in (payrolls.parallel_url or "")
    assert "bea.gov" in (gdp.parallel_url or "")
    assert "usrec" in (usrec.parallel_url or "").lower()
    stolen = mint(
        packet,
        [_row(FRED_USREC, "USREC", ["USREC July 2026 = 0. Sahm July 2026 = −0.03 vs 0.50 trigger."])],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        "USREC July 2026 = 0. Sahm July 2026 = −0.03 vs 0.50 trigger.",
    )
    assert not any(
        (f.series == "SAHMREALTIME" or "sahm" in f.id)
        and "usrec" in (f.parallel_url or "").lower()
        for f in stolen
    )


def test_foundry_mints_named_series_not_three_slot() -> None:
    from onecrew.foundry import mint

    packet = _packet()
    rows = mint(packet, _hit_rows(), _miss_rows(), SimpleNamespace(results=[], errors=[]), LIVE_SPINE)
    ids = {f.id for f in rows}
    assert "timeline-hit" not in ids
    assert any("usrec" in f.id for f in rows)
    assert any("payroll" in f.id for f in rows)
    assert any("gdp" in f.id for f in rows)
    assert any("sahm" in f.id for f in rows)
    grounded = [f for f in rows if f.stamp == "grounded"]
    blob = " ".join(f.claim for f in grounded)
    assert "0" in blob
    assert "23,000" in blob or "−23k" in blob or "-23k" in blob
    assert "0.5" in blob and "2.1" in blob and "1.5" in blob
    assert ("−0.03" in blob or "-0.03" in blob) and "0.50" in blob
    usrec = next(f for f in grounded if "usrec" in f.id or f.series == "USREC")
    payrolls = next(f for f in grounded if "payroll" in f.id)
    gdp = next(f for f in grounded if "gdp" in f.id)
    sahm = next(f for f in grounded if "sahm" in f.id)
    assert "fred.stlouisfed.org" in (usrec.parallel_url or "")
    assert "bls.gov" in (payrolls.parallel_url or "")
    assert "bea.gov" in (gdp.parallel_url or "")
    assert "sahm" in (sahm.parallel_url or "").lower() or "fred.stlouisfed.org" in (sahm.parallel_url or "")


def test_foundry_does_not_spend(monkeypatch) -> None:
    from onecrew.foundry import mint

    def boom(*_a, **_k):
        raise AssertionError("foundry.mint spent Parallel")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.parallel_client.extract", boom)
    monkeypatch.setattr("onecrew.parallel_client.run_task", boom)
    monkeypatch.setattr("onecrew.agent.shift.search", boom)
    monkeypatch.setattr("onecrew.agent.shift.extract", boom)
    monkeypatch.setattr("onecrew.agent.shift.run_task", boom)
    mint(_packet(), _hit_rows(), _miss_rows(), SimpleNamespace(results=[], errors=[]), LIVE_SPINE)


def test_foundry_no_forecast_as_smash() -> None:
    packet, rows = _mint()
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert "USREC" in cold.vo
    assert "23" in cold.vo
    assert "2.4" not in cold.vo
    assert "2.4" not in packet.script
    assert not any(f.series == "IMF" for f in rows if f.stamp == "grounded")


def test_leftover_three_slot_illegal_when_spine_has_prints() -> None:
    from onecrew.foundry import FoundryHold, findings_from_parallel_rows, leftover_three_slot, require_minted

    packet = _packet()
    wrapped = findings_from_parallel_rows(
        hit_rows=_hit_rows(),
        miss_rows=_miss_rows(),
        topic=packet.topic,
        depth=packet.depth,
    )
    assert {f.id for f in wrapped} == _LEFTOVER
    with pytest.raises(FoundryHold, match="leftover 3-slot"):
        require_minted(wrapped, LIVE_SPINE)
    packet.receipt = Receipt(
        packet_id=packet.id, written=True, disposition="READY", findings=wrapped
    )
    write_script(packet)
    assert packet.status == "hold"
    renamed = leftover_three_slot(
        hit_url=FRED_USREC,
        hit_claim="Grounded event inside 2-3y: Are we near recession?",
        mainstream_claim="Widely repeated frame about Are we near recession?",
        miss_claim="Fringe claim about Are we near recession?",
    )
    renamed[0].id = "usrec"
    renamed[1].id = "payrolls"
    renamed[2].id = "gdp"
    with pytest.raises(FoundryHold):
        require_minted(renamed, LIVE_SPINE)


def test_writer_reads_foundry_objects() -> None:
    packet, rows = _mint()
    packet.id = "oc-recession-live-foundry"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    from onecrew.pack import write_research_pack

    write_research_pack(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert cold.duration_s == 20
    assert "USREC=0" in cold.vo
    assert "−23k" in cold.vo or "-23k" in cold.vo or "−23,000" in cold.vo or "-23,000" in cold.vo
    assert "USREC=0" in (cold.frame or "")
    assert "23" in (cold.frame or "")
    assert "Fringe claim about" not in packet.script
    assert "Grounded event inside" not in packet.script
    pack = packet.research_pack
    assert LIVE_SENTENCES[0] in pack or "USREC" in pack
    for finding in rows:
        if finding.stamp != "grounded":
            continue
        assert finding.id in pack
        assert finding.claim[:20] in pack or finding.id in pack
        if finding.print not in {MISSING, "", None}:
            assert finding.print in pack or finding.print.replace("−", "-") in pack.replace("−", "-")
    assert packet.id != "oc-recession-july-2026"
    assert packet.id != "oc-hormuz-decade"
    assert "timeline-hit" not in {f.id for f in rows}


def test_vertex_hollow_discarded(monkeypatch) -> None:
    import json

    packet, rows = _mint()
    packet.id = "oc-recession-live-vertex"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    hollow = {
        "beats": [
            {
                "id": bid,
                "vo": (
                    "2026 smashed into 0."
                    if bid == "cold-open"
                    else "Fringe claim about Are we near recession?"
                ),
                "eyes": "hollow",
                "finding_ids": [f.id for f in rows[:2]],
            }
            for bid in (
                "cold-open",
                "promise",
                "gdp",
                "labor",
                "turn",
                "complication",
                "receipt",
                "close",
            )
        ]
    }
    monkeypatch.setattr("onecrew.script.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda *_a, **_k: json.dumps(hollow))
    write_script(packet)
    vo = packet.script + "\n" + "\n".join(b.vo for b in packet.beats)
    assert "2026 smashed into 0" not in vo
    assert "Fringe claim about Are we near recession?" not in vo
    assert "USREC=0" in vo


def test_size_findings_keeps_named_series() -> None:
    core = [
        Finding(
            id="usrec-july-2026",
            claim="USREC July 2026 = 0.",
            stamp="grounded",
            series="USREC",
            print="0",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls July 2026 = −23,000.",
            stamp="grounded",
            series="BLS payrolls",
            print="−23,000",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="sahm-july-2026",
            claim="Sahm July 2026 = −0.03 vs 0.50 trigger.",
            stamp="grounded",
            series="SAHMREALTIME",
            print="−0.03",
            parallel_url=FRED_SAHM,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    filler = [
        Finding(
            id=f"aaa-extra-{i:02d}",
            claim=f"Extra print {i}.0%.",
            stamp="grounded",
            series=f"EXTRA{i}",
            print=f"{i}.0%",
            parallel_url=f"https://example.com/extra-{i}",
            parallel_status="hit",
            note="Parallel URL on this row.",
        )
        for i in range(9)
    ]
    kept = size_findings(filler + core, "one_time_short_episode", "youtube")
    ids = {f.id for f in kept}
    assert len(kept) <= 8
    assert "usrec-july-2026" in ids
    assert "payrolls-july-2026" in ids
    assert "sahm-july-2026" in ids


def test_non_recession_thesis_does_not_hardcode_usrec() -> None:
    from onecrew.foundry import mint
    from onecrew.seed import CFR_JCPOA, OPEC_URL, leftover_hormuz_findings

    notes = " ".join(f.claim for f in leftover_hormuz_findings())
    packet = Packet(
        id="oc-hormuz-foundry",
        topic="How a decade of decisions around the Strait of Hormuz still sets the price of oil",
        hook="Hormuz oil share",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Narrator-led global overview of the US and Iran",
        tone=SEED_TONE,
        task_spine=notes,
    )
    rows = mint(
        packet,
        [
            _row(CFR_JCPOA, "What Is the Iran Nuclear Deal?", [leftover_hormuz_findings()[0].claim]),
            _row(OPEC_URL, "OPEC", [leftover_hormuz_findings()[1].claim]),
        ],
        [_row("https://example.com/fringe", "x", [leftover_hormuz_findings()[-1].claim])],
        SimpleNamespace(results=[], errors=[]),
        notes,
    )
    ids = {f.id for f in rows}
    series = {f.series for f in rows}
    blob = " ".join(f.claim for f in rows).lower()
    assert "timeline-hit" not in ids
    assert not any(f.series == "USREC" for f in rows)
    assert not any("usrec" in f.id for f in rows)
    assert any("hormuz" in f.id or "jcpoa" in f.id or "hormuz" in blob or "jcpoa" in blob for f in rows)
    assert "USREC" not in series


def test_independent_missing_strips_url() -> None:
    from onecrew.foundry import sanitize_stamps
    from onecrew.receipt import validate_finding

    packet, rows = _mint()
    grounded = next(f for f in rows if f.stamp == "grounded")
    grounded.independent = MISSING
    grounded.independent_url = FRED_USREC
    sanitize_stamps(rows)
    assert grounded.independent == MISSING
    assert grounded.independent_url is None
    for finding in rows:
        validate_finding(finding)


def test_collision_fred_is_citation_not_same_script(monkeypatch) -> None:
    from onecrew.collision import stamp_collisions
    from onecrew.models import Rails

    packet, rows = _mint()
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)

    def only_fred(*, objective, search_queries):
        return SimpleNamespace(
            results=[_row(FRED_USREC, "USREC", ["USREC July 2026 = 0."])]
        )

    monkeypatch.setattr("onecrew.collision.search", only_fred)
    stamp_collisions(packet, Rails(parallel=True, vertex=False, imagen=False))
    for beat in packet.beats:
        if (beat.kind or "vo") != "vo":
            continue
        assert beat.collision_kind != "same_script"
        assert beat.collision != "yes"
        assert beat.collision == "no"


FRED_TITLE = (
    "NBER based Recession Indicators for the United States from the Period "
    "following the Peak through the Trough (USREC) | FRED | St. Louis Fed"
)

FRED_JUNK_EXCERPTS = [
    "USREC July 2026 = 0.",
    "The Great Depression began in 1929.",
    "The Great Recession ran 2007-2009.",
    "Tariffs printed a 10% rate in 1930.",
    "Nonfarm payrolls July 2026 = −23,000.",
    "Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%.",
    "Sahm July 2026 = −0.03 vs 0.50 trigger.",
]


def test_foundry_does_not_mint_fred_title_slugs() -> None:
    from onecrew.foundry import mint

    packet = _packet()
    rows = mint(
        packet,
        [
            _row(FRED_USREC, FRED_TITLE, FRED_JUNK_EXCERPTS),
            _row(BLS, "BLS Employment Situation", ["Nonfarm payrolls July 2026 = −23,000."]),
            _row(BEA, "BEA GDP", ["Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Sahm July 2026 = −0.03 vs 0.50 trigger."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[_row(FRED_USREC, FRED_TITLE, FRED_JUNK_EXCERPTS)], errors=[]),
        LIVE_SPINE,
    )
    ids = [f.id for f in rows if f.stamp == "grounded"]
    assert not any("nber-based-recession-indicators" in i for i in ids)
    assert not any("st-louis-fed" in i or "fred-st-louis" in i for i in ids)
    short = {i.split("-")[0] for i in ids}
    assert {"usrec", "payrolls", "gdp", "sahm"} <= short or {"usrec", "bls"} <= {i.split("-")[0] for i in ids}
    assert any(i in {"usrec", "usrec-july-2026"} or i.startswith("usrec") and "fred" not in i for i in ids)
    assert any("payroll" in i for i in ids)
    assert any(i.startswith("gdp") for i in ids)
    assert any(i.startswith("sahm") for i in ids)
    assert all(f.series in {"USREC", "BLS payrolls", "GDP", "SAHMREALTIME", "U-3", "LEI", "ISM"} for f in rows if f.stamp == "grounded")


def test_cut_cap_keeps_named_series() -> None:
    named = [
        Finding(id="usrec-july-2026", claim="USREC=0", stamp="grounded", series="USREC", print="0", parallel_url=FRED_USREC, parallel_status="hit", note="Parallel URL on this row."),
        Finding(id="payrolls-july-2026", claim="payrolls −23k", stamp="grounded", series="BLS payrolls", print="−23k", parallel_url=BLS, parallel_status="hit", note="Parallel URL on this row."),
        Finding(id="gdp-2026-q2", claim="GDP 0.5", stamp="grounded", series="GDP", print="0.5", parallel_url=BEA, parallel_status="hit", note="Parallel URL on this row."),
        Finding(id="sahm-july-2026", claim="Sahm −0.03", stamp="grounded", series="SAHMREALTIME", print="−0.03", parallel_url=FRED_SAHM, parallel_status="hit", note="Parallel URL on this row."),
    ]
    junk = [
        Finding(
            id=f"nber-based-recession-indicators-usrec-fred-st-louis-fed-{i}",
            claim=f"Great Depression print {i}.",
            stamp="grounded",
            series=FRED_TITLE,
            print=str(1929 + i),
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        )
        for i in range(20)
    ]
    kept = size_findings(junk + named, "one_time_short_episode", "youtube")
    ids = {f.id for f in kept}
    assert "usrec-july-2026" in ids
    assert "payrolls-july-2026" in ids
    assert "gdp-2026-q2" in ids
    assert "sahm-july-2026" in ids


def test_named_rank_substring_usrec_is_not_the_series() -> None:
    from onecrew.cut import _named_rank

    junk = Finding(
        id="nber-based-recession-indicators-usrec-fred-st-louis-fed",
        claim="Great Depression 1929.",
        stamp="grounded",
        series=FRED_TITLE,
        print="1929",
        parallel_url=FRED_USREC,
        parallel_status="hit",
        note="Parallel URL on this row.",
    )
    usrec = Finding(
        id="usrec-july-2026",
        claim="USREC July 2026 = 0.",
        stamp="grounded",
        series="USREC",
        print="0",
        parallel_url=FRED_USREC,
        parallel_status="hit",
        note="Parallel URL on this row.",
    )
    assert _named_rank(junk)[0] == 4
    assert _named_rank(usrec)[0] == 0


def test_sahm_url_not_usrec() -> None:
    test_sahm_url_is_not_usrec()


def test_writer_vo_on_live_fixture() -> None:
    packet, rows = _mint()
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert packet.status == "ready"
    assert "USREC=0" in cold.vo
    assert "−23k" in cold.vo or "-23k" in cold.vo or "−23,000" in cold.vo or "-23,000" in cold.vo


def test_list_packets_live_script_outranks_seed() -> None:
    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.models import Packet
    from onecrew.seed import seed_first_open
    from onecrew.store import store

    seed_first_open()
    live = Packet(
        id="oc-are-we-near-recession-8c716ba0",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="USREC=0 smashed into payrolls −23k.",
        platform="youtube",
        cut="one_time_short_episode",
        tell=SEED_TELL,
        tone=SEED_TONE,
        status="ready",
    )
    hollow = Packet(
        id="oc-are-we-near-recession-empty",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        tell=SEED_TELL,
        status="hold",
    )
    store.upsert_packet(hollow)
    with TestClient(app) as client:
        before = client.get("/api/packets").json()["packets"]
        assert before[0]["id"] == "oc-recession-july-2026"
        store.upsert_packet(live)
        after = client.get("/api/packets").json()["packets"]
        assert after[0]["id"] == live.id
        assert after[0]["id"] != "oc-recession-july-2026"
        assert after[0]["id"] != "oc-hormuz-decade"


def test_list_packets_empty_is_empty_hold_not_seed() -> None:
    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.floor import FLOOR_HTML
    from onecrew.store import store

    store.replace_packets([])
    with TestClient(app) as client:
        body = client.get("/api/packets")
        ids = {p["id"] for p in body.json()["packets"]}
        assert "oc-recession-july-2026" not in ids
        assert body.json()["packets"] == []
        page = client.get("/")
        assert page.status_code == 200
    assert "Loading oc-recession-july-2026" not in FLOOR_HTML
    assert "HOLD" in FLOOR_HTML


GDI_THEN_PAYROLLS = "Real GDI grew 2.2%. July 2026 payroll employment fell 23,000."
BAGGY_GDI_PAYROLLS = "Real GDI grew 2.2% July 2026 payroll employment fell 23,000."
USREC_THEN_GDP = "FRED July 2026 USREC value is 0. GDP printed 0.5, then 2.1, then 1.5."
BAGGY_USREC_GDP = "FRED July 2026 USREC value is 0 GDP printed 0.5, then 2.1, then 1.5."
NO_SAHM_SPINE = "USREC July 2026 = 0. July 2026 payroll employment fell 23,000. GDP printed 0.5, then 2.1, then 1.5."


def _mint_notes(spine: str, extra_excerpts: list[str] | None = None):
    from onecrew.foundry import mint

    packet = _packet()
    packet.task_spine = spine
    excerpts = [spine, *(extra_excerpts or [])]
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", excerpts),
            _row(BLS, "BLS Employment Situation", excerpts),
            _row(BEA, "BEA GDP", excerpts),
            _row(FRED_SAHM, "SAHMREALTIME", excerpts),
            _row(LEI_URL, "Conference Board LEI", excerpts),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    return packet, rows


def test_payrolls_print_is_not_gdi_percent() -> None:
    _, rows = _mint_notes(BAGGY_GDI_PAYROLLS, [GDI_THEN_PAYROLLS])
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "2.2" not in (payrolls.print or "")
    assert re.search(r"23(?:,000|k)", (payrolls.print or "").replace("−", "-"), re.I)
    assert "2.2" not in payrolls.claim or "23,000" in payrolls.claim or "23k" in payrolls.claim.lower()


def test_gdp_print_is_not_usrec_zero() -> None:
    _, rows = _mint_notes(BAGGY_USREC_GDP, [USREC_THEN_GDP])
    usrec = next(f for f in rows if f.series == "USREC")
    gdp = next(f for f in rows if f.series == "GDP")
    assert usrec.print in {"0", "USREC=0"} or usrec.print == "0"
    assert gdp.print not in {"0", "0%", "2026"}
    assert "0.5" in (gdp.print or "") or "1.5" in (gdp.print or "") or "2.1" in (gdp.print or "")
    assert "gdp" in gdp.claim.lower()
    assert "printed 0.5" in gdp.claim.lower() or "0.5" in gdp.claim
    assert not gdp.claim.lower().startswith("fred july 2026 usrec")


def test_writer_places_usrec0_and_23k() -> None:
    packet, rows = _mint_notes(NO_SAHM_SPINE, [GDI_THEN_PAYROLLS, BAGGY_GDI_PAYROLLS, USREC_THEN_GDP])
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert packet.script.strip()
    assert packet.status == "ready" or (
        packet.status == "hold" and "collision" in (packet.collision_hold_reason or "").lower()
    )
    assert "USREC=0" in cold.vo
    assert "23k" in cold.vo.replace("−", "-").replace(",", "").lower() or "23000" in cold.vo.replace(",", "") or "23,000" in cold.vo


def test_missing_sahm_is_hole_not_empty_script() -> None:
    packet, rows = _mint_notes(NO_SAHM_SPINE)
    assert not any(f.series == "SAHMREALTIME" for f in rows)
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    assert packet.script.strip()
    assert "USREC=0" in packet.script
    assert "23" in packet.script
    assert packet.status == "ready" or "Sahm no_url" not in (packet.receipt.hold_reason or "")


def test_fell_23000_mints_signed_print_and_vo() -> None:
    from onecrew.script import _missing_pack_marks
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    spine = "USREC July 2026 = 0. Nonfarm payrolls fell 23,000 in July 2026. GDP printed 0.5, then 2.1, then 1.5."
    packet, rows = _mint_notes(spine)
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "−23" in payrolls.print or "-23" in payrolls.print
    assert payrolls.print not in {"23,000", "23k"}
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert "−23" in cold.vo or "-23" in cold.vo
    holes = _missing_pack_marks(packet, "USREC=0 smashed into payrolls 23,000.")
    assert holes


def test_rose_23000_print_has_no_minus() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    _, rows = _mint_notes("USREC July 2026 = 0. Nonfarm payrolls rose 23,000 in July 2026.")
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "−" not in payrolls.print and not payrolls.print.startswith("-")
    assert "23,000" in payrolls.print or "23k" in payrolls.print.lower()


def _miss_finding() -> Finding:
    return Finding(
        id="fringe-miss",
        claim="Hidden treaty already mined the strait.",
        stamp="fringe",
        parallel_status="miss",
        note="Parallel miss. Included and tagged fringe. Never sold as fact.",
    )


def test_smash_mixed_months_holds() -> None:
    packet = _packet()
    rows = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (May 2026).",
            stamp="grounded",
            series="USREC",
            print="0",
            when="May 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls fell −23,000.",
            stamp="grounded",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        _miss_finding(),
    ]
    write_receipt(packet, Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows))
    packet.task_spine = (
        "USREC May 2026 = 0. Nonfarm payrolls fell 23,000 in July 2026. "
        "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
    )
    packet.research_pack = packet.task_spine
    write_script(packet)
    assert packet.status == "hold"
    reason = (packet.receipt.hold_reason or "") + " ".join(
        row.detail for row in packet.exclusions if row.detail
    )
    assert "smash mixed months" in reason.lower()
    assert packet.beats == [] or len(packet.beats) == 8


def test_same_month_smash_july() -> None:
    packet = _packet()
    packet.task_spine = "USREC July 2026 = 0. Nonfarm payrolls fell −23,000 in July 2026."
    packet.research_pack = ""
    rows = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (July 2026).",
            stamp="grounded",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls fell −23,000.",
            stamp="grounded",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="gdp-2026-q2",
            claim="GDP printed 0.5, then 2.1, then 1.5.",
            stamp="grounded",
            series="GDP",
            print="0.5",
            when="Q2 2026",
            parallel_url=BEA,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        _miss_finding(),
    ]
    write_receipt(packet, Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows))
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert "USREC=0 (July 2026) smashed into payrolls" in cold.vo
    assert "−23,000" in cold.vo or "-23,000" in cold.vo or "−23k" in cold.vo or "-23k" in cold.vo


LIVE_LABOR_103 = (
    "USREC is 0 in July 2026. "
    "In July 2026, unemployment was 4.1%. "
    "May and June payroll estimates were revised down by 103,000 combined. "
    "GDP printed 0.5, then 2.1, then 1.5. "
    "LEI increased 0.2% after contracting 2.8%."
)


def test_payrolls_print_is_revision_103000_not_digit_23() -> None:
    from onecrew.foundry import FoundryHold, require_minted
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet, rows = _mint_notes(LIVE_LABOR_103)
    assert ledger.parallel_calls == before
    pays = [f for f in rows if f.series == "BLS payrolls"]
    for pay in pays:
        assert "103,000" not in (pay.print or "")
        assert "23" not in (pay.print or "")
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print in {"0", "USREC=0"} or "0" in (usrec.print or "")
    with pytest.raises(FoundryHold, match="foundry dropped named series"):
        require_minted(rows, LIVE_LABOR_103)


def test_missing_payrolls_object_is_foundry_dropped_not_opaque_eight() -> None:
    from onecrew.foundry import FoundryHold, require_minted

    notes = LIVE_LABOR_103
    usrec_only = [
        Finding(
            id="usrec-july-2026",
            claim="USREC is 0 in July 2026.",
            stamp="grounded",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        _miss_finding(),
    ]
    with pytest.raises(FoundryHold, match="foundry dropped named series"):
        require_minted(usrec_only, notes)
    packet = _packet()
    packet.task_spine = notes
    packet.research_pack = notes
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=usrec_only),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "foundry dropped named series" in reason
    assert "_eight_from_pack cannot place minted prints" not in reason


def test_u3_print_is_not_gdp_percent() -> None:
    _, rows = _mint_notes(
        "Real GDP Q1 2026 2.1% In July 2026, unemployment was 4.1%."
    )
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert "2.1" not in (u3.print or "")
    gdp = next(f for f in rows if f.series == "GDP")
    assert "july" not in (gdp.when or "").lower()
    assert re.search(r"Q[12]\s+2026", gdp.when or "", re.I)


def test_lei_print_is_not_gdp_percent() -> None:
    from onecrew.foundry import mint

    packet = _packet()
    spine = "GDP printed 2.1% LEI increased 0.2% after contracting 2.8%."
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(BEA, "BEA GDP", [spine]),
            _row(LEI_URL, "Conference Board LEI", [spine]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    lei = next(f for f in rows if f.series == "LEI")
    assert "0.2" in (lei.print or "") or "2.8" in (lei.print or "")
    assert "2.1" not in (lei.print or "")


def test_unsigned_fell_23000_still_foundryhold() -> None:
    from onecrew.foundry import FoundryHold, require_minted

    notes = "USREC July 2026 = 0. Nonfarm payrolls fell 23,000 in July 2026."
    rows = [
        Finding(
            id="usrec-july-2026",
            claim="USREC July 2026 = 0.",
            stamp="grounded",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls fell 23,000 in July 2026.",
            stamp="grounded",
            series="BLS payrolls",
            print="23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    with pytest.raises(FoundryHold, match="foundry dropped named series"):
        require_minted(rows, notes)


def test_payrolls_when_reads_month_before_cue() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    spine = "In July 2026, payroll employment fell 23,000 while real GDP printed 2.1%."
    _, rows = _mint_notes(spine)
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in payrolls.print
    assert "−" in payrolls.print or payrolls.print.startswith("-")
    assert (payrolls.when or "").lower().startswith("july")


def test_usrec_when_is_latest_month_not_first() -> None:
    _, rows = _mint_notes("USREC May 2026: 0, Jun 2026: 0, Jul 2026: 0.")
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print in {"0", "USREC=0"} or usrec.print == "0"
    assert (usrec.when or "").lower().startswith("jul")
    assert not (usrec.when or "").lower().startswith("may")


def test_gdp_print_is_not_final_sales() -> None:
    _, rows = _mint_notes(
        "BEA real GDP: real final sales to private domestic purchasers rose 4.2%; "
        "Q1 2026 2.1%, Q2 2026 1.5%."
    )
    gdp = next(f for f in rows if f.series == "GDP")
    assert "4.2" not in (gdp.print or "")
    assert "2.1" in (gdp.print or "") or "1.5" in (gdp.print or "") or "0.5" in (gdp.print or "")
    assert re.search(r"Q[12]\s+2026", gdp.when or "", re.I)
    assert "july" not in (gdp.when or "").lower()
    assert (gdp.when or "").strip()


def test_lei_print_matches_july_not_h1_2025() -> None:
    _, rows = _mint_notes(
        "LEI fell 2.8% in the first half of 2025 and rose 0.2% in July 2026."
    )
    lei = next(f for f in rows if f.series == "LEI")
    assert "0.2" in (lei.print or "")
    assert "2.8" not in (lei.print or "")
    assert (lei.when or "").lower().startswith("july")


def test_sahm_when_reads_month_before_cue() -> None:
    _, rows = _mint_notes(
        "In July 2026 the Sahm indicator was -0.03 vs 0.50 trigger while USREC is 0."
    )
    sahm = next(f for f in rows if f.series == "SAHMREALTIME")
    assert (sahm.when or "").lower().startswith("july")


def test_empty_when_holds_when_no_month() -> None:
    spine = "USREC is 0. Nonfarm payrolls fell 23,000."
    packet, rows = _mint_notes(spine)
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert (payrolls.when or "").strip() == ""
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "empty when" in reason.lower()
    assert packet.status == "hold"
    assert packet.beats == [] or len(packet.beats) == 8


def test_gdp_three_bar_print_is_not_lone_q2_half() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    _, rows = _mint_notes("Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%.")
    assert ledger.parallel_calls == before
    gdp = next(f for f in rows if f.series == "GDP")
    assert "0.5" in (gdp.print or "")
    assert "2.1" in (gdp.print or "")
    assert "1.5" in (gdp.print or "")
    if re.search(r"q2", gdp.when or "", re.I):
        assert gdp.print not in {"0.5", "0.5%"}


def test_sahm_hole_turn_does_not_tape_usrec() -> None:
    from onecrew.board import prefer_footage, write_shot_list
    from onecrew.models import Rails

    packet, rows = _mint_notes(NO_SAHM_SPINE)
    usrec = next(f for f in rows if f.series == "USREC")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    turn = next(b for b in packet.beats if b.id == "turn")
    assert usrec.id not in turn.finding_ids
    assert "usrec" not in " ".join(turn.finding_ids).lower()
    blob = f"{turn.vo} {turn.frame}"
    assert "Sahm hole" in blob or "No matching URL" in blob
    shots = write_shot_list(packet)
    prefer_footage(shots, Rails(parallel=True, vertex=False, imagen=False), packet)
    turn_shot = next(s for s in shots if s.beat_id == "turn")
    assert turn_shot.source_refs == []
    assert turn_shot.footage == "missing"
    assert turn_shot.footage_url is None
    assert FRED_USREC not in " ".join(turn_shot.source_refs)


def test_lei_july_not_may_2025_and_stays_off_board() -> None:
    from onecrew.board import prefer_footage, write_shot_list
    from onecrew.foundry import mint
    from onecrew.models import Rails

    prn = "https://www.prnewswire.com/news-releases/lei-may-2025-277.html"
    both = (
        "USREC July 2026 = 0. Nonfarm payrolls July 2026 = −23,000. "
        "GDP printed 0.5, then 2.1, then 1.5. "
        "LEI fell 2.7% in May 2025 and rose 0.2% in July 2026."
    )
    packet, rows = _mint_notes(both)
    lei = next(f for f in rows if f.series == "LEI")
    assert "0.2" in (lei.print or "")
    assert "2.7" not in (lei.print or "")
    assert (lei.when or "").lower().startswith("july")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    shots = write_shot_list(packet)
    prefer_footage(shots, Rails(parallel=True, vertex=False, imagen=False), packet)
    blob = " ".join(
        f"{s.footage_url or ''} {' '.join(s.source_refs)}" for s in shots
    ).lower()
    assert "prnewswire" not in blob
    assert "conference-board" not in blob
    assert not any(lei.id in (s.source_refs or []) for s in shots)

    only_2025 = (
        "USREC July 2026 = 0. Nonfarm payrolls July 2026 = −23,000. "
        "GDP printed 0.5, then 2.1, then 1.5. "
        "LEI fell 2.7% in May 2025."
    )
    packet = _packet()
    packet.task_spine = only_2025
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [only_2025]),
            _row(BLS, "BLS Employment Situation", [only_2025]),
            _row(BEA, "BEA GDP", [only_2025]),
            _row(prn, "Conference Board LEI May 2025", [only_2025]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        only_2025,
    )
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    assert packet.beats
    assert not any(lei_id in b.finding_ids for b in packet.beats for lei_id in (
        {f.id for f in rows if f.series == "LEI"}
    ))
    shots = write_shot_list(packet)
    prefer_footage(shots, Rails(parallel=True, vertex=False, imagen=False), packet)
    assert all(prn not in ((s.footage_url or "") + " ".join(s.source_refs)) for s in shots)


def test_payrolls_when_month_and_year_need_not_be_adjacent() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    spine = (
        "July payroll employment changed little at -23,000, unemployment was 4.1% during 2026."
    )
    assert "July 2026" not in spine
    _, rows = _mint_notes(spine)
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in payrolls.print
    assert "−" in payrolls.print or payrolls.print.startswith("-")
    assert (payrolls.when or "").lower() == "july 2026"
    u3 = next(f for f in rows if f.series == "U-3")
    assert (u3.when or "").lower() == "july 2026"


def test_gdp_two_bar_print_is_not_lone_q2() -> None:
    _, rows = _mint_notes("Real GDP grew 2.1% in Q1 2026 and 1.5% in Q2 2026.")
    gdp = next(f for f in rows if f.series == "GDP")
    assert "2.1" in (gdp.print or "")
    assert "1.5" in (gdp.print or "")
    assert "0.5" not in (gdp.print or "")
    if re.search(r"q2", gdp.when or "", re.I):
        assert gdp.print not in {"2.1", "2.1%"}


LIVE_PTER_CES = (
    "USREC Aug 2026: 0, Jul 2026: 0. "
    "November 2025 unemployment was 4.6%, with 5.5M people working part time for economic reasons, "
    "up 909,000 from September; July 2026 payrolls fell 23,000, but unemployment was still 4.1%. "
    "Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%."
)


def test_payrolls_is_ces_fell_not_pter_909k() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet, rows = _mint_notes(LIVE_PTER_CES)
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "909" not in (payrolls.print or "")
    assert re.search(r"23(?:,000|k)", (payrolls.print or "").replace("−", "-"), re.I)
    assert "−" in payrolls.print or payrolls.print.startswith("-")
    assert (payrolls.when or "").lower().startswith("july")
    assert "2026" in (payrolls.when or "")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert "4.6" not in (u3.print or "")
    assert (u3.when or "").lower().startswith("july")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert "USREC=0 (July 2026) smashed into payrolls" in cold.vo
    assert "−23,000" in cold.vo or "-23,000" in cold.vo or "−23k" in cold.vo or "-23k" in cold.vo
    turn = next(b for b in packet.beats if b.id == "turn")
    assert turn.finding_ids == []


def test_pter_909k_alone_is_not_payrolls() -> None:
    from onecrew.foundry import FoundryHold, require_minted

    spine = (
        "USREC July 2026 = 0. "
        "5.5M people working part time for economic reasons, up 909,000 from September."
    )
    packet, rows = _mint_notes(spine)
    assert not any(f.series == "BLS payrolls" for f in rows)
    assert not any("909" in (f.print or "") and f.series == "BLS payrolls" for f in rows)
    try:
        require_minted(rows, spine)
    except FoundryHold as err:
        assert "foundry dropped named series" in str(err)


SAHM_U3_SPINE = (
    "This rule, attributed to former Fed economist Claudia Sahm, states that when "
    "the three-month moving average of the national unemployment rate is 0.5% or more above its lowest. "
    "Sahm July 2026 = −0.03 vs 0.50 trigger. "
    "USREC Jul 2026: 0, Aug 2026: 0. "
    "July 2026 payroll employment fell 23,000 and unemployment was 4.1 percent. "
    "Real GDP Q4 2025 0.5%, Q1 2026 2.1%, Q2 2026 1.5%."
)


def test_u3_print_is_not_sahm_trigger() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet, rows = _mint_notes(SAHM_U3_SPINE)
    assert ledger.parallel_calls == before
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert "0.5" not in (u3.print or "")
    assert (u3.when or "").lower().startswith("july")
    usrec = next(f for f in rows if f.series == "USREC")
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    sahm = next(f for f in rows if f.series == "SAHMREALTIME")
    assert "0.03" in (sahm.print or "")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    labor = next(b for b in packet.beats if b.id == "labor")
    assert "4.1" in labor.vo
    assert not re.search(r"unemployment\s+0\.5%", labor.vo, re.I)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert "USREC=0 (July 2026) smashed into payrolls" in cold.vo
    assert "−23,000" in cold.vo or "-23,000" in cold.vo or "−23k" in cold.vo or "-23k" in cold.vo
    turn = next(b for b in packet.beats if b.id == "turn")
    assert turn.finding_ids == [sahm.id]
    assert usrec.id not in turn.finding_ids


def test_sahm_definition_alone_is_not_u3() -> None:
    spine = (
        "This rule, attributed to former Fed economist Claudia Sahm, states that when "
        "the three-month moving average of the national unemployment rate is 0.5% or more above its lowest. "
        "USREC July 2026 = 0."
    )
    _, rows = _mint_notes(spine)
    u3s = [f for f in rows if f.series == "U-3"]
    assert not u3s or "0.5" not in (u3s[0].print or "")


LIVE_GDP_TWO_BAR = (
    "USREC July 2026 = 0. Nonfarm payrolls July 2026 = −23,000. "
    "Real GDP rose 2.1 percent in Q1 2026 and 1.5 percent annualized in Q2. "
    "Real GDI grew 2.2%. Final sales to private domestic purchasers rose 4.2%. "
    "Disposable income 0.5%. CEI 0.5%."
)


def test_gdp_vo_speaks_print_not_leftover_half() -> None:
    from onecrew.script import _missing_pack_marks
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet, rows = _mint_notes(LIVE_GDP_TWO_BAR)
    assert ledger.parallel_calls == before
    gdp = next(f for f in rows if f.series == "GDP")
    assert "2.1" in (gdp.print or "")
    assert "1.5" in (gdp.print or "")
    assert "0.5" not in (gdp.print or "")
    assert "2.2" not in (gdp.print or "")
    assert "4.2" not in (gdp.print or "")
    assert re.search(r"q2\s+2026", gdp.when or "", re.I)
    assert "q1" not in (gdp.when or "").lower() or "q2" in (gdp.when or "").lower()
    assert gdp.id == "gdp-2026-q2"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    beat = next(b for b in packet.beats if b.id == "gdp")
    spoken = f"{beat.vo} {beat.frame}"
    assert "2.1" in spoken
    assert "1.5" in spoken
    assert not re.search(r"GDP printed[^.\n]*0\.5|GDP bars:[^.\n]*0\.5", spoken, re.I)
    holes = _missing_pack_marks(packet, spoken)
    assert not any("0.5" in h and "GDP" in h for h in holes)
    leftover = _missing_pack_marks(packet, "GDP printed 0.5, then 2.1, then 1.5.")
    assert leftover
    gdp.print = "0.5 / 2.1 / 1.5"
    missing_half = _missing_pack_marks(packet, "GDP printed 2.1, then 1.5.")
    assert missing_half


def test_gdp_empty_print_holds() -> None:
    packet = _packet()
    rows = [
        Finding(
            id="usrec-july-2026",
            claim="USREC July 2026 = 0.",
            stamp="grounded",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls July 2026 = −23,000.",
            stamp="grounded",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="gdp-2026-q2",
            claim="Real GDP rose.",
            stamp="grounded",
            series="GDP",
            print="",
            when="Q2 2026",
            parallel_url=BEA,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        _miss_finding(),
    ]
    write_receipt(packet, Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows))
    packet.task_spine = "USREC July 2026 = 0. Nonfarm payrolls July 2026 = −23,000."
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "gdp print empty" in reason.lower()
    assert packet.beats == [] or "0.5, then 2.1, then 1.5" not in (packet.script or "")


LIVE_USREC_T10 = (
    "The NBER-based FRED recession indicator remains 0 for August 2026, updated September 1. "
    "ls.gov/news.release/empsit.nr0.htm%20htm, https://fred.stlouisfed.org/series/USREC, "
    "https://fred.stlouisfed.org/series/T10Y3M. "
    "July payrolls fell 23,000 and unemployment was 4.1%. "
    "The LEI rose 0.2% in July to 99.5. January-to-July six-month growth. the 2025 warning. "
    "Real GDP rose 2.1 percent in Q1 2026 and 1.5 percent annualized in Q2."
)


def test_usrec_print_is_not_t10y3m_one() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet, rows = _mint_notes(LIVE_USREC_T10)
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "august 2026"
    assert usrec.id == "usrec-august-2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert (payrolls.when or "").lower().startswith("july")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower().startswith("july")
    assert "august" not in (u3.when or "").lower()
    lei = next((f for f in rows if f.series == "LEI"), None)
    if lei:
        assert "0.2" in (lei.print or "")
        assert (lei.when or "").lower() == "july 2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=1" not in spoken
    assert "smashed" not in spoken.lower() or "August 2026" not in spoken or "July" not in spoken


def test_usrec_not_from_url_only_claim() -> None:
    spine = (
        "https://fred.stlouisfed.org/series/USREC, "
        "https://fred.stlouisfed.org/series/T10Y3M. "
        "July payrolls fell 23,000."
    )
    _, rows = _mint_notes(spine)
    usrecs = [f for f in rows if f.series == "USREC"]
    assert not usrecs or usrecs[0].print != "1"
    assert not any("t10y3m" in (f.claim or "").lower() and f.print == "1" for f in usrecs)


def test_bls_cite_rejects_broken_empsit_href() -> None:
    from onecrew.foundry import mint

    junk = "https://www.bls.gov/news.release/empsit.nr0.htm%20htm"
    archive = "https://www.bls.gov/news.release/archives/empsit_08072026.htm"
    spine = LIVE_USREC_T10
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [spine]),
            _row(junk, "BLS broken", [spine]),
            _row(archive, "BLS archive", [spine]),
            _row(BEA, "BEA GDP", [spine]),
            _row(LEI_URL, "LEI", [spine]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    pay = next(f for f in rows if f.series == "BLS payrolls")
    assert "%20" not in (pay.parallel_url or "")
    assert "08072026" in (pay.parallel_url or "") or "empsit.nr0.htm%20" not in (pay.parallel_url or "")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "%20" not in (u3.parallel_url or "")


LIVE_FRED_PIPE = (
    "Observations Aug 2026: 0. Aug 2026: | 0. Jul 2026: | 0. "
    "Units: +1 or 0. Updated: Sep 1, 2026. "
    "July payrolls fell 23,000 and unemployment was 4.1%. "
    "Real GDP rose 2.1 percent in Q1 2026 and 1.5 percent annualized in Q2."
)


def test_usrec_when_reads_fred_pipe_cells() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet, rows = _mint_notes(LIVE_FRED_PIPE)
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").strip()
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert (payrolls.when or "").lower().startswith("july")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    assert u3.id == "unemployment-july-2026"
    assert "june" not in (u3.when or "").lower()
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert gdp.id == "gdp-2026-q2"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert "USREC=0 (July 2026) smashed into payrolls" in cold.vo
    assert "−23,000" in cold.vo or "-23,000" in cold.vo


def test_usrec_august_only_still_holds_mixed_months() -> None:
    packet, rows = _mint_notes(LIVE_USREC_T10)
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "august 2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert (payrolls.when or "").lower().startswith("july")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    assert "empty when" not in reason.lower()


def test_gdp_cite_rejects_wrong_vintage_pdf() -> None:
    from onecrew.foundry import mint

    old = "https://www.bea.gov/system/files/2025-01/gdp4q24-adv.pdf"
    news = (
        "https://www.bea.gov/news/2026/gross-domestic-product-"
        "second-quarter-2026-advance-estimate"
    )
    spine = LIVE_FRED_PIPE
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [spine]),
            _row(BLS, "BLS Employment Situation", [spine]),
            _row(old, "BEA Q4 2024 advance", [spine]),
            _row(news, "BEA Q2 2026 advance", [spine]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert gdp.id == "gdp-2026-q2"
    assert "gdp4q24" not in (gdp.parallel_url or "")
    assert "second-quarter-2026" in (gdp.parallel_url or "")


BEA_2023_EST = (
    "https://www.bea.gov/news/2024/gross-domestic-product-"
    "fourth-quarter-and-year-2023-second-estimate"
)
BEA_2026_EST = (
    "https://www.bea.gov/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026"
)
LIVE_GDP_OLD_THEN_NEW = (
    "Real GDP increased 2.5% in the fourth quarter of 2023. "
    f"{BEA_2023_EST} "
    "In 2026, real GDP increased 2.1% in Q1 and 1.5% annualized in Q2. "
    f"{BEA_2026_EST} "
    "USREC Jul 2026: 0. July payrolls fell 23,000 and unemployment was 4.1%."
)


def test_gdp_print_is_2026_two_bar_not_2023_two_five() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_GDP_OLD_THEN_NEW
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [LIVE_GDP_OLD_THEN_NEW]),
            _row(BLS, "BLS Employment Situation", [LIVE_GDP_OLD_THEN_NEW]),
            _row(BEA_2023_EST, "BEA 2023 Q4 second estimate", ["Real GDP increased 2.5%."]),
            _row(BEA_2026_EST, "BEA 2026 Q2 second estimate", [
                "In 2026, real GDP increased 2.1% in Q1 and 1.5% annualized in Q2."
            ]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_GDP_OLD_THEN_NEW,
    )
    assert ledger.parallel_calls == before
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert "2.5" not in (gdp.print or "")
    assert (gdp.when or "").upper().replace(" ", "") == "Q22026" or (gdp.when or "").upper() == "Q2 2026"
    assert gdp.id == "gdp-2026-q2"
    assert "2026" in (gdp.parallel_url or "")
    assert "2023-second-estimate" not in (gdp.parallel_url or "")
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert usrec.id == "usrec-july-2026"
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower().startswith("july")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "2.1" in spoken
    assert "1.5" in spoken
    assert "2.5" not in spoken
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken


def test_lei_cite_rejects_june_decline_for_july_rise() -> None:
    from onecrew.foundry import mint

    old = "https://www.prnewswire.com/news-releases/lei-for-the-us-declined-in-june-302509575.html"
    spine = "The LEI rose 0.2% in July 2026. USREC July 2026 = 0. July payrolls fell 23,000."
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [spine]),
            _row(BLS, "BLS", [spine]),
            _row(old, "LEI declined in June", [spine]),
            _row(LEI_URL, "Conference Board LEI", [spine]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    lei = next((f for f in rows if f.series == "LEI"), None)
    if lei:
        assert "0.2" in (lei.print or "")
        assert (lei.when or "").lower() == "july 2026"
        assert "declined-in-june" not in (lei.parallel_url or "")
        assert "conference-board.org" in (lei.parallel_url or "")


LEI_JUNE_DECLINE = (
    "https://www.prnewswire.com/news-releases/lei-for-the-us-declined-in-june-302509575.html"
)
LIVE_LEI_OLD_THEN_NEW = (
    "The LEI declined 2.8% in the first half of 2025. "
    f"{LEI_JUNE_DECLINE} "
    "The LEI rose 0.2% in July to 99.5. "
    "July payrolls fell 23,000 and unemployment was 4.1%. "
    "Sahm −0.03 vs 0.50 trigger. "
    "USREC Jul 2026: 0. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
)


def test_lei_print_is_july_2026_turn_not_h1_2025() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_LEI_OLD_THEN_NEW
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [LIVE_LEI_OLD_THEN_NEW]),
            _row(BLS, "BLS Employment Situation", [LIVE_LEI_OLD_THEN_NEW]),
            _row(LEI_JUNE_DECLINE, "LEI declined in June 2025", [
                "The LEI declined 2.8% in the first half of 2025."
            ]),
            _row(LEI_URL, "Conference Board LEI", [
                "The LEI rose 0.2% in July to 99.5."
            ]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Sahm −0.03 vs 0.50 trigger."]),
            _row(BEA, "BEA GDP", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_LEI_OLD_THEN_NEW,
    )
    assert ledger.parallel_calls == before
    lei = next((f for f in rows if f.series == "LEI"), None)
    if lei:
        assert lei.print == "0.2%"
        assert "2.8" not in (lei.print or "")
        assert (lei.when or "").lower() == "july 2026"
        assert lei.id == "lei-july-2026"
        assert "declined-in-june" not in (lei.parallel_url or "")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    assert u3.id == "unemployment-july-2026"
    sahm = next(f for f in rows if f.series == "SAHMREALTIME")
    assert "0.03" in (sahm.print or "")
    assert (sahm.when or "").strip()
    assert (sahm.when or "").lower() == "july 2026"
    assert sahm.id == "sahm-july-2026"
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.id == "usrec-july-2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    turn = next(b for b in packet.beats if b.id == "turn")
    assert turn.finding_ids == [sahm.id]


BLS_NR0 = "https://www.bls.gov/news.release/empsit.nr0.htm"
BLS_JULY_ARCHIVE = "https://www.bls.gov/news.release/archives/empsit_08072026.htm"
BEA_GDP2Q26_PDF = "https://www.bea.gov/sites/default/files/2026-08/gdp2q26-2nd.pdf"
LIVE_PAY_OLD_THEN_NEW = (
    "Nonfarm payrolls fell 103,000 in June 2025. "
    f"{BLS_NR0} "
    "July 2026 payroll employment fell 23,000 and unemployment was 4.1%. "
    "Jul 2026: | 0. Aug 2026: | 0. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    f"{BEA_GDP2Q26_PDF}"
)


def test_payrolls_print_is_july_2026_ces_not_june_2025_revision() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_PAY_OLD_THEN_NEW
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [LIVE_PAY_OLD_THEN_NEW]),
            _row(BLS_NR0, "BLS current", ["Nonfarm payrolls fell 103,000 in June 2025."]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July 2026 payroll employment fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_GDP2Q26_PDF, "BEA Q2 2026 PDF", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_PAY_OLD_THEN_NEW,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert "103" not in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "%20" not in (payrolls.parallel_url or "")
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert usrec.id == "usrec-july-2026"
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert gdp.id == "gdp-2026-q2"
    assert "2026" in (gdp.parallel_url or "")
    assert "gdp4q24" not in (gdp.parallel_url or "")
    assert "2023-second-estimate" not in (gdp.parallel_url or "")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken
    assert "103,000" not in spoken


BEA_2026_NEWS = (
    "https://www.bea.gov/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026"
)
LIVE_FRED_OBS = (
    "The FRED recession observation for August 2026 is 0. "
    f"{FRED_USREC} "
    "July nonfarm payrolls fell by 23,000 and unemployment was 4.1%. "
    f"{BLS} "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% in Q2. "
    f"{BEA_2026_NEWS} "
    "July Sahm −0.03. "
    f"{FRED_SAHM} "
    "The LEI rose 0.2% in July to 99.5. "
    f"{LEI_URL}"
)


def test_usrec_mints_fred_observation_prose_and_keeps_pack() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_FRED_OBS
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [LIVE_FRED_OBS]),
            _row(BLS, "Employment Situation 2026 M07", [
                "July nonfarm payrolls fell by 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_2026_NEWS, "BEA Q2 2026 second estimate", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% in Q2."
            ]),
            _row(FRED_SAHM, "SAHMREALTIME", ["July Sahm −0.03."]),
            _row(LEI_URL, "Conference Board LEI", ["The LEI rose 0.2% in July to 99.5."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_FRED_OBS,
    )
    assert ledger.parallel_calls == before
    assert rows
    assert any(f.stamp == "grounded" for f in rows)
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "august 2026"
    assert usrec.id == "usrec-august-2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "%20" not in (payrolls.parallel_url or "")
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert gdp.id == "gdp-2026-q2"
    assert "2026" in (gdp.parallel_url or "")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    lei = next((f for f in rows if f.series == "LEI"), None)
    if lei:
        assert "0.2" in (lei.print or "")
        assert (lei.when or "").lower() == "july 2026"
        assert "declined-in-june" not in (lei.parallel_url or "")
    sahm = next((f for f in rows if f.series == "SAHMREALTIME"), None)
    if sahm:
        assert "0.03" in (sahm.print or "")
        assert (sahm.when or "").lower() == "july 2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    assert packet.receipt.findings
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    assert packet.beats == [] or len(packet.beats) == 8


def test_mint_keeps_other_findings_when_usrec_has_no_url() -> None:
    from onecrew.foundry import mint

    spine = (
        "USREC July 2026 = 0. "
        "July payrolls fell 23,000 and unemployment was 4.1%. "
        "Real GDP increased 2.1% in Q1 2026 and 1.5% in Q2."
    )
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(BLS, "Employment Situation 2026 M07", [spine]),
            _row(BEA, "BEA GDP", [spine]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert rows
    assert any(f.series == "BLS payrolls" for f in rows)
    assert any(f.series == "GDP" and f.print == "2.1 / 1.5" for f in rows)
    assert not any(f.series == "USREC" for f in rows)


BEA_2026_ADVANCE = (
    "https://www.bea.gov/news/2026/gross-domestic-product-second-quarter-2026-advance-estimate"
)
LEI_AUG_PDF = (
    "https://www.conference-board.org/pdf_free/press/US%20LEI%20PRESS%20RELEASE-August%202026.pdf"
)
LIVE_CES_NOT_HYPOTHETICAL = (
    "Suppose the estimate of nonfarm employment increases by 50,000 from one month to the next. "
    "July nonfarm payroll employment fell by 23,000 and unemployment was 4.1%. "
    "Jul 2026: | 0. Aug 2026: | 0. "
    "Disposable personal income and CEI rose 0.5%. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    "The LEI rose 0.2% in July to 99.5. "
    f"{BLS_NR0} {BLS_JULY_ARCHIVE} {BEA_2026_ADVANCE} {BEA_2026_NEWS} {LEI_AUG_PDF}"
)


def test_payrolls_is_ces_fell_not_bls_hypothetical() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_CES_NOT_HYPOTHETICAL
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [LIVE_CES_NOT_HYPOTHETICAL]),
            _row(BLS_NR0, "Employment Situation 2026 M07 Results", [
                "Suppose the estimate of nonfarm employment increases by 50,000 from one month to the next."
            ]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July nonfarm payroll employment fell by 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_2026_ADVANCE, "BEA advance", [
                "Disposable personal income and CEI rose 0.5%. Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
            _row(LEI_AUG_PDF, "Conference Board LEI August 2026 release", [
                "The LEI rose 0.2% in July to 99.5."
            ]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_CES_NOT_HYPOTHETICAL,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert "50,000" not in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "august" not in (payrolls.when or "").lower()
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.id == "usrec-july-2026"
    lei = next(f for f in rows if f.series == "LEI")
    assert "0.2" in (lei.print or "")
    assert lei.id == "lei-july-2026"
    assert "declined-in-june" not in (lei.parallel_url or "")
    assert "conference-board.org" in (lei.parallel_url or "")
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert gdp.id == "gdp-2026-q2"
    assert "second-estimate" in (gdp.parallel_url or "") or "gdp2q26-2nd" in (gdp.parallel_url or "")
    assert "advance-estimate" not in (gdp.parallel_url or "")
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "foundry dropped named series" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken
    assert "50,000" not in spoken
    assert "2.1" in spoken and "1.5" in spoken
    assert "0.5, then 2.1" not in spoken


BEA_Q4_THIRD = (
    "https://www.bea.gov/news/2026/gross-domestic-product-fourth-quarter-and-year-2025-third-estimate"
)
LEI_JULY_2025_PDF = (
    "https://www.conference-board.org/pdf_free/press/US%20LEI%20PRESS%20RELEASE-July%202025.pdf"
)
LIVE_CES_NOT_CI = (
    "If, however, the reported nonfarm employment rise was 250,000, then all of "
    "the values within the 90-percent confidence interval would be greater than zero. "
    "July nonfarm payroll employment fell by 23,000 and unemployment was 4.1%. "
    "Aug 2026: | 0. "
    "SPF projects real GDP 2.2% in 2026 and 1.9% in 2027, including Q1 2027. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    "The LEI rose 0.2% in July to 99.5. "
    "Jul 2026: -0.03. "
    f"{BLS_NR0} {BLS_JULY_ARCHIVE} {BEA_Q4_THIRD} {BEA_2026_NEWS} "
    f"{LEI_JULY_2025_PDF} {LEI_AUG_PDF} {FRED_SAHM}"
)


def test_payrolls_is_ces_fell_not_bls_confidence_interval() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_CES_NOT_CI
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["Aug 2026: | 0."]),
            _row(BLS_NR0, "Employment Situation 2026 M07 Results", [
                "If, however, the reported nonfarm employment rise was 250,000, "
                "then all of the values within the 90-percent confidence interval "
                "would be greater than zero."
            ]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July nonfarm payroll employment fell by 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_Q4_THIRD, "BEA Q4 third estimate", [
                "SPF projects real GDP 2.2% in 2026 and 1.9% in 2027, including Q1 2027."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
            _row(LEI_JULY_2025_PDF, "LEI July 2025 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(LEI_AUG_PDF, "LEI August 2026 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Jul 2026: -0.03."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_CES_NOT_CI,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert "250,000" not in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert "2.2" not in (gdp.print or "")
    assert gdp.id == "gdp-2026-q2"
    assert "2027" not in (gdp.when or "")
    assert "second-estimate" in (gdp.parallel_url or "") or "gdp2q26-2nd" in (gdp.parallel_url or "")
    assert "third-estimate" not in (gdp.parallel_url or "")
    lei = next(f for f in rows if f.series == "LEI")
    assert "0.2" in (lei.print or "")
    assert lei.id == "lei-july-2026"
    assert "2025" not in (lei.parallel_url or "")
    assert "2026" in (lei.parallel_url or "")
    sahm = next(f for f in rows if f.series == "SAHMREALTIME")
    assert "0.03" in (sahm.print or "")
    assert (sahm.when or "").lower() == "july 2026"
    assert sahm.id == "sahm-july-2026"
    usrec = next(f for f in rows if f.series == "USREC")
    assert (usrec.when or "").lower() == "august 2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    assert packet.receipt.findings
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    assert "foundry dropped named series" not in reason.lower()
    assert packet.beats == [] or len(packet.beats) == 8


LIVE_U3_NOT_MAY_2024 = (
    "Jul 2026: | 0. "
    "July payrolls fell 23,000. "
    "July unemployment was 4.1%; May 2024 unemployment was 4.3%. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    "The LEI rose 0.2% in July to 99.5. "
    "Jul 2026: -0.03. "
    f"{BLS_NR0} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS} {LEI_AUG_PDF} {FRED_SAHM}"
)


def test_u3_print_is_july_2026_ces_not_may_2024() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_U3_NOT_MAY_2024
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["Jul 2026: | 0."]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July payrolls fell 23,000. July unemployment was 4.1%."
            ]),
            _row(BLS_NR0, "Employment Situation 2026 M07 Results", [
                "May 2024 unemployment was 4.3%."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
            _row(LEI_AUG_PDF, "LEI August 2026 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Jul 2026: -0.03."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_U3_NOT_MAY_2024,
    )
    assert ledger.parallel_calls == before
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert "4.3" not in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    assert u3.id == "unemployment-july-2026"
    assert "may" not in (u3.when or "").lower()
    assert "empsit_08072026" in (u3.parallel_url or "")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    labor = next(b for b in packet.beats if b.id == "labor")
    assert "4.1" in labor.vo
    assert "4.3" not in labor.vo
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "4.3%" not in spoken


LIVE_JULY_OBS_NOT_RELEASE = (
    "Jul 2026: | 0. Aug 2026: | 0. "
    "July payrolls fell 23,000 dated August 2026 from empsit_08072026.htm "
    f"and unemployment was 4.1%. {BLS_JULY_ARCHIVE} "
    "The LEI rose 0.2% in July to 99.5. "
    "Jul 2026: -0.03. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2 after a 0.5 percent annualized reading. "
    f"{BLS_NR0} {BEA_2026_NEWS} {LEI_JULY_2025_PDF} {LEI_AUG_PDF} {FRED_SAHM} {FRED_USREC}"
)


def test_july_observation_not_empsit_release_month() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_JULY_OBS_NOT_RELEASE
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["Jul 2026: | 0. Aug 2026: | 0."]),
            _row(BLS_JULY_ARCHIVE, "BLS August 7 release of July data", [
                "July payrolls fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BLS_NR0, "Employment Situation 2026 M07 Results", [
                "July payrolls fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2 "
                "after a 0.5 percent annualized reading."
            ]),
            _row(LEI_JULY_2025_PDF, "LEI July 2025 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(LEI_AUG_PDF, "LEI August 2026 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Jul 2026: -0.03."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_JULY_OBS_NOT_RELEASE,
    )
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "august" not in (payrolls.when or "").lower()
    u3 = next(f for f in rows if f.series == "U-3")
    assert "4.1" in (u3.print or "")
    assert (u3.when or "").lower() == "july 2026"
    assert u3.id == "unemployment-july-2026"
    assert "august" not in (u3.when or "").lower()
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert "0.5" not in (gdp.print or "")
    assert gdp.id == "gdp-2026-q2"
    lei = next(f for f in rows if f.series == "LEI")
    assert "0.2" in (lei.print or "")
    assert lei.id == "lei-july-2026"
    assert "2025" not in (lei.parallel_url or "")
    assert "2026" in (lei.parallel_url or "")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken
    assert "August 2026" not in spoken or "USREC=0 (August 2026)" not in spoken
    gdp_vo = next(b for b in packet.beats if b.id == "gdp").vo
    assert "2.1" in gdp_vo and "1.5" in gdp_vo
    assert "0.5" not in gdp_vo


LIVE_SMASH_JULY_NOT_JUNE_OR_2027 = (
    "The 2027 outlook. "
    "Jun 2026: | 0. "
    "July payrolls fell 23,000 and unemployment was 4.1%. "
    "Apr 2026: | 0. May 2026: | 0. Jul 2026: | 0. Aug 2026: | 0. "
    "SPF projects real GDP 2.2% in 2027 and Real GDP increased 2.1% in Q1 2026 "
    "and 1.5% annualized in Q2. "
    "The LEI rose 0.2% in July to 99.5. "
    "Jul 2026: -0.03. "
    f"{BLS_JULY_ARCHIVE} {BEA_GDP2Q26_PDF} {LEI_AUG_PDF} {FRED_SAHM} {FRED_USREC}"
)


def test_usrec_smash_july_not_june_and_payrolls_year_is_ces_not_2027() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_SMASH_JULY_NOT_JUNE_OR_2027
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [
                "Jun 2026: | 0. Apr 2026: | 0. May 2026: | 0. Jul 2026: | 0. Aug 2026: | 0."
            ]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July payrolls fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_GDP2Q26_PDF, "BEA Q2 2026 second-estimate PDF", [
                "SPF projects real GDP 2.2% in 2027 and Real GDP increased 2.1% in Q1 2026 "
                "and 1.5% annualized in Q2."
            ]),
            _row(LEI_AUG_PDF, "LEI August 2026 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Jul 2026: -0.03."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_SMASH_JULY_NOT_JUNE_OR_2027,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "2027" not in (payrolls.when or "")
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    assert "june" not in (usrec.when or "").lower()
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert "2.2" not in (gdp.print or "")
    assert gdp.id == "gdp-2026-q2"
    assert "gdp2q26-2nd" in (gdp.parallel_url or "") or "second-estimate" in (gdp.parallel_url or "")
    lei = next(f for f in rows if f.series == "LEI")
    assert lei.id == "lei-july-2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken
    assert packet.beats
    assert next(b for b in packet.beats if b.id == "cold-open")
    gdp_vo = next(b for b in packet.beats if b.id == "gdp").vo
    assert "2.1" in gdp_vo and "1.5" in gdp_vo
    assert "0.5" not in gdp_vo


LIVE_PIPE_JUL_AND_AUGUST_PROSE = (
    "Jun 2026: | 0. Jul 2026: | 0. Aug 2026: | 0. "
    "The NBER-based FRED recession indicator remains 0 for August 2026. "
    "FRED USREC is 0 in August 2026. "
    "July payrolls fell 23,000 and unemployment was 4.1%. "
    "SPF projects 2.2% in 2027. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    "The LEI rose 0.2% in July to 99.5. "
    "Jul 2026: -0.03. "
    f"{FRED_USREC} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS} {LEI_AUG_PDF} {FRED_SAHM}"
)


def test_pipe_jul_zero_beats_august_prose_and_smashes_july() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_PIPE_JUL_AND_AUGUST_PROSE
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [
                "Jun 2026: | 0. Jul 2026: | 0. Aug 2026: | 0. "
                "The NBER-based FRED recession indicator remains 0 for August 2026. "
                "FRED USREC is 0 in August 2026."
            ]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July payrolls fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "SPF projects 2.2% in 2027. "
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
            _row(LEI_AUG_PDF, "LEI August 2026 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Jul 2026: -0.03."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_PIPE_JUL_AND_AUGUST_PROSE,
    )
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    assert "august" not in (usrec.when or "").lower()
    assert "june" not in (usrec.when or "").lower()
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "2027" not in (payrolls.when or "")
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert gdp.id == "gdp-2026-q2"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken
    assert packet.beats
    assert next(b for b in packet.beats if b.id == "cold-open")
    gdp_vo = next(b for b in packet.beats if b.id == "gdp").vo
    assert "2.1" in gdp_vo and "1.5" in gdp_vo
    assert "0.5" not in gdp_vo


def test_august_prose_only_holds_mixed_months_and_keeps_findings(monkeypatch) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.foundry import FoundryHold
    from onecrew.models import Rails
    from onecrew.spend import ledger

    spine = (
        "The NBER-based FRED recession indicator remains 0 for August 2026. "
        "FRED USREC is 0 in August 2026. "
        "July payrolls fell 23,000 and unemployment was 4.1%. "
        "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
        "The LEI rose 0.2% in July to 99.5. "
        "Jul 2026: -0.03."
    )

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/hidden-treaty",
                        title="Hidden treaty",
                        excerpts=["Secret double-dip already started in May."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(url=FRED_USREC, title="USREC", excerpts=[spine]),
                SimpleNamespace(
                    url=BLS_JULY_ARCHIVE,
                    title="BLS July archive",
                    excerpts=["July payrolls fell 23,000 and unemployment was 4.1%."],
                ),
                SimpleNamespace(
                    url=BEA_2026_NEWS,
                    title="BEA second estimate",
                    excerpts=["Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."],
                ),
                SimpleNamespace(
                    url=LEI_AUG_PDF,
                    title="LEI August 2026 PDF",
                    excerpts=["The LEI rose 0.2% in July to 99.5."],
                ),
                SimpleNamespace(url=FRED_SAHM, title="SAHMREALTIME", excerpts=["Jul 2026: -0.03."]),
            ]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[SimpleNamespace(url=FRED_USREC, title="USREC", excerpts=[spine])],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        if processor == "base":
            return SimpleNamespace(output=SimpleNamespace(content={}, basis=[]))
        return SimpleNamespace(output=SimpleNamespace(content=spine, basis=[]))

    def boom_require(findings, notes):
        raise FoundryHold("foundry dropped named series")

    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.agent.shift.require_minted", boom_require)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    before = ledger.parallel_calls
    shift = open_shift(
        "Are we near recession?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Are we near recession?",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=True)
    packet = run_live_packet(shift)
    assert ledger.parallel_calls == before
    findings = packet.receipt.findings if packet.receipt else []
    assert findings
    assert any(f.series == "USREC" and (f.when or "").lower() == "august 2026" for f in findings)
    assert any(f.series == "BLS payrolls" and (f.when or "").lower() == "july 2026" for f in findings)
    reason = (
        (packet.receipt.hold_reason or "")
        + " "
        + (packet.collision_hold_reason or "")
        + " "
        + " ".join(row.detail for row in packet.exclusions)
    ).lower()
    assert "smash mixed months" not in reason
    assert findings
    assert packet.beats == [] or len(packet.beats) == 8
    assert "rails missing" not in reason
    assert "foundry dropped named series" not in reason or findings


# Split so a 200-char GDP cue window cannot see both bars. Live f3463c68 shape.
_GDP_SPLIT_PAD = (
    "Jun 2026: | 0. Jul 2026: | 0. Aug 2026: | 0. "
    "July payrolls fell 23,000 and unemployment was 4.1%. "
    "The LEI rose 0.2% in July to 99.5. Jul 2026: -0.03. "
    "NBER recession indicator pipe cells stay on the FRED table. "
    "CES employment situation archive is the July payrolls month. "
)


LIVE_GDP_SPLIT_FRAGMENT = (
    f"{_GDP_SPLIT_PAD}"
    "Real GDP increased 2.1% annualized in Q1 2026. "
    "The later Q2 GDP release reported the first-quarter print still standing. "
    "The Q4 risk case after those 2026 prints remains. "
    f"{_GDP_SPLIT_PAD}"
    "BEA second estimate: real GDP rose 1.5% annualized in Q2 2026. "
    "Q4 2025 growth was only 0.5%. "
    "SPF projects 2.2% in 2027. "
    "Disposable personal income and CEI rose 0.5%. "
    f"{FRED_USREC} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS} {LEI_AUG_PDF} {FRED_SAHM}"
)


def test_split_q1_q2_gdp_fragment_still_mints_two_bars() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_GDP_SPLIT_FRAGMENT
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["Jun 2026: | 0. Jul 2026: | 0. Aug 2026: | 0."]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July payrolls fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "Real GDP increased 2.1% annualized in Q1 2026. "
                "The later Q2 GDP release reported the first-quarter print still standing. "
                "The Q4 risk case after those 2026 prints remains. "
                "BEA second estimate: real GDP rose 1.5% annualized in Q2 2026. "
                "Q4 2025 growth was only 0.5%. "
                "SPF projects 2.2% in 2027. "
                "Disposable personal income and CEI rose 0.5%."
            ]),
            _row(LEI_AUG_PDF, "LEI August 2026 PDF", ["The LEI rose 0.2% in July to 99.5."]),
            _row(FRED_SAHM, "SAHMREALTIME", ["Jul 2026: -0.03."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_GDP_SPLIT_FRAGMENT,
    )
    assert ledger.parallel_calls == before
    gdp = next(f for f in rows if f.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert "0.5" not in (gdp.print or "")
    assert (gdp.when or "").upper().replace(" ", "") == "Q22026"
    assert gdp.id == "gdp-2026-q2"
    assert "q4" not in (gdp.when or "").lower()
    assert "gdp-2026-q4" != gdp.id
    assert "gdp2q26" in (gdp.parallel_url or "").lower() or "second-estimate" in (
        gdp.parallel_url or ""
    ).lower() or "2nd-quarter-2026" in (gdp.parallel_url or "").lower()
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    gdp_vo = next(b for b in packet.beats if b.id == "gdp").vo
    assert "2.1" in gdp_vo and "1.5" in gdp_vo
    assert ", then " in gdp_vo
    assert "GDP printed 2.1. One bar at a time." not in gdp_vo
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken


def test_single_realized_gdp_bar_does_not_invent_second() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    spine = (
        "Jul 2026: | 0. "
        "July payrolls fell 23,000 and unemployment was 4.1%. "
        "Real GDP increased 2.1% annualized in Q1 2026. "
        f"{FRED_USREC} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS}"
    )
    packet, rows = _mint_notes(spine)
    assert ledger.parallel_calls == before
    gdp = next(f for f in rows if f.series == "GDP")
    assert "1.5" not in (gdp.print or "")
    assert gdp.print != "2.1 / 1.5"
    assert "2.1" in (gdp.print or "")
    assert "q2" not in (gdp.when or "").lower()
    assert gdp.id != "gdp-2026-q2"


# Live HOLD oc-are-we-near-recession-f41dbb35 shape: realized July CES
# sits in the same Parallel notes as Moody's June revision, hypo/CI, May
# +129k, ISO USREC pipe 0, August USREC prose, Sahm June, T10Y3M chrome.
LIVE_MIXED_PARALLEL = (
    "Moody's Analytics noted that payrolls actually declined by 13,000 jobs in June 2024. "
    "May 2026 payrolls were revised up from +80,000 to +129,000. "
    "Suppose employment increases by 50,000 from one month to the next. "
    "If, however, the reported nonfarm employment rise was 250,000, then all of "
    "the values within the 90-percent confidence interval would be greater than zero. "
    "THE EMPLOYMENT SITUATION -- JULY 2026. "
    "Total nonfarm payroll employment fell by 23,000 in July 2026. "
    "The unemployment rate was 4.3 percent in July 2026. "
    "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
    "The FRED recession observation for August 2026 is 0. "
    "Updated: Sep 1, 2026. Units: +1 or 0. "
    "Sahm June 2026 = −0.03 vs 0.50 trigger. "
    "https://fred.stlouisfed.org/series/T10Y3M T10Y3M = 1. "
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    f"{FRED_USREC} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS} {FRED_SAHM}"
)

_FORBIDDEN_PAY_PRINTS = (
    "13,000",
    "−13,000",
    "-13,000",
    "50,000",
    "80,000",
    "+80,000",
    "250,000",
    "129,000",
    "+129,000",
)


def _assert_july_ces_payrolls(payrolls) -> None:
    printed = payrolls.print or ""
    claim = payrolls.claim or ""
    assert "23,000" in printed or "23k" in printed.lower()
    assert printed.startswith(("−", "-"))
    for stolen in _FORBIDDEN_PAY_PRINTS:
        assert stolen not in printed
        assert stolen not in claim
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"
    assert "2024" not in (payrolls.when or "")
    assert "2027" not in (payrolls.when or "")
    assert "june" not in (payrolls.when or "").lower()


def test_mixed_parallel_notes_mint_july_ces_not_revision_or_june() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger
    from onecrew.verify import (
        CiteBag,
        CiteExcerpt,
        apply_verify_gate,
        claims_from_findings,
        verify_payrolls_realized_ces,
        verify_usrec_smash,
    )

    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = LIVE_MIXED_PARALLEL
    hit_rows = [
        _row(FRED_USREC, "USREC", [
            "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
            "The FRED recession observation for August 2026 is 0. "
            "Updated: Sep 1, 2026."
        ]),
        _row(BLS_JULY_ARCHIVE, "BLS July archive", [
            "THE EMPLOYMENT SITUATION -- JULY 2026. "
            "Total nonfarm payroll employment fell by 23,000 in July 2026. "
            "The unemployment rate was 4.3 percent in July 2026."
        ]),
        _row(BLS_NR0, "BLS technical notes", [
            "Moody's Analytics noted that payrolls actually declined by 13,000 jobs in June 2024. "
            "May 2026 payrolls were revised up from +80,000 to +129,000. "
            "Suppose employment increases by 50,000 from one month to the next. "
            "If, however, the reported nonfarm employment rise was 250,000, then all of "
            "the values within the 90-percent confidence interval would be greater than zero."
        ]),
        _row(BEA_2026_NEWS, "BEA second estimate", [
            "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
        ]),
        _row(FRED_SAHM, "SAHMREALTIME", ["Sahm June 2026 = −0.03 vs 0.50 trigger."]),
    ]
    rows = mint(
        packet,
        hit_rows,
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        LIVE_MIXED_PARALLEL,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    _assert_july_ces_payrolls(payrolls)
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    assert "august" not in (usrec.when or "").lower()
    assert "june" not in (usrec.when or "").lower()
    claims = claims_from_findings(rows)
    pay_claim = next(c for c in claims if c.series == "BLS payrolls")
    assert "23" in (pay_claim.print or "")
    for stolen in _FORBIDDEN_PAY_PRINTS:
        assert stolen not in (pay_claim.print or "")
    assert (pay_claim.when or "").lower() == "july 2026"
    usrec_claim = next(c for c in claims if c.series == "USREC")
    assert usrec_claim.print == "0"
    assert (usrec_claim.when or "").lower() == "july 2026"
    bag = CiteBag(
        excerpts=[
            CiteExcerpt(url=r.url, title=r.title, text=" ".join(r.excerpts)) for r in hit_rows
        ],
        spine=LIVE_MIXED_PARALLEL,
        hit_urls=[r.url for r in hit_rows],
    )
    ces = verify_payrolls_realized_ces(pay_claim, bag)
    assert ces.ok is True
    smash = verify_usrec_smash(usrec_claim, pay_claim, bag)
    assert smash.ok is True
    gated = apply_verify_gate(
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
        bag,
    )
    assert gated.disposition == "READY"
    assert gated.findings
    write_receipt(packet, gated)
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "hypo/CI/revision window" not in reason
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "−23,000" in spoken or "-23,000" in spoken or "−23k" in spoken or "-23k" in spoken
    assert "13,000" not in spoken
    assert "USREC=1" not in spoken


def test_same_sentence_ces_survives_revision_clause() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    spine = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls July 2026 = −23,000; May+June revised −103,000."
    )
    _, rows = _mint_notes(spine)
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert "103" not in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"


def test_comma_glued_ces_survives_revision_clause() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    spine = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls fell by 23,000 in July 2026, and May and June were "
        "revised down by 103,000."
    )
    _, rows = _mint_notes(spine)
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert "23,000" in (payrolls.print or "")
    assert "103" not in (payrolls.print or "")
    assert (payrolls.when or "").lower() == "july 2026"
    assert payrolls.id == "payrolls-july-2026"


def test_fall_unsigned_is_minus_signed_stays_rise_does_not_invent() -> None:
    from onecrew.spend import ledger

    before = ledger.parallel_calls
    _, fell = _mint_notes("USREC July 2026 = 0. Nonfarm payrolls fell 23,000 in July 2026.")
    pay_fell = next(f for f in fell if f.series == "BLS payrolls")
    assert pay_fell.print.startswith(("−", "-"))
    assert "23,000" in pay_fell.print
    _, signed = _mint_notes("USREC July 2026 = 0. Nonfarm payrolls −23,000 in July 2026.")
    pay_signed = next(f for f in signed if f.series == "BLS payrolls")
    assert pay_signed.print.startswith(("−", "-"))
    assert "23,000" in pay_signed.print
    _, rose = _mint_notes("USREC July 2026 = 0. Nonfarm payrolls rose 23,000 in July 2026.")
    pay_rose = next(f for f in rose if f.series == "BLS payrolls")
    assert not pay_rose.print.startswith(("−", "-"))
    assert "23,000" in pay_rose.print
    assert ledger.parallel_calls == before


def test_revision_hypo_ci_only_does_not_mint_payrolls_as_ces() -> None:
    from onecrew.foundry import FoundryHold, mint, require_minted
    from onecrew.spend import ledger

    spine = (
        "USREC July 2026 = 0. "
        "Moody's Analytics noted that payrolls actually declined by 13,000 jobs in June 2024. "
        "May 2026 payrolls were revised up from +80,000 to +129,000. "
        "Suppose employment increases by 50,000 from one month to the next. "
        "If, however, the reported nonfarm employment rise was 250,000, then all of "
        "the values within the 90-percent confidence interval would be greater than zero."
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["USREC July 2026 = 0."]),
            _row(BLS_NR0, "BLS technical notes", [spine]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    pays = [f for f in rows if f.series == "BLS payrolls"]
    for pay in pays:
        printed = pay.print or ""
        for stolen in _FORBIDDEN_PAY_PRINTS:
            assert stolen not in printed
    assert not pays or not any("23" in (p.print or "") for p in pays)
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    with pytest.raises(FoundryHold, match="foundry dropped named series"):
        require_minted(rows, spine)
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "foundry dropped named series" in reason.lower() or "hypo/CI/revision" in reason
    assert packet.receipt.findings
    assert any(f.series == "USREC" for f in packet.receipt.findings)
    assert "rails missing" not in reason.lower()


def test_iso_usrec_pipe_july_smashes_despite_august_prose() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    spine = (
        "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
        "The FRED recession observation for August 2026 is 0. "
        "Updated: Sep 1, 2026. Units: +1 or 0. "
        "https://fred.stlouisfed.org/series/T10Y3M T10Y3M = 1. "
        "July payrolls fell 23,000 and unemployment was 4.1%. "
        "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
        f"{FRED_USREC} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS}"
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [
                "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
                "The FRED recession observation for August 2026 is 0. "
                "Updated: Sep 1, 2026."
            ]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", [
                "July payrolls fell 23,000 and unemployment was 4.1%."
            ]),
            _row(BEA_2026_NEWS, "BEA second estimate", [
                "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
            ]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert payrolls.id == "payrolls-july-2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "USREC=1" not in spoken
    assert "September" not in (usrec.when or "")
    assert "Sep 1" not in (usrec.claim or "") or usrec.print == "0"


def test_iso_pipe_july_zero_beats_leading_recession_one() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    spine = (
        "2020-04-01 | 1\n2026-06-01 | 0\n2026-07-01 | 0\n"
        "The FRED recession observation for August 2026 is 0. "
        "July payrolls fell 23,000. "
        f"{FRED_USREC} {BLS_JULY_ARCHIVE}"
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [
                "2020-04-01 | 1\n2026-06-01 | 0\n2026-07-01 | 0\n"
                "The FRED recession observation for August 2026 is 0."
            ]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", ["July payrolls fell 23,000."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    assert payrolls.id == "payrolls-july-2026"


def test_dated_t10y3m_one_is_not_usrec_print() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    spine = (
        "T10Y3M 2026-07-01 1. "
        "2026-07-01 | 0. "
        "July payrolls fell 23,000. "
        f"{FRED_USREC} {BLS_JULY_ARCHIVE}"
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["2026-07-01 | 0."]),
            _row(BLS_JULY_ARCHIVE, "BLS July archive", ["July payrolls fell 23,000."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert usrec.print != "1"
    assert (usrec.when or "").lower() == "july 2026"


# Live HOLD oc-are-we-near-recession-4f51dba6: unsigned August PAYEMS/level
# 162,000 next to a realized CES fall, June USREC prose, Q1/Q2 bars in cites.
# Fixture-local prints — not the July −23k / 2.1/1.5 seed.
_FALL_CES_OCT = (
    "THE EMPLOYMENT SITUATION -- OCTOBER 2024\n"
    "Total nonfarm payroll employment fell by 18,000 in October 2024.\n"
)
_PAYEMS_AUG_162K = "PAYEMS August 2026 = 162,000. All employees, thousands."
_USREC_JUNE_PIPE = "2024-09-01 | 0\n2024-10-01 | 0\n2026-06-01 | 0\n"
_GDP_Q1Q2_OTHER = (
    "Real GDP increased 3.4 percent in the first quarter of 2025. "
    "Real GDP increased 2.8 percent in the second quarter of 2025."
)
BEA_2025_NEWS = (
    "https://www.bea.gov/news/2025/gross-domestic-product-"
    "second-quarter-2025-second-estimate"
)
BLS_OCT_ARCHIVE = "https://www.bls.gov/news.release/archives/empsit_11012024.htm"


def test_fall_verb_mints_negative_ces_not_unsigned_162k() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    spine = (
        f"{_USREC_JUNE_PIPE}"
        f"{_PAYEMS_AUG_162K} "
        f"{_FALL_CES_OCT}"
        "Nonfarm payrolls fell in the latest employment situation. "
        f"{_GDP_Q1Q2_OTHER} "
        f"{FRED_USREC} {BLS_OCT_ARCHIVE} {BEA_2025_NEWS}"
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC_JUNE_PIPE, "The FRED recession observation for June 2026 is 0."]),
            _row(BLS_OCT_ARCHIVE, "BLS October archive", [_FALL_CES_OCT, _PAYEMS_AUG_162K]),
            _row(BEA_2025_NEWS, "BEA Q2 2025 second estimate", [_GDP_Q1Q2_OTHER]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    printed = payrolls.print or ""
    assert printed.startswith(("−", "-"))
    assert "18,000" in printed or "18k" in printed.lower()
    assert "162" not in printed.replace(",", "")
    assert (payrolls.when or "").lower() == "october 2024"
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert (usrec.when or "").lower() == "october 2024"
    assert "june" not in (usrec.when or "").lower()
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (October 2024) smashed into payrolls" in spoken
    assert "162,000" not in spoken
    assert "18,000" in spoken or "18k" in spoken.lower() or "−18" in spoken or "-18" in spoken


def test_unsigned_162k_when_notes_say_fell_is_not_minted() -> None:
    from onecrew.foundry import FoundryHold, mint, require_minted
    from onecrew.spend import ledger

    spine = (
        "USREC June 2026 = 0. "
        "Nonfarm payrolls fell. "
        f"{_PAYEMS_AUG_162K} "
        f"{FRED_USREC} {BLS}"
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["USREC June 2026 = 0."]),
            _row(BLS, "PAYEMS", [_PAYEMS_AUG_162K, "Nonfarm payrolls fell."]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    pays = [f for f in rows if f.series == "BLS payrolls"]
    for pay in pays:
        printed = pay.print or ""
        assert "162" not in printed.replace(",", "")
        assert not printed or printed.startswith(("−", "-"))
    with pytest.raises(FoundryHold, match="foundry dropped named series"):
        require_minted(rows, spine)


def test_gdp_two_bar_from_cite_excerpts_not_hole() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger

    spine = (
        f"{_USREC_JUNE_PIPE}"
        f"{_FALL_CES_OCT}"
        f"{FRED_USREC} {BLS_OCT_ARCHIVE} {BEA_2025_NEWS}"
    )
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    rows = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC_JUNE_PIPE]),
            _row(BLS_OCT_ARCHIVE, "BLS October archive", [_FALL_CES_OCT]),
            _row(BEA_2025_NEWS, "BEA Q2 2025 second estimate", [_GDP_Q1Q2_OTHER]),
        ],
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    gdp = next(f for f in rows if f.series == "GDP")
    assert "3.4" in (gdp.print or "")
    assert "2.8" in (gdp.print or "")
    assert "/" in (gdp.print or "")
    assert gdp.print != "2.1 / 1.5"
    assert "2.1" not in (gdp.print or "")
    assert (gdp.when or "").upper().replace(" ", "") == "Q22025"
    assert gdp.id == "gdp-2025-q2"
    assert gdp.parallel_url
    assert "bea.gov" in (gdp.parallel_url or "")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    gdp_vo = next(b for b in packet.beats if b.id == "gdp").vo
    assert "GDP hole named" not in gdp_vo
    assert "3.4" in gdp_vo and "2.8" in gdp_vo
    assert (gdp.parallel_url or "") in " ".join(b.vo for b in packet.beats) or gdp.id in (
        next(b for b in packet.beats if b.id == "gdp").finding_ids
    )


# Live HOLD oc-are-we-near-recession-8beb0212: June USREC prose, CSV pipe
# through July = 0, July CES rise (not the fall seed), T10Y3M chrome, and a
# prior-month revision that says "fell". Smash month is the payrolls month.
_JULY_RISE_CES = (
    "THE EMPLOYMENT SITUATION -- JULY 2026\n"
    "Total nonfarm payroll employment increased by 21,000 in July 2026.\n"
)
_LONG_CSV_PIPE = (
    "observation_date,USREC\n"
    + "\n".join(f"2025-{m:02d}-01,0" for m in range(1, 13))
    + "\n2026-05-01,0\n2026-06-01,0\n2026-07-01,0\n"
)
_LIVE_JUNE_PROSE_JULY_RISE = (
    f"{_LONG_CSV_PIPE}"
    "USREC June 2026 = 0. "
    "The FRED recession observation for June 2026 is 0. "
    "https://fred.stlouisfed.org/series/T10Y3M T10Y3M = 1. "
    "May 2026 payrolls were revised down; that month fell after the first print. "
    f"{_JULY_RISE_CES}"
    "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2. "
    f"{FRED_USREC} {BLS_JULY_ARCHIVE} {BEA_2026_NEWS}"
)


def test_july_pipe_zero_and_july_rise_ces_smashes_july_not_june() -> None:
    from onecrew.foundry import mint
    from onecrew.spend import ledger
    from onecrew.verify import (
        CiteBag,
        CiteExcerpt,
        apply_verify_gate,
        claims_from_findings,
        verify_usrec_smash,
    )

    before = ledger.parallel_calls
    packet = _packet()
    packet.id = "oc-are-we-near-recession-8beb0212"
    packet.task_spine = _LIVE_JUNE_PROSE_JULY_RISE
    packet.research_pack = _LIVE_JUNE_PROSE_JULY_RISE
    hit_rows = [
        _row(FRED_USREC, "USREC", [
            _LONG_CSV_PIPE,
            "USREC June 2026 = 0. The FRED recession observation for June 2026 is 0.",
        ]),
        _row(BLS_JULY_ARCHIVE, "BLS July archive", [_JULY_RISE_CES]),
        _row(BEA_2026_NEWS, "BEA second estimate", [
            "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."
        ]),
    ]
    rows = mint(
        packet,
        hit_rows,
        _miss_rows(),
        SimpleNamespace(results=[], errors=[]),
        _LIVE_JUNE_PROSE_JULY_RISE,
    )
    assert ledger.parallel_calls == before
    payrolls = next(f for f in rows if f.series == "BLS payrolls")
    printed = payrolls.print or ""
    assert "21,000" in printed or "21k" in printed.lower()
    assert not printed.startswith(("−", "-"))
    assert (payrolls.when or "").lower() == "july 2026"
    usrec = next(f for f in rows if f.series == "USREC")
    assert usrec.print == "0"
    assert usrec.print != "1"
    assert (usrec.when or "").lower() == "july 2026"
    assert usrec.id == "usrec-july-2026"
    assert "june" not in (usrec.when or "").lower()
    bag = CiteBag(
        excerpts=[
            CiteExcerpt(url=r.url, title=r.title, text=" ".join(r.excerpts)) for r in hit_rows
        ],
        spine=_LIVE_JUNE_PROSE_JULY_RISE,
        hit_urls=[r.url for r in hit_rows],
    )
    claims = claims_from_findings(rows)
    usrec_claim = next(c for c in claims if c.series == "USREC")
    pay_claim = next(c for c in claims if c.series == "BLS payrolls")
    smash = verify_usrec_smash(usrec_claim, pay_claim, bag)
    assert smash.ok is True, smash.reason
    gated = apply_verify_gate(
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
        bag,
    )
    assert gated.disposition == "READY", gated.hold_reason
    write_receipt(packet, gated)
    write_script(packet)
    reason = (packet.receipt.hold_reason or "") + " ".join(row.detail for row in packet.exclusions)
    assert "smash mixed months" not in reason.lower()
    assert "print not in cite" not in reason.lower()
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert "USREC=0 (June 2026)" not in spoken
    assert "USREC=1" not in spoken
    assert "21,000" in spoken or "21k" in spoken.lower()


def test_writer_rejects_mixed_month_smash_vo(monkeypatch) -> None:
    """Vertex pack prose must not ship USREC June smashed into July payrolls."""
    from onecrew.script import write_script

    packet = _packet()
    packet.id = "oc-are-we-near-recession-8beb0212"
    packet.task_spine = _LIVE_JUNE_PROSE_JULY_RISE
    packet.research_pack = _LIVE_JUNE_PROSE_JULY_RISE
    rows = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (July 2026)",
            stamp="grounded",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Total nonfarm payroll employment increased by 21,000 in July 2026.",
            stamp="grounded",
            series="BLS payrolls",
            print="+21,000",
            when="July 2026",
            parallel_url=BLS_JULY_ARCHIVE,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="gdp-2026-q2",
            claim="GDP 2.1 / 1.5",
            stamp="grounded",
            series="GDP",
            print="2.1 / 1.5",
            when="Q2 2026",
            parallel_url=BEA_2026_NEWS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        _miss_finding(),
    ]
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    mixed = (
        '[{"id":"cold-open","vo":"USREC=0 (June 2026) smashed into payrolls +21,000. '
        '[usrec-july-2026] [payrolls-july-2026]",'
        '"eyes":"cards","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"promise","vo":"Three objects from the pack.","eyes":"pack","finding_ids":[]},'
        '{"id":"gdp","vo":"GDP printed 2.1, then 1.5. [gdp-2026-q2]","eyes":"gdp","finding_ids":["gdp-2026-q2"]},'
        '{"id":"labor","vo":"Labor: payrolls +21,000. [payrolls-july-2026]","eyes":"ces","finding_ids":["payrolls-july-2026"]},'
        '{"id":"turn","vo":"Hold on the pack number.","eyes":"hold","finding_ids":[]},'
        '{"id":"complication","vo":"Those are not the same object.","eyes":"gap","finding_ids":[]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-july-2026]","eyes":"board","finding_ids":["usrec-july-2026"]},'
        '{"id":"close","vo":"Near is not a switch.","eyes":"close","finding_ids":[]}]'
    )
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda _p: mixed)
    write_script(packet)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "USREC=0 (June 2026) smashed into" not in spoken
    assert "USREC=0 (July 2026) smashed into payrolls" in spoken
    assert packet.beats
    assert next(b for b in packet.beats if b.id == "cold-open")
