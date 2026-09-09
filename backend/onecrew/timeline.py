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
_ARG_HEAD = re.compile(r"(?im)^(?:#{1,3}\s+)?argument\s*:?\s*$")
_TASK_BASIS_HEAD = re.compile(
    rf"(?im)^(?:#{1,3}\s+)?task\s+basis(?:\s+{_CHAIN_KEY})?\s*:?\s*$"
)
_HIGH_LIST_HEAD = re.compile(
    r"(?im)^(?:#{1,3}\s+)?high[- ]confidence\s+basis(?:\s+list)?\s*:?\s*$"
)
_INDEXED = re.compile(rf"(?im)^(?:argument\s+)?{_CHAIN_KEY}\[(\d+)\]\s*:\s*(.+)$")
_BASIS_FIELD = re.compile(rf"(?im)Task basis(?:\s+{_CHAIN_KEY})?\s*:\s*(.+)$")
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
    r"go to content|skip to (?:main )?content|cookie banner|"
    r"last[- ]verified|last[- ]updated|last[- ]checked",
    re.I,
)
_CHROME_COVER = re.compile(
    r"\blast[- ]verified\b|\blast[- ]updated\b|\blast[- ]checked\b|"
    r"\bretrieved(?:[- ]at)?\b|\bte-last-verified-",
    re.I,
)
_RSS_HUB_ID = re.compile(
    r"subscribe[-_]?rss|rss[-_]?feed|log[-_]?feed|(?:^|[-_])rss(?:[-_]|$)|"
    r"[-_]subscribe(?:[-_]|$)",
    re.I,
)
_RSS_HUB_TITLE = re.compile(r"\b(?:subscribe|rss(?:\s+feed)?)\b", re.I)
_URL_REUSE_CAP = 2
URL_REUSE_CAP = _URL_REUSE_CAP
MAX_CITES_PER_BEAT = 2
_SOURCES_HEAD = re.compile(r"(?im)^#{0,3}\s*sources\b")
_LEFT_OUT = re.compile(
    r"(?im)^Left out:\s*(.+?)\.\s*URL:\s*(https?://[^\s]+?)\.\s*reason=(\w+)"
)
_SKIP_HIT_REASONS = frozenset(
    {
        "parallel_miss",
        "outside_depth",
        "off_topic",
        "no_url",
        "not_searched",
        "rails_down",
    }
)
_EMPTY_MINT = "foundry minted nothing"
UNSTAMPED_HITS = "parallel hits present but unstamped"
EMPTY_AFTER_STAMP = "timeline empty after hit stamp"


