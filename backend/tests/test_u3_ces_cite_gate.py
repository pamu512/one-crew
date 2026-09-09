"""U-3 cite must be a CES-capable page. Year-absent HOLD is CES-page-only.

Forbidden easy wraps named below: leftover-slot rename, topic hardcode,
second Parallel call that ignores the gate, fake bls.gov without print/when
in the cite bag. No August 2026 / 4.3% lock in production — fixtures only.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.foundry import leftover_three_slot, _url_fits_series
from onecrew.models import Finding, Packet, Receipt, ScriptBeat
from onecrew.spend import ledger
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE
from onecrew.verify import (
    Claim,
    CiteBag,
    CiteExcerpt,
    apply_verify_gate,
    attach_cites_from_hits,
    relink_unsupported_cite,
    resolve_missing_cite,
    verify_print_in_cite,
    verify_u3_ces,
)

FRED_USREC = "https://fred.stlouisfed.org/series/USREC"
BLS_EMPSIT = "https://www.bls.gov/news.release/empsit.nr0.htm"
BLS_CHART = "https://www.bls.gov/charts/employment-situation/civilian-unemployment-rate.htm"
FACTUALLY = "https://factually.co/unemployment-rate-august-2026"
NEWS = "https://www.cnbc.com/economy/jobs-roundup.html"
FAKE_BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"

_USREC = "2026-08-01 | 0\nUSREC August 2026 = 0."
_CES_PAY_ONLY = (
    "THE EMPLOYMENT SITUATION -- AUGUST 2026. "
    "Total nonfarm payroll employment fell by 11,000 in August 2026."
)
_CES_U3_AUG = (
    "THE EMPLOYMENT SITUATION -- AUGUST 2026. "
    "Total nonfarm payroll employment fell by 11,000 in August 2026. "
    "The unemployment rate was 4.3 percent in August 2026."
)
_CES_U3_MAR = (
    "THE EMPLOYMENT SITUATION -- MARCH 2025. "
    "Total nonfarm payroll employment fell by 41,000 in March 2025. "
    "The unemployment rate was 4.2 percent in March 2025."
)
_FACTUALLY_U3 = (
    "The unemployment rate was 4.3 percent in August 2026. "
    "A jobs dashboard recap for readers."
)
_BOGUS_DEC = (
    "The unemployment rate was 20 percent in December 2026. "
    "Commentators asked whether the unemployment rate could reach 20 percent "
    "by December 2026."
)
_NEWS_U3 = "Jobs Friday: unemployment was 4.3% in August 2026, economists say."


def _row(url, title, excerpts):
    return SimpleNamespace(url=url, title=title, excerpts=list(excerpts))


def _packet() -> Packet:
    return Packet(
        id="oc-are-we-near-recession-a711d9a9",
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
        task_spine="",
    )


def _bag(*, excerpts, spine="", hit_urls=None) -> CiteBag:
    rows = [CiteExcerpt(url=u, title=t, text=x) for u, t, x in excerpts]
    urls = hit_urls if hit_urls is not None else list(dict.fromkeys(u for u, _, _ in excerpts))
    return CiteBag(excerpts=rows, spine=spine, hit_urls=urls)


def _u3_finding(*, printed: str, when: str, url: str | None, fid: str | None = None) -> Finding:
    slug = fid or f"unemployment-{when.lower().replace(' ', '-')}"
    return Finding(
        id=slug,
        claim=f"The unemployment rate was {printed} in {when}.",
        stamp="grounded",
        title="U-3",
        series="U-3",
        print=printed,
        when=when,
        parallel_url=url,
        parallel_status="hit" if url else "miss",
        note="Parallel URL on this row." if url else "cite missing",
    )


def _u3_claim(*, printed: str, when: str, url: str, span: str = "") -> Claim:
    return Claim(
        series="U-3",
        print=printed,
        when=when,
        id=f"unemployment-{when.lower().replace(' ', '-')}",
        cite_url=url,
        claim_span=span or f"The unemployment rate was {printed} in {when}.",
    )


def _beat(bid: str, finding_ids: list[str], vo: str) -> ScriptBeat:
    return ScriptBeat(
        id=bid,
        start="00:00",
        duration_s=20,
        scene=f"BEAT — {bid}",
        kind="vo",
        vo=vo,
        finding_ids=finding_ids,
        frame=f"card {bid}",
    )


def test_u3_factually_cite_cannot_hold_year_absent_from_ces() -> None:
    """Live oc-are-we-near-recession-a711d9a9: news cite is not a CES year check."""
    bag = _bag(
        excerpts=[
            (BLS_EMPSIT, "BLS", [_CES_PAY_ONLY][0]),
            (FACTUALLY, "Factually", _FACTUALLY_U3),
            (FRED_USREC, "USREC", _USREC),
        ],
        spine=f"{_USREC} {_CES_PAY_ONLY} {_FACTUALLY_U3}",
        hit_urls=[BLS_EMPSIT, FACTUALLY, FRED_USREC],
    )
    planted = _u3_claim(
        printed="4.3%",
        when="August 2026",
        url=FACTUALLY,
        span=_FACTUALLY_U3,
    )
    got = verify_u3_ces(planted, bag)
    assert got.ok is False
    assert got.reason != "u3 year absent from ces"
    gated = apply_verify_gate(
        Receipt(
            packet_id="oc-are-we-near-recession-a711d9a9",
            written=False,
            disposition="READY",
            findings=[_u3_finding(printed="4.3%", when="August 2026", url=FACTUALLY)],
        ),
        bag,
    )
    assert "u3 year absent from ces" not in (gated.hold_reason or "")
    stamped = [f for f in (gated.findings or []) if f.series == "U-3" and f.stamp == "grounded"]
    for finding in stamped:
        assert "factually.co" not in (finding.parallel_url or "")


def test_u3_mint_and_claimer_reject_non_ces_cites() -> None:
    from onecrew.claimer import claims_from_cites, findings_from_claims
    from onecrew.foundry import mint

    spine = f"{_USREC} {_FACTUALLY_U3} {_NEWS_U3}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(FACTUALLY, "Factually", [_FACTUALLY_U3]),
            _row(NEWS, "CNBC jobs", [_NEWS_U3]),
            _row(BLS_CHART, "BLS chart", [_FACTUALLY_U3]),
        ],
        [_row("https://example.com/fringe", "x", ["Secret double-dip already started."])],
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (FACTUALLY, "Factually", _FACTUALLY_U3),
            (NEWS, "CNBC jobs", _NEWS_U3),
            (BLS_CHART, "BLS chart", _FACTUALLY_U3),
            (FRED_USREC, "USREC", _USREC),
        ],
        spine=spine,
        hit_urls=[FACTUALLY, NEWS, BLS_CHART, FRED_USREC],
    )
    scanned = findings_from_claims(claims_from_cites(bag), bag)
    assert ledger.parallel_calls == before
    for rows in (minted, scanned):
        for finding in rows:
            if getattr(finding, "series", None) != "U-3":
                continue
            url = finding.parallel_url or ""
            assert "factually.co" not in url
            assert "cnbc.com" not in url
            assert "/charts/" not in url
            assert _url_fits_series(url, "U-3", ())


def test_forbidden_wrap_rename_leftover_slots_does_not_pass_u3_ces_gate() -> None:
    from onecrew.foundry import FoundryHold, require_minted

    spine = f"{_USREC} {_CES_PAY_ONLY} {_FACTUALLY_U3}"
    renamed = leftover_three_slot(
        hit_url=FACTUALLY,
        hit_claim="Grounded event inside 2-3y: Are we near recession?",
        mainstream_claim="Widely repeated frame about Are we near recession?",
        miss_claim="Fringe claim about Are we near recession?",
    )
    renamed[0].id = "unemployment-august-2026"
    renamed[0].series = "U-3"
    renamed[0].print = "4.3%"
    renamed[0].when = "August 2026"
    renamed[0].parallel_url = FACTUALLY
    renamed[1].id = "payrolls"
    renamed[2].id = "gdp"
    with pytest.raises(FoundryHold):
        require_minted(renamed, spine)
    bag = _bag(
        excerpts=[
            (FACTUALLY, "Factually", _FACTUALLY_U3),
            (BLS_EMPSIT, "BLS", _CES_PAY_ONLY),
            (FRED_USREC, "USREC", _USREC),
        ],
        spine=spine,
        hit_urls=[FACTUALLY, BLS_EMPSIT, FRED_USREC],
    )
    gated = apply_verify_gate(
        Receipt(
            packet_id="oc-leftover-rename",
            written=False,
            disposition="READY",
            findings=renamed,
        ),
        bag,
    )
    assert "u3 year absent from ces" not in (gated.hold_reason or "")
    stamped = [f for f in (gated.findings or []) if f.series == "U-3" and f.stamp == "grounded"]
    for finding in stamped:
        assert "factually.co" not in (finding.parallel_url or "")
        if finding.parallel_url:
            assert _url_fits_series(finding.parallel_url, "U-3", ())


def test_forbidden_wrap_topic_hardcode_august_2026_43_is_not_the_lock() -> None:
    """A different CES observation pair must stamp. August 2026 / 4.3% is not a constant."""
    from onecrew.claimer import claims_from_cites, findings_from_claims
    from onecrew.foundry import mint

    spine = f"USREC March 2025 = 0. {_CES_U3_MAR} {_FACTUALLY_U3}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", ["USREC March 2025 = 0."]),
            _row(BLS_EMPSIT, "BLS", [_CES_U3_MAR]),
            _row(FACTUALLY, "Factually", [_FACTUALLY_U3]),
        ],
        [_row("https://example.com/fringe", "x", ["Secret double-dip already started."])],
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (BLS_EMPSIT, "BLS", _CES_U3_MAR),
            (FACTUALLY, "Factually", _FACTUALLY_U3),
            (FRED_USREC, "USREC", "USREC March 2025 = 0."),
        ],
        spine=spine,
        hit_urls=[BLS_EMPSIT, FACTUALLY, FRED_USREC],
    )
    scanned = findings_from_claims(claims_from_cites(bag), bag)
    assert ledger.parallel_calls == before
    for rows in (minted, scanned):
        u3s = [f for f in rows if getattr(f, "series", None) == "U-3"]
        assert u3s
        for u3 in u3s:
            assert "4.2" in (u3.print or "")
            assert "4.3" not in (u3.print or "")
            assert (u3.when or "").lower() == "march 2025"
            assert "empsit" in (u3.parallel_url or "")
            assert "factually.co" not in (u3.parallel_url or "")


def test_forbidden_wrap_second_parallel_call_cannot_ignore_ces_cite_gate() -> None:
    """Re-query that only returns a news wrap must not stamp it. Gate stays closed."""
    usrec = Finding(
        id="usrec-august-2026",
        claim="USREC=0 (August 2026)",
        stamp="grounded",
        title="USREC",
        series="USREC",
        print="0",
        when="August 2026",
        parallel_url=FRED_USREC,
        parallel_status="hit",
        note="Parallel URL on this row.",
    )
    u3 = _u3_finding(printed="4.3%", when="August 2026", url=FACTUALLY)
    packet = _packet()
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="cite_url series mismatch",
        findings=[usrec, u3],
    )
    packet.beats = [
        _beat("cold-open", ["usrec-august-2026"], "NARRATOR\nUSREC=0. [usrec-august-2026]"),
        _beat("labor", ["unemployment-august-2026"], "NARRATOR\nUnemployment 4.3%. [unemployment-august-2026]"),
        _beat("close", ["usrec-august-2026"], "NARRATOR\nNear is not a switch. [usrec-august-2026]"),
    ]
    packet.script = "\n".join(b.vo for b in packet.beats)
    bag = _bag(
        excerpts=[
            (FRED_USREC, "USREC", _USREC),
            (FACTUALLY, "Factually", _FACTUALLY_U3),
        ],
        spine=f"{_USREC} {_FACTUALLY_U3}",
        hit_urls=[FRED_USREC, FACTUALLY],
    )
    object.__setattr__(packet, "_cite_bag", bag)
    before = ledger.parallel_calls
    calls = {"n": 0}

    def search(*, objective, search_queries):
        calls["n"] += 1
        return SimpleNamespace(
            results=[
                SimpleNamespace(url=FACTUALLY, title="Factually", excerpts=[_FACTUALLY_U3]),
                SimpleNamespace(url=NEWS, title="CNBC", excerpts=[_NEWS_U3]),
            ]
        )

    result = run_cite_recheck_loop(packet, search_fn=search, bag=bag)
    assert ledger.parallel_calls == before
    assert calls["n"] <= MAX_CITE_RECHECKS
    assert result.hold_reason != "cite-repair loop exhausted" or calls["n"] > MAX_CITE_RECHECKS
    stamped = [f for f in packet.receipt.findings if f.series == "U-3" and f.stamp == "grounded"]
    for finding in stamped:
        assert "factually.co" not in (finding.parallel_url or "")
        assert "cnbc.com" not in (finding.parallel_url or "")
        assert _url_fits_series(finding.parallel_url or "", "U-3", ())
    assert "u3 year absent from ces" not in (packet.receipt.hold_reason or "")


def test_forbidden_wrap_fake_bls_url_without_print_when_in_cite_bag() -> None:
    """A CES host with no observation in the excerpt cannot be attached."""
    bag = _bag(
        excerpts=[
            (FAKE_BLS, "Employment Situation", _CES_PAY_ONLY),
            (FACTUALLY, "Factually", _FACTUALLY_U3),
        ],
        spine=_FACTUALLY_U3,
        hit_urls=[FAKE_BLS, FACTUALLY],
    )
    missing = _u3_claim(printed="4.3%", when="August 2026", url="", span=_FACTUALLY_U3)
    resolved = resolve_missing_cite(missing, bag)
    assert resolved.cite_url != FAKE_BLS
    assert "factually.co" not in (resolved.cite_url or "")
    fake = _u3_claim(printed="4.3%", when="August 2026", url=FAKE_BLS, span=_FACTUALLY_U3)
    assert verify_print_in_cite(fake, bag).ok is False
    planted = _u3_finding(printed="4.3%", when="August 2026", url=None)
    attached = attach_cites_from_hits([planted], bag)
    for finding in attached:
        if finding.series != "U-3":
            continue
        assert finding.parallel_url != FAKE_BLS
        assert "factually.co" not in (finding.parallel_url or "")
    relinked = relink_unsupported_cite(
        _u3_claim(printed="4.3%", when="August 2026", url=FACTUALLY, span=_FACTUALLY_U3),
        bag,
    )
    assert relinked.cite_url != FAKE_BLS
    assert "factually.co" not in (relinked.cite_url or "")


def test_u3_dec_20_on_real_ces_page_still_holds_year_absent() -> None:
    """Dec / 20% stays dead when the stamped cite is the CES page."""
    bag = _bag(
        excerpts=[
            (BLS_EMPSIT, "CES", _CES_U3_AUG),
            ("https://example.com/forecast", "forecast", _BOGUS_DEC),
        ],
        spine=f"{_CES_U3_AUG} {_BOGUS_DEC}",
        hit_urls=[BLS_EMPSIT, "https://example.com/forecast"],
    )
    bogus = _u3_claim(
        printed="20%",
        when="December 2026",
        url=BLS_EMPSIT,
        span=_BOGUS_DEC,
    )
    got = verify_u3_ces(bogus, bag)
    assert got.ok is False
    assert got.reason == "u3 year absent from ces"
    gated = apply_verify_gate(
        Receipt(
            packet_id="oc-u3-future",
            written=False,
            disposition="READY",
            findings=[_u3_finding(printed="20%", when="December 2026", url=BLS_EMPSIT, fid="unemployment-december-2026")],
        ),
        bag,
    )
    assert gated.disposition == "HOLD"
    assert "u3 year absent from ces" in (gated.hold_reason or "")


def test_u3_ces_page_keeps_observation_from_that_row() -> None:
    from onecrew.foundry import mint

    spine = f"{_USREC} {_CES_U3_AUG}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS_EMPSIT, "BLS", [_CES_U3_AUG]),
        ],
        [_row("https://example.com/fringe", "x", ["Secret double-dip already started."])],
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    u3 = next(f for f in minted if f.series == "U-3")
    assert "4.3" in (u3.print or "")
    assert (u3.when or "").lower() == "august 2026"
    assert "empsit" in (u3.parallel_url or "")
    claim = _u3_claim(printed=u3.print, when=u3.when, url=u3.parallel_url or "")
    bag = _bag(
        excerpts=[(BLS_EMPSIT, "BLS", _CES_U3_AUG), (FRED_USREC, "USREC", _USREC)],
        spine=spine,
        hit_urls=[BLS_EMPSIT, FRED_USREC],
    )
    assert verify_u3_ces(claim, bag).ok is True
    assert verify_u3_ces(claim, bag).reason != "u3 year absent from ces"


def test_u3_cite_repair_fails_only_after_loop_gt_3() -> None:
    """Existing rule: exhaust HOLD only when re-checks exceed 3."""
    u3 = _u3_finding(printed="4.3%", when="August 2026", url=None)
    packet = _packet()
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="grounded claim missing cite_url",
        findings=[u3],
    )
    packet.beats = [
        _beat("labor", ["unemployment-august-2026"], "NARRATOR\nUnemployment 4.3%. [unemployment-august-2026]"),
    ]
    packet.script = packet.beats[0].vo
    calls = {"n": 0}

    def search(*, objective, search_queries):
        calls["n"] += 1
        return SimpleNamespace(results=[])

    result = run_cite_recheck_loop(packet, search_fn=search)
    assert result.ok is False
    assert calls["n"] == MAX_CITE_RECHECKS
    assert packet.receipt.hold_reason == "cite-repair loop exhausted" or (
        "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")
    )
    assert result.hold_reason == "cite-repair loop exhausted"
    again = run_cite_recheck_loop(packet, search_fn=search)
    assert again.ok is False
    assert calls["n"] == MAX_CITE_RECHECKS
