from __future__ import annotations

import logging
import uuid

from onecrew import config
from onecrew.agent.tools import findings_from_parallel_rows
from onecrew.board import write_board
from onecrew.collision import stamp_collisions
from onecrew.cut import size_findings
from onecrew.depth import pre1980_fail_closed
from onecrew.events import bus
from onecrew.models import MISSING, Depth, Exclusion, Packet, Rails, Receipt, ShiftRecord, utcnow
from onecrew.parallel_client import ParallelDownError, search
from onecrew.picks import require_picks
from onecrew.rails import assess_rails
from onecrew.receipt import attach_frames, hold_receipt, write_receipt
from onecrew.pack import leftover_hit_exclusions, write_research_pack
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
    tell: str | None = None,
    tone: str | None = None,
    topic: str = "",
) -> ShiftRecord:
    (
        chosen_topic,
        chosen_platform,
        chosen_cut,
        chosen_depth,
        chosen_lean,
        chosen_tell,
        chosen_tone,
    ) = require_picks(topic, platform, cut, depth, script_lean, tell, tone)
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
        tell=chosen_tell,
        tone=chosen_tone,
        topic=chosen_topic,
        rails=rails,
        store_backend=store.backend,
    )
    store.upsert_shift(shift)
    return shift


def _row_urls(rows: list) -> list[str]:
    return [url for url in (getattr(row, "url", None) for row in rows) if url]


def _research(packet: Packet, rails: Rails, depth: Depth) -> tuple[Receipt, list[Exclusion], list[str]]:
    if not rails.parallel:
        held = hold_receipt(packet.id, rails)
        pre = pre1980_fail_closed(packet_id=packet.id, depth=depth, rails=rails, parallel_hits=0)
        return (pre or held), [], []
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
        return (
            pre1980_fail_closed(
                packet_id=packet.id, depth=depth, rails=down, parallel_hits=0
            )
            or hold_receipt(packet.id, down),
            [],
            [],
        )
    hit_rows = list(getattr(hit, "results", None) or [])
    miss_rows = list(getattr(miss, "results", None) or [])
    hit_urls = _row_urls(hit_rows) + _row_urls(miss_rows)
    hit_url = getattr(hit_rows[0], "url", None) if hit_rows else None
    hit_title = getattr(hit_rows[0], "title", None) or MISSING if hit_rows else MISSING
    pre = pre1980_fail_closed(
        packet_id=packet.id,
        depth=depth,
        rails=rails,
        parallel_hits=len(hit_rows),
    )
    if pre:
        leftover = leftover_hit_exclusions(
            hit_rows + miss_rows,
            set(),
            reason="outside_depth",
            detail="Outside the pre-1980 window that held. Not silently dropped.",
        )
        return pre, leftover, hit_urls
    if not hit_url:
        leftover = leftover_hit_exclusions(
            hit_rows + miss_rows,
            set(),
            reason="no_url",
            detail="Parallel row without a usable URL. Not silently dropped.",
        )
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False})), leftover, hit_urls
    findings = findings_from_parallel_rows(
        hit_url=hit_url,
        hit_title=hit_title,
        hit_claim=f"Grounded event inside {depth}: {packet.topic or packet.hook}",
        mainstream_claim=f"Widely repeated frame about {packet.topic or packet.hook}",
        miss_claim=f"Fringe claim about {packet.topic or packet.hook}",
    )
    if not findings:
        leftover = leftover_hit_exclusions(
            hit_rows + miss_rows,
            set(),
            reason="other",
            detail="Parallel hit did not become a finding. Not silently dropped.",
        )
        return hold_receipt(packet.id, rails.model_copy(update={"parallel": False})), leftover, hit_urls
    if packet.cut:
        findings = size_findings(findings, packet.cut, packet.platform)
    kept_urls = {f.parallel_url for f in findings if f.parallel_url}
    leftover = leftover_hit_exclusions(
        hit_rows,
        kept_urls,
        reason="duplicate",
        detail="Same timeline search; not stamped as a finding.",
    ) + leftover_hit_exclusions(
        miss_rows,
        kept_urls,
        reason="other",
        detail="Returned on the fringe search; not added as a source.",
    )
    # ponytail: live causal_links stay empty unless Parallel sourced a this-led-to-that URL.
    # Seed shows one missing link; do not invent a 40-year chain here.
    return (
        Receipt(
            packet_id=packet.id,
            written=False,
            findings=findings,
            causal_links=[],
            disposition="READY",
        ),
        leftover,
        hit_urls,
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
        shift.tell,
        shift.tone,
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
        tell=shift.tell,
        tone=shift.tone,
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
        stamp_collisions(fresh, rails)
        attach_frames(fresh, [], rails=rails)
        fresh.exclusions = [
            Exclusion(
                what="Live Parallel search",
                reason="rails_down",
                detail="Parallel rail down. No invented source.",
            )
        ]
        write_research_pack(fresh, hit_urls=[])
        store.upsert_packet(fresh)
        return fresh

    receipt, leftover, hit_urls = _research(fresh, rails, shift.depth)
    if receipt.disposition == "HOLD":
        write_receipt(fresh, receipt)
        write_script(fresh)
        stamp_collisions(fresh, rails)
        attach_frames(fresh, [], rails=rails)
        if leftover:
            fresh.exclusions = leftover
        elif not fresh.exclusions:
            fresh.exclusions = [
                Exclusion(
                    what="Live Parallel search",
                    reason="rails_down" if not rails.parallel else "not_searched",
                    detail=receipt.hold_reason or "Receipt HOLD. No invented source.",
                )
            ]
        write_research_pack(fresh, hit_urls=hit_urls)
        store.upsert_packet(fresh)
        return fresh

    write_receipt(fresh, receipt)
    write_script(fresh)
    stamp_collisions(fresh, rails)
    bus.emit(shift.id, agent="boarder", kind="plan", message=f"Storyboard from script, cut={shift.cut}")
    frames = _board(fresh, rails)
    attach_frames(fresh, frames, rails=rails)
    fresh.exclusions = leftover
    write_research_pack(fresh, hit_urls=hit_urls)
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
    tell: str | None = None,
    tone: str | None = None,
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
            tell=tell,
            tone=tone,
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
