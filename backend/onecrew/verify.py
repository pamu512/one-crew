"""Deterministic critic tools. Agent prose cannot override ok: false."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from onecrew.foundry import leftover_slot_ids
from onecrew.models import MISSING, Finding, Receipt

SeriesName = Literal["USREC", "BLS payrolls", "U-3", "GDP", "LEI", "SAHMREALTIME"]
CLOSED_SERIES = frozenset({"USREC", "BLS payrolls", "U-3", "GDP", "LEI", "SAHMREALTIME"})
_LEFTOVER = leftover_slot_ids()

_MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}
_MONTH_NAMES = {n: [k for k, v in _MONTHS.items() if v == n] for n in range(1, 13)}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))
_FALL = re.compile(r"\b(fell|declined|dropped|lost|decreased|down)\b", re.I)
_REV = re.compile(r"revised\b.{0,80}from\s+[+\-−]\d", re.I | re.S)
_CES = re.compile(r"nonfarm|ces\b|employment situation|empsit|payroll employment|\bpayrolls\b", re.I)
_NAICS_LEVEL = re.compile(r"\bnaics\b|payroll services|employment level", re.I)
_UNEMP = re.compile(r"unemployment|u-3|\bu3\b", re.I)
_SAHM = re.compile(r"\bsahm\b", re.I)
_FORECAST_RE = re.compile(r"\b(?:spf|cei)\b|disposable|final sales", re.I)
_PIPE = re.compile(r"(20\d{2})-(\d{2})-(\d{2})\s*[|,]?\s*([01])\b")


class CiteExcerpt(BaseModel):
    url: str
    title: str
    text: str


class CiteBag(BaseModel):
    excerpts: list[CiteExcerpt] = Field(default_factory=list)
    spine: str = ""
    hit_urls: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    series: str
    print: str
    when: str
    id: str
    cite_url: str
    claim_span: str = ""


class VerifyResult(BaseModel):
    ok: bool
    reason: str | None
    matched_in: str | None = None


class ClaimSetResult(BaseModel):
    ok: bool
    results: list[VerifyResult] = Field(default_factory=list)
    hold_reasons: list[str] = Field(default_factory=list)


def _norm(text: str) -> str:
    out = (text or "").replace("−", "-").replace(",", "").replace("%", "").lower()
    return re.sub(r"(\d+)k\b", lambda m: m.group(1) + "000", out)


def _url_key(url: str) -> str:
    # ponytail: scheme/www stripped for hit matching. Paths stay; do not invent URLs.
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "").rstrip("/")
    if host:
        return f"{host}{path}"
    return raw.rstrip("/")


def _url_in(url: str, urls: list[str]) -> bool:
    want = _url_key(url)
    return bool(want) and any(_url_key(u) == want for u in urls)


def _cite_text(claim: Claim, bag: CiteBag) -> str:
    return "\n".join(e.text for e in bag.excerpts if _url_key(e.url) == _url_key(claim.cite_url))


def _bag_text(bag: CiteBag) -> str:
    return "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])


def _bars(print_: str) -> list[str]:
    return [part.strip() for part in (print_ or "").split("/") if part.strip()]


def _bar_in(bar: str, text: str) -> bool:
    nb = _norm(bar).strip()
    nt = _norm(text)
    if not nb:
        return False
    unsigned = nb.lstrip("+-")
    # Single-digit flags must be a pipe/equals token, not a digit inside 2026-07-01.
    if unsigned in {"0", "1"}:
        return bool(re.search(rf"(?:usrec\s*=\s*|[|=]\s*){unsigned}\b", nt))
    if nb in nt:
        return True
    return bool(unsigned) and unsigned in nt


def _parse_when(when: str) -> tuple[str, int, int] | None:
    text = when or ""
    q = re.search(r"\bQ([1-4])\s*(20\d{2})\b", text, re.I)
    if q:
        return ("quarter", int(q.group(2)), int(q.group(1)))
    m = re.search(rf"\b({_MONTH_RE})\.?\s+(20\d{{2}})\b", text, re.I)
    if m:
        return ("month", int(m.group(2)), _MONTHS[m.group(1).lower().rstrip(".")])
    return None


def _when_in_text(when: str, text: str) -> bool:
    parsed = _parse_when(when)
    if parsed is None:
        return not (when or "").strip()
    kind, year, num = parsed
    if kind == "quarter":
        blob = _norm(text)
        if str(year) not in blob and str(year) not in (text or ""):
            return False
        words = ("first", "second", "third", "fourth")
        return f"q{num}" in blob or words[num - 1] + " quarter" in blob
    return _year_adjacent_month(text, year, num)


def _usrec_month_on_table(bag: CiteBag, year: int, month: int) -> int | None:
    """0/1 if that month sits on a FRED-style pipe/table. None if absent — do not invent."""
    blob = _bag_text(bag)
    for match in _PIPE.finditer(blob):
        if int(match.group(1)) == year and int(match.group(2)) == month:
            return int(match.group(4))
    return None


def _legal_usrec_print(print_: str) -> bool:
    n = _norm(print_).strip().lstrip("+")
    return n in {"0", "1"} or n.endswith("=0") or n.endswith("=1")


def _strip_forecast(text: str) -> str:
    keep: list[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", text or ""):
        if _FORECAST_RE.search(sent):
            continue
        keep.append(sent)
    return " ".join(keep)


def _bad_window(text: str) -> bool:
    low = (text or "").lower()
    return "suppose" in low or "confidence interval" in low or bool(_REV.search(low))


def _ces_chunks(bag: CiteBag) -> list[str]:
    out: list[str] = []
    for chunk in (*(e.text for e in bag.excerpts), bag.spine or ""):
        if not _CES.search(chunk or ""):
            continue
        if _NAICS_LEVEL.search(chunk or "") and not re.search(
            r"nonfarm|employment situation|\bces\b|payroll employment", chunk or "", re.I
        ):
            continue
        out.append(chunk)
    return out


def _year_adjacent_month(text: str, year: int, month: int) -> bool:
    if f"{year}-{month:02d}" in (text or ""):
        return True
    names = _MONTH_NAMES.get(month, [])
    for name in names:
        if re.search(rf"\b{re.escape(name)}\.?\s*,?\s*{year}\b|\b{year}\s+{re.escape(name)}\b", text or "", re.I):
            return True
    return False


def _months_in(text: str) -> set[int]:
    found: set[int] = set()
    for match in re.finditer(rf"\b({_MONTH_RE})\b", text or "", re.I):
        found.add(_MONTHS[match.group(1).lower().rstrip(".")])
    for match in re.finditer(r"(20\d{2})-(\d{2})-\d{2}", text or ""):
        found.add(int(match.group(2)))
    return found


def _has_realized_print(text: str) -> bool:
    return bool(re.search(r"[+\-−]\s*\d|\bfell\b|\bincreased\b|\bdeclined\b|\bdropped\b|\brose\b|\bgained\b", text or "", re.I))


def cite_bag_from_rows(rows: list[Any], *, spine: str, hit_urls: list[str]) -> CiteBag:
    excerpts: list[CiteExcerpt] = []
    for row in rows or []:
        url = getattr(row, "url", None) or ""
        title = (getattr(row, "title", None) or "").strip()
        for excerpt in list(getattr(row, "excerpts", None) or []):
            text = str(excerpt).strip()
            if text:
                excerpts.append(CiteExcerpt(url=url, title=title, text=text))
    return CiteBag(excerpts=excerpts, spine=spine or "", hit_urls=list(hit_urls or []))


def _series_of(finding: Finding) -> str | None:
    if finding.id in _LEFTOVER:
        return "leftover"
    title = (finding.title or "").lower()
    fid = (finding.id or "").lower()
    # Title/id first. Foundry claim windows are wide and repeat neighbor series.
    labeled = f"{fid} {title}"
    rules = (
        ("usrec", "USREC"),
        ("payroll", "BLS payrolls"),
        ("nonfarm", "BLS payrolls"),
        ("u-3", "U-3"),
        ("unemployment", "U-3"),
        ("gdp", "GDP"),
        ("sahm", "SAHMREALTIME"),
    )
    for key, series in rules:
        if key in labeled:
            return series
    if re.search(r"\bu3\b", labeled) or re.search(r"\blei\b", labeled):
        return "U-3" if "u3" in labeled else "LEI"
    blob = f"{labeled} {finding.claim}".lower()
    for key, series in rules:
        if key in blob:
            return series
    if re.search(r"\bu3\b", blob):
        return "U-3"
    if re.search(r"\blei\b", blob):
        return "LEI"
    return None


def _print_of(series: str, claim: str) -> str:
    text = claim or ""
    if series == "USREC":
        match = re.search(r"usrec\s*=\s*([01])|=\s*([01])\b", text, re.I)
        if match:
            return next(g for g in match.groups() if g is not None)
        match = re.search(r"\b([01])\b", text)
        return match.group(1) if match else ""
    if series == "BLS payrolls":
        match = re.search(r"[+\-−]\s*\d[\d,]*\s*k?\b|\b\d[\d,]*\s*k\b", text, re.I)
        return re.sub(r"\s+", "", match.group(0)) if match else ""
    if series in {"U-3", "LEI"}:
        match = re.search(r"[+\-−]?\d+(?:\.\d+)?\s*%", text)
        return match.group(0).replace(" ", "") if match else ""
    if series == "GDP":
        nums = re.findall(r"\d+\.\d+", text)
        return " / ".join(nums) if nums else ""
    if series == "SAHMREALTIME":
        match = re.search(r"[+\-−]\s*\d+\.\d+", text)
        return re.sub(r"\s+", "", match.group(0)) if match else ""
    return ""


def _when_of(finding: Finding) -> str:
    if (finding.when or "").strip():
        return finding.when.strip()
    blob = finding.claim or ""
    q = re.search(r"\b(Q[1-4])\s+(20\d{2})\b", blob, re.I)
    if q:
        return f"{q.group(1).upper()} {q.group(2)}"
    m = re.search(rf"\b({_MONTH_RE})\.?\s+(20\d{{2}})\b", blob, re.I)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    return ""


def claims_from_findings(findings: list[Finding]) -> list[Claim]:
    """Map minted findings → Claim. Not a second mint brain."""
    out: list[Claim] = []
    for finding in findings or []:
        if finding.stamp == "fringe" and finding.id not in _LEFTOVER:
            continue
        series = _series_of(finding)
        if not series:
            continue
        minted = (finding.print or "").strip()
        printed = minted if minted and minted != MISSING else _print_of(series, finding.claim)
        out.append(
            Claim(
                series=series,
                print=printed,
                when=_when_of(finding),
                id=finding.id,
                cite_url=finding.parallel_url or "",
                claim_span=(finding.claim or "")[:400],
            )
        )
    return out


def verify_print_in_cite(claim: Claim, bag: CiteBag) -> VerifyResult:
    if not _url_in(claim.cite_url, bag.hit_urls):
        return VerifyResult(ok=False, reason="cite_url not in hits")
    excerpt = _cite_text(claim, bag)
    search = f"{excerpt}\n{bag.spine or ''}"
    bars = _bars(claim.print)
    if bars and not all(_bar_in(bar, search) for bar in bars):
        return VerifyResult(ok=False, reason="print not in cite")
    if (claim.when or "").strip() and not _when_in_text(claim.when, f"{excerpt}\n{bag.spine or ''}"):
        return VerifyResult(ok=False, reason="when not in cite")
    return VerifyResult(ok=True, reason=None, matched_in=excerpt or bag.spine or None)


def verify_payrolls_realized_ces(claim: Claim, bag: CiteBag) -> VerifyResult:
    if claim.series != "BLS payrolls":
        return VerifyResult(ok=True, reason=None)
    bag_blob = _bag_text(bag)
    cite = _cite_text(claim, bag)
    window = f"{cite}\n{bag_blob}"
    if _NAICS_LEVEL.search(window) and not re.search(
        r"nonfarm payroll|employment situation|\bces\b", window, re.I
    ):
        return VerifyResult(ok=False, reason="naics employment level")
    if _NAICS_LEVEL.search(claim.claim_span or "") and not re.search(
        r"nonfarm payroll|employment situation|\bces\b", claim.claim_span or "", re.I
    ):
        return VerifyResult(ok=False, reason="naics employment level")
    parsed = _parse_when(claim.when)
    chunks = _ces_chunks(bag)
    realized: list[str] = []
    for chunk in chunks:
        if _bad_window(chunk) or not _has_realized_print(chunk):
            continue
        if parsed is None or parsed[0] != "month":
            realized.append(chunk)
            continue
        _, year, month = parsed
        months = _months_in(chunk)
        if months and month not in months:
            continue
        if _year_adjacent_month(chunk, year, month):
            realized.append(chunk)
            continue
        if not months and _year_adjacent_month(cite or _bag_text(bag), year, month):
            realized.append(chunk)
    if parsed and parsed[0] == "month":
        _, year, month = parsed
        supporting = "\n".join(realized) or "\n".join(c for c in chunks if not _bad_window(c))
        if realized and not _year_adjacent_month(supporting, year, month) and not _year_adjacent_month(cite, year, month):
            return VerifyResult(ok=False, reason="when year not on CES")
        if not realized:
            return VerifyResult(ok=False, reason="hypo/CI/revision window")
    if not realized:
        return VerifyResult(ok=False, reason="hypo/CI/revision window")
    window = "\n".join(realized)
    if _FALL.search(window) and not _norm(claim.print).lstrip().startswith("-"):
        return VerifyResult(ok=False, reason="fall print must be negative")
    return VerifyResult(ok=True, reason=None, matched_in=window)


def verify_usrec_smash(
    usrec_claim: Claim, payrolls_claim: Claim | None, bag: CiteBag
) -> VerifyResult:
    if payrolls_claim is None:
        return VerifyResult(ok=True, reason=None)
    u_when = _parse_when(usrec_claim.when)
    p_when = _parse_when(payrolls_claim.when)
    if u_when and p_when and (u_when[0], u_when[1], u_when[2]) != (p_when[0], p_when[1], p_when[2]):
        return VerifyResult(ok=False, reason="smash mixed months")
    if p_when and p_when[0] == "month":
        flag = _usrec_month_on_table(bag, p_when[1], p_when[2])
        if flag in (0, 1) and (
            u_when is None or (u_when[1], u_when[2]) != (p_when[1], p_when[2])
        ):
            return VerifyResult(ok=False, reason="smash mixed months")
        # ponytail: table miss does not mint July. Upgrade: require pipe 0/1 before smash READY.
    flag_when = u_when if u_when and u_when[0] == "month" else None
    if flag_when:
        flag = _usrec_month_on_table(bag, flag_when[1], flag_when[2])
        if flag in (0, 1) and usrec_claim.print:
            digit = _norm(usrec_claim.print).lstrip("+-")
            if digit not in {str(flag)}:
                return VerifyResult(ok=False, reason="print not in cite")
    if usrec_claim.print and not _legal_usrec_print(usrec_claim.print):
        return VerifyResult(ok=False, reason="print not in cite")
    return VerifyResult(ok=True, reason=None)


def verify_gdp_bars(claim: Claim, bag: CiteBag) -> VerifyResult:
    if claim.series != "GDP":
        return VerifyResult(ok=True, reason=None)
    from onecrew.foundry import _gdp_print_from_bars, gdp_quarter_bars

    blob = _strip_forecast(_bag_text(bag))
    dated = [(k, v) for k, v in gdp_quarter_bars(blob) if k[0]]
    parsed = _parse_when(claim.when)
    pair: list[tuple[tuple[int, int], str]] = []
    if dated:
        latest_year = dated[-1][0][0]
        year_run = [row for row in dated if row[0][0] == latest_year]
        if len(year_run) >= 2:
            pair = year_run[-2:]
    if pair:
        if parsed and parsed[0] == "quarter" and parsed[2] == 4 and pair[-1][0][1] != 4:
            return VerifyResult(ok=False, reason="q4 vs q1/q2")
        want = {_norm(b).lstrip("+-") for _k, b in pair}
        bars = {_norm(b).lstrip("+-") for b in _bars(claim.print)}
        if bars != want:
            return VerifyResult(ok=False, reason="gdp bars mismatch")
        y2, q2 = pair[-1][0]
        if parsed != ("quarter", y2, q2):
            return VerifyResult(ok=False, reason="gdp when mismatch")
        if str(y2) not in claim.id or f"q{q2}" not in claim.id.lower():
            return VerifyResult(ok=False, reason="gdp id mismatch")
        return VerifyResult(ok=True, reason=None, matched_in=blob)
    cited = _gdp_print_from_bars(gdp_quarter_bars(blob))
    bars = _bars(claim.print)
    if cited and "/" in cited:
        want = {_norm(b).lstrip("+-") for b in _bars(cited)}
        if {_norm(b).lstrip("+-") for b in bars} != want:
            return VerifyResult(ok=False, reason="gdp bars mismatch")
    if len(bars) > 1:
        extra = [b for b in bars if not _bar_in(b, blob)]
        if extra:
            return VerifyResult(ok=False, reason="gdp bars mismatch")
    return VerifyResult(ok=True, reason=None, matched_in=blob or None)


def verify_u3_ces(claim: Claim, bag: CiteBag) -> VerifyResult:
    if claim.series != "U-3":
        return VerifyResult(ok=True, reason=None)
    blob = _bag_text(bag)
    sents = re.split(r"(?<=[.!?])\s+", blob)
    unemp = [s for s in sents if _UNEMP.search(s) and not _SAHM.search(s)]
    if not unemp:
        if _SAHM.search(blob) and not _UNEMP.search(blob):
            return VerifyResult(ok=False, reason="sahm-trigger window")
        if _SAHM.search(blob) and not any(_UNEMP.search(s) and not _SAHM.search(s) for s in sents):
            return VerifyResult(ok=False, reason="sahm-trigger window")
        unemp = [s for s in sents if _UNEMP.search(s)]
        if unemp and all(_SAHM.search(s) for s in unemp):
            return VerifyResult(ok=False, reason="sahm-trigger window")
    parsed = _parse_when(claim.when)
    if parsed and parsed[0] == "month":
        if not any(_year_adjacent_month(s, parsed[1], parsed[2]) for s in unemp):
            return VerifyResult(ok=False, reason="u3 year absent from ces")
    elif parsed:
        year = str(parsed[1])
        if year and not any(year in s for s in unemp):
            return VerifyResult(ok=False, reason="u3 year absent from ces")
    return VerifyResult(ok=True, reason=None, matched_in=" ".join(unemp) or None)


def verify_claim_set(claims: list[Claim], bag: CiteBag) -> ClaimSetResult:
    results: list[VerifyResult] = []
    hold: list[str] = []
    by_series: dict[str, Claim] = {}
    seen: set[str] = set()
    for claim in claims:
        if claim.id in _LEFTOVER:
            hold.append("leftover timeline ids")
        if claim.series in CLOSED_SERIES:
            if claim.series in seen:
                hold.append("duplicate series")
            seen.add(claim.series)
            by_series[claim.series] = claim
            if not (claim.cite_url or "").strip():
                hold.append("grounded claim missing cite_url")
        elif claim.id not in _LEFTOVER:
            hold.append("unknown series")

    for claim in claims:
        if claim.id in _LEFTOVER:
            continue
        printed = verify_print_in_cite(claim, bag)
        results.append(printed)
        extra: VerifyResult | None = None
        if claim.series == "BLS payrolls":
            extra = verify_payrolls_realized_ces(claim, bag)
        elif claim.series == "USREC":
            extra = verify_usrec_smash(claim, by_series.get("BLS payrolls"), bag)
        elif claim.series == "GDP":
            extra = verify_gdp_bars(claim, bag)
        elif claim.series == "U-3":
            extra = verify_u3_ces(claim, bag)
        if extra is not None:
            results.append(extra)
    for row in results:
        if not row.ok and row.reason:
            hold.append(row.reason)
    # de-dupe hold reasons, keep order
    uniq: list[str] = []
    for reason in hold:
        if reason not in uniq:
            uniq.append(reason)
    return ClaimSetResult(ok=not uniq, results=results, hold_reasons=uniq)


def apply_verify_gate(receipt: Receipt, bag: CiteBag) -> Receipt:
    """READY only if verify_claim_set passes. HOLD keeps findings. Writer is the caller's job."""
    claims = claims_from_findings(list(receipt.findings or []))
    named = [c for c in claims if c.series in CLOSED_SERIES]
    leftover = [c for c in claims if c.id in _LEFTOVER]
    if not named and not leftover:
        return receipt
    checked = verify_claim_set(claims, bag)
    if checked.ok:
        return receipt
    reason = "; ".join(checked.hold_reasons) or "verify_claim_set failed"
    return receipt.model_copy(
        update={
            "disposition": "HOLD",
            "hold_reason": reason,
            "findings": list(receipt.findings),
        }
    )
