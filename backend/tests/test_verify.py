"""Deterministic Claimer/Critic tools. Agent prose cannot override ok: false."""

from __future__ import annotations

import inspect

from onecrew.models import Finding, Packet, Rails, Receipt
from onecrew.receipt import write_receipt
from onecrew.verify import (
    Claim,
    CiteBag,
    CiteExcerpt,
    apply_verify_gate,
    claims_from_findings,
    verify_claim_set,
    verify_gdp_bars,
    verify_payrolls_realized_ces,
    verify_print_in_cite,
    verify_u3_ces,
    verify_usrec_smash,
)

FRED = "https://fred.stlouisfed.org/series/USREC"
BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
BEA = "https://www.bea.gov/data/gdp/gross-domestic-product"

_JULY_PIPE = "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
_JULY_CES = (
    "THE EMPLOYMENT SITUATION -- JULY 2026\n"
    "Total nonfarm payroll employment fell by 23,000 in July 2026.\n"
    "The unemployment rate was 4.3 percent in July 2026.\n"
)
_TWO_BAR_GDP = (
    "Real GDP increased 2.1 percent in the first quarter of 2026. "
    "Real GDP increased 1.5 percent in the second quarter of 2026."
)


def _bag(
    *,
    excerpts: list[tuple[str, str, str]],
    spine: str = "",
    hit_urls: list[str] | None = None,
) -> CiteBag:
    rows = [CiteExcerpt(url=url, title=title, text=text) for url, title, text in excerpts]
    urls = hit_urls if hit_urls is not None else list(dict.fromkeys(url for url, _, _ in excerpts))
    return CiteBag(excerpts=rows, spine=spine, hit_urls=urls)


def _good_bag() -> CiteBag:
    return _bag(
        excerpts=[
            (FRED, "USREC", _JULY_PIPE),
            (BLS, "Employment Situation", _JULY_CES),
            (BEA, "GDP", _TWO_BAR_GDP),
        ],
        spine="USREC July 2026 = 0. Nonfarm payrolls −23k. GDP 2.1 / 1.5 in Q2 2026.",
    )


def _good_claims() -> list[Claim]:
    return [
        Claim(
            series="USREC",
            print="0",
            when="July 2026",
            id="usrec-july-2026",
            cite_url=FRED,
            claim_span="USREC=0 (July 2026)",
        ),
        Claim(
            series="BLS payrolls",
            print="−23k",
            when="July 2026",
            id="payrolls-23k",
            cite_url=BLS,
            claim_span="Nonfarm payrolls fell −23k",
        ),
        Claim(
            series="GDP",
            print="2.1 / 1.5",
            when="Q2 2026",
            id="gdp-2026-q2",
            cite_url=BEA,
            claim_span="GDP 2.1 / 1.5",
        ),
        Claim(
            series="U-3",
            print="4.3%",
            when="July 2026",
            id="u3-july-2026",
            cite_url=BLS,
            claim_span="Unemployment 4.3%",
        ),
    ]


def test_good_july_ces_pipe_and_two_bar_gdp_claim_set_ok() -> None:
    result = verify_claim_set(_good_claims(), _good_bag())
    assert result.ok
    assert result.hold_reasons == []
    assert all(row.ok for row in result.results)


def test_may_revision_plus_129k_fails_payrolls_when_spine_has_july_minus_23k() -> None:
    bag = _bag(
        excerpts=[
            (
                BLS,
                "CES revisions",
                "May 2026 payrolls were revised up from +80,000 to +129,000.",
            )
        ],
        spine="July 2026 nonfarm payrolls −23k. Realized CES for July, not May.",
        hit_urls=[BLS],
    )
    claim = Claim(
        series="BLS payrolls",
        print="+129,000",
        when="May 2026",
        id="payrolls-may-rev",
        cite_url=BLS,
    )
    got = verify_payrolls_realized_ces(claim, bag)
    assert got.ok is False
    assert got.reason


def test_usrec_august_plus_july_payrolls_no_jul_pipe_smash_mixed_months() -> None:
    bag = _bag(
        excerpts=[
            (FRED, "USREC", "The August 2026 release discusses the recession indicator."),
            (BLS, "CES", "Nonfarm payrolls fell by 23,000 in July 2026."),
        ],
        spine="August prose only. No July USREC pipe.",
    )
    usrec = Claim(series="USREC", print="0", when="August 2026", id="usrec-aug", cite_url=FRED)
    payrolls = Claim(
        series="BLS payrolls",
        print="−23k",
        when="July 2026",
        id="payrolls-23k",
        cite_url=BLS,
    )
    got = verify_usrec_smash(usrec, payrolls, bag)
    assert got.ok is False
    assert got.reason == "smash mixed months"


