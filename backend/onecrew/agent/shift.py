from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from onecrew import config
from onecrew.agent.tools import findings_from_parallel_rows
from onecrew.board import write_board
from onecrew.collision import stamp_collisions
from onecrew.cut import size_findings
from onecrew.depth import pre1980_fail_closed
from onecrew.events import bus
from onecrew.models import MISSING, Depth, Exclusion, Packet, Rails, Receipt, ShiftRecord, utcnow
from onecrew.parallel_client import ParallelDownError, entity_search, extract, run_task, search
from onecrew.picks import require_picks
from onecrew.rails import assess_rails
from onecrew.receipt import attach_frames, hold_receipt, write_receipt
from onecrew.pack import leftover_hit_exclusions, write_research_pack
from onecrew.script import write_script
from onecrew.store import store
from onecrew.tell import invents_frame

log = logging.getLogger("onecrew.shift")


def snapshot_id(topic: str, shift_id: str) -> str:
    """New packet id per topic/shift. Never inherit or overwrite oc-hormuz-decade."""
    slug = re.sub(r"[^a-z0-9]+", "-", (topic or "topic").strip().lower()).strip("-")[:36] or "topic"
    tail = re.sub(r"[^a-z0-9]", "", (shift_id or "").lower())[-8:] or "snap"
    pid = f"oc-{slug}-{tail}"
    if pid == config.SEED_PACKET_ID:
        pid = f"oc-{slug}-{tail}-s"
    return pid


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


_ENRICH_SPEC = {
    "output_schema": {
        "type": "json",
        "json_schema": {
            "type": "object",
            "properties": {
                "vested_interest": {
                    "type": "string",
                    "description": "Who benefits if this source is believed. Parallel-cited only.",
                },
                "who_repeats": {
                    "type": "string",
                    "description": "Who repeats this line. Parallel-cited only.",
                },
                "propaganda_issuer": {
                    "type": "string",
                    "description": "Named campaign issuer if Parallel sourced one.",
                },
                "independent": {
                    "type": "string",
                    "description": "yes, no, or missing from Parallel ownership text.",
                },
            },
            "required": ["vested_interest", "who_repeats", "propaganda_issuer", "independent"],
            "additionalProperties": False,
        },
    }
}


def _row_urls(rows: list) -> list[str]:
    return [url for url in (getattr(row, "url", None) for row in rows) if url]


def _wants_entities(packet: Packet) -> bool:
    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        return False
    blob = f"{packet.topic or ''} {packet.tell or ''}".lower()
    return any(token in blob for token in ("producer state", "producer states", "lobby", "opec"))


def _cited_urls(field: Any) -> list[str]:
    out: list[str] = []
    for citation in getattr(field, "citations", None) or []:
        url = getattr(citation, "url", None)
        if url:
            out.append(url)
    return out


def _spine_from_task(result: Any) -> str:
    output = getattr(result, "output", None)
    if not output:
        return ""
    parts: list[str] = []
    content = getattr(output, "content", None)
    if content:
        parts.append(str(content).strip())
    for field in getattr(output, "basis", None) or []:
        name = getattr(field, "field", "field")
        cites = _cited_urls(field)
        if not cites:
            parts.append(f"Task basis {name}: citation missing.")
            continue
        parts.append(f"Task basis {name}: {', '.join(cites)}.")
    return " ".join(parts).strip()


def _apply_extract(findings: list, extracted: Any) -> list[Exclusion]:
    by_url = {f.parallel_url: f for f in findings if f.parallel_url}
    leftover: list[Exclusion] = []
    for item in getattr(extracted, "results", None) or []:
        url = getattr(item, "url", None)
        excerpts = [str(x) for x in (getattr(item, "excerpts", None) or []) if x]
        title = (getattr(item, "title", None) or "").strip()
        finding = by_url.get(url)
        if finding and excerpts:
            # ponytail: first excerpt only. Gemini does not invent extract text.
            finding.note = f"{finding.note} Extract: {excerpts[0][:400]}".strip()
            if title and (not finding.title or finding.title == MISSING):
                finding.title = title
    for err in getattr(extracted, "errors", None) or []:
        url = getattr(err, "url", None)
        if not url:
            continue
        leftover.append(
            Exclusion(
                what=url,
                reason="other",
                detail=f"Extract failed: {getattr(err, 'error_type', 'error')}. Not silently dropped.",
                url=url,
            )
        )
    return leftover


def _hold_account_hits(hit_urls: list[str], leftover: list[Exclusion]) -> list[Exclusion]:
    """A Search hit still has to appear when the later rail HOLDs."""
    cited = {row.url for row in leftover if row.url}
    for url in hit_urls:
        if url and url not in cited:
            leftover.append(
                Exclusion(
                    what=url,
                    reason="rails_down",
                    detail="Parallel down after Search. URL not silently dropped.",
                    url=url,
                )
            )
    return leftover


def _apply_enrichment(findings: list, result: Any) -> None:
    """Stamps only when Task basis carries a URL. Gemini does not invent Task citations."""
    output = getattr(result, "output", None)
    if not output:
        return
    content = getattr(output, "content", None) or {}
    if not isinstance(content, dict):
        return
    cited = {
        getattr(field, "field", ""): _cited_urls(field)
        for field in (getattr(output, "basis", None) or [])
    }
    grounded = next((f for f in findings if f.stamp == "grounded" and f.parallel_url), None)
    if grounded is None:
        return
    if cited.get("independent") and content.get("independent") in {"yes", "no", "missing"}:
        grounded.independent = content["independent"]
        grounded.independent_url = grounded.parallel_url
    if cited.get("vested_interest") and content.get("vested_interest"):
        grounded.vested_interest = content["vested_interest"]
        grounded.vested_interest_url = grounded.parallel_url
    if cited.get("who_repeats") and content.get("who_repeats"):
        grounded.who_repeats = content["who_repeats"]
        grounded.who_repeats_url = grounded.parallel_url
    if cited.get("propaganda_issuer") and content.get("propaganda_issuer"):
        grounded.propaganda = "yes"
        grounded.propaganda_issuer = content["propaganda_issuer"]
        grounded.propaganda_url = grounded.parallel_url


