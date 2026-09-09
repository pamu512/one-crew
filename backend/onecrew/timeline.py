"""chronological_events / chronological_event_chain → timeline_event findings."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
from collections import Counter
from typing import Iterable
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from onecrew.foundry import leftover_slot_ids, _unique_id, _when, clean_cite_url
from onecrew.models import Finding, Receipt, TimelineMapRow
from onecrew.verify import CLOSED_SERIES

log = logging.getLogger("onecrew.timeline")

TIMELINE_STAMP = "timeline_event"
TIMELINE_SERIES = "timeline_event"
_CLOSED = CLOSED_SERIES | {"ISM"}
_LEFTOVER = leftover_slot_ids()
_BEAT_SLOTS = frozenset(
    {"cold-open", "promise", "gdp", "labor", "turn", "complication", "receipt", "close"}
)
_MACRO_SLUG = frozenset(
    {"usrec", "payrolls", "gdp", "sahm", "lei", "ism", "unemployment", "u3", "nber", "payems"}
)
_CHAIN_KEY = r"chronological[_\s-]*events?(?:[_\s-]*chain)?"
_MONTH_NUM = {
    "january": "01",
    "jan": "01",
    "february": "02",
    "feb": "02",
    "march": "03",
    "mar": "03",
    "april": "04",
    "apr": "04",
    "may": "05",
    "june": "06",
    "jun": "06",
    "july": "07",
    "jul": "07",
    "august": "08",
    "aug": "08",
    "september": "09",
    "sep": "09",
    "sept": "09",
    "october": "10",
    "oct": "10",
    "november": "11",
    "nov": "11",
    "december": "12",
    "dec": "12",
}

_URL = re.compile(r"https?://[^\s\]\)<>\"']+")
_CITE_LABEL = re.compile(
    r"(?:high[- ]confidence\s+basis|basis|cite_url|cite\s*url|source)"
    r"\s*[:=]\s*(https?://[^\s\]\)<>\"']+)",
    re.I,
)
_HIGH_BASIS = re.compile(
    r"high[- ]confidence\s+basis\s*[:=]\s*(https?://[^\s\]\)<>\"']+)",
    re.I,
)
_HEADING = re.compile(rf"(?im)^(?:argument\s+)?{_CHAIN_KEY}\s*:?\s*$")
_INDEXED = re.compile(rf"(?im)^(?:argument\s+)?{_CHAIN_KEY}\[(\d+)\]\s*:\s*(.+)$")
_BASIS_FIELD = re.compile(rf"(?im)Task basis {_CHAIN_KEY}\s*:\s*(.+)$")
_BULLET = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_NEXT_HEAD = re.compile(r"(?m)^(?:#{1,3}\s+)?[A-Za-z][\w ]{0,48}:\s*$")
_DICT_EVENTS = re.compile(
    rf"['\"]{_CHAIN_KEY}['\"]\s*:\s*(\[(?:[^\[\]]|\[[^\[\]]*\])*\])",
    re.S | re.I,
)
_WORD = re.compile(r"[A-Za-z]{5,}")
_MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+20\d{2}\b",
    re.I,
)
_YEAR_TOK = re.compile(r"^20\d{2}$")
_BIBLIO_ID = re.compile(
    r"\[?(?:cold-open|promise|gdp|labor|turn|complication|receipt|close)"
    r"-(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december)-20\d{2}\]?",
    re.I,
)
_PACK_CHROME = re.compile(
    r"official series cards only|three pack objects|leftover map|"
    r"bibliography|executive_summary|scrape title|"
    r"go to content|skip to (?:main )?content",
    re.I,
)
_URL_REUSE_CAP = 2
_SOURCES_HEAD = re.compile(r"(?im)^#{0,3}\s*sources\b")
_EMPTY_MINT = "foundry minted nothing"


class TimelinePlan(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    mapping: list[TimelineMapRow] = Field(default_factory=list)


def _clean_url(raw: str) -> str:
    return clean_cite_url((raw or "").rstrip(").,;\"'")) or ""


def url_host(url: str) -> str:
    host = (urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def host_labels(url: str) -> set[str]:
    """Registrable labels a VO may speak. Derived from the URL, not a topic list."""
    host = url_host(url)
    if not host:
        return set()
    sld = host.split(".")[0]
    labels = {host, sld}
    if sld.startswith("the") and len(sld) > 5:
        labels.add(sld[3:])
    return {lab for lab in labels if len(lab) >= 3}


def _urls_in(text: str) -> list[str]:
    high = [_clean_url(m.group(1)) for m in _HIGH_BASIS.finditer(text or "")]
    high = [u for u in high if u]
    if high:
        return list(dict.fromkeys(high))
    labeled = [_clean_url(m.group(1)) for m in _CITE_LABEL.finditer(text or "")]
    labeled = [u for u in labeled if u]
    if labeled:
        return list(dict.fromkeys(labeled))
    return list(dict.fromkeys(u for u in (_clean_url(m.group(0)) for m in _URL.finditer(text or "")) if u))


def _basis_urls(text: str) -> list[str]:
    out: list[str] = []
    for match in _BASIS_FIELD.finditer(text or ""):
        out.extend(_urls_in(match.group(1)))
    return list(dict.fromkeys(out))


def _section_body(text: str) -> str:
    match = _HEADING.search(text or "")
    if not match:
        return ""
    rest = (text or "")[match.end() :]
    stop = _NEXT_HEAD.search(rest)
    return rest[: stop.start()] if stop else rest


def _structured_events(text: str) -> list[str]:
    blob = (text or "").strip()
    for loader in (json.loads, ast.literal_eval):
        try:
            data = loader(blob)
        except Exception:
            continue
        rows = _events_from_obj(data)
        if rows:
            return rows
    found = _DICT_EVENTS.search(text or "")
    if not found:
        return []
    try:
        data = ast.literal_eval(found.group(1))
    except Exception:
        try:
            data = json.loads(found.group(1))
        except Exception:
            return []
    return [str(x).strip() for x in data if str(x).strip()] if isinstance(data, list) else []


def _events_from_obj(data: object) -> list[str]:
    if isinstance(data, dict):
        for key in ("chronological_event_chain", "chronological_events"):
            raw = data.get(key)
            if isinstance(raw, list):
                return [str(x).strip() for x in raw if str(x).strip()]
            if isinstance(raw, str) and raw.strip():
                return [raw.strip()]
    if isinstance(data, list):
        return [str(x).strip() for x in data if str(x).strip()]
    return []


def _bullets(body: str) -> list[str]:
    rows = [m.group(1).strip() for m in _BULLET.finditer(body or "") if m.group(1).strip()]
    if rows:
        return rows
    stripped = (body or "").strip()
    if stripped.startswith("["):
        return _structured_events(stripped)
    return []


def _drop_sources(text: str) -> str:
    """Bibliography leftover slots are not the event chain."""
    match = _SOURCES_HEAD.search(text or "")
    return (text or "")[: match.start()] if match else (text or "")


def _chrome_thesis(thesis: str) -> bool:
    blob = (thesis or "").strip()
    if not blob:
        return True
    if _BIBLIO_ID.search(blob) or _PACK_CHROME.search(blob):
        return True
    stripped = _CITE_LABEL.sub("", _URL.sub("", blob))
    stripped = re.sub(r"\[[^\]]+\]", "", stripped).strip(" -—.:;")
    return len(stripped.split()) < 4


def parse_chronological_events(text: str) -> list[tuple[str, str]]:
    """(thesis, url) pairs. Prefer event-chain High-confidence basis URLs."""
    blob = _drop_sources(text or "")
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(thesis: str, url: str) -> None:
        thesis = (thesis or "").strip()
        url = _clean_url(url)
        if not thesis or not url or _chrome_thesis(thesis):
            return
        key = (thesis, url)
        if key in seen:
            return
        seen.add(key)
        pairs.append((thesis, url))

    indexed: dict[int, str] = {}
    for match in _INDEXED.finditer(blob):
        indexed[int(match.group(1))] = match.group(2).strip()
    basis = _basis_urls(blob)
    if indexed:
        for i in sorted(indexed):
            thesis = indexed[i]
            urls = _urls_in(thesis)
            url = urls[0] if urls else (basis[i] if i < len(basis) else "")
            _add(thesis, url)

    events = _structured_events(blob)
    section_events = _bullets(_section_body(blob))
    if section_events:
        events = section_events if not events else list(dict.fromkeys([*events, *section_events]))
    if events:
        for i, thesis in enumerate(events):
            urls = _urls_in(thesis)
            url = urls[0] if urls else (basis[i] if i < len(basis) else "")
            _add(thesis, url)
        return pairs

    for match in _BULLET.finditer(blob):
        thesis = match.group(1).strip()
        urls = _urls_in(thesis)
        if urls and (_HIGH_BASIS.search(thesis) or _CITE_LABEL.search(thesis)):
            _add(thesis, urls[0])
    return pairs


def _yyyy_mm(thesis: str) -> str:
    month = _MONTH_YEAR.search(thesis or "")
    if month:
        return f"{month.group(0)[-4:]}-{_MONTH_NUM[month.group(1).lower()]}"
    year = re.search(r"\b(20\d{2})\b", thesis or "")
    return f"{year.group(1)}-01" if year else ""


def _tl_id(thesis: str, url: str, used: set[str]) -> str:
    raw = _CITE_LABEL.sub("", _URL.sub("", thesis or ""))
    words = [
        w
        for w in re.findall(r"[a-z0-9]+", raw.lower())
        if w not in _MACRO_SLUG
        and w not in _BEAT_SLOTS
        and w not in {"high", "confidence", "basis", "a", "an", "the", "and", "of", "in"}
    ][:4]
    slug = "-".join(words) or "event"
    stamp = _yyyy_mm(thesis)
    cand = f"te-{slug}-{stamp}" if stamp else f"te-{slug}"
    cand = cand.strip("-")[:80]
    if cand in _LEFTOVER or _BIBLIO_ID.fullmatch(cand) or cand.split("-")[0] in _BEAT_SLOTS:
        digest = hashlib.sha1((url or "").encode()).hexdigest()[:6]
        cand = f"te-event-{stamp or digest}"
    return _unique_id(cand, used)


def _event_print(thesis: str) -> str:
    cleaned = _HIGH_BASIS.sub("", thesis or "")
    cleaned = _CITE_LABEL.sub("", cleaned)
    cleaned = _URL.sub("", cleaned)
    cleaned = re.sub(r"high[- ]confidence\s+basis\s*[:=]?\s*", "", cleaned, flags=re.I)
    return cleaned.strip(" -—.:;")


def plan_timeline(
    text: str,
    *,
    used: set[str] | None = None,
    seen_urls: Iterable[str] | None = None,
) -> TimelinePlan:
    """Parse + log mapping. Does not mutate a findings array."""
    used_ids = set(used or [])
    skip = {(u or "").strip() for u in (seen_urls or []) if (u or "").strip()}
    mapping: list[TimelineMapRow] = []
    findings: list[Finding] = []
    for thesis, url in parse_chronological_events(text):
        if url in skip:
            continue
        fid = _tl_id(thesis, url, used_ids)
        printed = _event_print(thesis) or thesis
        mapping.append(TimelineMapRow(thesis=thesis, url=url, finding_id=fid))
        findings.append(
            Finding(
                id=fid,
                claim=printed,
                stamp=TIMELINE_STAMP,
                title=TIMELINE_SERIES,
                series=TIMELINE_SERIES,
                print=printed,
                when=_when(thesis) or "",
                parallel_url=url,
                parallel_status="hit",
                note="Timeline event. Parallel URL on this row.",
            )
        )
        skip.add(url)
    for row in mapping:
        log.info("timeline map: %s -> %s -> %s", row.thesis, row.url, row.finding_id)
    return TimelinePlan(findings=findings, mapping=mapping)


def apply_timeline(findings: list[Finding], planned: TimelinePlan) -> None:
    have = {(f.parallel_url or "").strip() for f in findings if (f.parallel_url or "").strip()}
    have_ids = {f.id for f in findings}
    for finding in planned.findings:
        url = (finding.parallel_url or "").strip()
        if finding.id in have_ids or (url and url in have):
            continue
        if (finding.series or "") in _CLOSED:
            continue
        findings.append(finding)
        have_ids.add(finding.id)
        if url:
            have.add(url)


def chain_pairs(text: str, mapping: Iterable[TimelineMapRow] | None = None) -> list[tuple[str, str]]:
    """Prefer each chain bullet's own High-confidence basis over a leftover map row."""
    pairs = parse_chronological_events(text or "")
    if pairs:
        return pairs
    out: list[tuple[str, str]] = []
    for row in mapping or []:
        thesis = (getattr(row, "thesis", None) or "").strip()
        url = _clean_url(getattr(row, "url", None) or "")
        if thesis and url:
            out.append((thesis, url))
    return out


