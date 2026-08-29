from __future__ import annotations

from onecrew.models import (
    INDEPENDENT,
    MISSING,
    STAMPS,
    CausalLink,
    Finding,
    Packet,
    Rails,
    Receipt,
    ShotFrame,
)

GROUNDED = "grounded"
MAINSTREAM = "mainstream"
FRINGE = "fringe"


class ReceiptWriteOnceError(RuntimeError):
    """A written receipt cannot be overwritten."""


class ReceiptInvalidError(ValueError):
    """Stamp / hit-miss / source rules failed."""


def _url_ok(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


def _attr_filled(value: str | list[str] | None) -> bool:
    if value is None or value == MISSING:
        return False
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    return bool(str(value).strip())


def _validate_attr(name: str, value: str | list[str] | None, url: str | None) -> None:
    """Gemini cannot invent lean, interests, or who_repeats. Parallel hit or missing."""
    if _attr_filled(value):
        if not _url_ok(url):
            raise ReceiptInvalidError(
                f"{name} requires a Parallel hit; otherwise {name}={MISSING}"
            )
        return
    if value != MISSING:
        raise ReceiptInvalidError(f"{name} must be {MISSING} or Parallel-sourced")
    if url:
        raise ReceiptInvalidError(f"{name}={MISSING} cannot carry a Parallel URL")


def validate_attribution(finding: Finding) -> None:
    """Lean is not the stamp. Widely repeated is not who_repeats. No guessed lobby."""
    _validate_attr("lean", finding.lean, finding.lean_url)
    _validate_attr("interests", finding.interests, finding.interests_url)
    _validate_attr("who_repeats", finding.who_repeats, finding.who_repeats_url)
    validate_source_stake(finding)


def validate_source_stake(finding: Finding) -> None:
    """independent / vested_interest: Parallel hit for that fact, or missing. No invented parent."""
    if finding.independent not in INDEPENDENT:
        raise ReceiptInvalidError("independent must be yes, no, or missing")
    if finding.independent != MISSING and not _url_ok(finding.independent_url):
        raise ReceiptInvalidError("independent requires a Parallel hit; otherwise independent=missing")
    if finding.independent == MISSING and finding.independent_url:
        raise ReceiptInvalidError("independent=missing cannot carry a Parallel URL")
    _validate_attr("vested_interest", finding.vested_interest, finding.vested_interest_url)


def validate_causal_link(link: CausalLink) -> None:
    """A causal link without a Parallel hit cannot be grounded. Do not invent a chain."""
    if link.stamp == GROUNDED:
        if not _url_ok(link.parallel_url):
            raise ReceiptInvalidError("causal link without a Parallel hit cannot be grounded")
        return
    if link.stamp != MISSING:
        raise ReceiptInvalidError("causal link stamp is grounded or missing")
    if link.parallel_url:
        raise ReceiptInvalidError("missing causal link cannot carry a Parallel URL")


def validate_finding(finding: Finding) -> None:
    if finding.stamp not in STAMPS:
        raise ReceiptInvalidError(f"stamp must be exactly one of {sorted(STAMPS)}")
    if finding.stamp == GROUNDED:
        if finding.parallel_status != "hit" or not _url_ok(finding.parallel_url):
            raise ReceiptInvalidError("grounded requires a Parallel URL on the row")
    if finding.stamp == MAINSTREAM:
        if finding.parallel_url:
            raise ReceiptInvalidError("mainstream is widely repeated, not a source")
        if "not a source" not in finding.note.lower():
            raise ReceiptInvalidError("mainstream must say it is not a source")
    if finding.stamp == FRINGE:
        if "never sold as fact" not in finding.note.lower():
            raise ReceiptInvalidError("fringe must be tagged, never sold as fact")
    validate_attribution(finding)


def validate_ready_receipt(receipt: Receipt) -> None:
    if not receipt.findings:
        raise ReceiptInvalidError("READY receipt needs findings")
    for finding in receipt.findings:
        validate_finding(finding)
    for link in receipt.causal_links:
        validate_causal_link(link)
    if not receipt.parallel_hit or not receipt.parallel_miss:
        raise ReceiptInvalidError("same receipt MUST show a Parallel hit AND a Parallel miss")
    if receipt.invented_source or receipt.collage or receipt.invented_stamp or receipt.invented_lean:
        raise ReceiptInvalidError("READY receipt cannot invent source, collage, stamp, or lean")


def hold_receipt(packet_id: str, rails: Rails) -> Receipt:
    """Fail-closed. No invented source, no collage, no stamp invented."""
    missing = ", ".join(rails.missing) or "rails"
    return Receipt(
        packet_id=packet_id,
        written=True,
        findings=[],
        disposition="HOLD",
        hold_reason=(
            f"Fail-closed: {missing} missing — no invented source, no collage, "
            "no stamp invented, no invented lean."
        ),
        invented_source=False,
        collage=False,
        invented_stamp=False,
        invented_lean=False,
        causal_links=[],
    )


def write_receipt(packet: Packet, receipt: Receipt) -> Packet:
    """Write-once. Second stamp is a hard error."""
    if packet.receipt is not None and packet.receipt.written:
        raise ReceiptWriteOnceError(f"receipt already written for {packet.id}")
    if receipt.disposition == "READY":
        validate_ready_receipt(receipt)
    elif receipt.disposition == "HOLD":
        if receipt.findings:
            raise ReceiptInvalidError("HOLD must not invent stamps")
        if receipt.causal_links:
            raise ReceiptInvalidError("HOLD must not invent a causal chain")
        if receipt.invented_source or receipt.collage or receipt.invented_stamp or receipt.invented_lean:
            raise ReceiptInvalidError("HOLD forbids invented source, collage, stamp, or lean")
    else:
        raise ReceiptInvalidError("disposition must be READY or HOLD")
    receipt.written = True
    receipt.packet_id = packet.id
    packet.receipt = receipt
    packet.status = "ready" if receipt.disposition == "READY" else "hold"
    return packet


def attach_frames(packet: Packet, frames: list[ShotFrame], *, rails: Rails) -> Packet:
    if not rails.ok:
        packet.frames = []
        return packet
    if len(frames) != 4:
        raise ReceiptInvalidError("boarder delivers four shot frames, not a mood dump")
    for frame in frames:
        if not frame.shot.strip():
            raise ReceiptInvalidError("each frame needs a real shot, not a mood")
    packet.frames = frames
    return packet
