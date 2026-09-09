"""chronological_events → timeline_event findings. Fail-closed URL grounding."""

from __future__ import annotations

import ast
import hashlib
import json
import logging
import re
from typing import Iterable

from pydantic import BaseModel, Field

from onecrew.foundry import leftover_slot_ids, _unique_id, _when, clean_cite_url
from onecrew.models import Finding, TimelineMapRow
from onecrew.verify import CLOSED_SERIES

log = logging.getLogger("onecrew.timeline")

TIMELINE_STAMP = "timeline_event"
TIMELINE_SERIES = "timeline_event"
_CLOSED = CLOSED_SERIES | {"ISM"}
_LEFTOVER = leftover_slot_ids()

_URL = re.compile(r"https?://[^\s\]\)<>\"']+")
_CITE_LABEL = re.compile(
    r"(?:basis|cite_url|cite\s*url|source)\s*[:=]\s*(https?://[^\s\]\)<>\"']+)",
    re.I,
)
_HEADING = re.compile(r"(?im)^chronological[_\s-]*events\s*:?\s*$")
_INDEXED = re.compile(r"(?im)^chronological[_\s-]*events\[(\d+)\]\s*:\s*(.+)$")
_BASIS_FIELD = re.compile(r"(?im)Task basis chronological[_\s-]*events\s*:\s*(.+)$")
_BULLET = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_NEXT_HEAD = re.compile(r"(?m)^[A-Za-z][\w ]{0,48}:\s*$")
_DICT_EVENTS = re.compile(
    r"['\"]chronological_events['\"]\s*:\s*(\[(?:[^\[\]]|\[[^\[\]]*\])*\])",
    re.S,
)
_WORD = re.compile(r"[A-Za-z]{5,}")
_MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+20\d{2}\b",
    re.I,
)
_YEAR_TOK = re.compile(r"^20\d{2}$")


class TimelinePlan(BaseModel):
    findings: list[Finding] = Field(default_factory=list)
    mapping: list[TimelineMapRow] = Field(default_factory=list)


def _clean_url(raw: str) -> str:
    return clean_cite_url((raw or "").rstrip(").,;\"'")) or ""


def _urls_in(text: str) -> list[str]:
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
        raw = data.get("chronological_events")
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


def parse_chronological_events(text: str) -> list[tuple[str, str]]:
    """(thesis, url) pairs. Drop any bullet without a valid cite URL."""
    blob = text or ""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    def _add(thesis: str, url: str) -> None:
        thesis = (thesis or "").strip()
        url = _clean_url(url)
        if not thesis or not url:
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
        if urls and _CITE_LABEL.search(thesis):
            _add(thesis, urls[0])
    return pairs


def _tl_id(thesis: str, url: str, used: set[str]) -> str:
    words = re.findall(r"[a-z0-9]+", (thesis or "").lower())[:6]
    base = "tl-" + ("-".join(words) or "event")
    digest = hashlib.sha1((url or "").encode()).hexdigest()[:6]
    cand = f"{base}-{digest}"[:80]
    if cand in _LEFTOVER:
        cand = f"tl-event-{digest}"
    return _unique_id(cand, used)


def _event_print(thesis: str) -> str:
    return _CITE_LABEL.sub("", _URL.sub("", thesis or "")).strip(" -—.:;")


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


def spoken_match(vo: str, finding: Finding) -> bool:
    """Generic VO↔event overlap. No topic names."""
    from onecrew.script import pack_numbers

    blob = f"{finding.print or ''} {finding.claim or ''}"
    vo_nums = {
        re.sub(r"[^\d.]+", "", n.replace("−", "-"))
        for n in pack_numbers(vo or "")
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    }
    ev_nums = {
        re.sub(r"[^\d.]+", "", n.replace("−", "-"))
        for n in pack_numbers(blob)
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    }
    if vo_nums and ev_nums and vo_nums & ev_nums:
        return True
    vo_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(vo or "")}
    ev_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob)}
    if vo_months and ev_months and vo_months & ev_months:
        return True
    vo_toks = {w.lower() for w in _WORD.findall(vo or "")}
    ev_toks = {w.lower() for w in _WORD.findall(blob)}
    return len(vo_toks & ev_toks) >= 2