class TimelinePlan(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    mapping: list[TimelineMapRow] = Field(default_factory=list)


def _clean_url(raw: str) -> str:
    return clean_cite_url((raw or "").rstrip(").,;\"'")) or ""


def url_host(url: str) -> str:
    host = (urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def url_key(url: str) -> str:
    """Host + path. Scheme/www stripped; do not invent URLs."""
    raw = (url or "").strip()
    if not raw:
        return ""
    parts = urlsplit(raw)
    host = url_host(raw)
    path = (parts.path or "").rstrip("/")
    return f"{host}{path}" if host else raw.rstrip("/")


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


def _section_after(text: str, heading: re.Pattern[str]) -> str:
    match = heading.search(text or "")
    if not match:
        return ""
    rest = (text or "")[match.end() :]
    stop = _NEXT_HEAD.search(rest)
    return rest[: stop.start()] if stop else rest


def _basis_urls(text: str) -> list[str]:
    """Task basis / High-confidence lists. Sources already stripped by caller."""
    out: list[str] = []
    for match in _BASIS_FIELD.finditer(text or ""):
        out.extend(_urls_in(match.group(1)))
    for head in (_TASK_BASIS_HEAD, _HIGH_LIST_HEAD):
        out.extend(_urls_in(_section_after(text, head)))
    for match in _HIGH_BASIS.finditer(text or ""):
        url = _clean_url(match.group(1))
        if url:
            out.append(url)
    return list(dict.fromkeys(out))


def _section_body(text: str) -> str:
    for head in (_HEADING, _ARG_HEAD):
        body = _section_after(text, head)
        if _bullets(body):
            return body
    return ""


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


def _row_url(row: object) -> str:
    return _clean_url(getattr(row, "url", None) or "")


def _row_claim(row: object) -> str:
    title = (getattr(row, "title", None) or getattr(row, "what", None) or "").strip()
    excerpts = list(getattr(row, "excerpts", None) or [])
    for excerpt in excerpts:
        text = str(excerpt).strip()
        if text and not _hit_chrome(text):
            return title if title and not _hit_chrome(title) else text
    return title


def _row_reason(row: object) -> str:
    return (getattr(row, "reason", None) or "").strip().lower()


def _hit_chrome(thesis: str) -> bool:
    """Pack/nav chrome only. Short news titles stay — chain chrome uses _chrome_thesis."""
    blob = (thesis or "").strip()
    if not blob:
        return True
    if _BIBLIO_ID.search(blob) or _PACK_CHROME.search(blob):
        return True
    stripped = _CITE_LABEL.sub("", _URL.sub("", blob))
    stripped = re.sub(r"\[[^\]]+\]", "", stripped).strip(" -—.:;")
    return len(stripped.split()) < 2


def _news_hit(thesis: str, url: str) -> bool:
    """Event/news page with a real path. Drop chrome titles and bare homepages."""
    if not (url or "").startswith("http"):
        return False
    if _hit_chrome(thesis):
        return False
    return bool((urlsplit(url).path or "").rstrip("/"))


def parse_parallel_hits(
    text: str = "",
    rows: Iterable[object] | None = None,
) -> list[tuple[str, str]]:
    """Hit rows / Left-out https URLs when the event chain is missing. Require URL or drop."""
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()

    def _add(thesis: str, url: str) -> None:
        thesis = (thesis or "").strip()
        url = _clean_url(url)
        if not thesis or not url or not _news_hit(thesis, url) or url in seen:
            return
        seen.add(url)
        pairs.append((thesis, url))

    for row in rows or []:
        if _row_reason(row) in _SKIP_HIT_REASONS:
            continue
        _add(_row_claim(row), _row_url(row))
    for match in _LEFT_OUT.finditer(text or ""):
        if match.group(3).lower() in _SKIP_HIT_REASONS:
            continue
        _add(match.group(1).strip(), match.group(2))
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
    hit_rows: Iterable[object] | None = None,
) -> TimelinePlan:
    """Parse + log mapping. Does not mutate a findings array."""
    used_ids = set(used or [])
    skip = {(u or "").strip() for u in (seen_urls or []) if (u or "").strip()}
    mapping: list[TimelineMapRow] = []
    findings: list[Finding] = []
    pairs = parse_chronological_events(text)
    if not pairs:
        pairs = parse_parallel_hits(text, hit_rows)
    for thesis, url in pairs:
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
    hits = parse_parallel_hits(text or "")
    if hits:
        return hits
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


# Sentence-start / function words. Derived from grammar, not a topic list.
_FUNCTION = frozenset(
    {
        "the",
        "and",
        "for",
        "from",
        "this",
        "that",
        "with",
        "into",
        "over",
        "under",
        "about",
        "after",
        "before",
        "when",
        "those",
        "these",
        "their",
        "there",
        "then",
        "than",
        "narrator",
        "receipt",
        "near",
        "hold",
        "turn",
        "labor",
        "official",
        "named",
        "series",
        "board",
        "close",
        "promise",
        "asked",
        "whether",
        "already",
        "announced",
        "printed",
        "cited",
        "events",
        "title",
        "stays",
        "question",
        "same",
        "object",
        "switch",
        "beat",
        "action",
        "wide",
        "card",
    }
)
_PROPER = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:[A-Z][a-zA-Z0-9]+)*)\b")


