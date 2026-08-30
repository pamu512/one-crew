from __future__ import annotations

import re
from typing import Any

from onecrew.models import (
    EXCLUSION_REASONS,
    MISSING,
    Exclusion,
    Finding,
    Packet,
)
from onecrew.tell import invents_frame


class PackInvalidError(ValueError):
    """Research pack or exclusion row failed a lock."""


_CITE_TOKEN = re.compile(r"\[(?:[a-z0-9_]+\[\d+\]|\d+)\]")
_YEAR = re.compile(r"\b((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+)?((?:19|20)\d{2})\b")
_TEMPLATE_CLAIM = re.compile(
    r"^(Grounded event inside|Widely repeated frame about|Fringe claim about)\b",
    re.I,
)


def render_task_content(content: Any) -> str:
    """Task pro output as readable thesis prose. Never a Python dict dump."""
    if content is None:
        return ""
    if isinstance(content, dict):
        chunks: list[str] = []
        for key, val in content.items():
            title = str(key or "").replace("_", " ").strip() or "Section"
            title = title[:1].upper() + title[1:]
            if isinstance(val, list):
                body = "\n".join(str(item) for item in val)
            elif isinstance(val, dict):
                body = render_task_content(val)
            else:
                body = str(val)
            chunks.append(f"### {title}\n\n{_clean_task_text(body)}")
        return "\n\n".join(chunks).strip()
    return _clean_task_text(str(content))


