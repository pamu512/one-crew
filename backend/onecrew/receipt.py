from __future__ import annotations

from onecrew.models import STAMPS, Finding, Packet, Rails, Receipt, ShotFrame

GROUNDED = "grounded"
MAINSTREAM = "mainstream"
FRINGE = "fringe"


class ReceiptWriteOnceError(RuntimeError):
    """A written receipt cannot be overwritten."""


class ReceiptInvalidError(ValueError):
    """Stamp / hit-miss / source rules failed."""


def _url_ok(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


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


def validate_ready_receipt(receipt: Receipt) -> None:
    if not receipt.findings:
        raise ReceiptInvalidError("READY receipt needs findings")
    for finding in receipt.findings:
        validate_finding(finding)
    if not receipt.parallel_hit or not receipt.parallel_miss:
        raise ReceiptInvalidError("same receipt MUST show a Parallel hit AND a Parallel miss")
    if receipt.invented_source or receipt.collage or receipt.invented_stamp:
        raise ReceiptInvalidError("READY receipt cannot invent source, collage, or stamp")


def hold_receipt(packet_id: str, rails: Rails) -> Receipt:
    """Fail-closed. No invented source, no collage, no stamp invented."""
    missing = ", ".join(rails.missing) or "rails"
    return Receipt(
        packet_id=packet_id,
        written=True,
        findings=[],
        disposition="HOLD",
        hold_reason=(
            f"Fail-closed: {missing} missing — no invented source, no collage, no stamp invented."
        ),
        invented_source=False,
        collage=False,
        invented_stamp=False,
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
        if receipt.invented_source or receipt.collage or receipt.invented_stamp:
            raise ReceiptInvalidError("HOLD forbids invented source, collage, or stamp")
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