def _research(packet: Packet, rails: Rails, depth: Depth) -> tuple[Receipt, list[Exclusion], list[str], str]:
    if not rails.parallel:
        held = hold_receipt(packet.id, rails)
        pre = pre1980_fail_closed(packet_id=packet.id, depth=depth, rails=rails, parallel_hits=0)
        return (pre or held), [], [], ""
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
            "",
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
        return pre, leftover, hit_urls, ""
    if not hit_url:
        leftover = leftover_hit_exclusions(
            hit_rows + miss_rows,
            set(),
            reason="no_url",
            detail="Parallel row without a usable URL. Not silently dropped.",
        )
        return (
            hold_receipt(packet.id, rails.model_copy(update={"parallel": False})),
            leftover,
            hit_urls,
            "",
        )
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
        return (
            hold_receipt(packet.id, rails.model_copy(update={"parallel": False})),
            leftover,
            hit_urls,
            "",
        )
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
    try:
        extracted = extract(
            urls=hit_urls,
            objective=(
                f"Thesis quotes, ownership, propaganda, and independence text for "
                f"{packet.topic or packet.hook}"
            ),
        )
    except ParallelDownError:
        leftover.append(
            Exclusion(
                what="Live Parallel extract",
                reason="rails_down",
                detail="Extract rail down. No invented extract text.",
            )
        )
        down = rails.model_copy(update={"parallel": False})
        return hold_receipt(packet.id, down), _hold_account_hits(hit_urls, leftover), hit_urls, ""
    leftover.extend(_apply_extract(findings, extracted))
    try:
        task = run_task(
            prompt=(
                f"Write a citable thesis timeline for {packet.topic or packet.hook} "
                f"inside depth={depth}. Use only sourced events. Name missing causal "
                "links. Do not invent sources."
            ),
            processor="pro",
        )
    except ParallelDownError:
        leftover.append(
            Exclusion(
                what="Live Parallel task",
                reason="rails_down",
                detail="Task rail down. No invented Task citations.",
            )
        )
        down = rails.model_copy(update={"parallel": False})
        return hold_receipt(packet.id, down), _hold_account_hits(hit_urls, leftover), hit_urls, ""
    spine = _spine_from_task(task)
    if getattr(extracted, "results", None):
        try:
            enrich = run_task(
                prompt=f"Enrich the cited source at {hit_url} for {packet.topic or packet.hook}.",
                processor="base",
                task_spec=_ENRICH_SPEC,
            )
            _apply_enrichment(findings, enrich)
        except ParallelDownError:
            leftover.append(
                Exclusion(
                    what="Live Parallel enrichment task",
                    reason="rails_down",
                    detail="Enrichment Task down. Stamps stay missing. No invented citation.",
                )
            )
    if _wants_entities(packet):
        try:
            ents = entity_search(
                objective=f"Producer states or named lobby in {packet.topic or packet.hook}",
                entity_type="companies",
                match_limit=5,
            )
            names = []
            for ent in getattr(ents, "entities", None) or []:
                name = getattr(ent, "name", None)
                url = getattr(ent, "url", None)
                if name and url:
                    names.append(f"{name} ({url})")
            if names:
                spine = f"{spine} Verified entities: {'; '.join(names)}.".strip()
        except ParallelDownError:
            leftover.append(
                Exclusion(
                    what="Entity search",
                    reason="rails_down",
                    detail="Entity search down. No invented lobby or family.",
                )
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
        spine,
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
    fresh_id = snapshot_id(shift.topic, shift.id)
    if fresh_id == config.SEED_PACKET_ID:
        fresh_id = f"{fresh_id}-live"
    shift.packet_id = fresh_id
    store.upsert_shift(shift)
    fresh = Packet(
        id=fresh_id,
        topic=shift.topic,
        platform=shift.platform,
        depth=shift.depth,
        cut=shift.cut,
        script_lean=shift.script_lean,
        tell=shift.tell,
        tone=shift.tone,
        hook=shift.topic,
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
        fresh.exclusions = [
            Exclusion(
                what="Live Parallel search",
                reason="rails_down",
                detail="Parallel rail down. No invented source.",
            )
        ]
        write_research_pack(fresh, hit_urls=[])
        write_script(fresh)
        stamp_collisions(fresh, rails)
        attach_frames(fresh, [], rails=rails)
        store.upsert_packet(fresh)
        return fresh

    receipt, leftover, hit_urls, spine = _research(fresh, rails, shift.depth)
    fresh.task_spine = spine
    if receipt.disposition == "HOLD":
        write_receipt(fresh, receipt)
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
        write_script(fresh)
        stamp_collisions(fresh, rails)
        attach_frames(fresh, [], rails=rails)
        store.upsert_packet(fresh)
        return fresh

    write_receipt(fresh, receipt)
    fresh.exclusions = leftover
    write_research_pack(fresh, hit_urls=hit_urls)
    write_script(fresh)
    stamp_collisions(fresh, rails)
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
