"""Deterministic critic tools. Agent prose cannot override ok: false."""

from __future__ import annotations

import re
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from onecrew.foundry import leftover_slot_ids, _url_fits_series, lei_threshold_claim, clean_cite_url
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
_SMASH_CLAIM = re.compile(r"smash(?:ed)?\s+into", re.I)


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


def _cite_candidates(claim: Claim, bag: CiteBag) -> list[str]:
    """Parallel hit URLs only. Prefer the host that fits this series."""
    seen: set[str] = set()
    out: list[str] = []
    for url in (*(e.url for e in bag.excerpts), *(bag.hit_urls or [])):
        raw = (url or "").strip()
        if not raw or not _url_in(raw, bag.hit_urls):
            continue
        key = _url_key(raw)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(raw)
    out.sort(key=lambda u: (0 if _url_fits_series(u, claim.series, ()) else 1))
    if claim.series == "LEI":
        return [u for u in out if _url_fits_series(u, claim.series, ())]
    return out


def resolve_missing_cite(claim: Claim, bag: CiteBag) -> Claim:
    """Foundry forgot the URL. Copy the Parallel hit that supports print/when."""
    if (claim.cite_url or "").strip():
        return claim
    for url in _cite_candidates(claim, bag):
        trial = claim.model_copy(update={"cite_url": url})
        if verify_print_in_cite(trial, bag).ok:
            return trial
    return claim


def relink_unsupported_cite(claim: Claim, bag: CiteBag) -> Claim:
    """Swap a stamped URL only when another Parallel hit excerpt carries print+when."""
    if not (claim.cite_url or "").strip():
        return resolve_missing_cite(claim, bag)
    if verify_print_in_cite(claim, bag).ok:
        return claim
    for url in _cite_candidates(claim, bag):
        trial = claim.model_copy(update={"cite_url": url})
        if verify_print_in_cite(trial, bag).ok:
            return trial
    return claim


def attach_cites_from_hits(findings: list[Finding], bag: CiteBag) -> list[Finding]:
    """Stamp parallel_url from a supporting Parallel hit. Do not invent a URL."""
    claims = [resolve_missing_cite(c, bag) for c in claims_from_findings(findings)]
    out: list[Finding] = []
    for finding in findings:
        cite = clean_cite_url(finding.parallel_url or "")
        if cite:
            if cite != (finding.parallel_url or "").strip():
                finding = finding.model_copy(update={"parallel_url": cite})
            out.append(finding)
            continue
        claim = next((c for c in claims if c.id == finding.id), None)
        url = clean_cite_url((claim.cite_url or "") if claim else "")
        if url:
            out.append(finding.model_copy(update={"parallel_url": url, "parallel_status": "hit"}))
            continue
        if finding.parallel_url and not cite:
            out.append(finding.model_copy(update={"parallel_url": None}))
            continue
        out.append(finding)
    return out


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
        if re.search(rf"(?:usrec\s*=\s*|[|=]\s*){unsigned}(?!\.\d)\b", nt):
            return True
        if re.search(
            rf"(?:usrec|recession indicator|recession observation).{{0,80}}"
            rf"(?:remains|is)\s+{unsigned}(?!\.\d)\b",
            nt,
        ):
            return True
        # CSV 2026-07-01,0 — comma-strip glues the cell; match the raw or stripped row.
        if re.search(rf"(20\d{{2}})-(\d{{2}})-\d{{2}}\s*[|,]?\s*{unsigned}\b", text or ""):
            return True
        return bool(re.search(rf"(20\d{{2}})-(\d{{2}})-\d{{2}}{unsigned}\b", nt))
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
    names = _MONTH_NAMES.get(month, [])
    for name in names:
        for hit in re.finditer(rf"\b{re.escape(name)}\.?\s+{year}\b", blob, re.I):
            after = blob[hit.end() : hit.end() + 16]
            cell = re.search(r"[=:]\s*(?:\|\s*)*([01])\b", after)
            if cell:
                return int(cell.group(1))
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


