"""Fail-closed rooms for live packet oc-are-we-near-recession-1197ce06.

No topic hardcoding in the locks. No second Parallel/Vertex call. No leftover-slot rename.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from onecrew.models import Finding, Packet, Receipt
from onecrew.receipt import write_receipt
from onecrew.script import write_script
from onecrew.spend import ledger
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE
from onecrew.verify import CiteBag, CiteExcerpt

FRED_USREC = "https://fred.stlouisfed.org/series/USREC"
BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
BEA = "https://www.bea.gov/data/gdp/gross-domestic-product"
FRED_SAHM = "https://fred.stlouisfed.org/series/SAHMREALTIME"
LEI_HOST = "https://www.conference-board.org/topics/us-leading-indicators"
DIRTY_LEI = LEI_HOST + "\\n-"

_FRED_SAHM_TABLE = (
    "SAHMREALTIME\n"
    "Sahm −0.03 vs the 0.50 trigger.\n"
    "2026-06-01 0.07\n"
    "2026-07-01 -0.03\n"
    "June 2026 0.07\n"
    "July 2026 −0.03\n"
)
_CES = "Total nonfarm payroll employment fell by 23,000 in July 2026."
_USREC = "2026-07-01 | 0\nUSREC July 2026 = 0."
_GDP_BARS = "Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2 2026."
_LEI_JULY_2025 = "The LEI rose 0.3% in July 2025."

_MONTH = (
    "January|February|March|April|May|June|July|August|September|"
    "October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)
_FULL = {
    "jan": "January",
    "january": "January",
    "feb": "February",
    "february": "February",
    "mar": "March",
    "march": "March",
    "apr": "April",
    "april": "April",
    "may": "May",
    "jun": "June",
    "june": "June",
    "jul": "July",
    "july": "July",
    "aug": "August",
    "august": "August",
    "sep": "September",
    "sept": "September",
    "september": "September",
    "oct": "October",
    "october": "October",
    "nov": "November",
    "november": "November",
    "dec": "December",
    "december": "December",
}
_ISO_MONTH = (
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def _row(url, title, excerpts):
    return SimpleNamespace(url=url, title=title, excerpts=list(excerpts))


def _miss():
    return [_row("https://example.com/fringe", "x", ["Secret double-dip already started in May."])]


def _packet() -> Packet:
    return Packet(
        id="oc-are-we-near-recession-1197ce06",
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


def _norm_print(printed: str) -> str:
    return re.sub(r"\s+", "", (printed or "").replace("−", "-").replace("+", ""))


def _fred_decimal_rows(text: str) -> list[tuple[str, str]]:
    """Named or ISO FRED cells. Test lock: when+print must be one of these rows."""
    found: list[tuple[str, str]] = []
    blob = text or ""
    for match in re.finditer(
        rf"({_MONTH})\s+(20\d{{2}})\s*[=:]?\s*([+\-−]?\d+\.\d+)",
        blob,
        re.I,
    ):
        found.append((f"{_FULL[match.group(1).lower()]} {match.group(2)}", match.group(3)))
    for match in re.finditer(
        r"(20\d{2})-(\d{2})-\d{2}\s*[|,]?\s*([+\-−]?\d+\.\d+)",
        blob,
    ):
        month = _ISO_MONTH[int(match.group(2))]
        if month:
            found.append((f"{month} {match.group(1)}", match.group(3)))
    return found


def _when_print_on_fred_row(when: str, printed: str, blob: str) -> bool:
    want_w = (when or "").strip().lower()
    want_p = _norm_print(printed)
    if not want_w or not want_p:
        return False
    for stamp, value in _fred_decimal_rows(blob):
        if stamp.lower() == want_w and _norm_print(value) == want_p:
            return True
    return False


def _bag(*, excerpts, spine="", hit_urls=None):
    rows = [CiteExcerpt(url=u, title=t, text=x) for u, t, x in excerpts]
    urls = hit_urls if hit_urls is not None else list(dict.fromkeys(u for u, _, _ in excerpts))
    return CiteBag(excerpts=rows, spine=spine, hit_urls=urls)


def _cite_urls(finding: Finding) -> str:
    return f"{finding.parallel_url or ''} {getattr(finding, 'cite_url', '') or ''}"


def _dirty_cite(url: str) -> bool:
    raw = url or ""
    return "\n" in raw or "\r" in raw or "\\n" in raw or raw.endswith("\\n-") or raw.endswith("\n-")


def test_sahm_when_and_print_match_one_fred_row_in_claim() -> None:
    """Stamp when+print must be one FRED cell. Do not pair June with July's minus."""
    from onecrew.claimer import claims_from_cites, findings_from_claims
    from onecrew.foundry import mint

    spine = f"USREC July 2026 = 0. {_CES} {_FRED_SAHM_TABLE}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS, "BLS", [_CES]),
            _row(FRED_SAHM, "SAHMREALTIME", [_FRED_SAHM_TABLE]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (FRED_SAHM, "SAHMREALTIME", _FRED_SAHM_TABLE),
            (FRED_USREC, "USREC", _USREC),
            (BLS, "BLS", _CES),
        ],
        spine=spine,
        hit_urls=[FRED_SAHM, FRED_USREC, BLS],
    )
    claimed = findings_from_claims(claims_from_cites(bag), bag)
    assert ledger.parallel_calls == before
    table = _FRED_SAHM_TABLE
    for rows in (minted, claimed):
        sahms = [f for f in rows if f.series == "SAHMREALTIME"]
        for sahm in sahms:
            assert _when_print_on_fred_row(sahm.when, sahm.print, table), (
                f"{sahm.id} print={sahm.print!r} when={sahm.when!r} is not one FRED row"
            )
            assert "0.07" not in _norm_print(sahm.print) or "june" in (sahm.when or "").lower()
            if _norm_print(sahm.print) in {"-0.03", "−0.03".replace("−", "-")}:
                assert (sahm.when or "").lower() == "july 2026"