def _vo_mentions_label(vo: str, label: str) -> bool:
    if not vo or not label:
        return False
    return bool(re.search(rf"\b{re.escape(label)}\b", vo, re.I))


def named_basis_urls(vo: str, pairs: Iterable[tuple[str, str]]) -> list[str]:
    """Chain basis URLs whose host label is spoken. No topic names."""
    out: list[str] = []
    for _thesis, url in pairs or []:
        if any(_vo_mentions_label(vo, lab) for lab in host_labels(url)):
            out.append(url)
    return list(dict.fromkeys(out))


def _event_nums(text: str) -> set[str]:
    from onecrew.script import pack_numbers

    return {
        re.sub(r"[^\d.]+", "", n.replace("−", "-"))
        for n in pack_numbers(text or "")
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    }


def event_score(vo: str, blob: str) -> int:
    if not (vo or "").strip() or not (blob or "").strip():
        return 0
    score = len(_event_nums(vo) & _event_nums(blob)) * 10
    vo_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(vo or "")}
    ev_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob or "")}
    score += len(vo_months & ev_months) * 8
    vo_toks = {w.lower() for w in _WORD.findall(vo or "")}
    ev_toks = {w.lower() for w in _WORD.findall(blob or "")}
    return score + len(vo_toks & ev_toks)


