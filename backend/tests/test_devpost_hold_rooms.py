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


# Live HOLD oc-are-we-near-recession-6814d7c0: spine says June = −0.03,
# FRED pipe is Jun 0.07 / Jul −0.03. Stamp kept June; VO spoke July.
_LIVE_SAHM_JUNE_PROSE_JULY_PIPE = (
    "Sahm June 2026 = −0.03 vs 0.50 trigger. "
    "2026-06-01 | 0.07\n2026-07-01 | -0.03\n"
    "June 2026 0.07\n"
    "July 2026 −0.03\n"
)
_MONTH_YEAR = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+(20\d{2})",
    re.I,
)


def _assert_sahm_vo_month_matches_stamp(packet: Packet) -> None:
    """Fail if a beat speaks the Sahm print, cites the Sahm id, and names another month."""
    receipt = packet.receipt
    assert receipt is not None
    sahm = next(f for f in receipt.findings if f.series == "SAHMREALTIME")
    stamp = (sahm.when or "").strip().lower()
    printed = _norm_print(sahm.print)
    assert stamp and printed
    for beat in packet.beats:
        vo = beat.vo or ""
        if f"[{sahm.id}]" not in vo:
            continue
        vo_n = _norm_print(vo)
        if printed not in vo_n and printed.lstrip("+-") not in vo_n:
            continue
        for match in _MONTH_YEAR.finditer(vo):
            spoken = f"{match.group(1).title()} {match.group(2)}".lower()
            assert spoken == stamp, (
                f"{beat.id} speaks {spoken} for {printed} [{sahm.id}] but stamp when is {stamp}"
            )


def test_sahm_june_prose_july_pipe_stamps_july_and_vo_month_matches() -> None:
    """Print −0.03 on the July pipe. Do not keep June because prose said June = −0.03."""
    from onecrew.claimer import claims_from_cites, findings_from_claims, propose_claims
    from onecrew.foundry import mint
    from onecrew.verify import Claim

    spine = f"USREC July 2026 = 0. {_CES} {_LIVE_SAHM_JUNE_PROSE_JULY_PIPE}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.id = "oc-are-we-near-recession-6814d7c0"
    packet.task_spine = spine
    packet.research_pack = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS, "BLS", [_CES]),
            _row(FRED_SAHM, "SAHMREALTIME", [_LIVE_SAHM_JUNE_PROSE_JULY_PIPE]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (FRED_SAHM, "SAHMREALTIME", _LIVE_SAHM_JUNE_PROSE_JULY_PIPE),
            (FRED_USREC, "USREC", _USREC),
            (BLS, "BLS", _CES),
        ],
        spine=spine,
        hit_urls=[FRED_SAHM, FRED_USREC, BLS],
    )

    def june_vertex(_bag, _packet=None):
        return [
            Claim(
                series="SAHMREALTIME",
                print="−0.03",
                when="June 2026",
                id="sahm-june-2026",
                cite_url=FRED_SAHM,
                claim_span=_LIVE_SAHM_JUNE_PROSE_JULY_PIPE,
            )
        ]

    scanned = findings_from_claims(claims_from_cites(bag), bag)
    remapped = propose_claims(bag, proposer=june_vertex)
    assert ledger.parallel_calls == before
    for rows in (minted, scanned, remapped):
        sahm = next(f for f in rows if getattr(f, "series", None) == "SAHMREALTIME")
        assert _norm_print(sahm.print) == "-0.03"
        assert (sahm.when or "").lower() == "july 2026"
        assert sahm.id == "sahm-july-2026"
        assert "june" not in (sahm.when or "").lower()
    sahm = next(f for f in minted if f.series == "SAHMREALTIME")
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=minted),
    )
    write_script(packet)
    assert ledger.parallel_calls == before
    spoken = (packet.script or "") + "\n" + "\n".join(b.vo for b in packet.beats)
    assert "−0.03" in spoken or "-0.03" in spoken
    assert "[sahm-july-2026]" in spoken
    assert "[sahm-june-2026]" not in spoken
    _assert_sahm_vo_month_matches_stamp(packet)