_CONSENSUS = re.compile(r"\bconsensus\b|economists?\s+expect|expected\s+to\b", re.I)


def _bad_window(text: str) -> bool:
    low = (text or "").lower()
    return (
        "suppose" in low
        or "confidence interval" in low
        or bool(_REV.search(low))
        or bool(_CONSENSUS.search(low))
    )


def _clean_ces_chunk(chunk: str) -> str:
    """Drop hypo/CI/revision sentences. Keep realized CES + header year in the same extract."""
    return " ".join(
        sent
        for sent in re.split(r"(?<=[.!?])\s+", chunk or "")
        if sent.strip() and not _bad_window(sent)
    )


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
    stamped = (finding.series or "").strip()
    if stamped in CLOSED_SERIES:
        return stamped
    title = (finding.title or "").lower()
    fid = (finding.id or "").lower()
    # Title/id before claim blob. Foundry claim windows are wide and repeat neighbor series.
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
    if not (claim.cite_url or "").strip():
        resolved = resolve_missing_cite(claim, bag)
        if (resolved.cite_url or "").strip() and resolved.cite_url != claim.cite_url:
            return verify_print_in_cite(resolved, bag)
        return VerifyResult(ok=False, reason="grounded claim missing cite_url")
    if not _url_in(claim.cite_url, bag.hit_urls):
        return VerifyResult(ok=False, reason="cite_url not in hits")
    if claim.series == "LEI" and not _url_fits_series(claim.cite_url, claim.series, ()):
        return VerifyResult(ok=False, reason="cite_url series mismatch")
    if claim.series == "LEI" and lei_threshold_claim(claim.claim_span, claim.print):
        return VerifyResult(ok=False, reason="print not in cite")
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
        work = _clean_ces_chunk(chunk)
        if not work or not _has_realized_print(work):
            continue
        if parsed is None or parsed[0] != "month":
            realized.append(work)
            continue
        _, year, month = parsed
        months = _months_in(work)
        if months and month not in months:
            continue
        if _year_adjacent_month(work, year, month):
            realized.append(work)
            continue
        if not months and _year_adjacent_month(cite or _bag_text(bag), year, month):
            realized.append(work)
    if parsed and parsed[0] == "month":
        _, year, month = parsed
        supporting = "\n".join(realized) or "\n".join(
            w for w in (_clean_ces_chunk(c) for c in chunks) if w
        )
        if realized and not _year_adjacent_month(supporting, year, month) and not _year_adjacent_month(cite, year, month):
            return VerifyResult(ok=False, reason="when year not on CES")
        if not realized:
            return VerifyResult(ok=False, reason="hypo/CI/revision window")
    if not realized:
        return VerifyResult(ok=False, reason="hypo/CI/revision window")
    window = "\n".join(realized)
    signed = claim.claim_span or window
    if parsed and parsed[0] == "month":
        _, year, month = parsed
        month_sents = [
            sent
            for chunk in realized
            for sent in re.split(r"(?<=[.!?])\s+", chunk)
            if _year_adjacent_month(sent, year, month) and _has_realized_print(sent)
        ]
        if month_sents:
            signed = " ".join(month_sents)
    if _FALL.search(signed) and not _norm(claim.print).lstrip().startswith("-"):
        return VerifyResult(ok=False, reason="fall print must be negative")
    return VerifyResult(ok=True, reason=None, matched_in=window)


def smash_claim_in(*parts: str) -> bool:
    return any(_SMASH_CLAIM.search(part or "") for part in parts)


def smash_mixed_months(
    usrec_when: str,
    payrolls_when: str,
    bag: CiteBag,
    *,
    spoken: str = "",
) -> bool:
    """True only when a smash is claimed or the pipe requires remap."""
    u_when = _parse_when(usrec_when)
    p_when = _parse_when(payrolls_when)
    if p_when and p_when[0] == "month":
        flag = _usrec_month_on_table(bag, p_when[1], p_when[2])
        if flag in (0, 1) and (
            u_when is None or (u_when[1], u_when[2]) != (p_when[1], p_when[2])
        ):
            return True
    if not (u_when and p_when):
        return False
    if (u_when[0], u_when[1], u_when[2]) == (p_when[0], p_when[1], p_when[2]):
        return False
    return smash_claim_in(spoken, bag.spine or "")