def test_vo_promise_cannot_name_gdp_without_stamped_finding_and_spoken_print() -> None:
    """Empty GDP must not stay as a named object in promise/VO/ACTION."""
    pack = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls fell −23,000 in July 2026. "
        "Sahm is −0.03 vs the 0.50 trigger."
    )
    packet = _packet()
    packet.research_pack = pack
    packet.task_spine = pack
    rows = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (July 2026).",
            stamp="grounded",
            title="USREC",
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
            title="BLS payrolls",
            series="BLS payrolls",
            print="−23,000",
            when="July 2026",
            parallel_url=BLS,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="sahm-july-2026",
            claim="Sahm is −0.03 vs the 0.50 trigger.",
            stamp="grounded",
            title="Sahm rule",
            series="SAHMREALTIME",
            print="−0.03",
            when="July 2026",
            parallel_url=FRED_SAHM,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="fringe-miss",
            claim="Hidden treaty already mined the strait.",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]
    write_receipt(packet, Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows))
    before = ledger.parallel_calls
    write_script(packet)
    assert ledger.parallel_calls == before
    gdps = [f for f in packet.receipt.findings if f.series == "GDP"]
    spoken = "\n".join(
        [
            *(b.vo for b in packet.beats),
            *(b.frame or "" for b in packet.beats),
            *(line for line in (packet.script or "").splitlines() if line.startswith("ACTION:")),
        ]
    )
    promise = next(b for b in packet.beats if b.id == "promise")
    promise_blob = f"{promise.vo}\n{promise.frame or ''}"
    if not gdps:
        assert not re.search(r"\bgdp\b", spoken, re.I)
        assert "gdp prints" not in promise_blob.lower()
        assert not re.search(r"\bgdp\b", promise_blob, re.I)
        return
    printed = (gdps[0].print or "").strip()
    assert printed
    assert any(_norm_print(part) and _norm_print(part) in _norm_print(spoken) for part in printed.split("/"))
    assert any(f"[{gdps[0].id}]" in b.vo for b in packet.beats)