def test_writer_rejects_sahm_vo_month_off_stamp(monkeypatch) -> None:
    """Vertex must not speak July for −0.03 while citing a June Sahm id."""
    pack = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls fell −23,000 in July 2026. "
        "Sahm June 2026 = −0.03 vs the 0.50 trigger. "
        "2026-06-01 | 0.07\n2026-07-01 | -0.03\n"
    )
    packet = _packet()
    packet.id = "oc-are-we-near-recession-6814d7c0"
    packet.research_pack = pack
    packet.task_spine = pack
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
            id="sahm-june-2026",
            claim="Sahm June 2026 = −0.03 vs 0.50 trigger.",
            stamp="grounded",
            series="SAHMREALTIME",
            print="−0.03",
            when="June 2026",
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
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    mixed = (
        '[{"id":"cold-open","vo":"USREC=0 (July 2026) smashed into payrolls −23,000. '
        '[usrec-july-2026] [payrolls-july-2026]",'
        '"eyes":"cards","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"promise","vo":"Three objects from the pack. [usrec-july-2026]",'
        '"eyes":"pack","finding_ids":["usrec-july-2026"]},'
        '{"id":"gdp","vo":"The official series stay on the cards. [usrec-july-2026]",'
        '"eyes":"gdp","finding_ids":["usrec-july-2026"]},'
        '{"id":"labor","vo":"Labor: payrolls −23,000. Named BLS. [payrolls-july-2026]",'
        '"eyes":"ces","finding_ids":["payrolls-july-2026"]},'
        '{"id":"turn","vo":"Turn: Sahm −0.03 in July 2026 vs the 0.50 trigger. [sahm-june-2026]",'
        '"eyes":"sahm","finding_ids":["sahm-june-2026"]},'
        '{"id":"complication","vo":"Sahm −0.03 in July 2026 is not the official call. [sahm-june-2026]",'
        '"eyes":"gap","finding_ids":["sahm-june-2026"]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-july-2026]",'
        '"eyes":"board","finding_ids":["usrec-july-2026"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-july-2026]",'
        '"eyes":"close","finding_ids":["usrec-july-2026"]}]'
    )
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda _p: mixed)
    before = ledger.parallel_calls
    write_script(packet)
    assert ledger.parallel_calls == before
    sahm = next(f for f in packet.receipt.findings if f.series == "SAHMREALTIME")
    table = (
        "Sahm June 2026 = −0.03 vs the 0.50 trigger. "
        "2026-06-01 | 0.07\n2026-07-01 | -0.03\n"
    )
    assert _when_print_on_fred_row(sahm.when, sahm.print, table)
    pair = (_norm_print(sahm.print), (sahm.when or "").lower())
    assert pair != ("-0.03", "june 2026")
    spoken = (packet.script or "") + "\n" + "\n".join(b.vo for b in packet.beats)
    assert f"[{sahm.id}]" in spoken
    _assert_sahm_vo_month_matches_stamp(packet)
    if pair[0] == "-0.03":
        assert (sahm.when or "").lower() == "july 2026"
        assert "[sahm-july-2026]" in spoken
        assert "Sahm −0.03 in July 2026" in spoken or "Sahm -0.03 in July 2026" in spoken
    for beat in packet.beats:
        if "[sahm-june-2026]" in (beat.vo or "") and ("−0.03" in beat.vo or "-0.03" in beat.vo):
            assert "july 2026" not in beat.vo.lower()


# Live HOLD oc-are-we-near-recession-8945808e: CES August U-3 4.1% on the
# same BLS cite as payrolls, plus a non-CES 20% / December 2026 print.
_AUG_CES_U3 = (
    "THE EMPLOYMENT SITUATION -- AUGUST 2026. "
    "Total nonfarm payroll employment fell by 11,000 in August 2026. "
    "The unemployment rate was 4.1% in August 2026."
)
_BOGUS_U3 = (
    "The unemployment rate was 20 percent in December 2026. "
    "Commentators asked whether the unemployment rate could reach 20 percent "
    "by December 2026."
)
_USREC_AUG = "2026-08-01 | 0\nUSREC August 2026 = 0."


