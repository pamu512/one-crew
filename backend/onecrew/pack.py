from __future__ import annotations

from onecrew.models import (
    EXCLUSION_REASONS,
    MISSING,
    Exclusion,
    Finding,
    Packet,
)


class PackInvalidError(ValueError):
    """Research pack or exclusion row failed a lock."""


_STAMP_FIELDS = (
    "stamp",
    "parallel_status",
    "lean",
    "interests",
    "who_repeats",
    "independent",
    "vested_interest",
    "propaganda",
    "propaganda_issuer",
)


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


def validate_exclusions(packet: Packet) -> None:
    receipt = packet.receipt
    known_claims = {f.claim for f in (receipt.findings if receipt else [])}
    known_links = {link.claim for link in (receipt.causal_links if receipt else [])}
    known_urls = {f.parallel_url for f in (receipt.findings if receipt else []) if f.parallel_url}
    known_urls |= {link.parallel_url for link in (receipt.causal_links if receipt else []) if link.parallel_url}
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


def _finding_block(finding: Finding, packet: Packet) -> str:
    collide = ""
    for beat in packet.beats:
        if finding.id in beat.finding_ids and beat.collision and beat.collision != MISSING:
            collide = f"{beat.collision} {beat.collision_url or ''}".strip()
            break
    title = finding.claim.rstrip(".")
    url = finding.parallel_url or "no URL"
    when = finding.when or "date missing"
    return (
        f"### {finding.id}\n"
        f"{title}. Cited as {url} ({when}).\n"
        f"The claim on the row: {finding.claim}\n"
        f"stamps: grounded|mainstream|fringe = {finding.stamp}; "
        f"parallel = {finding.parallel_status}; "
        f"lean = {_join(finding.lean)}; "
        f"interests = {_join(finding.interests)}; "
        f"who_repeats = {_join(finding.who_repeats)}; "
        f"independent = {finding.independent}; "
        f"vested_interest = {_join(finding.vested_interest)}; "
        f"propaganda = {finding.propaganda}"
        f"{(' · issuer ' + finding.propaganda_issuer) if finding.propaganda_issuer and finding.propaganda_issuer != MISSING else ''}"
        f"{('; collision ' + collide) if collide else ''}.\n"
        f"{finding.note}\n"
    )


def write_research_pack(packet: Packet) -> Packet:
    """Always-written thesis. Lean/tone/tell do not rewrite stamps."""
    validate_exclusions(packet)
    receipt = packet.receipt
    lines: list[str] = [
        f"# Research pack · {packet.id}",
        "",
        "## Question",
        packet.topic or packet.hook or "No topic on this packet.",
        "",
        "## Picks",
        f"platform: {packet.platform or 'none'}",
        f"cut: {packet.cut or 'none'}",
        f"depth: {packet.depth or 'none'}",
        f"script lean: {packet.script_lean or 'none'} (voice only; does not restamp)",
        f"tell: {packet.tell or 'none'}",
        f"tone: {packet.tone or 'none'}",
        "",
        "## Timeline of what led here",
    ]
    if receipt and receipt.findings:
        sourced = [f for f in receipt.findings if f.parallel_status == "hit"]
        if sourced:
            for finding in sourced:
                lines.append(f"- {finding.when or 'undated'}: {finding.claim} [{finding.id}]")
        else:
            lines.append("No Parallel-sourced event made the timeline. The hole stays visible.")
    else:
        lines.append("No receipt rows. Nothing was invented to fill the page.")
    lines.extend(["", "## Sources"])
    if receipt and receipt.findings:
        for finding in receipt.findings:
            lines.append(_finding_block(finding, packet))
    else:
        lines.append("No findings. The thesis names the gap instead of inventing a source.")
    lines.extend(["", "## Causal links"])
    if receipt and receipt.causal_links:
        for link in receipt.causal_links:
            status = "sourced" if link.parallel_url else "explicitly missing"
            lines.append(f"- {link.claim} [{link.id}] — {status}. stamp={link.stamp}.")
    else:
        lines.append("No causal link on the receipt. Missing, not invented.")
    lines.extend(["", "## What we could not find"])
    misses = [f for f in (receipt.findings if receipt else []) if f.parallel_status == "miss"]
    if misses:
        for finding in misses:
            lines.append(f"- {finding.claim} [{finding.id}] — Parallel miss. Tagged {finding.stamp}, never sold as fact.")
    else:
        lines.append("No Parallel miss on the finding list.")
    if receipt and receipt.disposition == "HOLD":
        lines.append(f"HOLD: {receipt.hold_reason or 'receipt held'}.")
    lines.extend(["", "## Left out / not included"])
    if packet.exclusions:
        for row in packet.exclusions:
            url = f" {row.url}" if row.url else ""
            lines.append(f"- {row.what}{url} — reason={row.reason}. {row.detail}".rstrip())
    else:
        lines.append("No exclusion rows. Hits were not silently dropped.")
    lines.extend(
        [
            "",
            "## How to read this",
            "This pack is a citable thesis plus the holes. It is not a clearance. The floor does not post it.",
        ]
    )
    packet.research_pack = "\n".join(lines).strip() + "\n"
    return packet
