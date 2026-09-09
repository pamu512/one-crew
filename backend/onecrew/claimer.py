"""Vertex ADK Claimer. Proposes typed Claims from cites/spine only.

Parallel is citations. verify.py is the authority. Foundry is a v1 candidate, not READY.
"""

from __future__ import annotations

import json
import re
from typing import Any, Callable

from onecrew import config
from onecrew.foundry import (
    _has_usrec_and_payrolls,
    leftover_slot_ids,
    gdp_quarter_bars,
    _gdp_print_from_bars,
    _legal_print,
    _when,
    clean_cite_url,
    _url_fits_series,
    align_sahm_pair,
    latest_sahm_cell,
)
from onecrew.models import MISSING, Finding, Packet
from onecrew.verify import (
    CLOSED_SERIES,
    Claim,
    CiteBag,
    _parse_when,
    _usrec_month_on_table,
    _year_adjacent_month,
    resolve_missing_cite,
    verify_payrolls_realized_ces,
    verify_sahm_cell,
    verify_u3_ces,
)
from onecrew.vertex_client import VertexDownError, generate_script

_LEFTOVER = leftover_slot_ids()
_NAICS = re.compile(r"\bnaics\b|payroll services|employment level", re.I)
_CES_FALL = re.compile(
    r"(?:total\s+)?nonfarm payroll(?:s| employment)\s+"
    r"(fell|declined|dropped|lost|decreased|rose|gained|increased|fell by)\s+"
    r"(?:by\s+)?([+\-−]?\s*[\d,]+(?:\.\d+)?\s*k?)",
    re.I,
)
_MONTH_YEAR = re.compile(
    r"(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(20\d{2})",
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
    bag_blob = "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])
    notes_fall = bool(re.search(r"\b(fell|dropped|declined|lost|decreased|down)\b", bag_blob, re.I))
    ces_hits: list[Claim] = []
    for excerpt in bag.excerpts:
        if _excerpt_is_naics(excerpt.text):
            continue
        if re.search(r"\bpayems\b|employment level", excerpt.text, re.I) and not re.search(
            r"nonfarm payroll|employment situation|\bces\b", excerpt.text, re.I
        ):
            continue
        for fall in _CES_FALL.finditer(excerpt.text):
            month = _MONTH_YEAR.search(excerpt.text[max(0, fall.start() - 80) : fall.end() + 48]) or _MONTH_YEAR.search(excerpt.text)
            if not month or not excerpt.url:
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
            ces_hits.append(claim)
    if notes_fall:
        ces_hits = [c for c in ces_hits if (c.print or "").startswith(("−", "-"))]
    if ces_hits:
        def _when_key(claim: Claim) -> tuple[int, int]:
            parsed = _parse_when(claim.when)
            return (parsed[1], parsed[2]) if parsed else (0, 0)

        pay = max(ces_hits, key=_when_key)
        claims.append(pay)
        seen.add("BLS payrolls")
    if pay:
        parsed = _parse_when(pay.when)
        if parsed and parsed[0] == "month":
            _, year, month = parsed
            flag = _usrec_month_on_table(bag, year, month)
            if flag not in (0, 1):
                search = "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])
                if _year_adjacent_month(search, year, month):
                    eq = re.search(r"usrec[^\n.]{0,48}=\s*([01])\b", search, re.I)
                    if eq:
                        flag = int(eq.group(1))
            if flag in (0, 1):
                url = next(
                    (e.url for e in bag.excerpts if re.search(r"usrec", f"{e.title} {e.text}", re.I)),
                    "",
                ) or next((e.url for e in bag.excerpts if "fred" in (e.url or "")), "")
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
    gdp_blob = "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])
    gdp_printed = _gdp_print_from_bars(gdp_quarter_bars(gdp_blob)) or _legal_print("GDP", gdp_blob)
    if gdp_printed and "/" in gdp_printed and "GDP" not in seen:
        when = _when(gdp_blob, "GDP", gdp_blob, gdp_printed)
        if not when:
            dated = [k for k, _v in gdp_quarter_bars(gdp_blob) if k[0]]
            if dated:
                y2, q2 = dated[-1]
                when = f"Q{q2} {y2}"
        q = re.search(r"Q([1-4])\s+(20\d{2})", when or "", re.I)
        gdp_url = next(
            (
                e.url
                for e in bag.excerpts
                if all(
                    re.sub(r"[^\d.]+", "", part) in (e.text or "").replace(",", "")
                    for part in gdp_printed.split("/")
                    if part.strip()
                )
            ),
            "",
        ) or next((e.url for e in bag.excerpts if "gdp" in (e.text + e.title).lower()), "")
        if gdp_url and q:
            y2, q2 = int(q.group(2)), int(q.group(1))
            claims.append(
                Claim(
                    series="GDP",
                    print=gdp_printed,
                    when=when,
                    id=f"gdp-{y2}-q{q2}",
                    cite_url=gdp_url,
                    claim_span=f"GDP {gdp_printed} in {when}",
                )
            )
            seen.add("GDP")
    for excerpt in bag.excerpts:
        u3 = _U3.search(excerpt.text)
        month = _MONTH_YEAR.search(excerpt.text)
        if u3 and month and excerpt.url and "U-3" not in seen:
            if not _url_fits_series(excerpt.url, "U-3", ()):
                continue
            when = f"{month.group(1).title()} {month.group(2)}"
            claim = Claim(
                series="U-3",
                print=f"{u3.group(1)}%",
                when=when,
                id=_slug("U-3", when),
                cite_url=excerpt.url,
                claim_span=excerpt.text[:400],
            )
            if not verify_u3_ces(claim, bag).ok:
                continue
            claims.append(claim)
            seen.add("U-3")
        sahm_blob = f"{excerpt.text}\n{bag_blob}"
        cell = latest_sahm_cell(sahm_blob)
        sahm = _SAHM.search(excerpt.text)
        if excerpt.url and "SAHMREALTIME" not in seen and (cell or sahm):
            if sahm and not cell:
                printed = re.sub(r"\s+", "", sahm.group(1))
                month = _MONTH_YEAR.search(excerpt.text)
                when = f"{month.group(1).title()} {month.group(2)}" if month else ""
                when, printed = align_sahm_pair(when, printed, sahm_blob)
            else:
                when, printed = cell
                when, printed = align_sahm_pair(when, printed, sahm_blob)
            cite = clean_cite_url(excerpt.url)
            if not cite:
                continue
            claims.append(
                Claim(
                    series="SAHMREALTIME",
                    print=printed,
                    when=when,
                    id=_slug("SAHMREALTIME", when),
                    cite_url=cite,
                    claim_span=excerpt.text[:400],
                )
            )
            seen.add("SAHMREALTIME")
    if _has_usrec_and_payrolls(bag_blob) and (
        "USREC" not in seen or "BLS payrolls" not in seen
    ):
        # ponytail: incomplete cite scan yields to foundry. Do not READY a GDP-only set.
        return []
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
        if claim.series == "U-3" and not verify_u3_ces(claim, bag).ok:
            continue
        out.append(claim)
    return out


def _fill_missing_series(claims: list[Claim], bag: CiteBag) -> list[Claim]:
    """Cite-scan series Vertex omitted. Not a second Vertex/Parallel call."""
    have = {claim.series for claim in claims}
    extra: list[Claim] = []
    for claim in claims_from_cites(bag):
        if claim.series in have:
            continue
        extra.append(claim)
        have.add(claim.series)
    return list(claims) + extra


def _align_sahm_when(claims: list[Claim], bag: CiteBag) -> list[Claim]:
    """when+print must be one FRED cell. Remap. Do not invent a minus."""
    blob = "\n".join([*(e.text for e in bag.excerpts), bag.spine or ""])
    out: list[Claim] = []
    for claim in claims:
        if claim.series == "SAHMREALTIME":
            when, printed = align_sahm_pair(claim.when, claim.print, blob)
            if when and when != claim.when:
                claim.when = when
                claim.id = _slug("SAHMREALTIME", when)
            if printed:
                claim.print = printed
            if when:
                claim.id = _slug("SAHMREALTIME", when)
        out.append(claim)
    return out


def _align_usrec_smash(claims: list[Claim], bag: CiteBag) -> list[Claim]:
    """USREC when = payrolls month when that month is 0/1 on the FRED pipe. No invent."""
    pay = next((c for c in claims if c.series == "BLS payrolls"), None)
    usrec = next((c for c in claims if c.series == "USREC"), None)
    if pay is None or usrec is None:
        return claims
    parsed = _parse_when(pay.when)
    if parsed is None or parsed[0] != "month":
        return claims
    _, year, month = parsed
    flag = _usrec_month_on_table(bag, year, month)
    if flag not in (0, 1):
        return claims
    usrec.print = str(flag)
    usrec.when = pay.when
    usrec.id = _slug("USREC", pay.when)
    usrec.claim_span = f"USREC={flag} ({pay.when})"
    return claims


def propose_claims(
    bag: CiteBag,
    packet: Packet | None = None,
    *,
    proposer: Proposer | None = None,
) -> list[Claim]:
    """Claimer hook. Tests inject proposer. Live: Vertex, else cite scan. No foundry steal."""
    rows: list[Claim] = []
    if proposer is not None:
        rows = list(proposer(bag, packet) or [])
    elif config.has_vertex():
        try:
            rows = _vertex_propose(bag, packet)
        except (VertexDownError, json.JSONDecodeError, ValueError):
            rows = []
    if not rows:
        rows = claims_from_cites(bag)
    else:
        rows = [c for c in rows if c.series != "U-3" or verify_u3_ces(c, bag).ok]
        rows = _align_usrec_smash(_align_sahm_when(rows, bag), bag)
        rows = [c for c in rows if c.series != "SAHMREALTIME" or verify_sahm_cell(c, bag).ok]
        rows = _fill_missing_series(rows, bag)
    return _align_usrec_smash(_align_sahm_when(rows, bag), bag)


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
        if claim.series == "U-3" and bag is not None:
            if not verify_u3_ces(claim, bag).ok:
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
        cite = clean_cite_url(claim.cite_url or "")
        if not cite and bag is not None:
            cite = clean_cite_url((resolve_missing_cite(claim, bag).cite_url or ""))
        if not cite and claim.series == "LEI":
            continue
        if claim.series == "U-3" and (not cite or not _url_fits_series(cite, "U-3", ())):
            continue
        out.append(
            Finding(
                id=fid,
                claim=span,
                stamp="grounded",
                title=claim.series,
                series=claim.series,
                print=claim.print,
                when=claim.when,
                parallel_url=cite or None,
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