def test_u3_future_or_absurd_print_holds_year_absent_from_ces() -> None:
    """CES vintage is the lock. A later/non-CES U-3 print cannot stay READY."""
    from onecrew.claimer import claims_from_cites, findings_from_claims, propose_claims
    from onecrew.foundry import mint
    from onecrew.verify import Claim, apply_verify_gate, verify_claim_set, verify_u3_ces

    spine = f"{_USREC_AUG} {_AUG_CES_U3} {_BOGUS_U3} {_FRED_SAHM_TABLE}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.id = "oc-are-we-near-recession-8945808e"
    packet.task_spine = spine
    packet.research_pack = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC_AUG]),
            _row(BLS, "BLS", [_AUG_CES_U3]),
            _row("https://example.com/forecast", "forecast", [_BOGUS_U3]),
            _row(FRED_SAHM, "SAHMREALTIME", [_FRED_SAHM_TABLE]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (BLS, "BLS", _AUG_CES_U3),
            ("https://example.com/forecast", "forecast", _BOGUS_U3),
            (FRED_USREC, "USREC", _USREC_AUG),
            (FRED_SAHM, "SAHMREALTIME", _FRED_SAHM_TABLE),
        ],
        spine=spine,
        hit_urls=[BLS, "https://example.com/forecast", FRED_USREC, FRED_SAHM],
    )

    def plant_december(_bag, _packet=None):
        return [
            Claim(
                series="U-3",
                print="20%",
                when="December 2026",
                id="unemployment-december-2026",
                cite_url=BLS,
                claim_span=_BOGUS_U3,
            )
        ]

    scanned = findings_from_claims(claims_from_cites(bag), bag)
    remapped = propose_claims(bag, proposer=plant_december)
    assert ledger.parallel_calls == before
    bogus = Claim(
        series="U-3",
        print="20%",
        when="December 2026",
        id="unemployment-december-2026",
        cite_url=BLS,
        claim_span=_BOGUS_U3,
    )
    assert verify_u3_ces(bogus, bag).ok is False
    assert verify_u3_ces(bogus, bag).reason == "u3 year absent from ces"
    checked = verify_claim_set([bogus], bag)
    assert checked.ok is False
    assert "u3 year absent from ces" in checked.hold_reasons
    for rows in (minted, scanned, remapped):
        for finding in rows:
            if getattr(finding, "series", None) != "U-3":
                continue
            assert "20" not in _norm_print(finding.print)
            assert "december" not in (finding.when or "").lower()
            assert finding.id != "unemployment-december-2026"
            assert "4.1" in (finding.print or "")
    planted = [
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
    ]
    gated = apply_verify_gate(
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=planted),
        bag,
    )
    assert ledger.parallel_calls == before
    assert gated.disposition == "HOLD"
    assert "u3 year absent from ces" in (gated.hold_reason or "")


def _assert_sahm_vo_speaks_stamp_when_and_print(packet: Packet) -> None:
    """Turn VO must speak the stamp when and the stamp print together."""
    receipt = packet.receipt
    assert receipt is not None
    sahm = next(f for f in receipt.findings if f.series == "SAHMREALTIME")
    stamp = (sahm.when or "").strip().lower()
    printed = _norm_print(sahm.print)
    assert stamp and printed
    turn = next(b for b in packet.beats if b.id == "turn")
    vo = turn.vo or ""
    vo_n = _norm_print(vo)
    assert f"[{sahm.id}]" in vo
    assert printed in vo_n or printed.lstrip("+-") in vo_n
    months = [f"{m.group(1).title()} {m.group(2)}".lower() for m in _MONTH_YEAR.finditer(vo)]
    assert stamp in months, f"turn vo={vo!r} missing stamp when {stamp}"
    _assert_sahm_vo_month_matches_stamp(packet)