def verify_usrec_smash(
    usrec_claim: Claim, payrolls_claim: Claim | None, bag: CiteBag
) -> VerifyResult:
    if payrolls_claim is None:
        return VerifyResult(ok=True, reason=None)
    spoken = "\n".join(
        part for part in (usrec_claim.claim_span, payrolls_claim.claim_span) if part
    )
    if smash_mixed_months(usrec_claim.when, payrolls_claim.when, bag, spoken=spoken):
        return VerifyResult(ok=False, reason="smash mixed months")
    # ponytail: table miss does not mint a smash month. Upgrade: require pipe 0/1 before smash READY.
    u_when = _parse_when(usrec_claim.when)
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
    dated = [
        (k, v)
        for k, v in gdp_quarter_bars(blob)
        if k[0] and re.sub(r"[^\d.]", "", v) not in {"0.5", "0.50"}
    ]
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
    if cited:
        want = {_norm(b).lstrip("+-") for b in _bars(cited)}
        if {_norm(b).lstrip("+-") for b in bars} != want:
            return VerifyResult(ok=False, reason="gdp bars mismatch")
    elif bars:
        return VerifyResult(ok=False, reason="gdp bars mismatch")
    if len(bars) > 1:
        extra = [b for b in bars if not _bar_in(b, blob)]
        if extra:
            return VerifyResult(ok=False, reason="gdp bars mismatch")
    return VerifyResult(ok=True, reason=None, matched_in=blob or None)


_U3_HEDGE = re.compile(
    r"\bcould\b|\bforecast|\basked whether\b|\bprojects?\b|\boutlook\b|\bexpected\b",
    re.I,
)
_U3_NUM = r"\d+(?:\.\d+)?"
_CES_VINTAGE = re.compile(
    rf"EMPLOYMENT SITUATION\s*[—–\-]+\s*({_MONTH_RE})\.?\s+(20\d{{2}})"
    rf"|(?:nonfarm\s+)?payroll(?:s|\s+employment)\s+"
    rf"(?:rose|fell|increased|decreased|grew|dropped)\s+by\s+[\d,]+\s+"
    rf"in\s+({_MONTH_RE})\.?\s+(20\d{{2}})",
    re.I,
)
_U3_OBS = re.compile(
    rf"unemployment rate (?:was|is) ({_U3_NUM})(?:\s*%|\s*percent\b|%)"
    rf"(?:\s+in\s+({_MONTH_RE})\.?\s+(20\d{{2}}))?",
    re.I,
)


def _u3_hedge(text: str) -> bool:
    return bool(_U3_HEDGE.search(text or "")) or _bad_window(text or "")


def _u3_ces_excerpt_texts(bag: CiteBag) -> list[str]:
    out: list[str] = []
    for excerpt in bag.excerpts:
        chunk = excerpt.text or ""
        if not _CES.search(chunk):
            continue
        if _NAICS_LEVEL.search(chunk) and not re.search(
            r"nonfarm|employment situation|\bces\b|payroll employment", chunk, re.I
        ):
            continue
        out.append(chunk)
    return out


def _u3_lock_text(bag: CiteBag) -> str:
    """Realized CES unemployment + header. CES excerpts beat a mixed spine."""
    chunks = _u3_ces_excerpt_texts(bag) or _ces_chunks(bag)
    if not chunks:
        chunks = [e.text for e in bag.excerpts if (e.text or "").strip()]
    kept: list[str] = []
    for chunk in chunks:
        for sent in re.split(r"(?<=[.!?])\s+", chunk or ""):
            if not sent.strip() or _u3_hedge(sent):
                continue
            if _SAHM.search(sent) and _UNEMP.search(sent):
                continue
            if _UNEMP.search(sent) or _CES.search(sent):
                kept.append(sent)
    return " ".join(kept)