def spoken_overlap(vo: str, blob: str) -> bool:
    """Generic VO↔text overlap. No topic names."""
    if _event_nums(vo) and _event_nums(vo) & _event_nums(blob):
        return True
    vo_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(vo or "")}
    ev_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob or "")}
    if vo_months and ev_months and vo_months & ev_months:
        return True
    vo_toks = {w.lower() for w in _WORD.findall(vo or "")}
    ev_toks = {w.lower() for w in _WORD.findall(blob or "")}
    return len(vo_toks & ev_toks) >= 2


def spoken_match(vo: str, finding: Finding) -> bool:
    """Generic VO↔event overlap. No topic names."""
    return spoken_overlap(vo, f"{finding.print or ''} {finding.claim or ''}")


def spoken_basis_url(vo: str, pairs: Iterable[tuple[str, str]]) -> str | None:
    """High-confidence basis URL for this spoken beat. Named host wins over soft overlap."""
    rows = [(t, u) for t, u in (pairs or []) if t and u]
    if not rows:
        return None
    named = named_basis_urls(vo, rows)
    pool = [(t, u) for t, u in rows if u in named] if named else rows
    best_url: str | None = None
    best = -1
    for thesis, url in pool:
        score = event_score(vo, thesis)
        if score > best:
            best = score
            best_url = url
    if named:
        return best_url
    if best_url and (best > 0 or spoken_overlap(vo, next(t for t, u in pool if u == best_url))):
        return best_url
    return None