def test_sahm_stamp_when_print_is_one_fred_row_and_vo_speaks_it() -> None:
    """June/−0.03 is not a FRED cell. Latest row with that print, or June/0.07."""
    from onecrew.claimer import claims_from_cites, findings_from_claims, propose_claims
    from onecrew.foundry import mint
    from onecrew.verify import Claim

    table = _LIVE_SAHM_JUNE_PROSE_JULY_PIPE
    spine = f"USREC July 2026 = 0. {_CES} {table}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.id = "oc-are-we-near-recession-8945808e"
    packet.task_spine = spine
    packet.research_pack = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS, "BLS", [_CES]),
            _row(FRED_SAHM, "SAHMREALTIME", [table]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (FRED_SAHM, "SAHMREALTIME", table),
            (FRED_USREC, "USREC", _USREC),
            (BLS, "BLS", _CES),
        ],
        spine=spine,
        hit_urls=[FRED_SAHM, FRED_USREC, BLS],
    )

    def june_minus(_bag, _packet=None):
        return [
            Claim(
                series="SAHMREALTIME",
                print="−0.03",
                when="June 2026",
                id="sahm-june-2026",
                cite_url=FRED_SAHM,
                claim_span=table,
            )
        ]

    scanned = findings_from_claims(claims_from_cites(bag), bag)
    remapped = propose_claims(bag, proposer=june_minus)
    assert ledger.parallel_calls == before
    for rows in (minted, scanned, remapped):
        sahm = next(f for f in rows if getattr(f, "series", None) == "SAHMREALTIME")
        assert _when_print_on_fred_row(sahm.when, sahm.print, table), (
            f"{sahm.id} print={sahm.print!r} when={sahm.when!r} is not one FRED row"
        )
        pair = (_norm_print(sahm.print), (sahm.when or "").lower())
        assert pair != ("-0.03", "june 2026")
        if pair[0] == "-0.03":
            assert pair[1] == "july 2026"
            assert sahm.id == "sahm-july-2026"
        if pair[1] == "june 2026":
            assert pair[0] == "0.07"
            assert sahm.id == "sahm-june-2026"
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=minted),
    )
    write_script(packet)
    assert ledger.parallel_calls == before
    sahm = next(f for f in packet.receipt.findings if f.series == "SAHMREALTIME")
    assert _when_print_on_fred_row(sahm.when, sahm.print, table)
    _assert_sahm_vo_speaks_stamp_when_and_print(packet)


# Live READY oc-are-we-near-recession-562aa326: Parallel FRED cells are
# Jun 0.07 / Jul −0.03 / Aug −0.07. Stamp kept June/−0.03 (July's print
# on June's when) and id sahm-june-2026. VO said July and cited that id.
_LIVE_SAHM_562_PIPE = (
    "2026-06-01 | 0.07\n"
    "2026-07-01 | -0.03\n"
    "2026-08-01 | -0.07\n"
)
_LIVE_SAHM_562_HTML = (
    "<table><tr><td>2026-06-01</td><td>0.07</td></tr>"
    "<tr><td>2026-07-01</td><td>-0.03</td></tr>"
    "<tr><td>2026-08-01</td><td>-0.07</td></tr></table>"
)
_LIVE_SAHM_562_NAMED = "June 2026 0.07\nJuly 2026 −0.03\nAugust 2026 −0.07\n"
_LIVE_SAHM_562 = (
    "SAHMREALTIME\n"
    "Sahm June 2026 = −0.03 vs 0.50 trigger.\n"
    f"{_LIVE_SAHM_562_PIPE}"
    f"{_LIVE_SAHM_562_NAMED}"
)
_NO_MINUS_003_TABLE = (
    "SAHMREALTIME\n"
    "2026-06-01 | 0.07\n"
    "2026-08-01 | -0.07\n"
    "June 2026 0.07\n"
    "August 2026 −0.07\n"
)


def _pipe_sahm_cells(blob: str) -> set[tuple[str, str]]:
    """ISO/pipe FRED cells only. Prose 'June = −0.03' is not a cell when the pipe exists."""
    found: set[tuple[str, str]] = set()
    for match in re.finditer(
        r"(20\d{2})-(\d{2})-\d{2}\s*[|,]?\s*([+\-−]?\d+\.\d+)",
        blob or "",
    ):
        month = _ISO_MONTH[int(match.group(2))]
        if month:
            found.add((f"{month} {match.group(1)}".lower(), _norm_print(match.group(3))))
    return found