def _u3_num(printed: str) -> str | None:
    raw = re.sub(r"[^\d.]", "", (printed or "").replace("−", "-"))
    return raw or None


def _ces_vintage(text: str) -> tuple[int, int] | None:
    match = _CES_VINTAGE.search(text or "")
    if not match:
        return None
    if match.group(1):
        return (int(match.group(2)), _MONTHS[match.group(1).lower().rstrip(".")])
    return (int(match.group(4)), _MONTHS[match.group(3).lower().rstrip(".")])


def _when_month_key(when: str) -> tuple[int, int] | None:
    parsed = _parse_when(when)
    if parsed and parsed[0] == "month":
        return (parsed[1], parsed[2])
    return None


def _ces_u3_rows(text: str) -> list[tuple[tuple[int, int], str]]:
    """Unhedged CES U-3 (year, month, print) pairs. Vintage month wins when present."""
    vintage = _ces_vintage(text)
    rows: list[tuple[tuple[int, int], str]] = []
    for match in _U3_OBS.finditer(text or ""):
        if _u3_hedge(text[max(0, match.start() - 80) : match.end() + 40]):
            continue
        raw = match.group(1)
        if match.group(2):
            key = (int(match.group(3)), _MONTHS[match.group(2).lower().rstrip(".")])
        elif vintage:
            key = vintage
        else:
            continue
        rows.append((key, raw))
    if vintage:
        rows = [row for row in rows if row[0] == vintage]
    return rows


def verify_u3_ces(claim: Claim, bag: CiteBag) -> VerifyResult:
    """U-3 when+print must be one unhedged CES observation.

    Month and print are locked as a pair. A CES vintage (Employment Situation
    header or payrolls-in-month) admits only that month's rate. Topic-agnostic.
    """
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
    ces = _u3_lock_text(bag)
    rows = _ces_u3_rows(ces)
    want = _u3_num(claim.print)
    key = _when_month_key(claim.when)
    if not rows or want is None or key is None:
        return VerifyResult(ok=False, reason="u3 year absent from ces")
    for when_key, raw in rows:
        if when_key == key and raw == want:
            return VerifyResult(ok=True, reason=None, matched_in=ces)
    return VerifyResult(ok=False, reason="u3 year absent from ces")


def verify_claim_set(claims: list[Claim], bag: CiteBag) -> ClaimSetResult:
    results: list[VerifyResult] = []
    hold: list[str] = []
    by_series: dict[str, Claim] = {}
    seen: set[str] = set()
    claims = [resolve_missing_cite(c, bag) for c in claims]
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


_SOFT_CITE_REASONS = frozenset(
    {
        "grounded claim missing cite_url",
        "cite_url not in hits",
        "cite_url series mismatch",
        "print not in cite",
        "when not in cite",
    }
)


def apply_verify_gate(receipt: Receipt, bag: CiteBag) -> Receipt:
    """READY if hard verify passes. Print/when/missing cite are soft — the cite-repair loop handles them."""
    from onecrew.foundry import align_sahm_findings

    blob = "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])
    findings = align_sahm_findings(attach_cites_from_hits(list(receipt.findings or []), bag), blob)
    claims = claims_from_findings(findings)
    named = [c for c in claims if c.series in CLOSED_SERIES]
    leftover = [c for c in claims if c.id in _LEFTOVER]
    if not named and not leftover:
        return receipt if findings == list(receipt.findings or []) else receipt.model_copy(
            update={"findings": findings}
        )
    checked = verify_claim_set(claims, bag)
    hard = [r for r in checked.hold_reasons if r not in _SOFT_CITE_REASONS]
    if not hard:
        if findings == list(receipt.findings or []) and receipt.disposition != "HOLD":
            return receipt
        return receipt.model_copy(
            update={"disposition": "READY", "hold_reason": None, "findings": findings}
        )
    reason = "; ".join(hard) or "verify_claim_set failed"
    return receipt.model_copy(
        update={
            "disposition": "HOLD",
            "hold_reason": reason,
            "findings": findings,
        }
    )
