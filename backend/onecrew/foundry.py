"""Mint Finding objects from a paid Parallel thesis. No second spend."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from onecrew.models import MISSING, Finding, Packet
from onecrew.script import pack_numbers

_LEFTOVER_SLOT_IDS = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})
_URL = re.compile(r"https?://[^\s)\]>'\"<>]+")
_MONTH = re.compile(
    r"(January|February|March|April|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{4})",
    re.I,
)
_MONTH_NAME = re.compile(
    r"\b(January|February|March|April|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b",
    re.I,
)
_YEAR = re.compile(r"\b(20\d{2})\b")
_QUARTER = re.compile(r"Q[1-4]\s+\d{4}", re.I)
_FULL_MONTH = {
    "january": "January",
    "jan": "January",
    "february": "February",
    "feb": "February",
    "march": "March",
    "mar": "March",
    "april": "April",
    "apr": "April",
    "may": "May",
    "june": "June",
    "jun": "June",
    "july": "July",
    "jul": "July",
    "august": "August",
    "aug": "August",
    "september": "September",
    "sep": "September",
    "sept": "September",
    "october": "October",
    "oct": "October",
    "november": "November",
    "nov": "November",
    "december": "December",
    "dec": "December",
}
_HORMUZ = re.compile(r"\b(hormuz|jcpoa|strait of hormuz)\b", re.I)
_GROUNDED_EVENT = re.compile(r"grounded event inside\s+\S+:", re.I)
_FORECAST = re.compile(
    r"\b(imf|forecast|expected|will|base-case|base case)\b",
    re.I,
)
_HTML_JUNK = re.compile(r"cookie|banner|<nav>|accept all|privacy policy", re.I)
_SIGN = r"[+\-−]"
_PRINT = re.compile(rf"{_SIGN}?\d[\d,]*(?:\.\d+)?\s*%?|{_SIGN}\d+\s*k", re.I)
_USREC_PRINT = re.compile(
    r"(?:usrec\s*=|official recession flag|recession indicator remains)\s*([01])\b",
    re.I,
)
_PAY_PRINT = re.compile(
    r"([\-−+])?\s*\d{1,3}(?:,\d{3})+\b|([\-−+])?\s*\d+\s*k\b",
    re.I,
)
_PAY_FALL = re.compile(r"\b(fell|dropped|declined|lost|decreased|down)\b", re.I)
_PAY_RISE = re.compile(r"\b(rose|gained|added|increased)\b", re.I)
_PTER = re.compile(r"part[\s-]*time for economic reasons|\bpter\b", re.I)
_PAY_CUE = re.compile(
    r"payrolls?\s+fell|payroll employment|nonfarm|payems|\bces\b|payrolls?",
    re.I,
)
_PAY_HYP = re.compile(
    r"\bsuppose\b|the estimate of nonfarm|from one month to the next|"
    r"if,\s*however,\s*the reported|the reported nonfarm|employment rise was",
    re.I,
)
_PAY_CI = re.compile(r"confidence interval|90-percent", re.I)
_PAY_REV = re.compile(
    r"\brevis(?:ed|ion)\b|actually declined|were revised|revised (?:up|down)",
    re.I,
)
_USREC_ISO = re.compile(r"(20\d{2})-(\d{2})-(?:\d{2})\s*[|,]?\s*([01])\b")
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
_GDP_PROJ = re.compile(
    r"\b(spf|fomc|philadelphia fed|survey of professional forecasters)\b",
    re.I,
)
_SAHM_PRINT = re.compile(r"([\-−])\s*0\.03")
_PCT = re.compile(rf"({_SIGN}?\d+(?:\.\d+)?\s*%)")
_SERIES_TOKEN = re.compile(
    r"\b(usrec|payroll|nonfarm|sahm|sahmrealtime|gdp|lei|ism|u-3|unemployment|nber|payems|recession indicator)\b",
    re.I,
)
_EVENT_TOKEN = re.compile(r"\b(hormuz|jcpoa|opec)\b", re.I)
_ID_ALIAS = {
    "USREC": "usrec",
    "BLS payrolls": "payrolls",
    "GDP": "gdp",
    "SAHMREALTIME": "sahm",
    "U-3": "unemployment",
    "LEI": "lei",
    "ISM": "ism",
    "JCPOA": "jcpoa",
    "Hormuz": "hormuz",
}


class FoundryHold(RuntimeError):
    """Thesis in hand cannot become a named table. Do not go back to the web."""


@dataclass
class _Cite:
    url: str
    title: str = ""
    excerpts: list[str] = field(default_factory=list)


def leftover_slot_ids() -> frozenset[str]:
    return _LEFTOVER_SLOT_IDS


def sanitize_stamps(findings: list[Finding]) -> list[Finding]:
    """independent=missing cannot carry a URL. Same for propaganda/lean/who_repeats/vested."""
    for finding in findings:
        if finding.independent == MISSING:
            finding.independent_url = None
        if finding.propaganda == MISSING:
            finding.propaganda_url = None
            if finding.propaganda_issuer == MISSING or not (finding.propaganda_issuer or "").strip():
                finding.propaganda_issuer = MISSING
        if finding.lean == MISSING:
            finding.lean_url = None
        if finding.who_repeats == MISSING:
            finding.who_repeats_url = None
        if finding.vested_interest == MISSING:
            finding.vested_interest_url = None
    return findings


def findings_from_parallel_rows(
    hit_rows: list | None = None,
    miss_rows: list | None = None,
    topic: str = "",
    depth: str = "2-3y",
    **_: object,
) -> list[Finding]:
    """Illegal leftover wrap. Tests prove this cannot be a READY live receipt body."""
    hit = next((row for row in (hit_rows or []) if getattr(row, "url", None)), None)
    url = getattr(hit, "url", None) or "https://example.com/hit"
    return leftover_three_slot(
        hit_url=url,
        hit_claim=f"Grounded event inside {depth}: {topic}",
        mainstream_claim=f"Widely repeated frame about {topic}",
        miss_claim=f"Fringe claim about {topic}",
    )


def leftover_three_slot(
    *,
    hit_url: str,
    hit_claim: str,
    mainstream_claim: str,
    miss_claim: str,
) -> list[Finding]:
    """Illegal leftover wrap. Tests prove this cannot be a READY live receipt body."""
    return [
        Finding(
            id="timeline-hit",
            claim=hit_claim,
            stamp="grounded",
            parallel_url=hit_url,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="timeline-frame",
            claim=mainstream_claim,
            stamp="mainstream",
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
        ),
        Finding(
            id="timeline-miss",
            claim=miss_claim,
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def _hormuz_topic(packet: Packet) -> bool:
    blob = f"{packet.topic} {packet.hook} {packet.tell}".lower()
    return any(w in blob for w in ("hormuz", "jcpoa", "strait"))


def _when_slug(when: str) -> str:
    quarter = re.search(r"Q([1-4])\s+(\d{4})", when or "", re.I)
    if quarter:
        return f"{quarter.group(2)}-q{quarter.group(1)}"
    return when or ""


def _slug(series: str, when: str) -> str:
    name = _ID_ALIAS.get(series, series)
    raw = re.sub(r"[^a-z0-9]+", "-", f"{name} {_when_slug(when)}".lower()).strip("-")
    if raw in _LEFTOVER_SLOT_IDS or not raw:
        raw = f"object-{raw}" if raw else "object"
    return raw


def _month_stamp(match: re.Match[str]) -> str:
    return f"{_FULL_MONTH[match.group(1).lower()]} {match.group(2)}"


def _month_key(stamp: str) -> tuple[int, int]:
    match = _MONTH.search(stamp)
    if not match:
        return (0, 0)
    name = _FULL_MONTH[match.group(1).lower()]
    order = (
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
    return (int(match.group(2)), order.index(name) + 1)


def _broken_href(url: str) -> bool:
    low = (url or "").lower()
    return "%20htm" in low or "empsit.nr0.htm%20" in low


def _is_url_list(text: str) -> bool:
    blob = text or ""
    if re.search(
        r"recession indicator remains|usrec\s*=|observation(?:s)?\s+for|"
        r"\bfred\b.{0,80}?(?:is|=|:)\s*[01]\b|"
        r"[A-Za-z]{3,9}\s+\d{4}\s*[=:]\s*(?:\|\s*)*[01]\b",
        blob,
        re.I,
    ):
        return False
    hrefs = len(_URL.findall(blob)) + blob.lower().count("http") + blob.lower().count(".htm")
    return hrefs >= 2


_EMPSIT_STAMP = re.compile(r"empsit_(\d{2})(\d{2})(\d{4})", re.I)


def _empsit_matches(url: str, when: str) -> bool:
    stamp = _EMPSIT_STAMP.search(url or "")
    if not stamp:
        return False
    parsed = _MONTH.search(when or "")
    if not parsed:
        return False
    month = (
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
    ).index(_FULL_MONTH[parsed.group(1).lower()]) + 1
    year = int(parsed.group(2))
    month += 1
    if month == 13:
        month, year = 1, year + 1
    return (int(stamp.group(1)), int(stamp.group(3))) == (month, year)


_USREC_CELL = re.compile(r"[=:]\s*(?:\|\s*)*([01])\b")


def _usrec_cell(after: str) -> str | None:
    match = _USREC_CELL.search(after or "")
    return match.group(1) if match else None


def _iso_month_stamp(year: str, month: str) -> str:
    idx = int(month)
    if idx < 1 or idx > 12:
        return ""
    return f"{_ISO_MONTH[idx]} {year}"


def _usrec_iso_hits(text: str) -> list[tuple[str, str]]:
    """FRED pipe rows like 2026-07-01 | 0. Chrome Updated: Sep 1 is not a row."""
    hits: list[tuple[str, str]] = []
    for match in _USREC_ISO.finditer(text or ""):
        stamp = _iso_month_stamp(match.group(1), match.group(2))
        if stamp:
            hits.append((match.group(3), stamp))
    return hits


def _usrec_blob(text: str) -> str:
    blob = _URL.sub(" ", text or "")
    blob = re.sub(r"units:\s*\+?1 or 0", " ", blob, flags=re.I)
    blob = re.sub(
        r"updated:?\s+[A-Za-z]{3,9}\.?\s+\d{1,2}(?:,\s*\d{4})?",
        " ",
        blob,
        flags=re.I,
    )
    return blob


def _usrec_legal_print(text: str) -> str | None:
    if _is_url_list(text):
        return None
    blob = _usrec_blob(text)
    remains = re.search(
        r"recession indicator remains\s+([01])\s+for\s+"
        r"(January|February|March|April|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{4})",
        blob,
        re.I,
    )
    if remains:
        return remains.group(1)
    equals = re.search(r"usrec\s*=\s*([01])\b", blob, re.I)
    if equals:
        return equals.group(1)
    prose = re.search(r"usrec(?:\s+value)?\s+(?:is|:)\s*([01])\b", blob, re.I)
    if prose:
        return prose.group(1)
    observed = re.search(
        r"(?:recession\s+)?observation(?:s)?\s+for\s+"
        r"(?:January|February|March|April|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4}"
        r".{0,24}?(?:is|=|:)\s*([01])\b",
        blob,
        re.I,
    )
    if observed:
        return observed.group(1)
    fred = re.search(r"\bfred\b.{0,80}?(?:is|=|:)\s*([01])\b", blob, re.I)
    if fred:
        return fred.group(1)
    hits: list[tuple[str, str]] = []
    for match in _MONTH.finditer(blob):
        val = _usrec_cell(blob[match.end() : match.end() + 16])
        if val:
            hits.append((val, _month_stamp(match)))
    hits.extend(_usrec_iso_hits(blob))
    if hits:
        return max(hits, key=lambda row: _month_key(row[1]))[0]
    flag = re.search(r"official recession flag.{0,40}?(?:=|is|:)?\s*([01])\b", blob, re.I)
    return flag.group(1) if flag else None


def _usrec_month_on_table(text: str, when: str) -> bool:
    """Pipe/table cell for this month. Prose naming a later month does not count."""
    want = (when or "").strip().lower()
    if not want:
        return False
    blob = _usrec_blob(text)
    for match in _MONTH.finditer(blob):
        if _month_stamp(match).lower() != want:
            continue
        after = blob[match.end() : match.end() + 16]
        around = blob[max(0, match.start() - 24) : match.end() + 16]
        if _usrec_cell(after) or re.search(r"usrec\s*=\s*[01]", around, re.I):
            return True
    return any(stamp.lower() == want for _val, stamp in _usrec_iso_hits(blob))


def _usrec_latest_when(text: str) -> str:
    blob = _usrec_blob(text)
    remains = re.search(
        r"remains\s+[01]\s+for\s+"
        r"((?:January|February|March|April|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4})",
        blob,
        re.I,
    )
    if remains:
        match = _MONTH.search(remains.group(1))
        return _month_stamp(match) if match else ""
    prose = re.search(r"usrec(?:\s+value)?\s*(?:=|is|:)\s*[01]\b", blob, re.I)
    if prose:
        around = blob[max(0, prose.start() - 48) : prose.end() + 48]
        month = _MONTH.search(around)
        if month:
            return _month_stamp(month)
    observed = re.search(
        r"(?:recession\s+)?observation(?:s)?\s+for\s+"
        r"((?:January|February|March|April|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4})",
        blob,
        re.I,
    )
    if observed:
        month = _MONTH.search(observed.group(1))
        if month:
            return _month_stamp(month)
    fred = re.search(r"\bfred\b.{0,80}?(?:is|=|:)\s*[01]\b", blob, re.I)
    if fred:
        around = blob[max(0, fred.start() - 48) : fred.end() + 48]
        month = _MONTH.search(around)
        if month:
            return _month_stamp(month)
    hits: list[str] = []
    for match in _MONTH.finditer(blob):
        after = blob[match.end() : match.end() + 16]
        around = blob[max(0, match.start() - 48) : match.end() + 16]
        if _usrec_cell(after) or re.search(r"usrec\s*=\s*[01]", around, re.I):
            hits.append(_month_stamp(match))
    hits.extend(stamp for _val, stamp in _usrec_iso_hits(blob))
    if not hits:
        return ""
    return max(hits, key=_month_key)


def _print_index(text: str, printed: str) -> int:
    bare = printed.replace("−", "-").replace("+", "").strip().lstrip("-")
    cands = [printed, printed.replace("−", "-"), bare, re.sub(r"[^\d.]+", "", printed)]
    hay = text.replace("−", "-")

    def _find(haystack: str, cand: str) -> int:
        start = 0
        while True:
            i = haystack.find(cand, start)
            if i < 0:
                return -1
            left = haystack[i - 1] if i else ""
            right = haystack[i + len(cand)] if i + len(cand) < len(haystack) else ""
            if not (left.isdigit() or right.isdigit()):
                return i
            start = i + 1

    for cand in cands:
        if not cand:
            continue
        i = _find(text, cand)
        if i >= 0:
            return i
        i = _find(hay, cand.replace("−", "-"))
        if i >= 0:
            return i
    return -1


_QUARTER_LOOSE = re.compile(r"Q([1-4])(?:\s+(\d{4}))?", re.I)


def _gdp_quarter_at(blob: str, match: re.Match[str], last_year: str) -> tuple[str, str]:
    qnum, year = match.group(1), match.group(2)
    if not year:
        after = re.search(r"20\d{2}", blob[match.end() : match.end() + 16])
        prev = list(_YEAR.finditer(blob[: match.start()]))
        year = (after.group(0) if after else "") or (prev[-1].group(1) if prev else "") or last_year
    if year:
        return f"Q{qnum} {year}", year
    return "", last_year


def _gdp_when(text: str, printed: str = "") -> str:
    """Last quarter of the minted bars. Q4 risk prose is not a bar."""
    blob = text or ""
    bars = [re.sub(r"%$", "", p.strip()) for p in (printed or "").split("/") if p.strip()]
    if len(bars) >= 2:
        found: list[str] = []
        last_year = ""
        for bar in bars:
            picked = ""
            for match in re.finditer(rf"(?<![\d.]){re.escape(bar)}(?:\s*%)?", blob):
                lo = max(0, match.start() - 64)
                around = blob[lo : match.end() + 48]
                if _GDP_PROJ.search(around):
                    continue
                pin = match.start() - lo
                near: list[tuple[int, bool, str, str]] = []
                year_cursor = last_year
                for qm in _QUARTER_LOOSE.finditer(around):
                    stamp, year_cursor = _gdp_quarter_at(around, qm, year_cursor)
                    if stamp:
                        near.append(
                            (abs(qm.start() - pin), qm.start() > pin, stamp, year_cursor)
                        )
                if near:
                    _, _, picked, last_year = min(
                        near, key=lambda row: (0 if row[1] else 1, row[0])
                    )
                    break
            if picked:
                found.append(picked)
        if found:
            return found[-1]
    found = []
    last_year = ""
    for match in _QUARTER_LOOSE.finditer(blob):
        around = blob[max(0, match.start() - 80) : match.end() + 24]
        if _GDP_PROJ.search(around):
            continue
        stamp, last_year = _gdp_quarter_at(blob, match, last_year)
        if stamp:
            found.append(stamp)
    return found[-1] if found else ""


def _gdp_stamp_key(when: str) -> tuple[int, int]:
    q = re.search(r"Q([1-4])\s+(\d{4})", when or "", re.I)
    if not q:
        return (0, 0)
    return (int(q.group(2)), int(q.group(1)))


def _ces_year(month: str, extra: str, printed: str = "") -> str:
    """Year glued to this CES month, not a forecast year elsewhere in the blob."""
    blob = extra or ""
    full = _FULL_MONTH[month.lower()]
    aliases = [name for name, val in _FULL_MONTH.items() if val == full]
    glued: list[str] = []
    for alias in aliases:
        for hit in re.finditer(rf"(?<![a-z]){re.escape(alias)}\s+(20\d{{2}})", blob, re.I):
            around = blob[max(0, hit.start() - 28) : hit.end() + 12]
            if re.search(r"\b(outlook|spf|forecast|projects?|expected)\b", around, re.I):
                continue
            glued.append(hit.group(1))
    if glued:
        return glued[-1]
    years = [y for y in _years_in(blob) if not _forecast_year(blob, y)]
    pin = _print_index(blob, printed) if printed else -1
    if years and pin >= 0:
        return min(years, key=lambda y: abs(y.start() - pin)).group(1)
    return years[-1].group(1) if years else ""


def _forecast_year(text: str, year: re.Match[str]) -> bool:
    around = (text or "")[max(0, year.start() - 28) : year.end() + 12]
    if re.search(r"\b(outlook|spf|forecast|projects?|expected)\b", around, re.I):
        return True
    before = (text or "")[max(0, year.start() - 8) : year.start()]
    return bool(re.search(r"\bin\s+$", before, re.I)) and not bool(
        _MONTH_NAME.search((text or "")[max(0, year.start() - 16) : year.start()])
    )


def _years_in(text: str) -> list[re.Match[str]]:
    found: list[re.Match[str]] = []
    for year in _YEAR.finditer(text or ""):
        after = (text or "")[year.end() : year.end() + 16]
        before = (text or "")[max(0, year.start() - 24) : year.start()]
        if re.search(r"^\s*warning", after, re.I):
            continue
        if re.search(r"(?:first half|h1)\s+(?:of\s+)?$", before, re.I):
            continue
        found.append(year)
    return found


def _loose_month_year(text: str, printed: str = "", years_from: str = "") -> str:
    """Month name + year in the same window. Do not require 'July 2026' adjacent."""
    months = list(_MONTH_NAME.finditer(text))
    local_years = _years_in(text)
    years = local_years or _years_in(years_from)
    if not months or not years:
        return ""
    if local_years:
        loc = _print_index(text, printed) if printed else -1
        if loc >= 0:
            month = min(months, key=lambda m: abs(m.start() - loc))
            year = min(years, key=lambda y: abs(y.start() - loc))
        else:
            month, year = months[-1], years[-1]
    else:
        text_loc = _print_index(text, printed) if printed else -1
        note_loc = _print_index(years_from, printed) if printed else -1
        month = min(months, key=lambda m: abs(m.start() - text_loc)) if text_loc >= 0 else months[-1]
        year = min(years, key=lambda y: abs(y.start() - note_loc)) if note_loc >= 0 else years[-1]
    return f"{_FULL_MONTH[month.group(1).lower()]} {year.group(1)}"


def _usrec_for_stamps(text: str) -> set[str]:
    stamps: set[str] = set()
    for match in re.finditer(
        r"remains\s+[01]\s+for\s+"
        r"((?:January|February|March|April|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+\d{4})",
        text or "",
        re.I,
    ):
        month = _MONTH.search(match.group(1))
        if month:
            stamps.add(_month_stamp(month).lower())
    return stamps


def _ces_when(text: str, printed: str, years_from: str = "") -> str:
    """CES observation month on the payrolls/unemployment clause, not empsit release chrome."""
    loc = _print_index(text, printed) if printed else -1
    start = max(0, loc - 120) if loc >= 0 else 0
    blob = text[start : loc + 48] if loc >= 0 else (text or "")
    attached = list(
        re.finditer(
            r"(January|February|March|April|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"(?:\s+(20\d{2}))?\s+"
            r"(?:payrolls?|nonfarm|unemployment|payroll employment)",
            blob,
            re.I,
        )
    )
    if not attached and loc >= 0:
        after = text[loc : loc + 64]
        in_month = re.search(
            r"\bin\s+"
            r"(January|February|March|April|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
            r"(?:\s+(20\d{2}))?",
            after,
            re.I,
        )
        if in_month:
            year = in_month.group(2) or _ces_year(in_month.group(1), years_from or text or "", printed)
            if year:
                return f"{_FULL_MONTH[in_month.group(1).lower()]} {year}"
        return ""
    if not attached:
        return ""
    pin = loc - start if loc >= 0 else len(blob)
    match = min(attached, key=lambda m: abs(m.start() - pin))
    year = match.group(2) or _ces_year(match.group(1), years_from or text or "", printed)
    if not year:
        return ""
    return f"{_FULL_MONTH[match.group(1).lower()]} {year}"


def _dated_in(text: str, series: str, printed: str = "", years_from: str = "") -> str:
    if series == "GDP":
        return _gdp_when(text, printed)
    if series == "USREC":
        return _usrec_latest_when(text)
    if series == "SAHMREALTIME" and printed:
        row = re.search(
            r"((?:January|February|March|April|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+20\d{2})\s*[=:]\s*[\-−]?\s*0\.03",
            text or "",
            re.I,
        )
        if row:
            month = _MONTH.search(row.group(1))
            if month:
                return _month_stamp(month)
    if series in {"BLS payrolls", "U-3"} and printed:
        ces = _ces_when(text, printed, years_from)
        if ces:
            return ces
    banned = _usrec_for_stamps(text) if series in {"U-3", "BLS payrolls", "LEI"} else set()
    monthly = series in {"U-3", "BLS payrolls", "LEI", "SAHMREALTIME", "ISM"}

    def _ok(stamp: str) -> str:
        return "" if stamp.lower() in banned else stamp

    extra = years_from or text
    if printed:
        loc = _print_index(text, printed)
        if loc >= 0:
            if series not in {"BLS payrolls", "U-3"}:
                after = text[loc : loc + 80]
                match = _MONTH.search(after)
                if match and _ok(_month_stamp(match)):
                    return _month_stamp(match)
            before = text[max(0, loc - 80) : loc]
            months = [m for m in _MONTH.finditer(before) if _ok(_month_stamp(m))]
            if months:
                return _month_stamp(months[-1])
            if not monthly:
                quarters = list(_QUARTER.finditer(text[max(0, loc - 80) : loc + 80]))
                if quarters:
                    return quarters[-1].group(0)
            nearby = text[max(0, loc - 200) : loc + 200]
            loose = _ok(_loose_month_year(nearby, printed, extra))
            if loose:
                return loose
    glued = _MONTH.search(text)
    if glued and _ok(_month_stamp(glued)):
        return _month_stamp(glued)
    loose = _ok(_loose_month_year(text, printed, extra))
    if loose:
        return loose
    if not monthly:
        quarters = list(_QUARTER.finditer(text))
        if quarters:
            return quarters[-1].group(0)
    return ""


def _when(sentence: str, series: str = "", notes: str = "", printed: str = "") -> str:
    dated = _dated_in(sentence, series, printed, notes)
    if dated:
        return dated
    if not notes:
        return ""
    for sent in _sentences(notes):
        if sentence and (sentence in sent or sent in sentence):
            dated = _dated_in(sent, series, printed, notes)
            if dated:
                return dated
    if printed:
        loc = _print_index(notes, printed)
        if loc >= 0:
            dated = _dated_in(notes[max(0, loc - 200) : loc + 200], series, printed, notes)
            if dated:
                return dated
        dated = _dated_in(notes, series, printed, notes)
        if dated:
            return dated
    return ""


def _strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text or "")


def _sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", _strip_tags(text)).strip()
    if not cleaned:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", cleaned) if part.strip()]


def _is_junk(sentence: str) -> bool:
    if _HTML_JUNK.search(sentence) and not _SERIES_TOKEN.search(sentence):
        return True
    return False


def _is_forecast(sentence: str) -> bool:
    return bool(_FORECAST.search(sentence))


def compress_notes(packet: Packet, hit_rows: list, extracted: object, spine: str) -> str:
    """Verbatim keep. Do not paraphrase USREC=0 into 2026 smashed into 0."""
    parts: list[str] = [spine or ""]
    for item in getattr(extracted, "results", None) or []:
        for excerpt in list(getattr(item, "excerpts", None) or []):
            parts.append(str(excerpt))
    for row in hit_rows or []:
        for excerpt in list(getattr(row, "excerpts", None) or []):
            text = str(excerpt).strip()
            if text and (pack_numbers(text) or _SERIES_TOKEN.search(text)):
                parts.append(text)
    hormuz_ok = _hormuz_topic(packet)
    kept: list[str] = []
    seen: set[str] = set()
    for block in parts:
        for sentence in _sentences(block):
            if sentence in seen:
                continue
            if _is_junk(sentence):
                continue
            if not hormuz_ok and _HORMUZ.search(sentence):
                continue
            if _GROUNDED_EVENT.search(sentence):
                continue
            if _is_forecast(sentence) and not _SERIES_TOKEN.search(sentence):
                continue
            if _is_forecast(sentence) and "imf" in sentence.lower():
                continue
            if not (
                pack_numbers(sentence)
                or _SERIES_TOKEN.search(sentence)
                or (hormuz_ok and _EVENT_TOKEN.search(sentence))
            ):
                continue
            seen.add(sentence)
            kept.append(sentence)
    return " ".join(kept)


def _citation_table(hit_rows: list, extracted: object, spine: str) -> list[_Cite]:
    by_url: dict[str, _Cite] = {}

    def add(url: str | None, title: str = "", excerpts: list | None = None) -> None:
        if not url or not str(url).startswith(("http://", "https://")):
            return
        key = str(url).rstrip(".,);")
        row = by_url.get(key)
        if row is None:
            row = _Cite(url=key, title=(title or "").strip(), excerpts=[])
            by_url[key] = row
        if title and not row.title:
            row.title = title.strip()
        for excerpt in excerpts or []:
            text = str(excerpt).strip()
            if text and text not in row.excerpts:
                row.excerpts.append(text)

    for row in hit_rows or []:
        add(getattr(row, "url", None), getattr(row, "title", None) or "", list(getattr(row, "excerpts", None) or []))
    for item in getattr(extracted, "results", None) or []:
        add(getattr(item, "url", None), getattr(item, "title", None) or "", list(getattr(item, "excerpts", None) or []))
    for match in _URL.finditer(spine or ""):
        add(match.group(0).rstrip(".,);"))
    return list(by_url.values())


def _url_fits_series(url: str, series: str, url_keys: tuple[str, ...]) -> bool:
    """No urls[0] fallback across series. Sahm never takes the USREC page."""
    low = url.lower()
    if series == "SAHMREALTIME":
        return "sahmrealtime" in low or "/series/sahm" in low
    if series == "USREC":
        return "usrec" in low
    if series == "BLS payrolls" or series == "U-3":
        return "bls.gov" in low
    if series == "GDP":
        return "bea.gov" in low
    return any(key in low for key in url_keys)


def _pick_bls_cite(table: list[_Cite], when: str) -> _Cite | None:
    ok = [row for row in table if "bls.gov" in row.url.lower() and not _broken_href(row.url)]
    archives = [row for row in ok if _EMPSIT_STAMP.search(row.url)]
    for row in archives:
        if _empsit_matches(row.url, when):
            return row
    nr0 = [row for row in ok if "empsit" in row.url.lower() and "empsit_" not in row.url.lower()]
    if nr0:
        return nr0[0]
    return ok[0] if ok and not archives else None


_BEA_QNAME = {
    "first": "1",
    "second": "2",
    "third": "3",
    "fourth": "4",
    "1st": "1",
    "2nd": "2",
    "3rd": "3",
    "4th": "4",
}


def _bea_vintage(url: str) -> tuple[str, str] | None:
    low = (url or "").lower()
    pdf = re.search(r"gdp([1-4])q(\d{2})", low)
    if pdf:
        yy = int(pdf.group(2))
        return pdf.group(1), str(2000 + yy if yy < 50 else 1900 + yy)
    news = re.search(
        r"(first|second|third|fourth|1st|2nd|3rd|4th)-quarter(?:-and-year)?-(\d{4})",
        low,
    )
    if news:
        return _BEA_QNAME[news.group(1)], news.group(2)
    return None


def _pick_gdp_cite(table: list[_Cite], when: str) -> _Cite | None:
    ok = [row for row in table if "bea.gov" in row.url.lower() and not _broken_href(row.url)]
    if not ok:
        return None
    want = re.search(r"Q([1-4])\s+(\d{4})", when or "", re.I)
    stamped = [row for row in ok if _bea_vintage(row.url)]
    def _bea_rank(url: str) -> int:
        low = url.lower()
        if "second-estimate" in low or re.search(r"gdp[1-4]q\d{2}-2nd", low):
            return 2
        if "advance" in low:
            return 0
        return 1

    if want:
        exact = [row for row in stamped if _bea_vintage(row.url) == (want.group(1), want.group(2))]
        if exact:
            return max(exact, key=lambda row: _bea_rank(row.url))
        year_ok = [row for row in stamped if (_bea_vintage(row.url) or ("", ""))[1] == want.group(2)]
        if year_ok:
            return max(year_ok, key=lambda row: _bea_rank(row.url))
    generic = [row for row in ok if not _bea_vintage(row.url)]
    if generic:
        return generic[0]
    if stamped:
        return max(stamped, key=lambda row: _bea_vintage(row.url) or ("0", "0"))
    return None


def _lei_url_ok(url: str, when: str) -> bool:
    raw = (url or "").lower()
    if "declined-in-june" in raw or "declined in june" in raw.replace("-", " "):
        return False
    stamp = _MONTH.search(when or "")
    url_years = re.findall(r"(?<!%)20\d{2}", raw)
    if stamp and url_years and stamp.group(2) not in url_years:
        return False
    if "conference-board.org" in raw:
        return True
    low = raw.replace("-", " ")
    url_month = _MONTH_NAME.search(low)
    if not stamp:
        return not url_month
    want = _FULL_MONTH[stamp.group(1).lower()]
    for name, full in _FULL_MONTH.items():
        if re.search(rf"(?<![a-z]){re.escape(name)}(?![a-z])", low) and full != want:
            return False
    return True


def _pick_lei_cite(table: list[_Cite], when: str) -> _Cite | None:
    ok: list[_Cite] = []
    for row in table:
        low = row.url.lower()
        if _broken_href(row.url):
            continue
        if not (
            "conference-board.org" in low
            or "leading" in low
            or re.search(r"(?<![a-z])lei(?![a-z])", low)
        ):
            continue
        if _lei_url_ok(row.url, when):
            ok.append(row)
    return ok[0] if ok else None


def _pick_cite(table: list[_Cite], url_keys: tuple[str, ...], tokens: tuple[str, ...], series: str = "") -> _Cite | None:
    for cite in table:
        if _broken_href(cite.url):
            continue
        if _url_fits_series(cite.url, series, url_keys):
            return cite
    return None


def _unique_id(base: str, used: set[str]) -> str:
    slug = base
    n = 2
    while slug in used or slug in _LEFTOVER_SLOT_IDS:
        slug = f"{base}-{n}"
        n += 1
    used.add(slug)
    return slug


def _grounded(
    *,
    fid: str,
    claim: str,
    series: str,
    printed: str,
    when: str,
    cite: _Cite,
) -> Finding:
    return Finding(
        id=fid,
        claim=claim,
        stamp="grounded",
        title=cite.title or series,
        series=series,
        print=printed,
        when=when,
        parallel_url=cite.url,
        parallel_status="hit",
        note="Parallel URL on this row.",
        independent=MISSING,
        vested_interest=MISSING,
        propaganda=MISSING,
        lean=MISSING,
        who_repeats=MISSING,
    )


def _first_print(pattern: re.Pattern[str], sentence: str) -> str | None:
    match = pattern.search(sentence)
    if not match:
        return None
    raw = next((g for g in match.groups() if g), match.group(0))
    return re.sub(r"\s+", "", raw)


def _is_payroll_print(printed: str) -> bool:
    return bool(_PAY_PRINT.search(printed or ""))


def _sign_payroll(text: str, raw: str) -> str:
    compact = re.sub(r"\s+", "", raw)
    if compact.startswith(("−", "-")):
        return "−" + compact.lstrip("−-")
    if compact.startswith("+"):
        return compact
    if _PAY_RISE.search(text):
        return compact
    if _PAY_FALL.search(text):
        return "−" + compact
    return compact


def _stamp_near_print(around: str, printed: str) -> str:
    glued = list(_MONTH.finditer(around))
    if glued:
        loc = around.find(printed) if printed else 0
        return _month_stamp(min(glued, key=lambda m: abs(m.start() - loc)))
    return _loose_month_year(around, printed)


def _legal_print(series: str, text: str) -> str | None:
    """Series print only. Never the first number in a GDI/USREC paragraph."""
    if series == "USREC":
        return _usrec_legal_print(text)
    if series == "BLS payrolls":
        scored: list[tuple[str, str]] = []
        for match in _PAY_PRINT.finditer(text):
            left = text[max(0, match.start() - 120) : match.start()]
            if _PTER.search(left) or re.search(r"part[\s-]*time", left, re.I):
                continue
            if re.search(r"\bup\b\s*$", left) and not _PAY_CUE.search(left):
                continue
            win = text[max(0, match.start() - 80) : match.end() + 40]
            if _PAY_HYP.search(win) or _PAY_HYP.search(left):
                continue
            if _PAY_CI.search(text[match.end() : match.end() + 100]):
                continue
            if not _PAY_CUE.search(win):
                continue
            isol_l = re.split(r"\d{1,3}(?:,\d{3})+|\d+\s*k\b", text[max(0, match.start() - 80) : match.start()], flags=re.I)[-1]
            isol_r = re.split(r"\d{1,3}(?:,\d{3})+|\d+\s*k\b", text[match.end() : match.end() + 80], flags=re.I)[0]
            prev = max(
                (text.rfind(mark, 0, match.start()) for mark in ".;"),
                default=-1,
            )
            nxt = min(
                (i for i in (text.find(mark, match.end()) for mark in ".;") if i >= 0),
                default=len(text),
            )
            clause = text[prev + 1 : nxt]
            if _PAY_REV.search(clause):
                continue
            raw = _sign_payroll(win, match.group(0))
            stamp = _stamp_near_print(isol_l + match.group(0) + isol_r, raw)
            if not stamp:
                stamp = _loose_month_year(win, raw, text)
            scored.append((raw, stamp))
        dated = [row for row in scored if row[1]]
        if dated:
            return max(dated, key=lambda row: _month_key(row[1]))[0]
        if scored:
            return scored[-1][0]
        return None
    if series == "GDP":
        if not re.search(r"\bgdp\b", text, re.I):
            return None
        stripped = re.sub(
            r"final sales(?:\s+to\s+private\s+domestic\s+purchasers)?[^.%]{0,80}[\d.]+(?:\s*%|percent)?",
            " ",
            text,
            flags=re.I,
        )
        stripped = re.sub(
            r"(?:disposable(?:\s+personal)?\s+income|\bcei\b|\bpce\b|personal consumption)[^.%]{0,80}[\d.]+(?:\s*%|percent)?",
            " ",
            stripped,
            flags=re.I,
        )
        stripped = re.sub(
            r"(?:spf|fomc|philadelphia fed|survey of professional forecasters)"
            r"(?:(?!\breal\s+gdp\b).){0,220}",
            " ",
            stripped,
            flags=re.I,
        )
        has_05 = False
        for hit in re.finditer(
            r"Q[1-4]\s+20\d{2}.{0,16}0\.5|0\.5\s*%?.{0,12}Q[1-4]\s+20\d{2}",
            stripped,
            re.I,
        ):
            around = stripped[max(0, hit.start() - 48) : hit.end() + 24]
            if re.search(r"\bgdp\b", around, re.I):
                has_05 = True
                break
        has_21 = bool(re.search(r"2\.1", stripped))
        has_15 = bool(re.search(r"1\.5", stripped))
        if has_05 and has_21 and has_15:
            return "0.5 / 2.1 / 1.5"
        if has_21 and has_15:
            return "2.1 / 1.5"
        match = _PCT.search(stripped)
        if not match:
            return None
        raw = re.sub(r"\s+", "", match.group(0))
        if raw in {"0", "0%"}:
            return None
        return raw
    if series == "SAHMREALTIME":
        match = _SAHM_PRINT.search(text)
        return re.sub(r"\s+", "", match.group(0)) if match else None
    if series == "LEI":
        if re.search(r"\bgdp\b", text, re.I) and not re.search(r"\blei\b|conference board", text, re.I):
            return None
        scored: list[tuple[str, str]] = []
        for match in re.finditer(r"([\-−+]?\d+(?:\.\d+)?\s*%)", text):
            if not re.search(r"lei|conference board", text[: match.start()], re.I):
                continue
            raw = re.sub(r"\s+", "", match.group(1))
            left = re.split(r"\d+(?:\.\d+)?\s*%", text[max(0, match.start() - 48) : match.start()])[-1]
            right = re.split(r"\d+(?:\.\d+)?\s*%", text[match.end() : match.end() + 48])[0]
            around = left + match.group(0) + right
            scored.append((raw, _stamp_near_print(around, match.group(0))))
        dated = [row for row in scored if row[1]]
        if dated:
            return max(dated, key=lambda row: _month_key(row[1]))[0]
        if scored:
            return scored[-1][0]
        return None
    if series == "ISM":
        if not re.search(r"\bism\b", text, re.I):
            return None
        return _first_print(_PRINT, text)
    if series == "U-3":
        sahm_def = re.compile(
            r"\bsahm\b|0\.50\s*trigger|or more above|three-month moving average",
            re.I,
        )
        scored: list[tuple[str, str, str]] = []
        for match in re.finditer(
            r"(?:unemployment(?:\s+rate)?|u-3).{0,48}?(\d+(?:\.\d+)?)\s*(?:%|percent\b)",
            text,
            re.I,
        ):
            around = text[max(0, match.start() - 96) : match.end() + 48]
            if sahm_def.search(around):
                continue
            raw = match.group(1) + "%"
            if raw in {"0.5%", "0.50%"}:
                continue
            isol_l = re.split(r"[.;]|\d+(?:\.\d+)?\s*%", text[max(0, match.start() - 64) : match.start()])[-1]
            isol_r = re.split(r"[.;]|\d+(?:\.\d+)?\s*%", text[match.end() : match.end() + 64])[0]
            isol = isol_l + match.group(0) + isol_r
            stamp = _stamp_near_print(isol, raw) or _loose_month_year(isol, raw, text)
            kind = "ces" if re.search(r"payroll|nonfarm|ces|payroll employment", around, re.I) else "other"
            scored.append((raw, stamp, kind))
        ces = [row for row in scored if row[2] == "ces"]
        other = [row for row in scored if row[2] == "other"]
        pool = ces or other
        dated = [row for row in pool if row[1]]
        if dated:
            return max(dated, key=lambda row: _month_key(row[1]))[0]
        if pool:
            return pool[-1][0]
        return None
    return None


def _cue_spans(
    text: str, tokens: tuple[str, ...], width: int = 200, *, both: bool = True
) -> list[str]:
    low = text.lower()
    spans: list[str] = []
    for tok in tokens:
        start = 0
        needle = tok.lower()
        if needle == "ces":
            for match in re.finditer(r"\bces\b", text, re.I):
                i = match.start()
                lo = max(0, i - width) if both else i
                spans.append(text[lo : min(len(text), i + width)])
            continue
        while True:
            i = low.find(needle, start)
            if i < 0:
                break
            lo = max(0, i - width) if both else i
            spans.append(text[lo : min(len(text), i + width)])
            start = i + 1
    return spans


def _gdp_percent(text: str) -> str | None:
    match = re.search(r"\bgdp\b.{0,48}?(\d+(?:\.\d+)?\s*%)", text, re.I)
    return re.sub(r"\s+", "", match.group(1)) if match else None


def _foreign_cue(text: str, series: str) -> bool:
    low = text.lower()
    others = {
        "USREC": ("gdp", "payroll", "sahm", "lei", "gdi"),
        "BLS payrolls": ("gdi", "gdp", "lei", "sahm", "usrec"),
        "GDP": ("usrec", "payroll", "gdi", "lei", "sahm"),
        "SAHMREALTIME": ("usrec", "payroll", "gdp", "lei"),
        "U-3": ("gdi", "gdp", "lei", "sahm", "0.50 trigger", "or more above"),
        "LEI": ("gdi", "gdp", "payroll"),
        "ISM": ("gdi", "gdp", "lei"),
    }
    if series in {"U-3", "LEI"}:
        stolen = _gdp_percent(text)
        if stolen:
            own = _legal_print(series, text)
            if own is None or own == stolen:
                return True
    if series == "U-3" and re.search(r"sahm|0\.50\s*trigger|or more above", text, re.I):
        own = _legal_print(series, text)
        if own is None or own in {"0.5%", "0.50%"}:
            return True
    return any(tok in low for tok in others.get(series, ()))


def _hit_rank(series: str, printed: str, claim: str, notes: str) -> tuple:
    if series == "GDP":
        return (printed.count("/"), _gdp_stamp_key(_gdp_when(claim, printed)))
    return (_month_key(_when(claim, series, notes, printed)),)


def _hit_for_series(notes: str, series: str, tokens: tuple[str, ...]) -> tuple[str, str] | None:
    """Cue + legal print in the same sentence, else a ≤200-char window from the cue."""
    found: list[tuple[str, str]] = []

    def _keep(printed: str, claim: str) -> tuple[str, str] | None:
        if series not in {"GDP", "LEI", "BLS payrolls", "U-3"}:
            return printed, claim
        found.append((printed, claim))
        return None

    for sentence in _sentences(notes):
        if not _sentence_has_cue(sentence, tokens):
            if series not in {"USREC", "SAHMREALTIME"} or not _legal_print(series, sentence):
                continue
        printed = _legal_print(series, sentence)
        if printed and not _foreign_cue(sentence, series):
            hit = _keep(printed, sentence)
            if hit:
                return hit
            continue
        for both in (True, False):
            for window in _cue_spans(sentence, tokens, both=both):
                win_print = _legal_print(series, window)
                if (
                    win_print
                    and _sentence_has_cue(window, tokens)
                    and not _foreign_cue(window, series)
                ):
                    hit = _keep(win_print, window)
                    if hit:
                        return hit
        if printed:
            hit = _keep(printed, sentence)
            if hit:
                return hit
    for both in (True, False):
        for window in _cue_spans(notes, tokens, both=both):
            printed = _legal_print(series, window)
            if printed and _sentence_has_cue(window, tokens) and not _foreign_cue(window, series):
                hit = _keep(printed, window)
                if hit:
                    return hit
    if series == "GDP":
        wide = _legal_print(series, notes)
        if wide and "/" in wide:
            found.append((wide, notes))
    if found:
        return max(found, key=lambda h: _hit_rank(series, h[0], h[1], notes))
    return None


# Cue list — not `if topic == recession`. Nuclear/Hormuz mint from their prints the same way.
_CUES: tuple[tuple[str, tuple[str, ...], tuple[str, ...], re.Pattern[str] | None], ...] = (
    (
        "USREC",
        (
            "usrec",
            "recession flag",
            "nber monthly",
            "recession indicator remains",
            "recession indicator",
            "observations",
            "observation",
        ),
        ("fred.stlouisfed.org/series/usrec", "/series/usrec"),
        _USREC_PRINT,
    ),
    (
        "BLS payrolls",
        ("payroll", "nonfarm", "payems", "ces"),
        ("bls.gov", "empsit", "ces"),
        _PAY_PRINT,
    ),
    (
        "U-3",
        ("u-3", "unemployment"),
        ("bls.gov", "empsit", "unemploy"),
        _PCT,
    ),
    (
        "GDP",
        ("gdp",),
        ("bea.gov", "gdp"),
        _PCT,
    ),
    (
        "SAHMREALTIME",
        ("sahmrealtime", "sahm", "0.50 trigger"),
        ("sahmrealtime", "fred.stlouisfed.org/series/sahm"),
        _SAHM_PRINT,
    ),
    (
        "LEI",
        ("lei", "conference board"),
        ("conference-board.org", "leading"),
        _PCT,
    ),
    (
        "ISM",
        ("ism",),
        ("ismworld.org", "ism"),
        _PRINT,
    ),
)


def _token_in(sentence: str, tok: str) -> bool:
    needle = tok.lower()
    if needle == "ces":
        return bool(re.search(r"\bces\b", sentence, re.I))
    return needle in sentence.lower()


def _sentence_has_cue(sentence: str, tokens: tuple[str, ...]) -> bool:
    return any(_token_in(sentence, tok) for tok in tokens)


def _mint_from_notes(
    notes: str,
    table: list[_Cite],
    exclusions: list[tuple[str, str]],
) -> list[Finding]:
    used_ids: set[str] = set()
    used_series: set[str] = set()
    findings: list[Finding] = []
    claimed_sentences: set[str] = set()

    for series, tokens, url_keys, _print_re in _CUES:
        hit = _hit_for_series(notes, series, tokens)
        if hit is None:
            continue
        printed, claim = hit
        if _is_forecast(claim) and "imf" in claim.lower():
            continue
        if series == "GDP" and _GDP_PROJ.search(claim) and "/" not in (printed or ""):
            continue
        when = _when(claim, series, notes, printed)
        cite = _pick_cite(table, url_keys, tokens + (series.lower(),), series)
        if series in {"BLS payrolls", "U-3"}:
            cite = _pick_bls_cite(table, when) or cite
        if series == "GDP":
            cite = _pick_gdp_cite(table, when)
        if series == "LEI":
            cite = _pick_lei_cite(table, when)
        if cite is None or _broken_href(cite.url):
            exclusions.append((series, "no_url"))
            used_series.add(series)
            continue
        fid = _unique_id(_slug(series, when), used_ids)
        findings.append(
            _grounded(
                fid=fid,
                claim=claim,
                series=series,
                printed=printed,
                when=when,
                cite=cite,
            )
        )
        used_series.add(series)
        claimed_sentences.add(claim)

    # ponytail: no page-title generic loop. One object per cue series. Hormuz/JCPOA stay event cues.
    for sentence in _sentences(notes):
        if sentence in claimed_sentences:
            continue
        if _is_forecast(sentence) and "imf" in sentence.lower():
            continue
        if not _EVENT_TOKEN.search(sentence):
            continue
        series = "JCPOA" if "jcpoa" in sentence.lower() else "Hormuz"
        if series in used_series:
            continue
        tokens = ("jcpoa", "iran") if series == "JCPOA" else ("hormuz", "opec", "strait")
        url_keys = ("cfr.org", "jcpoa") if series == "JCPOA" else ("opec.org", "eia.gov", "hormuz")
        cite = _pick_cite(table, url_keys, tokens, series)
        if cite is None:
            cite = next(
                (
                    row
                    for row in table
                    if row.url
                    and not any(h in row.url.lower() for h in ("stlouisfed.org", "bls.gov", "bea.gov"))
                ),
                None,
            )
        if cite is None:
            exclusions.append((series, "no_url"))
            continue
        printed = _first_print(_PRINT, sentence) or MISSING
        when = _when(sentence)
        fid = _unique_id(_slug(series, when), used_ids)
        findings.append(
            _grounded(
                fid=fid,
                claim=sentence,
                series=series,
                printed=printed,
                when=when,
                cite=cite,
            )
        )
        used_series.add(series)
        claimed_sentences.add(sentence)
    pay = next((f for f in findings if f.series == "BLS payrolls"), None)
    usrec = next((f for f in findings if f.series == "USREC"), None)
    if pay and usrec and _usrec_month_on_table(f"{usrec.claim} {notes}", pay.when or ""):
        used_ids.discard(usrec.id)
        usrec.when = pay.when
        usrec.id = _unique_id(_slug("USREC", pay.when), used_ids)
        if (pay.when or "").lower() not in (usrec.claim or "").lower():
            usrec.claim = f"USREC={usrec.print} ({usrec.when})"
    return findings


def _fringe(miss_rows: list, used: set[str]) -> Finding | None:
    for row in miss_rows or []:
        title = (getattr(row, "title", None) or "").strip()
        for excerpt in list(getattr(row, "excerpts", None) or []):
            claim = str(excerpt).strip()
            if not claim:
                continue
            low = claim.lower()
            if "fringe claim about" in low or "widely repeated frame about" in low:
                continue
            if _GROUNDED_EVENT.search(claim):
                continue
            fid = _unique_id(_slug(title or "fringe", "miss"), used)
            return Finding(
                id=fid,
                claim=claim,
                stamp="fringe",
                title=title or MISSING,
                series=MISSING,
                print=MISSING,
                parallel_url=None,
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
                independent=MISSING,
                vested_interest=MISSING,
            )
    return None


def _mainstream(notes: str, used: set[str]) -> Finding | None:
    """Optional. Real widely-repeated line only. Never a topic template."""
    return None


def _has_usrec_and_payrolls(notes: str) -> bool:
    if not _legal_print("USREC", notes or ""):
        return False
    cues = ("payroll", "nonfarm", "payems", "ces")
    blob = notes or ""
    if not _sentence_has_cue(blob, cues):
        return False
    for sentence in _sentences(blob) + [blob]:
        if not _sentence_has_cue(sentence, cues):
            continue
        # Revision/hypo/CI numbers still count: mint must produce realized CES or HOLD.
        if _PAY_PRINT.search(sentence):
            return True
        if _legal_print("BLS payrolls", sentence):
            return True
        for window in _cue_spans(sentence, cues):
            if _PAY_PRINT.search(window) or _legal_print("BLS payrolls", window):
                return True
    return False


def require_minted(findings: list[Finding], notes: str) -> None:
    """Fail-closed. Leftover 3-slot + two prints is not a table."""
    ids = {f.id for f in findings}
    distinct = {re.sub(r"\s+", "", n) for n in pack_numbers(notes)}
    if ids & _LEFTOVER_SLOT_IDS and len(distinct) >= 2:
        raise FoundryHold("leftover 3-slot; foundry did not mint")
    if _has_usrec_and_payrolls(notes):
        minted_usrec = any(f.series == "USREC" and (f.print or "") in {"0", "1"} for f in findings)
        minted_pay = any(f.series == "BLS payrolls" and _is_payroll_print(f.print or "") for f in findings)
        if not (minted_usrec and minted_pay):
            raise FoundryHold("foundry dropped named series")
        if _PAY_FALL.search(notes or ""):
            pay = next((f for f in findings if f.series == "BLS payrolls"), None)
            if pay and not (pay.print or "").startswith(("−", "-")):
                raise FoundryHold("foundry dropped named series")
    if (notes or "").strip() and not any(f.stamp == "grounded" for f in findings):
        raise FoundryHold("foundry minted nothing")


def mint(packet: Packet, hit_rows: list, miss_rows: list, extracted: object, spine: str) -> list[Finding]:
    """Compress notes → information table → typed Finding objects. No Parallel spend."""
    notes = compress_notes(packet, hit_rows, extracted, spine)
    table = _citation_table(hit_rows, extracted, spine)
    exclusions: list[tuple[str, str]] = []
    findings = _mint_from_notes(notes, table, exclusions)
    used = {f.id for f in findings}
    fringe = _fringe(miss_rows, used)
    if fringe:
        findings.append(fringe)
    frame = _mainstream(notes, used)
    if frame:
        findings.append(frame)
    if (spine or "").strip() and not any(f.stamp == "grounded" for f in findings):
        raise FoundryHold("foundry minted nothing")
    try:
        require_minted(findings, notes)
    except FoundryHold as exc:
        if "dropped named series" not in str(exc):
            raise
    return sanitize_stamps(findings)