def _assert_sahm_one_pipe_cell(sahm, blob: str) -> None:
    cells = _pipe_sahm_cells(blob)
    assert cells, "test table must carry dated FRED cells"
    pair = ((sahm.when or "").strip().lower(), _norm_print(sahm.print))
    assert pair in cells, f"{sahm.id} {pair} is not a FRED pipe cell {sorted(cells)}"
    assert pair != ("june 2026", "-0.03")
    if pair[1] == "-0.03":
        assert pair[0] == "july 2026"
        assert sahm.id != "sahm-june-2026"


def test_forbidden_wrap_renames_sahm_id_to_june_while_print_is_july_cell() -> None:
    """Vertex/id rename to june cannot keep July's print. One FRED cell or HOLD."""
    from onecrew.claimer import findings_from_claims, propose_claims
    from onecrew.foundry import mint
    from onecrew.verify import Claim, apply_verify_gate, verify_claim_set

    table = _LIVE_SAHM_562
    html = f"Sahm June 2026 = −0.03 vs 0.50 trigger. {_LIVE_SAHM_562_HTML}"
    spine = f"USREC July 2026 = 0. {_CES} {table}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.id = "oc-are-we-near-recession-562aa326"
    packet.task_spine = spine
    packet.research_pack = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS, "BLS", [_CES]),
            _row(FRED_SAHM, "SAHMREALTIME", [html]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    bag = _bag(
        excerpts=[
            (FRED_SAHM, "SAHMREALTIME", html),
            (FRED_USREC, "USREC", _USREC),
            (BLS, "BLS", _CES),
        ],
        spine=spine,
        hit_urls=[FRED_SAHM, FRED_USREC, BLS],
    )

    def june_july_print(_bag, _packet=None):
        return [
            Claim(
                series="SAHMREALTIME",
                print="−0.03",
                when="June 2026",
                id="sahm-june-2026",
                cite_url=FRED_SAHM,
                claim_span=html,
            )
        ]

    remapped = propose_claims(bag, proposer=june_july_print)
    planted = findings_from_claims(june_july_print(bag), bag)
    mixed = next(c for c in june_july_print(bag) if c.series == "SAHMREALTIME")
    checked = verify_claim_set([mixed], bag)
    gated = apply_verify_gate(
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=planted),
        bag,
    )
    assert ledger.parallel_calls == before
    assert checked.ok is False
    assert any(
        "sahm when print mismatch" in r or "smash mixed months" in r
        for r in checked.hold_reasons
    )
    for rows in (minted, remapped):
        sahm = next(f for f in rows if getattr(f, "series", None) == "SAHMREALTIME")
        _assert_sahm_one_pipe_cell(sahm, _LIVE_SAHM_562_PIPE)
        assert sahm.id != "sahm-june-2026" or _norm_print(sahm.print) != "-0.03"
        cite = _cite_urls(sahm) if hasattr(sahm, "parallel_url") else (sahm.cite_url or "")
        assert "fred.stlouisfed.org/series/sahmrealtime" in cite.lower()
    if gated.disposition == "READY":
        sahm = next(f for f in gated.findings if f.series == "SAHMREALTIME")
        _assert_sahm_one_pipe_cell(sahm, _LIVE_SAHM_562_PIPE)
        assert sahm.id != "sahm-june-2026"
    else:
        assert gated.disposition == "HOLD"
        assert gated.findings
        reason = (gated.hold_reason or "").lower()
        assert "sahm when print mismatch" in reason or "smash mixed months" in reason


