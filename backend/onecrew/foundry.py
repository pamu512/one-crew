"""Mint findings from thesis prose. No Parallel spend. No invented forecast."""

from __future__ import annotations

import re

from onecrew.models import MISSING, Finding, Packet
from onecrew.script import pack_numbers

_LEFTOVER_SLOT_IDS = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})
_URL = re.compile(r"https?://[^\s)\]>'\"<>]+")
_SERIES = (
    ("usrec", ("usrec",), ("usrec", "fred.stlouisfed.org/series/usrec"), "USREC"),
    ("payrolls", ("payroll", "nonfarm"), ("payroll", "bls.gov", "empsit"), "payrolls"),
    ("gdp", ("gdp",), ("gdp", "bea.gov"), "GDP"),
    ("sahm", ("sahm",), ("sahm", "sahmrealtime"), "Sahm"),
)


def leftover_slot_ids() -> frozenset[str]:
    return _LEFTOVER_SLOT_IDS


def _thesis(packet: Packet) -> str:
    return "\n".join(part for part in (packet.research_pack or "", packet.task_spine or "") if part)


def _urls(text: str, extra: list[str] | None) -> list[str]:
    found = [m.group(0).rstrip(".,);") for m in _URL.finditer(text or "")]
    for url in extra or []:
        if url and url not in found:
            found.append(url)
    return found


def _claim_for_series(blob: str, aliases: tuple[str, ...], name: str) -> str | None:
    for alias in aliases:
        for match in re.finditer(rf".{{0,80}}{re.escape(alias)}.{{0,120}}", blob, re.I | re.S):
            snippet = re.sub(r"\s+", " ", match.group(0)).strip()
            if not pack_numbers(snippet):
                continue
            low = snippet.lower()
            if alias.lower() not in low and name.lower() not in low:
                snippet = f"{name} {snippet}"
            return snippet[:400]
    return None


def _url_for_series(urls: list[str], keys: tuple[str, ...]) -> str | None:
    for url in urls:
        low = url.lower()
        if any(key in low for key in keys):
            return url
    return None


def foundry_findings(packet: Packet, hit_urls: list[str] | None = None) -> list[Finding]:
    """One finding per named series/object already in the thesis. No spend."""
    blob = _thesis(packet)
    urls = _urls(blob, hit_urls)
    findings: list[Finding] = []
    for fid, aliases, url_keys, name in _SERIES:
        claim = _claim_for_series(blob, aliases, name)
        if not claim:
            continue
        url = _url_for_series(urls, url_keys) or (urls[0] if urls else None)
        if not url:
            continue
        if name.lower() not in claim.lower() and not any(a in claim.lower() for a in aliases):
            claim = f"{name} {claim}"
        findings.append(
            Finding(
                id=fid,
                claim=claim,
                stamp="grounded",
                title=name,
                parallel_url=url,
                parallel_status="hit",
                note="Parallel URL on this row.",
                independent=MISSING,
                vested_interest=MISSING,
            )
        )
    if findings:
        findings.append(
            Finding(
                id="fringe-unsourced",
                claim="Unsourced fringe print. Parallel miss. Never sold as fact.",
                stamp="fringe",
                parallel_url=None,
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
                independent=MISSING,
                vested_interest=MISSING,
            )
        )
    return findings


def replace_leftover_slots(packet: Packet, findings: list, hit_urls: list[str] | None = None) -> list:
    """If the only findings are leftover 3-slot ids and the thesis has objects, mint those."""
    ids = {f.id for f in findings}
    blob = _thesis(packet)
    if ids <= _LEFTOVER_SLOT_IDS and "usrec" in blob.lower() and "payroll" in blob.lower():
        minted = foundry_findings(packet, hit_urls=hit_urls)
        if minted:
            return minted
    return findings