def _clean_task_text(text: str) -> str:
    cleaned = (text or "").replace("\\n", "\n")
    cleaned = _CITE_TOKEN.sub("", cleaned)
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", cleaned)
    cleaned = re.sub(r"[ \t]+\n", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(r"[ ]{2,}", " ", cleaned)
    return cleaned.strip()


def is_template_claim(claim: str) -> bool:
    return bool(_TEMPLATE_CLAIM.match((claim or "").strip()))


def facts_from_spine(spine: str) -> list[dict[str, str]]:
    """Dated, numbered sentences already in the Task spine. Nothing invented."""
    facts: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw in _spine_lines(spine):
        line = _clean_task_text(raw).strip(" -*|")
        if line.count("|") >= 2:
            cols = [c.strip() for c in line.strip("|").split("|")]
            if not cols or cols[0].lower() in {"date", "sourced event"} or set(cols[0]) <= {"-"}:
                continue
            line = f"{cols[0]}: {cols[1]}" if len(cols) > 1 else cols[0]
        if len(line) < 24 or len(line) > 280:
            continue
        low = line.lower()
        if not _YEAR.search(line) and not any(
            key in low for key in ("nber", "usrec", "payroll", "gdp", "sahm", "lei", "fred")
        ):
            continue
        if not re.search(r"\d", line) and "nber" not in low:
            continue
        if low in seen:
            continue
        seen.add(low)
        when = ""
        found = _YEAR.search(line)
        if found:
            when = found.group(0).strip()
        spoken = re.split(r"\s*->\s*", line, maxsplit=1)[0]
        spoken = re.sub(r"^[A-Z][A-Za-z0-9 /&'-]{1,40}:\s+", "", spoken).strip()
        facts.append({"when": when, "claim": spoken.rstrip(".") + "."})
        if len(facts) >= 8:
            break
    return facts


def _spine_lines(spine: str) -> list[str]:
    text = spine or ""
    out: list[str] = []
    for block in re.split(r"\n+", text):
        if re.match(r"^\s*[-*]\s+", block):
            out.append(re.sub(r"^\s*[-*]\s+", "", block))
            continue
        out.extend(re.split(r"(?<=\.)\s+(?=[A-Z*-])", block))
    return out


def topic_claim_text(packet: Packet) -> str:
    """Topic + finding claims only. Leftover exclusion titles do not unlock Hormuz."""
    parts = [packet.topic or "", packet.hook or ""]
    receipt = packet.receipt
    if receipt:
        for finding in receipt.findings:
            parts.extend([finding.claim, finding.title or "", finding.when or ""])
    return " ".join(parts).lower()


def seed_exclusions() -> list[Exclusion]:
    return [
        Exclusion(
            what="The 2018 JCPOA exit caused the 2023-2024 Hormuz panic.",
            reason="parallel_miss",
            detail="Causal link is on the receipt as missing. Not drawn as fact.",
        )
    ]


def hits_accounted(hit_urls: list[str], packet: Packet) -> bool:
    """Every Parallel hit URL is a finding or an exclusion. Silent drop fails."""
    cited = {f.parallel_url for f in (packet.receipt.findings if packet.receipt else []) if f.parallel_url}
    left = {ex.url for ex in packet.exclusions if ex.url}
    return all(url in cited or url in left for url in hit_urls if url)


def require_hits_accounted(hit_urls: list[str], packet: Packet) -> None:
    if not hits_accounted(hit_urls, packet):
        raise PackInvalidError("silent drop of a Parallel hit")


def leftover_hit_exclusions(
    rows: list,
    kept_urls: set[str],
    *,
    reason: str,
    detail: str,
) -> list[Exclusion]:
    """Cite Parallel hits that did not make the findings list. Never invent a title."""
    if reason not in EXCLUSION_REASONS:
        raise PackInvalidError("exclusion reason is not on the closed list")
    out: list[Exclusion] = []
    seen: set[str] = set()
    for item in rows:
        url = getattr(item, "url", None)
        if not url or url in kept_urls or url in seen:
            continue
        seen.add(url)
        title = (getattr(item, "title", None) or "").strip()
        # ponytail: Parallel title or the URL. Never invent a page name.
        out.append(Exclusion(what=title or url, reason=reason, detail=detail, url=url))
    return out


def validate_exclusions(packet: Packet) -> None:
    receipt = packet.receipt
    known_claims = {f.claim for f in (receipt.findings if receipt else [])}
    known_links = {link.claim for link in (receipt.causal_links if receipt else [])}
    for row in packet.exclusions:
        if row.reason not in EXCLUSION_REASONS:
            raise PackInvalidError("exclusion reason is not on the closed list")
        what = (row.what or "").strip()
        if not what:
            raise PackInvalidError("exclusion needs a what")
        if row.url:
            continue
        if what in known_claims or what in known_links:
            continue
        if row.reason in {"rails_down", "not_searched"}:
            continue
        raise PackInvalidError("invented exclusion title without a Parallel row")


def _join(value: str | list[str] | None) -> str:
    if value is None or value == MISSING:
        return MISSING
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or MISSING
    return str(value)


def _collision_for(finding: Finding, packet: Packet) -> str:
    for beat in packet.beats:
        if finding.id in beat.finding_ids and beat.collision and beat.collision != MISSING:
            extra = f" at {beat.collision_url}" if beat.collision_url else ""
            return f"{beat.collision}{extra}"
    return MISSING


def _citation_title(finding: Finding) -> str:
    title = (finding.title or "").strip()
    if title and title != MISSING:
        return title
    return "title missing"


def _finding_prose(finding: Finding, packet: Packet) -> str:
    url = finding.parallel_url or "no URL"
    when = finding.when or "date missing"
    issuer = ""
    if finding.propaganda_issuer and finding.propaganda_issuer != MISSING:
        issuer = f" The named issuer is {finding.propaganda_issuer}."
    fringe = ""
    if finding.stamp == "fringe":
        fringe = " This stays in the thesis, tagged fringe, and is never sold as fact."
    house = ""
    if finding.propaganda == "yes":
        house = " Propaganda stays marked yes on this row."
    return (
        f"[{finding.id}] {finding.claim} "
        f"The full citation is {_citation_title(finding)}, {url} ({when}). "
        f"The stamp is {finding.stamp} (grounded|mainstream|fringe). "
        f"parallel = {finding.parallel_status}. "
        f"lean = {_join(finding.lean)}. "
        f"interests = {_join(finding.interests)}. "
        f"who_repeats = {_join(finding.who_repeats)}. "
        f"independent = {finding.independent}. "
        f"vested_interest = {_join(finding.vested_interest)}. "
        f"propaganda = {finding.propaganda}.{issuer} "
        f"collision = {_collision_for(finding, packet)}."
        f"{house}{fringe} {finding.note}"
    )


def _timeline_prose(packet: Packet) -> str:
    receipt = packet.receipt
    if not receipt or not receipt.findings:
        return "No receipt rows. Nothing was invented to fill the page."
    hits = [f for f in receipt.findings if f.parallel_status == "hit"]
    if not hits:
        return "No Parallel-sourced event made the timeline. The hole stays visible."
    parts = [
        "The timeline below uses only Parallel-sourced events. Mainstream scares and fringe rumors are kept in the bibliography, tagged. Missing links are named, not drawn."
    ]
    for finding in hits:
        parts.append(
            f"In {finding.when or 'an unsourced year'}, {finding.claim.rstrip('.')} [{finding.id}]."
        )
    links = receipt.causal_links or []
    missing = [link for link in links if not link.parallel_url]
    if missing:
        for link in missing:
            parts.append(
                f"We do not have a sourced chain that {link.claim.rstrip('.')} [{link.id}]. That link is explicitly missing."
            )
    return " ".join(parts)


def _argument_prose(packet: Packet) -> str:
    receipt = packet.receipt
    if not receipt or not receipt.findings:
        return (
            "No Parallel rows. The thesis names that gap instead of inventing a source to fatten the page."
        )
    grounded = [f for f in receipt.findings if f.stamp == "grounded"]
    mainstream = [f for f in receipt.findings if f.stamp == "mainstream"]
    fringe = [f for f in receipt.findings if f.stamp == "fringe"]
    parts = [
        "This argument uses only the citations Parallel returned and the honest holes. "
        "Lean, tell, and tone change the later script. They do not restamp these rows."
    ]
    if packet.task_spine:
        parts.append(packet.task_spine)
    if grounded:
        bits = "; ".join(f"{f.claim.rstrip('.')} [{f.id}]" for f in grounded)
        parts.append(f"The grounded record, Parallel-sourced where marked hit, is this: {bits}.")
    if mainstream:
        bits = "; ".join(f"{f.claim.rstrip('.')} [{f.id}]" for f in mainstream)
        parts.append(
            f"Mainstream frames stay in the thesis as widely repeated lines, not as sources: {bits}."
        )
    if fringe:
        bits = "; ".join(f"{f.claim.rstrip('.')} [{f.id}]" for f in fringe)
        parts.append(f"Fringe stays in the thesis, tagged, and is never sold as fact: {bits}.")
    missing_links = [link for link in (receipt.causal_links or []) if not link.parallel_url]
    if missing_links:
        bits = "; ".join(f"{link.claim.rstrip('.')} [{link.id}]" for link in missing_links)
        parts.append(f"Causal links Parallel did not source stay named as missing: {bits}.")
    return "\n\n".join(part.strip() for part in parts if part.strip())


def write_desk_card(packet: Packet) -> str:
    """One page a desk can record from. Not a license and not a clearance."""
    receipt = packet.receipt
    held = bool(receipt and receipt.disposition == "HOLD")
    can: list[str] = []
    cannot: list[str] = []
    cites: list[str] = []
    if held:
        cannot.append(
            f"Do not record this VO. HOLD: {(receipt.hold_reason if receipt else '') or 'receipt held'}."
        )
        can.append("Nothing. The receipt is HOLD.")
    elif receipt:
        for finding in receipt.findings:
            claim = (finding.claim or "").strip()
            if not claim or is_template_claim(claim):
                continue
            if finding.stamp == "grounded":
                can.append(claim)
                if finding.parallel_url:
                    cites.append(finding.parallel_url)
            else:
                cannot.append(f"Do not sell as fact: {claim}")
        if not can:
            can.append("Nothing grounded is on this card yet.")
    else:
        can.append("Nothing grounded is on this card yet.")
    if packet.cut and not invents_frame(cut=packet.cut, tell=packet.tell or ""):
        cannot.append("Do not invent a family, named civilians, or a kitchen-radio scene.")
    cannot.append("Do not invent numbers or dates that are not on the You can say list.")
    for beat in packet.beats:
        title = (beat.collision_title or "").strip()
        if beat.collision == "yes" and title and title != MISSING:
            cannot.append(f"Do not copy this title on air: {title}")
    if packet.collision_disposition == "HOLD":
        cannot.append(
            f"Collision is HOLD. {packet.collision_hold_reason or 'No search ran.'} That is not a clearance."
        )

    def bullets(rows: list[str]) -> str:
        return "\n".join(f"- {row}" for row in rows) if rows else "- None on this card."

    body = "\n".join(
        [
            "## Desk card",
            "",
            "Read this first. Tape is not a license. Collision is not a clearance. The floor does not post.",
            "",
            "### You can say",
            "",
            bullets(can),
            "",
            "### Do not say",
            "",
            bullets(cannot),
            "",
            "### Cite",
            "",
            bullets(cites) if cites else "- No grounded URL on this card.",
            "",
            "### Legal",
            "",
            "- Sourced footage is someone else's tape. We do not license it.",
            "- A collision=yes row is a match list, not a copyright clearance.",
            "- This pack is not legal advice.",
        ]
    )
    packet.desk_card = body
    return body


def write_research_pack(packet: Packet, hit_urls: list[str] | None = None) -> Packet:
    """Always-written thesis. Lean/tone/tell do not rewrite stamps."""
    validate_exclusions(packet)
    if hit_urls is not None:
        require_hits_accounted(hit_urls, packet)
    receipt = packet.receipt
    held = receipt.disposition == "HOLD" if receipt else False
    hold_line = ""
    if held:
        hold_line = (
            f" This run is HOLD. {receipt.hold_reason or 'The receipt was held.'} "
            "The pack still records what ran, what missed, and why."
        )
    topic = packet.topic or packet.hook or "No topic on this packet."
    question = topic
    lines: list[str] = [
        f"# Research pack · {packet.id}",
        "",
        write_desk_card(packet),
        "",
        "## Question",
        "",
        f"The topic under study is {topic}. The working question is {question}.{hold_line} "
        "This document is the citable thesis for that question. It is not a stamp list "
        "and it is not a script. The script, if written, is a later telling of this record.",
        "",
        "## Picks",
        "",
        (
            f"The ask is a {packet.cut or 'unset-cut'} for {packet.platform or 'no platform'}, "
            f"depth {packet.depth or 'none'}."
        ),
        "",
        "## Tell",
        "",
        (
            f"The tell is {packet.tell or 'no tell'}. Tell is how the later script is voiced. "
            "It does not restamp sources."
        ),
        "",
        "## Tone",
        "",
        (
            f"The tone is {packet.tone or 'none'}. Tone is host stance, not a source stamp. "
            f"Script lean is {packet.script_lean or 'none'} (voice only; does not restamp)."
        ),
        "",
        "## Timeline of what led here",
        "",
        _timeline_prose(packet),
        "",
        "## Argument",
        "",
        _argument_prose(packet),
        "",
        "## Sources",
        "",
    ]
    if receipt and receipt.findings:
        lines.append(
            "Bibliography. Each finding keeps every stamp. Lean and tone do not rewrite these fields."
        )
        for finding in receipt.findings:
            lines.append("")
            lines.append(_finding_prose(finding, packet))
    else:
        lines.append("No findings. The thesis names the gap instead of inventing a source.")
    lines.extend(["", "## Causal links", ""])
    if receipt and receipt.causal_links:
        for link in receipt.causal_links:
            status = "sourced" if link.parallel_url else "explicitly missing"
            lines.append(
                f"{link.claim} [{link.id}] is {status}. stamp={link.stamp}. "
                "We do not invent a 40-year chain to close the page."
            )
    else:
        lines.append("No causal link on the receipt. Missing, not invented.")
    lines.extend(["", "## What we could not find", ""])
    misses = [f for f in (receipt.findings if receipt else []) if f.parallel_status == "miss"]
    if misses:
        for finding in misses:
            lines.append(
                f"Parallel missed [{finding.id}]: {finding.claim} Tagged {finding.stamp}, never sold as fact."
            )
    else:
        lines.append("No Parallel miss on the finding list.")
    if held:
        lines.append(f"HOLD: {receipt.hold_reason or 'receipt held'}.")
    lines.extend(["", "## Left out / not included", ""])
    if packet.exclusions:
        for row in packet.exclusions:
            url = row.url or "no URL"
            lines.append(
                f"Left out: {row.what}. URL: {url}. reason={row.reason}. {row.detail}".rstrip()
            )
    else:
        lines.append("No exclusion rows. Hits were not silently dropped.")
    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "This pack is a citable thesis plus the holes. It is not a clearance. The floor does not post it.",
        ]
    )
    packet.research_pack = "\n".join(lines).strip() + "\n"
    return packet
