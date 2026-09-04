"""Vertex ADK Claimer. Proposes typed Claims from cites/spine only.

Parallel is citations. verify.py is the authority. Foundry is a v1 candidate, not READY.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from onecrew import config
from onecrew.foundry import leftover_slot_ids
from onecrew.models import MISSING, Finding, Packet
from onecrew.verify import (
    CLOSED_SERIES,
    Claim,
    CiteBag,
    _parse_when,
    _usrec_month_on_table,
    _year_adjacent_month,
    verify_payrolls_realized_ces,
)
from onecrew.vertex_client import VertexDownError, generate_script

_LEFTOVER = leftover_slot_ids()
_NAICS = re.compile(r"\bnaics\b|payroll services|employment level", re.I)
_CES_FALL = re.compile(
    r"(?:total\s+)?nonfarm payroll(?:s| employment)\s+"
    r"(fell|declined|dropped|lost|decreased|rose|gained|increased|fell by)\s+"
    r"(?:by\s+)?([\d,]+)",
    re.I,
)
_MONTH_YEAR = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(20\d{2})",
    re.I,
)
_GDP_Q = re.compile(
    r"(?:real\s+)?gdp\s+(?:increased|rose|grew)\s+(\d+(?:\.\d+)?)\s*%?"
    r".{0,48}?(?:q([1-4])|first|second|third|fourth)\s+(?:quarter\s+)?(20\d{2})|"
    r"(?:q([1-4])|first|second|third|fourth)\s+(?:quarter\s+of\s+)?(20\d{2})"
    r".{0,48}?(?:real\s+)?gdp\s+(?:increased|rose|grew)\s+(\d+(?:\.\d+)?)",
    re.I,
)
_U3 = re.compile(
    r"unemployment rate was\s+(\d+(?:\.\d+)?)\s+percent",
    re.I,
)
_SAHM = re.compile(r"\bsahm\b.{0,24}([+\-−]\s*\d+\.\d+)", re.I)
_ID_ALIAS = {
    "USREC": "usrec",
    "BLS payrolls": "payrolls",
    "GDP": "gdp",
    "U-3": "unemployment",
    "SAHMREALTIME": "sahm",
    "LEI": "lei",
}

Proposer = Callable[[CiteBag, Packet | None], list[Claim]]


def _slug(series: str, when: str) -> str:
    name = _ID_ALIAS.get(series, re.sub(r"[^a-z0-9]+", "-", series.lower()).strip("-") or "claim")
    raw = re.sub(r"[^a-z0-9]+", "-", f"{name} {when}".lower()).strip("-")
    if raw in _LEFTOVER or not raw:
        raw = f"claim-{raw}" if raw else "claim"
    return raw


def _sign_fall(verb: str, raw: str) -> str:
    compact = re.sub(r"\s+", "", raw)
    if compact.startswith(("−", "-", "+")):
        return "−" + compact.lstrip("−-+") if verb.lower() in {
            "fell", "declined", "dropped", "lost", "decreased", "fell by",
        } or compact.startswith(("−", "-")) else compact
    if verb.lower() in {"fell", "declined", "dropped", "lost", "decreased", "fell by"}:
        return "−" + compact
    return compact


def _excerpt_is_naics(text: str) -> bool:
    return bool(_NAICS.search(text or "")) and not re.search(
        r"nonfarm payroll|employment situation|\bces\b", text or "", re.I
    )


def claims_from_cites(bag: CiteBag) -> list[Claim]:
    """Deterministic cite scan. Fixture-local prints only. No leftover 3-slot ids."""
    claims: list[Claim] = []
    seen: set[str] = set()
    pay: Claim | None = None
    for excerpt in bag.excerpts:
        if _excerpt_is_naics(excerpt.text):
            continue
        fall = _CES_FALL.search(excerpt.text)
        if fall and excerpt.url:
            month = _MONTH_YEAR.search(excerpt.text)
            if not month:
                continue
            when = f"{month.group(1).title()} {month.group(2)}"
            printed = _sign_fall(fall.group(1), fall.group(2))
            claim = Claim(
                series="BLS payrolls",
                print=printed,
                when=when,
                id=_slug("BLS payrolls", when),
                cite_url=excerpt.url,
                claim_span=excerpt.text[:400],
            )
            if not verify_payrolls_realized_ces(claim, bag).ok:
                continue
            if "BLS payrolls" not in seen:
                claims.append(claim)
                seen.add("BLS payrolls")
                pay = claim
    if pay:
        parsed = _parse_when(pay.when)
        if parsed and parsed[0] == "month":
            _, year, month = parsed
            flag = _usrec_month_on_table(bag, year, month)
            if flag in (0, 1):
                url = next(
                    (e.url for e in bag.excerpts if _year_adjacent_month(e.text, year, month) and re.search(r"[|=]\s*[01]\b|usrec", e.text, re.I)),
                    "",
                ) or next((e.url for e in bag.excerpts if "usrec" in (e.title or "").lower() or "fred" in (e.url or "")), "")
                if url:
                    claims.append(
                        Claim(
                            series="USREC",
                            print=str(flag),
                            when=pay.when,
                            id=_slug("USREC", pay.when),
                            cite_url=url,
                            claim_span=f"USREC={flag} ({pay.when})",
                        )
                    )
                    seen.add("USREC")
    blob = "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])
    qbars: dict[tuple[int, int], str] = {}
    for excerpt in bag.excerpts:
        for match in re.finditer(
            r"real gdp (?:increased|rose|grew)\s+(\d+(?:\.\d+)?)\s*%?.{0,40}?"
            r"(?:(?:q([1-4]))|(first|second|third|fourth))\s+(?:quarter\s+)?(?:of\s+)?(20\d{2})",
            excerpt.text,
            re.I | re.S,
        ):
            bar = match.group(1)
            qn = int(match.group(2)) if match.group(2) else {"first": 1, "second": 2, "third": 3, "fourth": 4}[match.group(3).lower()]
            year = int(match.group(4))
            qbars[(year, qn)] = bar
            url = excerpt.url
        for match in re.finditer(
            r"(?:q([1-4])|(first|second|third|fourth))\s+(?:quarter\s+)?(?:of\s+)?(20\d{2})"
            r".{0,40}?real gdp (?:increased|rose|grew)\s+(\d+(?:\.\d+)?)",
            excerpt.text,
            re.I | re.S,
        ):
            qn = int(match.group(1)) if match.group(1) else {"first": 1, "second": 2, "third": 3, "fourth": 4}[match.group(2).lower()]
            year = int(match.group(3))
            qbars[(year, qn)] = match.group(4)
            url = excerpt.url
    if len(qbars) >= 2:
        keys = sorted(qbars)
        (y1, q1), (y2, q2) = keys[-2], keys[-1]
        if y1 == y2:
            printed = f"{qbars[(y1, q1)]} / {qbars[(y2, q2)]}"
            when = f"Q{q2} {y2}"
            gdp_url = next((e.url for e in bag.excerpts if "gdp" in (e.text + e.title).lower()), "")
            if gdp_url and "GDP" not in seen:
                claims.append(
                    Claim(
                        series="GDP",
                        print=printed,
                        when=when,
                        id=f"gdp-{y2}-q{q2}",
                        cite_url=gdp_url,
                        claim_span=f"GDP {printed} in {when}",
                    )
                )
                seen.add("GDP")
    for excerpt in bag.excerpts:
        u3 = _U3.search(excerpt.text)
        month = _MONTH_YEAR.search(excerpt.text)
        if u3 and month and excerpt.url and "U-3" not in seen:
            when = f"{month.group(1).title()} {month.group(2)}"
            claims.append(
                Claim(
                    series="U-3",
                    print=f"{u3.group(1)}%",
                    when=when,
                    id=_slug("U-3", when),
                    cite_url=excerpt.url,
                    claim_span=excerpt.text[:400],
                )
            )
            seen.add("U-3")
        sahm = _SAHM.search(excerpt.text)
        if sahm and excerpt.url and "SAHMREALTIME" not in seen:
            month = _MONTH_YEAR.search(excerpt.text)
            when = f"{month.group(1).title()} {month.group(2)}" if month else ""
            claims.append(
                Claim(
                    series="SAHMREALTIME",
                    print=re.sub(r"\s+", "", sahm.group(1)),
                    when=when,
                    id=_slug("SAHMREALTIME", when),
                    cite_url=excerpt.url,
                    claim_span=excerpt.text[:400],
                )
            )
            seen.add("SAHMREALTIME")
    _ = blob
    return claims


def _vertex_propose(bag: CiteBag, packet: Packet | None) -> list[Claim]:
    """One Vertex call. Cites only. Critic tools still decide READY."""
    payload = {
        "topic": (packet.topic if packet else "") or "",
        "spine": bag.spine,
        "excerpts": [{"url": e.url, "title": e.title, "text": e.text[:800]} for e in bag.excerpts],
        "hit_urls": list(bag.hit_urls),
        "series": sorted(CLOSED_SERIES),
    }
    prompt = (
        "Propose typed Claims from these Parallel cites and spine only. "
        "Each claim: series, print, when, id, cite_url, claim_span. "
        "series must be one of the listed official series. "
        "print and when must appear in the cite or spine. "
        "Do not invent a CES print. Do not use NAICS employment levels as BLS payrolls. "
        "Do not emit leftover timeline-hit/frame/miss ids. "
        "Do not stamp propaganda or an issuer. "
        "Return JSON {\"claims\": [...]} only.\n"
        f"{json.dumps(payload, ensure_ascii=True)}"
    )
    raw = generate_script(prompt)
    text = raw.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    data = json.loads(text)
    rows = data.get("claims") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    out: list[Claim] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if (row.get("id") or "") in _LEFTOVER:
            continue
        try:
            claim = Claim(
                series=str(row.get("series") or ""),
                print=str(row.get("print") or ""),
                when=str(row.get("when") or ""),
                id=str(row.get("id") or _slug(str(row.get("series") or "claim"), str(row.get("when") or ""))),
                cite_url=str(row.get("cite_url") or ""),
                claim_span=str(row.get("claim_span") or "")[:400],
            )
        except Exception:
            continue
        if claim.series == "BLS payrolls" and not verify_payrolls_realized_ces(claim, bag).ok:
            continue
        out.append(claim)
    return out


def propose_claims(
    bag: CiteBag,
    packet: Packet | None = None,
    *,
    proposer: Proposer | None = None,
) -> list[Claim]:
    """Claimer hook. Tests inject proposer. Live: Vertex, else cite scan. No foundry steal."""
    if proposer is not None:
        return list(proposer(bag, packet) or [])
    if config.has_vertex():
        try:
            rows = _vertex_propose(bag, packet)
            if rows:
                return rows
        except (VertexDownError, json.JSONDecodeError, ValueError):
            pass
    return claims_from_cites(bag)


def findings_from_claims(claims: list[Claim], bag: CiteBag | None = None) -> list[Finding]:
    """Map Claimer output → findings. Never leftover ids. Never invent propaganda issuer."""
    out: list[Finding] = []
    used: set[str] = set()
    for claim in claims or []:
        if (claim.id or "") in _LEFTOVER:
            continue
        if claim.series == "BLS payrolls" and bag is not None:
            if not verify_payrolls_realized_ces(claim, bag).ok:
                continue
        fid = claim.id or _slug(claim.series, claim.when)
        if fid in _LEFTOVER:
            fid = _slug(claim.series, claim.when)
        n = 2
        base = fid
        while fid in used:
            fid = f"{base}-{n}"
            n += 1
        used.add(fid)
        span = (claim.claim_span or "").strip() or f"{claim.series}={claim.print} ({claim.when})".strip()
        out.append(
            Finding(
                id=fid,
                claim=span,
                stamp="grounded",
                title=claim.series,
                series=claim.series,
                print=claim.print,
                when=claim.when,
                parallel_url=claim.cite_url or None,
                parallel_status="hit",
                note="Parallel URL on this row.",
                independent=MISSING,
                vested_interest=MISSING,
                propaganda=MISSING,
                propaganda_issuer=MISSING,
                lean=MISSING,
                who_repeats=MISSING,
            )
        )
    return out


def frame_findings(hit_rows: list[Any], miss_rows: list[Any], packet: Packet) -> list[Finding]:
    """Fiction / invented tell: cite-backed frame + miss. No leftover 3-slot. No CES required."""
    findings: list[Finding] = []
    used: set[str] = set()
    hit = next((row for row in (hit_rows or []) if getattr(row, "url", None)), None)
    if hit is not None:
        excerpts = [str(x).strip() for x in (getattr(hit, "excerpts", None) or []) if str(x).strip()]
        claim = excerpts[0] if excerpts else ((getattr(hit, "title", None) or packet.tell or packet.topic or "frame").strip())
        fid = "frame-cite"
        used.add(fid)
        findings.append(
            Finding(
                id=fid,
                claim=claim,
                stamp="grounded",
                title=(getattr(hit, "title", None) or "frame").strip() or "frame",
                series=MISSING,
                print=MISSING,
                parallel_url=getattr(hit, "url", None),
                parallel_status="hit",
                note="Parallel URL on this row. Fiction frame from cite.",
                propaganda=MISSING,
                propaganda_issuer=MISSING,
            )
        )
    for row in miss_rows or []:
        excerpts = [str(x).strip() for x in (getattr(row, "excerpts", None) or []) if str(x).strip()]
        if not excerpts:
            continue
        fid = "frame-miss"
        if fid in used:
            break
        used.add(fid)
        findings.append(
            Finding(
                id=fid,
                claim=excerpts[0],
                stamp="fringe",
                title=(getattr(row, "title", None) or "fringe").strip() or "fringe",
                series=MISSING,
                print=MISSING,
                parallel_url=None,
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
                propaganda=MISSING,
                propaganda_issuer=MISSING,
            )
        )
        break
    return [row for row in findings if row.id not in _LEFTOVER]