def test_gdp_2_1_percent_q4_fails_when_cites_have_q1_q2_pair() -> None:
    bag = _bag(
        excerpts=[(BEA, "GDP", _TWO_BAR_GDP)],
        spine="SPF Q4 risk prose is not a realized bar.",
        hit_urls=[BEA],
    )
    claim = Claim(
        series="GDP",
        print="2.1%",
        when="Q4 2026",
        id="gdp-2026-q4",
        cite_url=BEA,
    )
    got = verify_gdp_bars(claim, bag)
    assert got.ok is False
    assert got.reason


def test_u3_4_3_june_2028_fails_when_year_absent_from_cite() -> None:
    bag = _bag(
        excerpts=[
            (
                BLS,
                "CES",
                "The unemployment rate was 4.3 percent in July 2026.",
            )
        ],
        hit_urls=[BLS],
    )
    claim = Claim(
        series="U-3",
        print="4.3%",
        when="June 2028",
        id="u3-june-2028",
        cite_url=BLS,
    )
    got = verify_u3_ces(claim, bag)
    assert got.ok is False
    assert got.reason


def test_verify_claim_set_ignores_agent_critic_prose() -> None:
    params = list(inspect.signature(verify_claim_set).parameters)
    assert params == ["claims", "bag"]
    bag = _bag(
        excerpts=[(BEA, "GDP", _TWO_BAR_GDP)],
        hit_urls=[BEA],
    )
    bad = [
        Claim(
            series="GDP",
            print="2.1%",
            when="Q4 2026",
            id="gdp-2026-q4",
            cite_url=BEA,
        )
    ]
    # A fake critic saying PASS is not an argument. Tools only.
    result = verify_claim_set(bad, bag)
    assert result.ok is False
    assert result.hold_reasons


def test_apply_verify_gate_holds_keeps_findings_and_hold_reasons() -> None:
    findings = [
        Finding(
            id="payrolls-may-rev",
            claim="May 2026 payrolls +129,000.",
            stamp="grounded",
            title="BLS payrolls",
            when="May 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="fringe-unsourced",
            claim="Unsourced fringe print. Parallel miss. Never sold as fact.",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]
    receipt = Receipt(
        packet_id="oc-verify-hold",
        written=False,
        disposition="READY",
        findings=findings,
    )
    bag = _bag(
        excerpts=[
            (
                BLS,
                "CES revisions",
                "May 2026 payrolls were revised up from +80,000 to +129,000.",
            )
        ],
        spine="July 2026 nonfarm payrolls −23k.",
        hit_urls=[BLS],
    )
    held = apply_verify_gate(receipt, bag)
    assert held.disposition == "HOLD"
    assert held.findings == findings
    assert held.findings != []
    assert held.hold_reason
    packet = Packet(
        id="oc-verify-hold",
        hook="Are we near recession?",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
    )
    write_receipt(packet, held)
    assert packet.status == "hold"
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert packet.receipt.findings
    assert {f.id for f in packet.receipt.findings} == {"payrolls-may-rev", "fringe-unsourced"}
    assert packet.receipt.hold_reason


def test_print_in_cite_requires_hit_url_and_when_tokens() -> None:
    bag = _good_bag()
    missing_hit = Claim(
        series="USREC",
        print="0",
        when="July 2026",
        id="usrec-july-2026",
        cite_url="https://example.com/not-in-hits",
    )
    assert verify_print_in_cite(missing_hit, bag).reason == "cite_url not in hits"
    wrong_print = Claim(
        series="BLS payrolls",
        print="+129k",
        when="July 2026",
        id="payrolls-23k",
        cite_url=BLS,
    )
    assert verify_print_in_cite(wrong_print, bag).reason == "print not in cite"
    wrong_when = Claim(
        series="USREC",
        print="0",
        when="June 2028",
        id="usrec-june-2028",
        cite_url=FRED,
    )
    assert verify_print_in_cite(wrong_when, bag).reason == "when not in cite"


def test_claims_from_findings_maps_named_series_not_leftover_slots() -> None:
    rows = [
        Finding(
            id="usrec",
            claim="USREC July 2026 = 0.",
            stamp="grounded",
            title="USREC",
            parallel_url=FRED,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="timeline-hit",
            claim="Grounded event inside 2-3y: leftover",
            stamp="grounded",
            title="leftover",
            parallel_url=FRED,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    claims = claims_from_findings(rows)
    assert any(c.series == "USREC" and c.print in {"0", "USREC=0"} or "0" in c.print for c in claims)
    leftover = [c for c in claims if c.id == "timeline-hit"]
    assert leftover
    result = verify_claim_set(claims, _good_bag())
    assert result.ok is False
    assert any("leftover" in r.lower() or "timeline" in r.lower() for r in result.hold_reasons)


def test_hold_receipt_helper_still_empties_only_when_no_named_series() -> None:
    from onecrew.receipt import hold_receipt

    empty = hold_receipt("oc-rails-down", Rails(parallel=False, vertex=True, imagen=True))
    assert empty.findings == []
    assert empty.disposition == "HOLD"