def test_finding_cite_url_has_no_newline_or_trailing_n_dash() -> None:
    """Mangled conference-board\\n- is drop or repair. Never a leftover dirty href."""
    from onecrew.claimer import findings_from_claims
    from onecrew.foundry import mint
    from onecrew.verify import Claim

    spine = f"USREC July 2026 = 0. {_CES} {_LEI_JULY_2025}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.task_spine = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS, "BLS", [_CES]),
            _row(DIRTY_LEI, "Conference Board LEI", [_LEI_JULY_2025]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[(DIRTY_LEI, "Conference Board LEI", _LEI_JULY_2025)],
        spine=spine,
        hit_urls=[DIRTY_LEI],
    )
    claimed = findings_from_claims(
        [
            Claim(
                series="LEI",
                print="0.3%",
                when="July 2025",
                id="lei-july-2025",
                cite_url=DIRTY_LEI,
                claim_span=_LEI_JULY_2025,
            )
        ],
        bag,
    )
    assert ledger.parallel_calls == before
    for rows in (minted, claimed):
        for finding in rows:
            cite = _cite_urls(finding)
            assert not _dirty_cite(finding.parallel_url or "")
            assert not _dirty_cite(getattr(finding, "cite_url", "") or "")
            assert "\n" not in cite and "\\n" not in cite
        leis = [f for f in rows if f.series == "LEI"]
        for lei in leis:
            host = (lei.parallel_url or "").lower()
            assert "conference-board.org" in host
            assert "sahm" not in host
            assert "sahmrealtime" not in host
            assert host.startswith("http")
            assert not host.endswith("\\n-")
            assert "4.3" not in (lei.print or "").replace("−", "-")


def test_propose_claims_fills_gdp_pair_when_vertex_omits_it() -> None:
    """Cite-scan fill. Not a second Vertex/Parallel call."""
    from onecrew.claimer import propose_claims
    from onecrew.verify import Claim

    spine = f"{_USREC} {_CES} {_GDP_BARS} {_FRED_SAHM_TABLE}"
    bag = _bag(
        excerpts=[
            (FRED_USREC, "USREC", _USREC),
            (BLS, "BLS", _CES),
            (BEA, "BEA", _GDP_BARS),
            (FRED_SAHM, "SAHMREALTIME", _FRED_SAHM_TABLE),
        ],
        spine=spine,
        hit_urls=[FRED_USREC, BLS, BEA, FRED_SAHM],
    )

    def omit_gdp(_bag, _packet=None):
        return [
            Claim(
                series="USREC",
                print="0",
                when="July 2026",
                id="usrec-july-2026",
                cite_url=FRED_USREC,
                claim_span="USREC=0 (July 2026)",
            ),
            Claim(
                series="BLS payrolls",
                print="−23,000",
                when="July 2026",
                id="payrolls-july-2026",
                cite_url=BLS,
                claim_span=_CES,
            ),
            Claim(
                series="SAHMREALTIME",
                print="−0.03",
                when="June 2026",
                id="sahm-june-2026",
                cite_url=FRED_SAHM,
                claim_span=_FRED_SAHM_TABLE,
            ),
        ]

    before = ledger.parallel_calls
    claims = propose_claims(bag, proposer=omit_gdp)
    assert ledger.parallel_calls == before
    gdp = next(c for c in claims if c.series == "GDP")
    assert gdp.print == "2.1 / 1.5"
    assert "0.5" not in (gdp.print or "")
    assert (gdp.when or "").upper().replace(" ", "") == "Q22026"
    assert gdp.id == "gdp-2026-q2"
    sahm = next(c for c in claims if c.series == "SAHMREALTIME")
    assert _when_print_on_fred_row(sahm.when, sahm.print, _FRED_SAHM_TABLE)
    if _norm_print(sahm.print) == "-0.03":
        assert (sahm.when or "").lower() == "july 2026"
