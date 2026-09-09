from __future__ import annotations

from onecrew.models import (
    INDEPENDENT,
    MISSING,
    PROPAGANDA,
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
TIMELINE = "timeline_event"
_MACRO_SERIES = frozenset(
    {"USREC", "BLS payrolls", "U-3", "GDP", "LEI", "SAHMREALTIME", "ISM"}
)


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
    validate_propaganda(finding)


def validate_propaganda(finding: Finding) -> None:
    """propaganda yes/no only from a Parallel hit. Gemini must not stamp from tone."""
    if finding.propaganda not in PROPAGANDA:
        raise ReceiptInvalidError("propaganda must be yes, no, or missing")
    issuer = (finding.propaganda_issuer or "").strip()
    if finding.propaganda == "yes":
        if not _url_ok(finding.propaganda_url):
            raise ReceiptInvalidError(
                "cannot stamp propaganda=yes without a Parallel hit naming the issuer"
            )
        if not issuer or issuer == MISSING:
            raise ReceiptInvalidError(
                "cannot stamp propaganda=yes without a Parallel hit naming the issuer"
            )
        return
    if finding.propaganda == "no":
        if not _url_ok(finding.propaganda_url):
            raise ReceiptInvalidError("propaganda=no requires a Parallel hit; otherwise missing")
        if issuer and issuer != MISSING:
            raise ReceiptInvalidError("propaganda=no has no campaign issuer")
        return
    if finding.propaganda_url:
        raise ReceiptInvalidError("propaganda=missing cannot carry a Parallel URL")
    if issuer and issuer != MISSING:
        raise ReceiptInvalidError("propaganda=missing cannot carry an issuer")


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
    if finding.stamp == TIMELINE:
        if finding.parallel_status != "hit" or not _url_ok(finding.parallel_url):
            raise ReceiptInvalidError("timeline_event requires a Parallel URL on the row")
        series = (finding.series or "").strip()
        if series in _MACRO_SERIES:
            raise ReceiptInvalidError("timeline_event cannot carry a closed macro series")
        if series not in {"", TIMELINE, MISSING}:
            raise ReceiptInvalidError("timeline_event series must be timeline_event or empty")
    if finding.stamp == MAINSTREAM:
        if finding.parallel_url:
            raise ReceiptInvalidError("mainstream is widely repeated, not a source")
        if "not a source" not in finding.note.lower():
            raise ReceiptInvalidError("mainstream must say it is not a source")
    if finding.stamp == FRINGE:
        if "never sold as fact" not in finding.note.lower():
            raise ReceiptInvalidError("fringe must be tagged, never sold as fact")
    validate_attribution(finding)


def validate_ready_receipt(
    receipt: Receipt, *, cut: str | None = None, platform: str | None = None
) -> None:
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
    if cut is None:
        raise ReceiptInvalidError("No cut chosen = no run")
    from onecrew.cut import event_cap

    if len(receipt.findings) > event_cap(cut, platform):  # type: ignore[arg-type]
        surface = (platform or "").strip()
        short = (cut or "") in {"tiktok-length", "shorts"}
        stories = surface in {
            "instagram_stories",
            "instagram_reels",
            "facebook_reels",
            "tiktok",
            "youtube_shorts",
            "threads",
        }
        if stories or short:
            raise ReceiptInvalidError(
                "A Stories board is not a documentary board; a Reels board is not a YouTube long-form board"
            )


def credit_hold_receipt(packet_id: str) -> Receipt:
    """Parallel 402. Empty findings. Do not invent a pack."""
    return Receipt(
        packet_id=packet_id,
        written=False,
        findings=[],
        disposition="HOLD",
        hold_reason="Fail-closed: Parallel credit — Parallel 402. No invented pack.",
        invented_source=False,
        collage=False,
        invented_stamp=False,
        invented_lean=False,
        causal_links=[],
    )


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
        validate_ready_receipt(receipt, cut=packet.cut, platform=packet.platform)
    elif receipt.disposition == "HOLD":
        for finding in receipt.findings:
            validate_finding(finding)
        if receipt.causal_links:
            raise ReceiptInvalidError("HOLD must not invent a causal chain")
        if receipt.invented_source or receipt.collage or receipt.invented_stamp or receipt.invented_lean:
            raise ReceiptInvalidError("HOLD forbids invented source, collage, stamp, or lean")
    else:
        raise ReceiptInvalidError("disposition must be READY or HOLD")
    receipt.written = True
    receipt.packet_id = packet.id
    packet.receipt = receipt
    from onecrew.cite_repair import stamp_cite_recheck_attempts

    stamp_cite_recheck_attempts(packet)
    packet.status = "ready" if receipt.disposition == "READY" else "hold"
    return packet


def attach_frames(packet: Packet, frames: list[ShotFrame], *, rails: Rails) -> Packet:
    """Keep the shot list from the VO. If Imagen/Vertex is down, images stay missing."""
    if not packet.script.strip() and not packet.beats:
        packet.frames = []
        return packet
    if not frames and packet.beats:
        from onecrew.board import write_shot_list
        from onecrew.script import sanitize_for_ship

        sanitize_for_ship(packet)
        frames = write_shot_list(packet)
    out: list[ShotFrame] = []
    for frame in frames:
        if not frame.shot.strip():
            raise ReceiptInvalidError("each frame needs a real shot, not a mood")
        copied = frame.model_copy()
        if not rails.imagen or not rails.vertex:
            copied.image_href = ""
            copied.imagen = False
        out.append(copied)
    packet.frames = out
    from onecrew.script import persist_mute_on_screen, refuse_empty_numeric_mute

    persist_mute_on_screen(packet, out)
    refuse_empty_numeric_mute(packet, out)
    return packet
