from __future__ import annotations

import logging
import uuid

from onecrew import config
from onecrew.agent.tools import findings_from_parallel_rows
from onecrew.board import write_board
from onecrew.cut import size_findings
from onecrew.depth import pre1980_fail_closed
from onecrew.events import bus
from onecrew.models import Depth, Packet, Rails, Receipt, ShiftRecord, utcnow
from onecrew.parallel_client import ParallelDownError, search
from onecrew.picks import require_picks
from onecrew.rails import assess_rails
from onecrew.receipt import attach_frames, hold_receipt, write_receipt
from onecrew.script import write_script
from onecrew.seed import reset_floor
from onecrew.store import store

log = logging.getLogger("onecrew.shift")


def open_shift(
    goal: str,
    *,
    packet_id: str | None = None,
    platform: str | None = None,
    depth: str | None = None,
    cut: str | None = None,
    script_lean: str | None = None,
    genre: str | None = None,
    vantage: str | None = None,
    topic: str = "",
) -> ShiftRecord:
    (
        chosen_topic,
        chosen_platform,
        chosen_cut,
        chosen_depth,
        chosen_lean,
        chosen_genre,
        chosen_vantage,
    ) = require_picks(topic, platform, cut, depth, script_lean, genre, vantage)
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
        platform=chosen_platform,
        depth=chosen_depth,
        cut=chosen_cut,
        script_lean=chosen_lean,
        genre=chosen_genre,
        vantage=chosen_vantage,
        topic=chosen_topic,
        rails=rails,
        store_backend=store.backend,
    )
    store.upsert_shift(shift)
    return shift


def _research(packet: Packet, rails: Rails, depth: Depth) -> Receipt:
    if not rails.parallel:
        held = hold_receipt(packet.id, rails)
        pre = pre1980_fail_closed(packet_id=packet.id, depth=depth, rails=rails, parallel_hits=0)
        return pre or held
    try:
        hit = search(
            objective=f"Timeline for {packet.topic or packet.hook} inside depth={depth}",
            search_queries=[packet.topic or packet.hook, f"{packet.topic} {depth}"],
        )
        miss = search(
            objective=f"Unsourced fringe claim in {packet.topic or packet.hook}",
            search_queries=[f"{packet.topic} hidden treaty Hormuz"],
        )
    except ParallelDownError:
        down = rails.model_copy(update={"parallel": False})
        return pre1980_fail_closed(
            packet_id=packet.id, depth=depth, rails=down, parallel_hits=0
        ) or hold_receipt(packet.id, down)
    hit_rows = list(getattr(hit, "results", None) or [])
    miss_rows = list(getattr(miss, "results", None) or [])
    hit_url = getattr(hit_rows[0], "url", None) if hit_rows else None
    pre = pre1980_fail_closed(
        packet_id=packet.id,
        depth=depth,
        rails=rails,
        parallel_hits=len(hit_rows),
    )
    if pre:
        return pre
    if not hit_url:
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False}))
    findings = findings_from_parallel_rows(
        hit_url=hit_url,
        hit_claim=f"Grounded event inside {depth}: {packet.topic or packet.hook}",
        mainstream_claim=f"Widely repeated frame about {packet.topic or packet.hook}",
        miss_claim=f"Fringe claim about {packet.topic or packet.hook}",
    )
    if not findings:
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False}))
    if packet.cut:
        findings = size_findings(findings, packet.cut, packet.platform)
    # ponytail: live causal_links stay empty unless Parallel sourced a this-led-to-that URL.
    # Seed shows one missing link; do not invent a 40-year chain here.
    return Receipt(
        packet_id=packet.id,
        written=False,
        findings=findings,
        causal_links=[],
        disposition="READY",
    )


def _board(packet: Packet, rails: Rails) -> list:
    """Shot list from the timed VO, then Imagen onto those shots."""
    return write_board(packet, rails)


def run_live_packet(shift: ShiftRecord) -> Packet:
    """Spend path. Picks → sources → script → storyboard. Boards are not optional."""
    require_picks(
        shift.topic,
        shift.platform,
        shift.cut,
        shift.depth,
        shift.script_lean,
        shift.genre,
        shift.vantage,
    )
    rails = shift.rails or assess_rails()
    existing = store.get_packet(shift.packet_id) or reset_floor()
    fresh = Packet(
        id=existing.id,
        topic=shift.topic or existing.topic or existing.hook,
        platform=shift.platform,
        depth=shift.depth,
        cut=shift.cut,
        script_lean=shift.script_lean,
        genre=shift.genre,
        vantage=shift.vantage,
        hook=shift.topic or existing.hook,
        script="",
        status="running",
        shift_id=shift.id,
    )
    bus.emit(shift.id, agent="researcher", kind="plan", message=f"Research {fresh.id} depth={shift.depth}")
    if not rails.parallel:
        write_receipt(
            fresh,
            pre1980_fail_closed(
                packet_id=fresh.id, depth=shift.depth, rails=rails, parallel_hits=0
            )
            or hold_receipt(fresh.id, rails),
        )
        write_script(fresh)
        attach_frames(fresh, [], rails=rails)
        store.upsert_packet(fresh)
        return fresh

    receipt = _research(fresh, rails, shift.depth)
    if receipt.disposition == "HOLD":
        write_receipt(fresh, receipt)
        write_script(fresh)
        attach_frames(fresh, [], rails=rails)
        store.upsert_packet(fresh)
        return fresh

    write_receipt(fresh, receipt)
    write_script(fresh)
    bus.emit(shift.id, agent="boarder", kind="plan", message=f"Storyboard from script, cut={shift.cut}")
    frames = _board(fresh, rails)
    attach_frames(fresh, frames, rails=rails)
    store.upsert_packet(fresh)
    return fresh


async def run_shift(
    goal: str,
    *,
    packet_id: str | None = None,
    shift: ShiftRecord | None = None,
    platform: str | None = None,
    depth: str | None = None,
    cut: str | None = None,
    script_lean: str | None = None,
    genre: str | None = None,
    vantage: str | None = None,
    topic: str = "",
) -> ShiftRecord:
    if shift is None:
        shift = open_shift(
            goal,
            packet_id=packet_id,
            platform=platform,
            depth=depth,
            cut=cut,
            script_lean=script_lean,
            genre=genre,
            vantage=vantage,
            topic=topic,
        )
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
