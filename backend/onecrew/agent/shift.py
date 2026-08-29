from __future__ import annotations

import logging
import uuid

from onecrew import config
from onecrew.agent.tools import findings_from_parallel_rows, frames_from_script
from onecrew.events import bus
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.models import Packet, Rails, Receipt, ShiftRecord, utcnow
from onecrew.parallel_client import ParallelDownError, search
from onecrew.rails import assess_rails
from onecrew.receipt import attach_frames, hold_receipt, write_receipt
from onecrew.seed import reset_floor
from onecrew.store import store

log = logging.getLogger("onecrew.shift")


def open_shift(goal: str, *, packet_id: str | None = None) -> ShiftRecord:
    packet_id = packet_id or config.SEED_PACKET_ID
    shift_id = f"shift-{uuid.uuid4().hex[:10]}"
    rails = assess_rails()
    live = rails.ok
    shift = ShiftRecord(
        id=shift_id,
        goal=goal,
        status="running",
        started_at=utcnow(),
        engine=f"adk+{config.GEMINI_MODEL}" if live else "receipt-stamp",
        model=config.GEMINI_MODEL if live else "none",
        packet_id=packet_id,
        rails=rails,
        store_backend=store.backend,
    )
    store.upsert_shift(shift)
    return shift


def _research(packet: Packet, rails: Rails) -> Receipt:
    if not rails.ok:
        return hold_receipt(packet.id, rails)
    try:
        hit = search(
            objective=f"Ground the ranking claim in: {packet.hook}",
            search_queries=["pickle juice sodium sports drink ranking recovery"],
        )
        miss = search(
            objective="Confirm whether NASA studied pickle juice for astronaut cramps",
            search_queries=["NASA pickle juice astronaut cramps study"],
        )
    except ParallelDownError:
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False}))
    hit_rows = list(getattr(hit, "results", None) or [])
    miss_rows = list(getattr(miss, "results", None) or [])
    hit_url = getattr(hit_rows[0], "url", None) if hit_rows else None
    if not hit_url or miss_rows:
        # Need a Parallel hit AND a Parallel miss. Do not invent either.
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False}))
    findings = findings_from_parallel_rows(
        hit_url=hit_url,
        hit_claim="Pickle juice sodium ranks with common sports drinks in published recovery tables.",
        mainstream_claim="A 3am kitchen pickle-juice shot is a hangover ranking hack.",
        miss_claim="NASA studied pickle juice for astronaut cramps.",
    )
    if not findings:
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False}))
    return Receipt(packet_id=packet.id, written=False, findings=findings, disposition="READY")


def _board(packet: Packet, rails: Rails) -> list:
    if not rails.ok:
        return []
    refs = [f.parallel_url for f in (packet.receipt.findings if packet.receipt else []) if f.parallel_url]
    try:
        generate_frames(
            prompt=(
                f"Four photoreal shot frames. Script: {packet.script}. "
                f"Refs: {', '.join(r for r in refs if r)}. Real shots, not a mood dump."
            ),
            number_of_images=4,
        )
    except ImagenDownError:
        return []
    return frames_from_script(packet, [r for r in refs if r])


def run_live_packet(shift: ShiftRecord) -> Packet:
    """Spend path. Caller already checked X-Shift-Token. One write at the end."""
    rails = shift.rails or assess_rails()
    existing = store.get_packet(shift.packet_id) or reset_floor()
    fresh = Packet(
        id=existing.id,
        hook=existing.hook,
        script=existing.script,
        status="running",
        shift_id=shift.id,
    )
    bus.emit(shift.id, agent="researcher", kind="plan", message=f"Research {fresh.id}")
    if not rails.ok:
        write_receipt(fresh, hold_receipt(fresh.id, rails))
        attach_frames(fresh, [], rails=rails)
        store.upsert_packet(fresh)
        return fresh

    receipt = _research(fresh, rails)
    if receipt.disposition == "HOLD":
        write_receipt(fresh, receipt)
        attach_frames(fresh, [], rails=rails)
        store.upsert_packet(fresh)
        return fresh

    bus.emit(shift.id, agent="boarder", kind="plan", message="Four shot frames")
    frames = _board(fresh, rails)
    if not frames:
        down = rails.model_copy(update={"imagen": False, "vertex": rails.vertex})
        if not rails.imagen:
            down = rails.model_copy(update={"imagen": False})
        write_receipt(fresh, hold_receipt(fresh.id, down.model_copy(update={"imagen": False})))
        attach_frames(fresh, [], rails=down.model_copy(update={"imagen": False}))
        store.upsert_packet(fresh)
        return fresh

    write_receipt(fresh, receipt)
    attach_frames(fresh, frames, rails=rails)
    store.upsert_packet(fresh)
    return fresh


async def run_shift(goal: str, *, packet_id: str | None = None, shift: ShiftRecord | None = None) -> ShiftRecord:
    shift = shift or open_shift(goal, packet_id=packet_id)
    try:
        packet = run_live_packet(shift)
        shift.status = "completed"
        shift.finished_at = utcnow()
        store.upsert_shift(shift)
        bus.emit(
            shift.id,
            agent="floor",
            kind="info",
            message=f"{packet.id} {packet.status} — floor does not post",
        )
    except Exception as exc:  # noqa: BLE001
        log.exception("shift failed")
        shift.status = "failed"
        shift.finished_at = utcnow()
        shift.error = f"{type(exc).__name__}: {exc}"
        store.upsert_shift(shift)
        bus.emit(shift.id, agent="floor", kind="error", message=shift.error)
        raise
    finally:
        bus.close(shift.id)
    return shift
