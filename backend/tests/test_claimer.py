"""Claimer proposes from cites; Critic/verify is the authority. No global payrolls constant."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from onecrew.models import MISSING, Finding, Packet, Rails, Receipt
from onecrew.receipt import ReceiptInvalidError, validate_finding, write_receipt
from onecrew.script import write_script
from onecrew.verify import (
    Claim,
    CiteBag,
    CiteExcerpt,
    apply_verify_gate,
    verify_claim_set,
    verify_payrolls_realized_ces,
)

FRED = "https://fred.stlouisfed.org/series/USREC"
BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
NAICS = "https://www.bls.gov/iag/tgs/iag541.htm"

# Fixture-local prints. Not the live July −23k seed.
_MAR_CES = (
    "THE EMPLOYMENT SITUATION -- MARCH 2025\n"
    "Total nonfarm payroll employment fell by 41,000 in March 2025.\n"
)
_MAR_PIPE = "2025-01-01 | 0\n2025-02-01 | 0\n2025-03-01 | 0\n"
_OCT_CES = (
    "THE EMPLOYMENT SITUATION -- OCTOBER 2024\n"
    "Total nonfarm payroll employment fell by 18,000 in October 2024.\n"
)
_OCT_PIPE = "2024-09-01 | 0\n2024-10-01 | 0\n"
_NAICS_LEVEL = (
    "NAICS 541214 Payroll services. Employment level 1,126. "
    "Industry employment, not CES nonfarm payrolls."
)


def _bag(*, excerpts, spine="", hit_urls=None):
    rows = [CiteExcerpt(url=u, title=t, text=x) for u, t, x in excerpts]
    urls = hit_urls if hit_urls is not None else list(dict.fromkeys(u for u, _, _ in excerpts))
    return CiteBag(excerpts=rows, spine=spine, hit_urls=urls)


def _print_from_ces(text: str) -> str:
    import re

    match = re.search(r"fell by\s+([\d,]+)", text, re.I)
    assert match, "fixture CES must name a fall print"
    return f"−{match.group(1)}"


def _when_from_ces(text: str) -> str:
    import re

    match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})",
        text,
        re.I,
    )
    assert match, "fixture CES must name a month"
    return f"{match.group(1).title()} {match.group(2)}"


def _fake_claimer_from_bag(bag: CiteBag, packet=None) -> list[Claim]:
    """Stub Claimer: reads this bag only. No global −23k / July / Hormuz=13."""
    ces = next((e for e in bag.excerpts if "nonfarm payroll employment fell" in e.text.lower()), None)
    pipe = next((e for e in bag.excerpts if "| 0" in e.text or "| 0" in (bag.spine or "")), None)
    if ces is None:
        return []
    printed = _print_from_ces(ces.text)
    when = _when_from_ces(ces.text)
    claims = [
        Claim(
            series="BLS payrolls",
            print=printed,
            when=when,
            id=f"payrolls-{when.lower().replace(' ', '-')}",
            cite_url=ces.url,
            claim_span=ces.text[:400],
        )
    ]
    if pipe is not None:
        claims.append(
            Claim(
                series="USREC",
                print="0",
                when=when,
                id=f"usrec-{when.lower().replace(' ', '-')}",
                cite_url=pipe.url,
                claim_span=f"USREC=0 ({when})",
            )
        )
    return claims


def test_stubbed_claimer_maps_fixture_local_ces_and_usrec_to_findings() -> None:
    from onecrew.claimer import findings_from_claims, propose_claims

    bag = _bag(
        excerpts=[
            (FRED, "USREC", _MAR_PIPE),
            (BLS, "Employment Situation", _MAR_CES),
        ],
        spine="USREC March 2025 = 0. Nonfarm payrolls fell 41,000.",
    )
    expected_print = _print_from_ces(_MAR_CES)
    expected_when = _when_from_ces(_MAR_CES)
    claims = propose_claims(bag, proposer=_fake_claimer_from_bag)
    assert all("23,000" not in (c.print or "") and "23k" not in (c.print or "").lower() for c in claims)
    assert all("july" not in (c.when or "").lower() for c in claims)
    checked = verify_claim_set(claims, bag)
    assert checked.ok, checked.hold_reasons
    findings = findings_from_claims(claims, bag)
    pay = next(f for f in findings if f.series == "BLS payrolls")
    usrec = next(f for f in findings if f.series == "USREC")
    assert expected_print in (pay.print or "") or "41,000" in (pay.print or "")
    assert pay.when.lower() == expected_when.lower()
    assert usrec.print == "0"
    assert usrec.when.lower() == expected_when.lower()
    gated = apply_verify_gate(
        Receipt(packet_id="oc-claimer-mar", written=False, disposition="READY", findings=findings),
        bag,
    )
    assert gated.disposition == "READY"
    assert gated.findings

    other = _bag(
        excerpts=[
            (FRED, "USREC", _OCT_PIPE),
            (BLS, "Employment Situation", _OCT_CES),
        ],
        spine="USREC October 2024 = 0. Nonfarm payrolls fell 18,000.",
    )
    other_print = _print_from_ces(_OCT_CES)
    other_when = _when_from_ces(_OCT_CES)
    other_claims = propose_claims(other, proposer=_fake_claimer_from_bag)
    assert verify_claim_set(other_claims, other).ok
    other_rows = findings_from_claims(other_claims, other)
    other_pay = next(f for f in other_rows if f.series == "BLS payrolls")
    assert "18,000" in (other_pay.print or "") or other_print in (other_pay.print or "")
    assert other_pay.when.lower() == other_when.lower()
    assert other_pay.print != pay.print
    assert other_pay.when.lower() != pay.when.lower()


def test_naics_employment_level_is_not_bls_payrolls() -> None:
    from onecrew.claimer import findings_from_claims, propose_claims

    bag = _bag(
        excerpts=[(NAICS, "Payroll services NAICS", _NAICS_LEVEL)],
        spine="NAICS 541214 payroll services employment level 1,126.",
        hit_urls=[NAICS],
    )
    stolen = Claim(
        series="BLS payrolls",
        print="1,126",
        when="March 2025",
        id="payrolls-naics-1126",
        cite_url=NAICS,
        claim_span=_NAICS_LEVEL,
    )
    got = verify_payrolls_realized_ces(stolen, bag)
    assert got.ok is False
    proposed = propose_claims(bag, proposer=_fake_claimer_from_bag)
    assert not any(c.series == "BLS payrolls" for c in proposed)
    rows = findings_from_claims(proposed, bag)
    assert not any(f.series == "BLS payrolls" for f in rows)


def test_claimer_cannot_stamp_propaganda_yes_without_parallel_issuer() -> None:
    from onecrew.claimer import findings_from_claims

    bag = _bag(
        excerpts=[(BLS, "Employment Situation", _MAR_CES)],
        hit_urls=[BLS],
    )
    claims = _fake_claimer_from_bag(bag)
    rows = findings_from_claims(claims, bag)
    assert rows
    for finding in rows:
        assert finding.propaganda != "yes"
        assert finding.propaganda_issuer in {MISSING, "", None}
        validate_finding(finding)
    invented = Finding(
        id="bubble-hit",
        claim="AI bubble weekly desk read.",
        stamp="grounded",
        series="BLS payrolls",
        print="−41,000",
        when="March 2025",
        parallel_url=BLS,
        parallel_status="hit",
        note="Parallel URL on this row.",
        propaganda="yes",
        propaganda_issuer=MISSING,
    )
    with pytest.raises(ReceiptInvalidError, match="naming the issuer"):
        validate_finding(invented)


def test_fiction_ready_from_frame_when_foundry_mints_nothing(monkeypatch) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.foundry import FoundryHold
    from onecrew.spend import ledger

    cite = "Kitchen radio on. A storm warning, no CES table."
    hit = "https://example.com/storm-desk"
    miss = "https://example.com/fringe-storm"

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[SimpleNamespace(url=miss, title="Fringe", excerpts=["Secret storm already started."])]
            )
        return SimpleNamespace(
            results=[SimpleNamespace(url=hit, title="Storm desk", excerpts=[cite])]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(results=[SimpleNamespace(url=hit, title="Storm desk", excerpts=[cite])], errors=[])

    def task(*, prompt, processor="pro", task_spec=None):
        return SimpleNamespace(output=SimpleNamespace(content=cite, basis=[]))

    def boom_mint(*_a, **_k):
        raise FoundryHold("foundry minted nothing")

    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.agent.shift.mint", boom_mint)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    before = ledger.parallel_calls
    shift = open_shift(
        "Kitchen storm",
        platform="youtube",
        cut="feature_film",
        depth="1y",
        script_lean="centered_independent",
        tell="One family in Bandar Abbas, kitchen radio on",
        topic="Kitchen storm",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert ledger.parallel_calls == before
    assert packet.receipt is not None
    assert packet.receipt.disposition == "READY"
    assert packet.receipt.findings
    ids = {f.id for f in packet.receipt.findings}
    assert ids.isdisjoint({"timeline-hit", "timeline-frame", "timeline-miss"})
    assert packet.script
    assert packet.beats
    assert "(frame)" in packet.script
    spoken = packet.script + "".join(b.vo for b in packet.beats)
    assert "Hormuz=13" not in spoken
    assert "smashed into JCPOA" not in spoken
    assert "foundry minted nothing" not in (packet.receipt.hold_reason or "").lower()


def test_leftover_hormuz_slots_are_not_cold_open_on_unrelated_topic() -> None:
    from onecrew.foundry import leftover_slot_ids

    leftover = leftover_slot_ids()
    packet = Packet(
        id="oc-nuclear-decade",
        topic="Did the 10-year break?",
        hook="Did the 10-year break?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        research_pack="The 10-year yield printed 4.8% in March 2026.",
        task_spine="The 10-year yield printed 4.8% in March 2026.",
    )
    findings = [
        Finding(
            id="timeline-hit",
            claim="Hormuz=13 smashed into JCPOA 2231.",
            stamp="grounded",
            series="Hormuz",
            print="13",
            when="leftover",
            parallel_url="https://example.com/leftover-hormuz",
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="yield-2026",
            claim="The 10-year yield printed 4.8% in March 2026.",
            stamp="grounded",
            series="DGS10",
            print="4.8%",
            when="March 2026",
            parallel_url="https://fred.stlouisfed.org/series/DGS10",
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="timeline-miss",
            claim="Fringe claim about leftover Hormuz.",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=findings),
    )
    write_script(packet)
    cold = next((b for b in packet.beats if b.id == "cold-open"), None)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    if cold is not None:
        assert not leftover.intersection(cold.finding_ids)
        assert "hormuz=13" not in cold.vo.lower()
        assert "smashed into jcpoa" not in cold.vo.lower()
    assert "hormuz=13 smashed into jcpoa" not in spoken.lower()
    assert "timeline-hit" not in spoken


_PAYEMS_162K = "PAYEMS August 2026 = 162,000. All employees, thousands."
_GDP_34_28 = (
    "Real GDP increased 3.4 percent in the first quarter of 2025. "
    "Real GDP increased 2.8 percent in the second quarter of 2025."
)
BEA_2025 = (
    "https://www.bea.gov/news/2025/gross-domestic-product-"
    "second-quarter-2025-second-estimate"
)


def test_claims_from_cites_fall_ces_not_unsigned_162k_and_gdp_bars() -> None:
    from onecrew.claimer import claims_from_cites, findings_from_claims

    bag = _bag(
        excerpts=[
            (FRED, "USREC", _OCT_PIPE + "The FRED recession observation for June 2026 is 0."),
            (BLS, "Employment Situation", _OCT_CES + " " + _PAYEMS_162K),
            (BEA_2025, "BEA GDP", _GDP_34_28),
        ],
        spine=(
            "Nonfarm payrolls fell. PAYEMS August 2026 = 162,000. "
            "USREC June 2026 = 0. "
            + _OCT_CES
        ),
        hit_urls=[FRED, BLS, BEA_2025],
    )
    claims = claims_from_cites(bag)
    pay = next(c for c in claims if c.series == "BLS payrolls")
    assert pay.print.startswith(("−", "-"))
    assert "18,000" in pay.print
    assert "162" not in pay.print.replace(",", "")
    assert pay.when.lower() == "october 2024"
    usrec = next(c for c in claims if c.series == "USREC")
    assert usrec.print == "0"
    assert usrec.when.lower() == "october 2024"
    gdp = next(c for c in claims if c.series == "GDP")
    assert "3.4" in gdp.print and "2.8" in gdp.print
    assert gdp.print != "2.1 / 1.5"
    assert gdp.when.upper().replace(" ", "") == "Q22025"
    assert gdp.cite_url.startswith("http")
    checked = verify_claim_set(claims, bag)
    assert checked.ok, checked.hold_reasons
    findings = findings_from_claims(claims, bag)
    pay_f = next(f for f in findings if f.series == "BLS payrolls")
    assert pay_f.print.startswith(("−", "-"))
    assert "162" not in (pay_f.print or "").replace(",", "")


def test_forbidden_wrap_claimer_drops_excerpt_slot_gdp_and_trillion_without_official_cite() -> None:
    """Claimer stays closed-series. excerpts[N] / $126 trillion without BEA/FRED is not GDP."""
    from onecrew.claimer import findings_from_claims, propose_claims
    from onecrew.foundry import is_pack_slot_id

    scrape = "https://www.noahpinion.blog/p/compute-campus-scrape"
    chrome = "excerpts[18]: GDP=$126 trillion. excerpts[19]: 0.6% of GDP."
    bag = _bag(
        excerpts=[(scrape, "scrape title", chrome)],
        spine=chrome,
        hit_urls=[scrape],
    )

    def junk_proposer(_bag, _packet=None):
        return [
            Claim(
                series="GDP",
                print="$126 trillion",
                when="2025",
                id="excerpts[18]",
                cite_url=scrape,
                claim_span=chrome,
            ),
            Claim(
                series="GDP",
                print="0.6%",
                when="2025",
                id="excerpts[19]",
                cite_url=scrape,
                claim_span=chrome,
            ),
        ]

    claims = propose_claims(bag, proposer=junk_proposer)
    assert not any(c.series == "GDP" for c in claims)
    assert not any(is_pack_slot_id(c.id) for c in claims)
    rows = findings_from_claims(
        [
            Claim(
                series="GDP",
                print="$126 trillion",
                when="2025",
                id="excerpts[18]",
                cite_url=scrape,
                claim_span=chrome,
            )
        ],
        bag,
    )
    assert not any(f.series == "GDP" for f in rows)
    assert not any(is_pack_slot_id(f.id) for f in rows)

    official = findings_from_claims(
        [
            Claim(
                series="GDP",
                print="3.4 / 2.8",
                when="Q2 2025",
                id="gdp-2025-q2",
                cite_url=BEA_2025,
                claim_span=_GDP_34_28,
            )
        ],
        _bag(excerpts=[(BEA_2025, "BEA GDP", _GDP_34_28)], hit_urls=[BEA_2025]),
    )
    assert any(f.series == "GDP" and "3.4" in (f.print or "") for f in official)


def test_propose_claims_remaps_june_usrec_to_july_pipe_month() -> None:
    """Vertex-style mixed months remap when the payrolls month is 0 on the pipe."""
    from onecrew.claimer import propose_claims

    july_ces = (
        "THE EMPLOYMENT SITUATION -- JULY 2026\n"
        "Total nonfarm payroll employment increased by 21,000 in July 2026.\n"
    )
    csv = (
        "observation_date,USREC\n"
        + "\n".join(f"2025-{m:02d}-01,0" for m in range(1, 13))
        + "\n2026-05-01,0\n2026-06-01,0\n2026-07-01,0\n"
    )
    bag = _bag(
        excerpts=[
            (FRED, "USREC", csv + "USREC June 2026 = 0."),
            (BLS, "Employment Situation", july_ces),
        ],
        spine="USREC June 2026 = 0. " + july_ces,
        hit_urls=[FRED, BLS],
    )

    def mixed(_bag, _packet=None):
        return [
            Claim(
                series="USREC",
                print="0",
                when="June 2026",
                id="usrec-june-2026",
                cite_url=FRED,
                claim_span="USREC=0 (June 2026)",
            ),
            Claim(
                series="BLS payrolls",
                print="+21,000",
                when="July 2026",
                id="payrolls-july-2026",
                cite_url=BLS,
                claim_span=july_ces,
            ),
        ]

    claims = propose_claims(bag, proposer=mixed)
    usrec = next(c for c in claims if c.series == "USREC")
    pay = next(c for c in claims if c.series == "BLS payrolls")
    assert usrec.when.lower() == "july 2026"
    assert usrec.print == "0"
    assert pay.when.lower() == "july 2026"
    checked = verify_claim_set(claims, bag)
    assert checked.ok, checked.hold_reasons