def cite_host_ok(vo: str, url: str, pairs: Iterable[tuple[str, str]]) -> bool:
    """Refuse a survey host when the spoken beat names (or maps to) another chain basis."""
    raw = (url or "").strip()
    if not raw:
        return False
    want = spoken_basis_url(vo, pairs)
    if want:
        return url_host(raw) == url_host(want)
    named = named_basis_urls(vo, pairs)
    if named:
        return url_host(raw) in {url_host(u) for u in named}
    return False


def best_timeline_finding(
    vo: str,
    findings: Iterable[Finding],
    pairs: Iterable[tuple[str, str]],
) -> Finding | None:
    """Attach the chain-basis finding for this VO. Do not soft-match a survey cover."""
    want = spoken_basis_url(vo, pairs)
    if not want:
        return None
    tls = [
        f
        for f in findings or []
        if getattr(f, "stamp", "") == TIMELINE_STAMP and (f.parallel_url or "").strip()
    ]
    exact = [f for f in tls if (f.parallel_url or "").strip() == want]
    if exact:
        return exact[0]
    host = url_host(want)
    same = [f for f in tls if url_host(f.parallel_url or "") == host]
    if not same:
        return None
    return max(same, key=lambda f: event_score(vo, f"{f.print or ''} {f.claim or ''}"))


