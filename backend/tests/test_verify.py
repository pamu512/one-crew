"""Deterministic Claimer/Critic tools. Agent prose cannot override ok: false."""

from __future__ import annotations

import inspect

from onecrew.models import Finding, Packet, Rails, Receipt
from onecrew.receipt import write_receipt
from onecrew.verify import (
    Claim,
    CiteBag,
    CiteExcerpt,
    _url_in,
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
    assert got.reason == "hypo/CI/revision window"


def test_usrec_august_plus_july_payrolls_no_jul_pipe_smash_mixed_months() -> None:
    bag = _bag(
        excerpts=[
            (FRED, "USREC", "The August 2026 release discusses the recession indicator."),
            (BLS, "CES", "Nonfarm payrolls fell by 23,000 in July 2026."),
        ],
        spine="USREC=0 (August 2026) smashed into payrolls. August prose only. No July USREC pipe.",
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


def test_independent_usrec_and_payrolls_months_no_smash_no_pipe_ok() -> None:
    """Different observation months without a smash claim or payrolls-month pipe are normal."""
    bag = _bag(
        excerpts=[
            (FRED, "USREC", "The NBER-based FRED recession indicator remains 0 for June 2026."),
            (BLS, "CES", "Total nonfarm payroll employment increased in August 2026."),
        ],
        spine="Independent series. No smash stamp. No August USREC pipe cell.",
    )
    usrec = Claim(series="USREC", print="0", when="June 2026", id="usrec-june-2026", cite_url=FRED)
    payrolls = Claim(
        series="BLS payrolls",
        print="+10,000",
        when="August 2026",
        id="payrolls-august-2026",
        cite_url=BLS,
    )
    got = verify_usrec_smash(usrec, payrolls, bag)
    assert got.ok is True
    assert got.reason != "smash mixed months"


def test_pipe_payrolls_month_zero_usrec_other_month_smash_mixed() -> None:
    """Pipe flags the payrolls month 0/1 while USREC.when differs → foundry missed remap."""
    bag = _bag(
        excerpts=[
            (FRED, "USREC", "2026-05-01,0\n2026-06-01,0\n2026-08-01,0\n"),
            (BLS, "CES", "Nonfarm payrolls increased in August 2026."),
        ],
        spine="June prose. August payrolls. Pipe has the payrolls month.",
    )
    usrec = Claim(series="USREC", print="0", when="June 2026", id="usrec-june-2026", cite_url=FRED)
    payrolls = Claim(
        series="BLS payrolls",
        print="+10,000",
        when="August 2026",
        id="payrolls-august-2026",
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
    assert got.reason == "q4 vs q1/q2"


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
    assert got.reason == "u3 year absent from ces"


def test_u3_20_percent_december_fails_when_ces_has_other_month() -> None:
    """Non-CES / future / absurd U-3 is not a CES observation. No topic literals in verify."""
    ces = (
        "THE EMPLOYMENT SITUATION -- AUGUST 2026. "
        "Total nonfarm payroll employment fell by 11,000 in August 2026. "
        "The unemployment rate was 4.1% in August 2026."
    )
    noise = (
        "The unemployment rate was 20 percent in December 2026. "
        "A blog asked whether unemployment could reach 20 percent by December 2026."
    )
    bag = _bag(
        excerpts=[
            (BLS, "CES", ces),
            ("https://example.com/forecast", "forecast", noise),
        ],
        spine=f"{ces} {noise}",
        hit_urls=[BLS, "https://example.com/forecast"],
    )
    claim = Claim(
        series="U-3",
        print="20%",
        when="December 2026",
        id="unemployment-december-2026",
        cite_url=BLS,
        claim_span=noise,
    )
    got = verify_u3_ces(claim, bag)
    assert got.ok is False
    assert got.reason == "u3 year absent from ces"
    mixed_when = Claim(
        series="U-3",
        print="4.1%",
        when="December 2026",
        id="unemployment-december-2026",
        cite_url=BLS,
        claim_span=noise,
    )
    mixed_print = Claim(
        series="U-3",
        print="20%",
        when="August 2026",
        id="unemployment-august-2026",
        cite_url=BLS,
        claim_span=ces,
    )
    ces_ok = Claim(
        series="U-3",
        print="4.1%",
        when="August 2026",
        id="unemployment-august-2026",
        cite_url=BLS,
        claim_span=ces,
    )
    assert verify_u3_ces(mixed_when, bag).ok is False
    assert verify_u3_ces(mixed_when, bag).reason == "u3 year absent from ces"
    assert verify_u3_ces(mixed_print, bag).ok is False
    assert verify_u3_ces(mixed_print, bag).reason == "u3 year absent from ces"
    assert verify_u3_ces(ces_ok, bag).ok is True
    gated = apply_verify_gate(
        Receipt(
            packet_id="oc-u3-future",
            written=False,
            disposition="READY",
            findings=[
                Finding(
                    id="unemployment-december-2026",
                    claim="Unemployment is 20% in December 2026.",
                    stamp="grounded",
                    series="U-3",
                    print="20%",
                    when="December 2026",
                    parallel_url=BLS,
                    parallel_status="hit",
                    note="Parallel URL on this row.",
                )
            ],
        ),
        bag,
    )
    assert gated.disposition == "HOLD"
    assert "u3 year absent from ces" in (gated.hold_reason or "")


def test_u3_ces_header_year_is_not_absent() -> None:
    bag = _bag(
        excerpts=[
            (
                BLS,
                "CES",
                "THE EMPLOYMENT SITUATION -- JULY 2026. "
                "The unemployment rate was 4.3 percent.",
            )
        ],
        hit_urls=[BLS],
    )
    claim = Claim(
        series="U-3",
        print="4.3%",
        when="July 2026",
        id="u3-july-2026",
        cite_url=BLS,
        claim_span="The unemployment rate was 4.3 percent.",
    )
    got = verify_u3_ces(claim, bag)
    assert got.ok is True
    assert got.reason != "u3 year absent from ces"


_HYPO_THEN_JULY_CES = (
    "Moody's Analytics noted that payrolls actually declined by 13,000 jobs in June 2024. "
    "May 2026 payrolls were revised up from +80,000 to +129,000. "
    "Suppose employment increases by 50,000 from one month to the next. "
    "If, however, the reported nonfarm employment rise was 250,000, then all of "
    "the values within the 90-percent confidence interval would be greater than zero. "
    "THE EMPLOYMENT SITUATION -- JULY 2026. "
    "Total nonfarm payroll employment fell by 23,000 in July 2026."
)


def test_consensus_estimate_only_is_hypo_ci_not_realized_ces() -> None:
    bag = _bag(
        excerpts=[
            (
                BLS,
                "CES consensus",
                "Economists' consensus estimate for August payrolls is +53,000.",
            )
        ],
        spine="USREC July 2026 = 0. Consensus estimate for August payrolls is +53,000.",
        hit_urls=[BLS],
    )
    claim = Claim(
        series="BLS payrolls",
        print="+53,000",
        when="August 2026",
        id="payrolls-august-2026",
        cite_url=BLS,
        claim_span="Economists' consensus estimate for August payrolls is +53,000.",
    )
    got = verify_payrolls_realized_ces(claim, bag)
    assert got.ok is False
    assert got.reason == "hypo/CI/revision window"


def test_hypo_ci_same_excerpt_does_not_hold_realized_july_ces() -> None:
    bag = _bag(
        excerpts=[(BLS, "CES mixed", _HYPO_THEN_JULY_CES)],
        spine=_HYPO_THEN_JULY_CES,
        hit_urls=[BLS],
    )
    claim = Claim(
        series="BLS payrolls",
        print="−23,000",
        when="July 2026",
        id="payrolls-july-2026",
        cite_url=BLS,
        claim_span="Total nonfarm payroll employment fell by 23,000 in July 2026.",
    )
    got = verify_payrolls_realized_ces(claim, bag)
    assert got.ok is True
    assert got.reason != "hypo/CI/revision window"


def test_gdp_34_percent_index_is_not_a_bar() -> None:
    bag = _bag(
        excerpts=[
            (
                BEA,
                "GDP",
                "Gross Domestic Product, Second Quarter 2026 and Corporate Profits. "
                "The index level stood at 34%. Profits were 34.0 percent of GDP.",
            )
        ],
        hit_urls=[BEA],
    )
    claim = Claim(
        series="GDP",
        print="34%",
        when="Q2 2026",
        id="gdp-2026-q2",
        cite_url=BEA,
        claim_span="The index level stood at 34%.",
    )
    got = verify_gdp_bars(claim, bag)
    assert got.ok is False
    assert got.reason == "gdp bars mismatch"


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
    usrec = next(c for c in claims if c.series == "USREC")
    assert usrec.print in {"0", "USREC=0"}
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


def test_usrec_print_one_fails_against_july_pipe_zero() -> None:
    bag = _good_bag()
    claim = Claim(series="USREC", print="1", when="July 2026", id="usrec-july-2026", cite_url=FRED)
    got = verify_print_in_cite(claim, bag)
    assert got.ok is False
    assert got.reason == "print not in cite"
    smash = verify_usrec_smash(claim, _good_claims()[1], bag)
    assert smash.ok is False
    assert smash.reason == "print not in cite"


def test_when_month_must_sit_next_to_its_year() -> None:
    bag = _bag(
        excerpts=[(FRED, "USREC", "USREC=0. July 2025 observation. January 2026 note.")],
        hit_urls=[FRED],
    )
    claim = Claim(series="USREC", print="0", when="July 2026", id="usrec-july-2026", cite_url=FRED)
    got = verify_print_in_cite(claim, bag)
    assert got.ok is False
    assert got.reason == "when not in cite"


def test_foundry_three_bar_gdp_holds_when_cites_have_q1_q2_pair() -> None:
    """Three-bar GDP claim vs two-bar cite bag → HOLD; findings kept."""
    from onecrew.models import Finding

    findings = [
        Finding(
            id="gdp-three-bar",
            when="Q2 2026",
            claim="GDP printed 0.5 / 2.1 / 1.5.",
            stamp="grounded",
            title="BEA GDP",
            parallel_url=BEA,
            parallel_status="hit",
            note="Three bars must not pass a Q1/Q2 two-bar cite bag.",
        ),
        Finding(
            id="usrec-july-2026",
            when="July 2026",
            claim="USREC=0.",
            stamp="grounded",
            title="FRED USREC",
            parallel_url=FRED,
            parallel_status="hit",
            note="kept on HOLD",
        ),
    ]
    receipt = Receipt(packet_id="oc-foundry-gdp-gate", written=False, disposition="READY", findings=findings)
    held = apply_verify_gate(receipt, _good_bag())
    assert held.disposition == "HOLD"
    assert held.findings == findings
    assert held.findings != []
    assert "gdp" in (held.hold_reason or "").lower()


def test_claims_from_findings_reads_finding_print_and_when_not_blob() -> None:
    rows = [
        Finding(
            id="payrolls-july-2026",
            claim=(
                "Moody's payrolls actually declined by 13,000 jobs in June 2024. "
                "Suppose employment increases by 50,000. "
                "Total nonfarm payroll employment fell by 23,000 in July 2026."
            ),
            stamp="grounded",
            title="BLS payrolls",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="usrec-july-2026",
            claim="The FRED recession observation for August 2026 is 0. T10Y3M = 1.",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=FRED,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    claims = claims_from_findings(rows)
    pay = next(c for c in claims if c.series == "BLS payrolls")
    assert "23,000" in pay.print or "23k" in pay.print.lower()
    assert "13,000" not in pay.print
    assert "50,000" not in pay.print
    assert pay.when.lower() == "july 2026"
    usrec = next(c for c in claims if c.series == "USREC")
    assert usrec.print == "0"
    assert usrec.when.lower() == "july 2026"


def test_unicode_minus_print_matches_bare_digits_in_cite_and_spine() -> None:
    """Finding.print −23,000 matches ASCII / bare digits in excerpt or spine."""
    claim = Claim(
        series="BLS payrolls",
        print="−23,000",
        when="July 2026",
        id="payrolls-july-2026",
        cite_url=BLS,
    )
    excerpt_bag = _bag(
        excerpts=[
            (
                BLS,
                "Employment Situation",
                "Total nonfarm payroll employment fell **23,000** in July 2026.",
            )
        ],
        hit_urls=[BLS],
    )
    excerpt_got = verify_print_in_cite(claim, excerpt_bag)
    assert excerpt_got.ok is True
    assert excerpt_got.reason is None
    spine_bag = _bag(
        excerpts=[(BLS, "Employment Situation", "THE EMPLOYMENT SITUATION -- JULY 2026")],
        spine="Nonfarm payrolls fell **23,000** in July 2026.",
        hit_urls=[BLS],
    )
    spine_got = verify_print_in_cite(claim, spine_bag)
    assert spine_got.ok is True
    assert spine_got.reason is None
    ascii_claim = Claim(
        series="BLS payrolls",
        print="-23,000",
        when="July 2026",
        id="payrolls-july-2026",
        cite_url=BLS,
    )
    assert verify_print_in_cite(ascii_claim, excerpt_bag).ok is True
    missing = Claim(
        series="BLS payrolls",
        print="−23,000",
        when="July 2026",
        id="payrolls-july-2026",
        cite_url=BLS,
    )
    empty = _bag(
        excerpts=[(BLS, "Employment Situation", "THE EMPLOYMENT SITUATION -- JULY 2026")],
        spine="July 2026 CES release. No payroll print.",
        hit_urls=[BLS],
    )
    missed = verify_print_in_cite(missing, empty)
    assert missed.ok is False
    assert missed.reason == "print not in cite"


def test_gdp_slash_print_matches_percent_bars_in_bag_or_spine() -> None:
    """GDP print 2.1 / 1.5 matches 2.1% and 1.5% (or 2.1 and 1.5) in bag/spine."""
    bea_www = "https://www.bea.gov/sites/default/files/2026-08/gdp2q26-2nd.pdf"
    bea_bare = "http://bea.gov/sites/default/files/2026-08/gdp2q26-2nd.pdf"
    claim = Claim(
        series="GDP",
        print="2.1 / 1.5",
        when="Q2 2026",
        id="gdp-2026-q2",
        cite_url=bea_bare,
    )
    percent_bag = _bag(
        excerpts=[
            (
                bea_www,
                "GDP second estimate",
                "Real GDP increased **2.1%** in the first quarter of 2026 "
                "and **1.5%** in the second quarter of 2026.",
            )
        ],
        spine="Q2 2026 GDP printed **2.1%** then **1.5%**.",
        hit_urls=[bea_www],
    )
    got = verify_print_in_cite(claim, percent_bag)
    assert got.ok is True
    assert got.reason is None
    bare_bag = _bag(
        excerpts=[
            (
                bea_www,
                "GDP second estimate",
                "Real GDP increased 2.1 in Q1 2026 and 1.5 in Q2 2026.",
            )
        ],
        spine="GDP 2.1 / 1.5 in Q2 2026.",
        hit_urls=[bea_www],
    )
    assert verify_print_in_cite(claim, bare_bag).ok is True
    invented = Claim(
        series="GDP",
        print="2.1 / 9.9",
        when="Q2 2026",
        id="gdp-2026-q2",
        cite_url=bea_bare,
    )
    invented_got = verify_print_in_cite(invented, percent_bag)
    assert invented_got.ok is False
    assert invented_got.reason == "print not in cite"


def test_cite_url_host_drift_still_counts_as_hit() -> None:
    """http://bea.gov vs https://www.bea.gov is the same hit; other hosts/paths are not."""
    bea_www = "https://www.bea.gov/sites/default/files/2026-08/gdp2q26-2nd.pdf"
    bea_bare = "http://bea.gov/sites/default/files/2026-08/gdp2q26-2nd.pdf"
    bea_other = "https://www.bea.gov/sites/default/files/2025-01/gdp4q24-adv.pdf"
    assert _url_in(bea_bare, [bea_www]) is True
    assert _url_in(bea_www, [bea_bare]) is True
    assert _url_in(bea_bare, [bea_other]) is False
    assert _url_in(bea_bare, ["https://fred.stlouisfed.org/series/USREC"]) is False
    claim = Claim(
        series="GDP",
        print="2.1 / 1.5",
        when="Q2 2026",
        id="gdp-2026-q2",
        cite_url=bea_bare,
    )
    bag = _bag(
        excerpts=[
            (
                bea_www,
                "GDP second estimate",
                "Real GDP increased 2.1 percent in Q1 2026 and 1.5 percent in Q2 2026.",
            )
        ],
        spine="GDP 2.1 / 1.5 in Q2 2026.",
        hit_urls=[bea_www],
    )
    got = verify_print_in_cite(claim, bag)
    assert got.ok is True
    assert got.reason is None
    wrong_host = Claim(
        series="GDP",
        print="2.1 / 1.5",
        when="Q2 2026",
        id="gdp-2026-q2",
        cite_url="https://example.com/gdp2q26-2nd.pdf",
    )
    missed = verify_print_in_cite(wrong_host, bag)
    assert missed.ok is False
    assert missed.reason == "cite_url not in hits"


def test_stamped_finding_gets_cite_url_from_supporting_parallel_hit() -> None:
    """Pack notes minted a print; the Parallel hit that supports it must be the cite."""
    from onecrew.claimer import findings_from_claims

    harvard = "https://news.harvard.edu/gazette/story/2026/08/recession-watch"
    bag = _bag(
        excerpts=[
            (FRED, "USREC", _JULY_PIPE),
            (BLS, "Employment Situation", _JULY_CES),
            (harvard, "Gazette", "Recession watch recap. No official series table."),
        ],
        spine="USREC July 2026 = 0. Nonfarm payrolls fell 23,000 in July 2026.",
        hit_urls=[FRED, BLS, harvard],
    )
    claims = [
        Claim(
            series="USREC",
            print="0",
            when="July 2026",
            id="usrec-july-2026",
            cite_url="",
            claim_span="USREC=0 (July 2026)",
        ),
        Claim(
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            id="payrolls-july-2026",
            cite_url="",
            claim_span="Total nonfarm payroll employment fell by 23,000 in July 2026.",
        ),
    ]
    rows = findings_from_claims(claims, bag)
    usrec = next(f for f in rows if f.series == "USREC")
    pay = next(f for f in rows if f.series == "BLS payrolls")
    assert usrec.parallel_url == FRED
    assert pay.parallel_url == BLS
    gated = apply_verify_gate(
        Receipt(packet_id="oc-cite-from-hit", written=False, disposition="READY", findings=rows),
        bag,
    )
    assert "cite_url not in hits" not in (gated.hold_reason or "")
    assert gated.disposition == "READY"


def test_missing_cite_url_resolves_from_hits_before_hold() -> None:
    """Foundry forgot to copy the URL. Resolve from Parallel hits; do not HOLD."""
    findings = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (July 2026)",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=None,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Total nonfarm payroll employment fell by 23,000 in July 2026.",
            stamp="grounded",
            title="BLS payrolls",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=None,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    bag = _good_bag()
    gated = apply_verify_gate(
        Receipt(packet_id="oc-forgot-cite", written=False, disposition="READY", findings=findings),
        bag,
    )
    assert "cite_url not in hits" not in (gated.hold_reason or "")
    assert gated.disposition == "READY"
    usrec = next(f for f in gated.findings if f.series == "USREC")
    pay = next(f for f in gated.findings if f.series == "BLS payrolls")
    assert usrec.parallel_url == FRED
    assert pay.parallel_url == BLS
    named = [c for c in claims_from_findings(gated.findings) if c.series in {"USREC", "BLS payrolls"}]
    assert named
    assert all(c.cite_url in {FRED, BLS} for c in named)
    checked = verify_claim_set(named, bag)
    assert "cite_url not in hits" not in checked.hold_reasons
    assert checked.ok


def test_stamped_series_without_series_id_still_gets_hit_url() -> None:
    """Series already on the row. Do not require usrec/payrolls in the id."""
    findings = [
        Finding(
            id="object-1",
            claim="Official flag remains 0 for July 2026.",
            stamp="grounded",
            title="FRED",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url=None,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    gated = apply_verify_gate(
        Receipt(packet_id="oc-stamped-series", written=False, disposition="READY", findings=findings),
        _good_bag(),
    )
    assert gated.findings[0].parallel_url == FRED
    assert "cite_url not in hits" not in (gated.hold_reason or "")


def test_cite_url_in_hits_is_not_cite_url_not_in_hits() -> None:
    result = verify_claim_set(_good_claims(), _good_bag())
    assert result.ok
    assert "cite_url not in hits" not in result.hold_reasons
    for claim in _good_claims():
        got = verify_print_in_cite(claim, _good_bag())
        assert got.reason != "cite_url not in hits"
        assert got.ok is True


def test_named_cite_url_absent_from_hits_is_soft_not_hold() -> None:
    """cite_url not in hits is a critic miss. Gate stays READY; do not HOLD solely for it."""
    findings = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (July 2026)",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url="https://example.com/not-in-hits",
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    bag = _good_bag()
    gated = apply_verify_gate(
        Receipt(packet_id="oc-named-miss", written=False, disposition="READY", findings=findings),
        bag,
    )
    assert gated.disposition == "READY"
    assert "cite_url not in hits" not in (gated.hold_reason or "")
    usrec = next(f for f in gated.findings if f.id == "usrec-july-2026")
    assert usrec.parallel_url == "https://example.com/not-in-hits"
    checked = verify_claim_set(claims_from_findings(gated.findings), bag)
    assert "cite_url not in hits" in checked.hold_reasons


def test_usrec_print_zero_must_appear_in_cite_or_spine() -> None:
    """USREC print 0 is not always-ok; the flag token must sit in cite or spine."""
    claim = Claim(
        series="USREC",
        print="0",
        when="July 2026",
        id="usrec-july-2026",
        cite_url=FRED,
    )
    pipe = _bag(
        excerpts=[(FRED, "USREC", "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n")],
        hit_urls=[FRED],
    )
    assert verify_print_in_cite(claim, pipe).ok is True
    spine_only = _bag(
        excerpts=[(FRED, "USREC", "FRED USREC series page. July 2026 release.")],
        spine="USREC July 2026 = 0.",
        hit_urls=[FRED],
    )
    assert verify_print_in_cite(claim, spine_only).ok is True
    absent = _bag(
        excerpts=[(FRED, "USREC", "NBER discussion only. July 2026 release notes.")],
        spine="July 2026 discussion. No recession flag printed.",
        hit_urls=[FRED],
    )
    missed = verify_print_in_cite(claim, absent)
    assert missed.ok is False
    assert missed.reason == "print not in cite"


def test_csv_usrec_pipe_zero_is_print_in_cite_and_same_month_smash() -> None:
    """FRED CSV cells 2026-07-01,0 must count as print 0. Comma-strip must not glue the date."""
    csv_pipe = (
        "observation_date,USREC\n"
        + "\n".join(f"2025-{m:02d}-01,0" for m in range(1, 13))
        + "\n2026-05-01,0\n2026-06-01,0\n2026-07-01,0\n"
    )
    bag = _bag(
        excerpts=[
            (FRED, "USREC", csv_pipe),
            (BLS, "Employment Situation", _JULY_CES),
        ],
        spine="June prose names the series. July payrolls named in the CES.",
        hit_urls=[FRED, BLS],
    )
    usrec = Claim(
        series="USREC",
        print="0",
        when="July 2026",
        id="usrec-july-2026",
        cite_url=FRED,
        claim_span="USREC=0 (July 2026)",
    )
    payrolls = Claim(
        series="BLS payrolls",
        print="+21,000",
        when="July 2026",
        id="payrolls-july-2026",
        cite_url=BLS,
        claim_span="Total nonfarm payroll employment increased by 21,000 in July 2026.",
    )
    printed = verify_print_in_cite(usrec, bag)
    assert printed.ok is True, printed.reason
    smash = verify_usrec_smash(usrec, payrolls, bag)
    assert smash.ok is True, smash.reason
    june = Claim(
        series="USREC",
        print="0",
        when="June 2026",
        id="usrec-june-2026",
        cite_url=FRED,
        claim_span="USREC=0 (June 2026)",
    )
    mixed = verify_usrec_smash(june, payrolls, bag)
    assert mixed.ok is False
    assert mixed.reason == "smash mixed months"


def test_gdp_or_lei_decimal_is_not_usrec_print() -> None:
    """`is 1.5` / `is 0.2` must not satisfy USREC print 0/1."""
    claim = Claim(series="USREC", print="0", when="June 2026", id="usrec-june-2026", cite_url=FRED)
    bag = _bag(
        excerpts=[(FRED, "USREC", "Real GDP is 1.5 percent. The LEI is 0.2 percent. June 2026 notes.")],
        spine="June 2026 discussion. No recession flag printed.",
        hit_urls=[FRED],
    )
    missed = verify_print_in_cite(claim, bag)
    assert missed.ok is False
    assert missed.reason == "print not in cite"
    ones = Claim(series="USREC", print="1", when="June 2026", id="usrec-june-2026", cite_url=FRED)
    assert verify_print_in_cite(ones, bag).reason == "print not in cite"


def test_recession_indicator_remains_zero_is_print_in_cite() -> None:
    claim = Claim(series="USREC", print="0", when="June 2026", id="usrec-june-2026", cite_url=FRED)
    bag = _bag(
        excerpts=[
            (FRED, "USREC", "The NBER-based FRED recession indicator remains 0 for June 2026.")
        ],
        hit_urls=[FRED],
    )
    got = verify_print_in_cite(claim, bag)
    assert got.ok is True, got.reason


def test_glued_csv_date_still_counts_as_usrec_print() -> None:
    """Comma-stripped FRED cells (2026-06-010) must still count as print 0 for that when."""
    usrec = Claim(
        series="USREC",
        print="0",
        when="June 2026",
        id="usrec-june-2026",
        cite_url=FRED,
        claim_span="USREC=0 (June 2026)",
    )
    glued = _bag(
        excerpts=[(FRED, "USREC", "observation_dateUSREC\n2026-05-010\n2026-06-010\n")],
        spine="Series page. Observation month named June 2026.",
        hit_urls=[FRED],
    )
    printed = verify_print_in_cite(usrec, glued)
    assert printed.ok is True, printed.reason
    smash = verify_usrec_smash(usrec, None, glued)
    assert smash.ok is True, smash.reason


def test_gdp_q4_half_is_rejected_when_2026_pair_exists() -> None:
    bag = _bag(
        excerpts=[
            (
                BEA,
                "GDP",
                "BEA third estimate: real GDP rose 2.1% annualized in Q1 vs 0.5% in Q4 2025. "
                "Real GDP increased 1.5% annualized in Q2 2026.",
            )
        ],
        hit_urls=[BEA],
    )
    claim = Claim(
        series="GDP",
        print="0.5",
        when="Q4 2025",
        id="gdp-2025-q4",
        cite_url=BEA,
        claim_span="real GDP rose 2.1% annualized in Q1 vs 0.5% in Q4 2025",
    )
    got = verify_gdp_bars(claim, bag)
    assert got.ok is False
    assert got.reason in {"gdp bars mismatch", "q4 vs q1/q2", "gdp when mismatch", "gdp id mismatch"}


def test_gdp_sole_q4_half_comparison_is_not_a_bar() -> None:
    bag = _bag(
        excerpts=[
            (
                BEA,
                "GDP",
                "BEA third estimate: real GDP rose vs 0.5% in Q4 2025. "
                "Q4 2025 growth was only 0.5%.",
            )
        ],
        hit_urls=[BEA],
    )
    claim = Claim(
        series="GDP",
        print="0.5",
        when="Q4 2025",
        id="gdp-2025-q4",
        cite_url=BEA,
        claim_span="Q4 2025 growth was only 0.5%.",
    )
    got = verify_gdp_bars(claim, bag)
    assert got.ok is False
    assert got.reason == "gdp bars mismatch"


FRED_SAHM = "https://fred.stlouisfed.org/series/SAHMREALTIME"
LEI_URL = "https://www.conference-board.org/topics/us-leading-indicators"


def test_lei_sahm_url_is_wrong_series_even_if_spine_has_print() -> None:
    from onecrew.foundry import _url_fits_series

    assert _url_fits_series(FRED_SAHM, "LEI", ()) is False
    assert _url_fits_series(BLS, "LEI", ()) is False
    assert _url_fits_series(LEI_URL, "LEI", ()) is True
    claim = Claim(
        series="LEI",
        print="-4.3%",
        when="June 2026",
        id="lei-june-2026",
        cite_url=FRED_SAHM,
        claim_span=(
            "The Conference Board 3Ds recession signal requires a six-month "
            "LEI growth rate below −4.3%."
        ),
    )
    bag = _bag(
        excerpts=[
            (
                FRED_SAHM,
                "SAHMREALTIME",
                "Sahm June 2026 = −0.03 vs 0.50 trigger. "
                "The Conference Board 3Ds recession signal requires a "
                "six-month LEI growth rate below −4.3%.",
            )
        ],
        spine=(
            "June 2026 notes: six-month LEI growth rate below −4.3% is the "
            "3Ds signal threshold."
        ),
        hit_urls=[FRED_SAHM],
    )
    got = verify_print_in_cite(claim, bag)
    assert got.ok is False
    assert got.reason == "cite_url series mismatch"


def test_lei_conference_board_july_turn_still_prints_in_cite() -> None:
    claim = Claim(
        series="LEI",
        print="0.2%",
        when="July 2026",
        id="lei-july-2026",
        cite_url=LEI_URL,
        claim_span="Conference Board LEI increased 0.2% in July 2026.",
    )
    bag = _bag(
        excerpts=[
            (
                LEI_URL,
                "Conference Board LEI",
                "Conference Board LEI increased 0.2% in July 2026.",
            )
        ],
        hit_urls=[LEI_URL],
    )
    got = verify_print_in_cite(claim, bag)
    assert got.ok is True, got.reason


def test_sahm_when_print_mismatch_holds_june_with_july_cell() -> None:
    """June/−0.03 is not a FRED cell when the pipe says June 0.07 / July −0.03."""
    from onecrew.verify import verify_sahm_cell

    table = (
        "Sahm June 2026 = −0.03 vs 0.50 trigger. "
        "2026-06-01 | 0.07\n2026-07-01 | -0.03\n2026-08-01 | -0.07\n"
        "June 2026 0.07\nJuly 2026 −0.03\nAugust 2026 −0.07\n"
    )
    bag = _bag(
        excerpts=[(FRED_SAHM, "SAHMREALTIME", table)],
        spine=table,
        hit_urls=[FRED_SAHM],
    )
    mixed = Claim(
        series="SAHMREALTIME",
        print="−0.03",
        when="June 2026",
        id="sahm-june-2026",
        cite_url=FRED_SAHM,
        claim_span=table,
    )
    got = verify_sahm_cell(mixed, bag)
    assert got.ok is False
    assert got.reason == "sahm when print mismatch"
    checked = verify_claim_set([mixed], bag)
    assert checked.ok is False
    assert "sahm when print mismatch" in checked.hold_reasons
    july = mixed.model_copy(update={"when": "July 2026", "id": "sahm-july-2026"})
    ok = verify_sahm_cell(july, bag)
    assert ok.ok is True, ok.reason