def vo_proper_names(vo: str) -> set[str]:
    """Capitalized tokens in VO. Months and function words dropped. No topic list."""
    skip = {k.lower() for k in _MONTH_NUM} | _FUNCTION
    names: set[str] = set()
    for match in _PROPER.finditer(vo or ""):
        raw = match.group(1)
        if raw.lower() in skip or len(raw) < 4:
            continue
        names.add(raw.lower())
    return names


def pair_covers_vo(vo: str, thesis: str, url: str) -> bool:
    """Every named VO token must appear on this stamp's URL/title/claim/note. Else refuse."""
    names = vo_proper_names(vo)
    if not names:
        return True
    labels = {lab.lower() for lab in host_labels(url)}
    blob = f"{thesis or ''} {url or ''}".lower()
    return all(name in blob or name in labels for name in names)


def stamp_text(finding: object) -> str:
    """Host-adjacent blob a named VO may use. Generic titles are not cover."""
    title = (getattr(finding, "title", None) or "").strip()
    parts = [
        getattr(finding, "claim", None) or "",
        getattr(finding, "print", None) or "",
        getattr(finding, "note", None) or "",
        getattr(finding, "when", None) or "",
    ]
    if title.lower() not in {"timeline_event", "grounded", "mainstream", "fringe", ""}:
        parts.append(title)
    return " ".join(parts)


def is_rss_hub_stamp(finding: object) -> bool:
    """Subscribe / RSS / log-feed hub. Not a covering stamp."""
    fid = str(getattr(finding, "id", None) or "")
    title = str(getattr(finding, "title", None) or "")
    return bool(_RSS_HUB_ID.search(fid) or _RSS_HUB_TITLE.search(title))


def is_chrome_cover_stamp(finding: object) -> bool:
    """Last-verified / retrieved / RSS hub chrome. Not a print-bearing cover."""
    if is_rss_hub_stamp(finding):
        return True
    blob = " ".join(
        str(getattr(finding, key, None) or "")
        for key in ("id", "title", "print", "claim", "note")
    )
    return bool(_CHROME_COVER.search(blob))


def stamp_covers_vo(vo: str, finding: Finding) -> bool:
    if is_chrome_cover_stamp(finding):
        return False
    return pair_covers_vo(vo, stamp_text(finding), getattr(finding, "parallel_url", None) or getattr(finding, "url", None) or "")


def _years(text: str) -> set[str]:
    cleaned = re.sub(r"\[[^\]]+\]", "", text or "")
    return set(re.findall(r"\b20\d{2}\b", cleaned))


def stamp_supports_prints(vo: str, finding: object) -> bool:
    """Spoken non-year prints and dated when must sit on this stamp. Else refuse."""
    blob = stamp_text(finding)
    nums = _event_nums(vo)
    if nums and not nums <= _event_nums(blob):
        return False
    vo_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(vo or "")}
    ev_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob or "")}
    if vo_months and not (vo_months & ev_months):
        return False
    vo_years = _years(vo)
    ev_years = _years(blob)
    if vo_years and ev_years and not (vo_years & ev_years):
        return False
    return True


def named_basis_urls(vo: str, pairs: Iterable[tuple[str, str]]) -> list[str]:
    """Chain basis URLs whose host label is spoken. No topic names."""
    out: list[str] = []
    for _thesis, url in pairs or []:
        if any(_vo_mentions_label(vo, lab) for lab in host_labels(url)):
            out.append(url)
    return list(dict.fromkeys(out))