def cap_url_reuse(
    findings: list[Finding],
    pairs: Iterable[tuple[str, str]],
) -> list[Finding]:
    """Same parallel_url on >2 timeline_event rows is a smell unless the chain repeats that basis."""
    basis_n = Counter(u for _t, u in (pairs or []) if u)
    used: Counter[str] = Counter()
    kept: list[Finding] = []
    for finding in findings:
        if getattr(finding, "stamp", "") != TIMELINE_STAMP:
            kept.append(finding)
            continue
        url = (finding.parallel_url or "").strip()
        if not url:
            kept.append(finding)
            continue
        cap = basis_n[url] if basis_n[url] else _URL_REUSE_CAP
        if used[url] >= cap:
            continue
        used[url] += 1
        kept.append(finding)
    return kept


def has_timeline_url(findings: Iterable[Finding]) -> bool:
    return any(
        getattr(f, "stamp", "") == TIMELINE_STAMP
        and bool(clean_cite_url(getattr(f, "parallel_url", None) or ""))
        for f in findings or []
    )


def empty_mint_hold_ok_to_clear(reason: str, findings: Iterable[Finding], notes: str = "") -> bool:
    """Timeline-only is not empty-macro HOLD. Named-series demand still HOLDs."""
    if not has_timeline_url(findings):
        return False
    low = (reason or "").lower()
    if "leftover 3-slot" in low or "dropped named series" in low:
        return False
    if _EMPTY_MINT not in low:
        return False
    from onecrew.foundry import _has_usrec_and_payrolls

    if _has_usrec_and_payrolls(notes or ""):
        rows = list(findings or [])
        minted_usrec = any(getattr(f, "series", "") == "USREC" for f in rows)
        minted_pay = any(getattr(f, "series", "") == "BLS payrolls" for f in rows)
        if not (minted_usrec and minted_pay):
            return False
    return True


def clear_empty_mint_hold(receipt: Receipt, notes: str = "") -> Receipt:
    """Drop HOLD that exists only because Foundry minted no closed macros."""
    if receipt.disposition != "HOLD":
        return receipt
    if not empty_mint_hold_ok_to_clear(receipt.hold_reason or "", receipt.findings, notes):
        return receipt
    kept = [
        part.strip()
        for part in (receipt.hold_reason or "").replace("\n", ";").split(";")
        if part.strip() and _EMPTY_MINT not in part.lower()
    ]
    receipt.hold_reason = "; ".join(kept) or None
    if not receipt.hold_reason:
        receipt.disposition = "READY"
    return receipt