def test_forbidden_wrap_vo_july_with_stamp_june(monkeypatch) -> None:
    """#42 bar: spoken Sahm month must match stamped when. July VO + June stamp dies."""
    pack = (
        "USREC July 2026 = 0. "
        "Nonfarm payrolls fell −23,000 in July 2026. "
        "Sahm June 2026 = 0.07 vs the 0.50 trigger. "
        "2026-06-01 | 0.07\n"
    )
    packet = _packet()
    packet.id = "oc-are-we-near-recession-562aa326"
    packet.research_pack = pack
    packet.task_spine = pack
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
            id="sahm-june-2026",
            claim="Sahm June 2026 = 0.07 vs 0.50 trigger.",
            stamp="grounded",
            series="SAHMREALTIME",
            print="0.07",
            when="June 2026",
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
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    mixed = (
        '[{"id":"cold-open","vo":"USREC=0 (July 2026) smashed into payrolls −23,000. '
        '[usrec-july-2026] [payrolls-july-2026]",'
        '"eyes":"cards","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"promise","vo":"Three objects from the pack. [usrec-july-2026]",'
        '"eyes":"pack","finding_ids":["usrec-july-2026"]},'
        '{"id":"gdp","vo":"The official series stay on the cards. [usrec-july-2026]",'
        '"eyes":"gdp","finding_ids":["usrec-july-2026"]},'
        '{"id":"labor","vo":"Labor: payrolls −23,000. Named BLS. [payrolls-july-2026]",'
        '"eyes":"ces","finding_ids":["payrolls-july-2026"]},'
        '{"id":"turn","vo":"Turn: Sahm −0.03 in July 2026 vs the 0.50 trigger. [sahm-june-2026]",'
        '"eyes":"sahm","finding_ids":["sahm-june-2026"]},'
        '{"id":"complication","vo":"Sahm −0.03 in July 2026 is not the official call. [sahm-june-2026]",'
        '"eyes":"gap","finding_ids":["sahm-june-2026"]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-july-2026]",'
        '"eyes":"board","finding_ids":["usrec-july-2026"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-july-2026]",'
        '"eyes":"close","finding_ids":["usrec-july-2026"]}]'
    )
    from onecrew.script import _assemble, _parse_units

    sneak = _assemble(packet.model_copy(deep=True), _parse_units(mixed))
    assert sneak.status == "hold" or (
        sneak.receipt is not None and sneak.receipt.disposition == "HOLD"
    )
    sneak_spoken = (sneak.script or "") + "\n" + "\n".join(b.vo for b in sneak.beats)
    assert sneak_spoken.strip() == "" or all(
        "[sahm-june-2026]" not in (b.vo or "") or "july 2026" not in (b.vo or "").lower()
        for b in sneak.beats
    )
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda _p: mixed)
    before = ledger.parallel_calls
    write_script(packet)
    assert ledger.parallel_calls == before
    sahm = next(f for f in packet.receipt.findings if f.series == "SAHMREALTIME")
    assert (sahm.when or "").lower() == "june 2026"
    if packet.status == "hold" or (
        packet.receipt is not None and packet.receipt.disposition == "HOLD"
    ):
        reason = (
            (packet.receipt.hold_reason or "")
            + " "
            + " ".join(row.detail for row in packet.exclusions)
        ).lower()
        assert reason
    else:
        _assert_sahm_vo_month_matches_stamp(packet)
        for beat in packet.beats:
            vo = beat.vo or ""
            if "[sahm-june-2026]" in vo and "july 2026" in vo.lower():
                raise AssertionError(f"{beat.id} speaks July with June stamp: {vo!r}")


def test_forbidden_wrap_hardcodes_sahm_minus_003() -> None:
    """Mint must take a dated FRED cell. Do not invent −0.03 when no cell has it."""
    from onecrew.foundry import mint

    table = _NO_MINUS_003_TABLE
    spine = f"USREC July 2026 = 0. {_CES} {table}"
    before = ledger.parallel_calls
    packet = _packet()
    packet.id = "oc-are-we-near-recession-562aa326"
    packet.task_spine = spine
    packet.research_pack = spine
    minted = mint(
        packet,
        [
            _row(FRED_USREC, "USREC", [_USREC]),
            _row(BLS, "BLS", [_CES]),
            _row(FRED_SAHM, "SAHMREALTIME", [table]),
        ],
        _miss(),
        SimpleNamespace(results=[], errors=[]),
        spine,
    )
    assert ledger.parallel_calls == before
    sahm = next(f for f in minted if f.series == "SAHMREALTIME")
    _assert_sahm_one_pipe_cell(sahm, table)
    assert _norm_print(sahm.print) != "-0.03"
    assert "0.03" not in _norm_print(sahm.print)
    assert "fred.stlouisfed.org/series/sahmrealtime" in _cite_urls(sahm).lower()