def _event_nums(text: str) -> set[str]:
    from onecrew.script import pack_numbers

    cleaned = re.sub(r"\[[^\]]+\]", "", text or "")
    return {
        re.sub(r"[^\d.]+", "", n.replace("−", "-"))
        for n in pack_numbers(cleaned)
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
    rows = [(t, u) for t, u in rows if pair_covers_vo(vo, t, u)]
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
    if vo_proper_names(vo) and not pair_covers_vo(vo, "", raw):
        covered = [(t, u) for t, u in (pairs or []) if pair_covers_vo(vo, t, u)]
        if not any(url_key(u) == url_key(raw) for _t, u in covered):
            return False
    want = spoken_basis_url(vo, pairs)
    if want:
        return url_key(raw) == url_key(want)
    named = named_basis_urls(vo, pairs)
    if named:
        return url_key(raw) in {url_key(u) for u in named}
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
    exact = [
        f
        for f in tls
        if url_key(f.parallel_url or "") == url_key(want) and stamp_covers_vo(vo, f)
    ]
    return exact[0] if exact else None


def _months(text: str) -> set[str]:
    return {m.group(0).lower() for m in _MONTH_YEAR.finditer(text or "")}


def union_supports_prints(vo: str, findings: Iterable[object]) -> bool:
    """Spoken non-year prints and dated when must sit on the attached set."""
    rows = list(findings or [])
    blob = " ".join(stamp_text(f) for f in rows)
    nums = _event_nums(vo)
    if nums and not nums <= _event_nums(blob):
        return False
    vo_months = _months(vo)
    if vo_months and not (vo_months & _months(blob)):
        return False
    vo_years = _years(vo)
    ev_years = _years(blob)
    if vo_years and ev_years and not (vo_years & ev_years):
        return False
    return True


def _print_bearing(finding: Finding) -> bool:
    """Non-year magnitude on the stamp. A when-year is not a print."""
    return bool(_event_nums(stamp_text(finding)))


def _print_stamp_for_thin_vo(vo: str, tls: list[Finding]) -> list[Finding]:
    """Comparative VO without a spoken print may take one overlapping print stamp. Else none."""
    printed = [f for f in tls if _print_bearing(f)]
    if not printed:
        return []
    printed = sorted(printed, key=lambda f: event_score(vo, stamp_text(f)), reverse=True)
    if event_score(vo, stamp_text(printed[0])) > 0:
        return [printed[0]]
    return []


def _prefer_unused_host(vo: str, tls: list[Finding]) -> Finding | None:
    covers = [f for f in tls if not is_chrome_cover_stamp(f) and stamp_covers_vo(vo, f)]
    if not covers:
        return None
    full = [f for f in covers if stamp_supports_prints(vo, f)]
    # ponytail: spoken nums need a print-bearing stamp. Chrome/name-only fallback is soft-cover.
    pool = full if (_event_nums(vo) or full) else covers
    if _event_nums(vo) and not full:
        return None
    if not pool:
        return None
    load = host_load(tls)
    pool.sort(key=lambda f: (load[url_host(f.parallel_url or "")], f.id))
    return pool[0]


def stamps_for_vo(
    vo: str,
    findings: Iterable[Finding],
    pairs: Iterable[tuple[str, str]],
) -> list[Finding]:
    """Name-covering stamp(s). Leftover prints/whens only from stamps that also cover names."""
    from onecrew.script import is_comparative_vo

    tls = [
        f
        for f in findings or []
        if getattr(f, "stamp", "") == TIMELINE_STAMP
        and (f.parallel_url or "").strip()
        and not is_chrome_cover_stamp(f)
    ]
    names = vo_proper_names(vo)
    if not names and not _event_nums(vo) and not _months(vo):
        best = best_timeline_finding(vo, tls, pairs)
        if best is not None:
            return [best]
        if is_comparative_vo(vo):
            return _print_stamp_for_thin_vo(vo, tls)
        return []
    best = best_timeline_finding(vo, tls, pairs)
    if best is None:
        best = _prefer_unused_host(vo, tls)
    out: list[Finding] = []
    if best is not None:
        out.append(best)
    elif names:
        return []
    have_n = _event_nums(" ".join(stamp_text(f) for f in out))
    have_m = _months(" ".join(stamp_text(f) for f in out))
    want_n = _event_nums(vo) - have_n
    want_m = _months(vo) - have_m
    for finding in tls:
        if finding.id in {f.id for f in out}:
            continue
        if names and not stamp_covers_vo(vo, finding):
            continue
        blob = stamp_text(finding)
        give_n = _event_nums(blob) & want_n
        give_m = _months(blob) & want_m
        if not give_n and not give_m:
            continue
        out.append(finding)
        want_n -= give_n
        want_m -= give_m
    if not _event_nums(vo):
        return out[:MAX_CITES_PER_BEAT]
    num_rows = [f for f in out if _event_nums(vo) & _event_nums(stamp_text(f))]
    month_need = _months(vo) - _months(" ".join(stamp_text(f) for f in num_rows))
    when_rows = [f for f in out if month_need & _months(stamp_text(f))]
    picked = list({f.id: f for f in [*num_rows, *when_rows]}.values()) or out
    return picked[:MAX_CITES_PER_BEAT]


def _reuse_capped(finding: Finding) -> bool:
    """Parallel/cite rows share the host cap. CLOSED_SERIES official stamps do not."""
    if not (getattr(finding, "parallel_url", None) or "").strip():
        return False
    series = (getattr(finding, "series", None) or "").strip()
    return series not in CLOSED_SERIES


def cap_beat_cites(
    vo: str,
    fids: list[str],
    findings: Iterable[Finding],
    *,
    cap: int = MAX_CITES_PER_BEAT,
) -> list[str]:
    """Keep CLOSED_SERIES. Cap other board cites to covering stamps that support the VO."""
    rows = list(findings or [])
    by_id = {f.id: f for f in rows}
    closed = list(
        dict.fromkeys(
            fid
            for fid in fids
            if fid in by_id and (by_id[fid].series or "").strip() in CLOSED_SERIES
        )
    )
    other = list(dict.fromkeys(fid for fid in fids if fid in by_id and fid not in closed))
    if len(other) <= cap:
        return list(dict.fromkeys([*closed, *other]))
    load = host_load(rows)

    def _score(fid: str) -> tuple:
        finding = by_id[fid]
        cover = stamp_covers_vo(vo, finding)
        support = stamp_supports_prints(vo, finding)
        printed = _print_bearing(finding)
        host = url_host(finding.parallel_url or "")
        return (
            -(1 if cover and support else 0),
            -(1 if cover else 0),
            -(1 if printed else 0),
            load[host],
            fid,
        )

    covering = [fid for fid in other if stamp_covers_vo(vo, by_id[fid])]
    pool = covering or other
    picked = list(dict.fromkeys(sorted(pool, key=_score)))[:cap]
    return list(dict.fromkeys([*closed, *picked]))


def host_load(findings: Iterable[Finding]) -> Counter[str]:
    used: Counter[str] = Counter()
    for finding in findings or []:
        if not _reuse_capped(finding):
            continue
        host = url_host(getattr(finding, "parallel_url", None) or "")
        if host:
            used[host] += 1
    return used


def host_under_cap(
    url: str,
    findings: Iterable[Finding],
    *,
    vo: str = "",
    pairs: Iterable[tuple[str, str]] | None = None,
) -> bool:
    """One survey host cannot soft-cover half the cut. Named chain basis may reuse."""
    host = url_host(url)
    if not host:
        return True
    if host_load(findings)[host] < _URL_REUSE_CAP:
        return True
    want = spoken_basis_url(vo, pairs or []) if vo else None
    return bool(want and url_key(want) == url_key(url))


def cap_url_reuse(
    findings: list[Finding],
    pairs: Iterable[tuple[str, str]],
) -> list[Finding]:
    """Same URL or host on >2 Parallel/cite rows is a smell unless that exact basis repeats."""
    basis_n = Counter(u for _t, u in (pairs or []) if u)
    used: Counter[str] = Counter()
    used_host: Counter[str] = Counter()
    kept: list[Finding] = []
    for finding in findings:
        url = (finding.parallel_url or "").strip()
        if not _reuse_capped(finding):
            kept.append(finding)
            continue
        cap = basis_n[url] if basis_n[url] else _URL_REUSE_CAP
        host = url_host(url)
        if used[url] >= cap or (host and used_host[host] >= _URL_REUSE_CAP):
            continue
        used[url] += 1
        if host:
            used_host[host] += 1
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
