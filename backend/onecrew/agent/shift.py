from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from onecrew import config
from onecrew.board import write_board
from onecrew.collision import stamp_collisions
from onecrew.cut import event_cap, size_findings
from onecrew.depth import pre1980_fail_closed
from onecrew.events import bus
from onecrew.models import Finding, MISSING, Depth, Exclusion, Packet, Rails, Receipt, ShiftRecord, utcnow
from onecrew.parallel_client import (
    ParallelCreditError,
    ParallelDownError,
    entity_search,
    extract,
    run_task,
    search,
)
from onecrew.picks import require_picks
from onecrew.rails import assess_rails
from onecrew.receipt import (
    ReceiptInvalidError,
    ReceiptWriteOnceError,
    attach_frames,
    credit_hold_receipt,
    hold_receipt,
    write_receipt,
)
from onecrew.claimer import findings_from_claims, frame_findings, propose_claims
from onecrew.foundry import FoundryHold, leftover_slot_ids, mint, require_minted, sanitize_stamps
from onecrew.cite_repair import run_cite_recheck_loop
from onecrew.verify import apply_verify_gate, attach_cites_from_hits, cite_bag_from_rows
from onecrew.pack import leftover_hit_exclusions, write_research_pack
from onecrew.research import extract_objective, search_objective, search_queries, task_research_prompt
from onecrew.room import make_grade_artifact, run_room_loop
from onecrew.script import pack_numbers
from onecrew.script_writer import write_vo_from_pack
from onecrew.store import store
from onecrew.tell import invents_frame

log = logging.getLogger("onecrew.shift")


_RESERVED_IDS = frozenset({config.SEED_PACKET_ID, "oc-hormuz-decade"})


def snapshot_id(topic: str, shift_id: str) -> str:
    """New packet id per topic/shift. Never inherit or overwrite oc-hormuz-decade."""
    slug = re.sub(r"[^a-z0-9]+", "-", (topic or "topic").strip().lower()).strip("-")[:36] or "topic"
    tail = re.sub(r"[^a-z0-9]", "", (shift_id or "").lower())[-8:] or "snap"
    pid = f"oc-{slug}-{tail}"
    if pid in _RESERVED_IDS or pid.endswith("hormuz-decade"):
        pid = f"oc-{slug}-{tail}-s"
    return pid


def resolve_live_packet_id(requested: str | None, topic: str, shift_id: str) -> str:
    """Honor a unique body packet_id. Mint otherwise. Never write onto seed or leftover Hormuz."""
    req = (requested or "").strip()
    if req and req not in _RESERVED_IDS and not req.endswith("hormuz-decade"):
        return req
    return snapshot_id(topic, shift_id)


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
    deeper_history: bool = False,
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
        deeper_history=bool(deeper_history),
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


def _search_queries(packet: Packet, depth: Depth, *, deeper_history: bool = False) -> list[str]:
    """Named official series when the topic is recession. Floor depth is not the horizon."""
    return search_queries(
        packet.topic or packet.hook or "topic",
        tell=packet.tell or "",
        deeper_history=deeper_history,
    )


def _fringe_queries(packet: Packet) -> list[str]:
    topic = packet.topic or packet.hook or "topic"
    blob = topic.lower()
    if any(w in blob for w in ("hormuz", "jcpoa", "strait")):
        return [f"{topic} hidden treaty Hormuz"]
    return [f"{topic} unsourced fringe claim"]


def _rows_blob(rows: list) -> str:
    parts: list[str] = []
    for row in rows:
        title = (getattr(row, "title", None) or "").strip()
        if title:
            parts.append(title)
        for excerpt in list(getattr(row, "excerpts", None) or []):
            text = str(excerpt).strip()
            if text:
                parts.append(text)
    return "\n".join(parts)


def _size_live_findings(findings: list[Finding], packet: Packet) -> list[Finding]:
    """Named prints first. Reserve one miss. Never keep leftover 3-slot over USREC."""
    if not packet.cut or not findings:
        return findings
    miss = [row for row in findings if row.parallel_status == "miss"][:1]
    core = [row for row in findings if row.parallel_status != "miss"]
    ranked = size_findings(core, packet.cut, packet.platform)
    cap = event_cap(packet.cut, packet.platform)  # type: ignore[arg-type]
    room = max(1, cap - len(miss))
    return ranked[:room] + miss


def _hit_claim_from_rows(rows: list, title: str) -> str:
    """Pack text from Parallel excerpts. Never 'Grounded event inside {depth}: {topic}'."""
    numbered: list[str] = []
    first = ""
    for row in rows:
        for excerpt in list(getattr(row, "excerpts", None) or []):
            text = str(excerpt).strip()
            if not text:
                continue
            if not first:
                first = text
            if pack_numbers(text):
                numbered.append(text)
        row_title = (getattr(row, "title", None) or "").strip()
        if row_title and pack_numbers(row_title):
            numbered.append(row_title)
    if numbered:
        return " ".join(numbered).strip()[:800]
    return first or (title or "").strip()


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


def _parallel_credit(exc: BaseException) -> bool:
    if isinstance(exc, ParallelCreditError):
        return True
    if getattr(exc, "status_code", None) == 402:
        return True
    blob = str(exc).lower()
    return "insufficient credit" in blob or (
        "402" in blob and "payment required" in blob
    )


def _credit_account_hits(hit_urls: list[str], leftover: list[Exclusion]) -> list[Exclusion]:
    cited = {row.url for row in leftover if row.url}
    for url in hit_urls:
        if url and url not in cited:
            leftover.append(
                Exclusion(
                    what=url,
                    reason="other",
                    detail="Parallel 402 after Search. URL not silently dropped.",
                    url=url,
                )
            )
    return leftover


def _credit_hold(
    packet: Packet, hit_urls: list[str], leftover: list[Exclusion], what: str
) -> tuple[Receipt, list[Exclusion], list[str], str]:
    leftover.append(
        Exclusion(
            what=what,
            reason="rails_down",
            detail="Parallel 402 Payment Required. No invented pack.",
        )
    )
    return (
        credit_hold_receipt(packet.id),
        _credit_account_hits(hit_urls, leftover),
        hit_urls,
        "",
    )


_NAMED_SERIES = frozenset(
    {"USREC", "BLS payrolls", "GDP", "U-3", "LEI", "SAHMREALTIME"}
)


def _fringe_from_rows(miss_rows: list, used: set[str]) -> Finding | None:
    """One Parallel miss. Never leftover 3-slot ids. Claimer path still needs hit+miss."""
    for row in miss_rows or []:
        title = (getattr(row, "title", None) or "").strip()
        for excerpt in list(getattr(row, "excerpts", None) or []):
            claim = str(excerpt).strip()
            if not claim:
                continue
            fid = "frame-miss" if "frame-cite" in used else "cite-miss"
            n = 2
            base = fid
            while fid in used or fid in leftover_slot_ids():
                fid = f"{base}-{n}"
                n += 1
            return Finding(
                id=fid,
                claim=claim,
                stamp="fringe",
                title=title or MISSING,
                series=MISSING,
                print=MISSING,
                parallel_url=None,
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
                propaganda=MISSING,
                propaganda_issuer=MISSING,
            )
    return None


def _named_grounded(findings: list) -> bool:
    rows = findings or []
    if any(getattr(f, "id", "") in leftover_slot_ids() for f in rows):
        return False
    return any(
        getattr(f, "stamp", "") == "grounded"
        and getattr(f, "series", "") in _NAMED_SERIES
        for f in rows
    )


def _foundry_outcome(
    packet: Packet,
    rails: Rails,
    leftover: list[Exclusion],
    hit_urls: list[str],
    spine: str,
    exc: FoundryHold,
    findings: list | None = None,
) -> tuple[Receipt, list[Exclusion], list[str], str]:
    if _named_grounded(findings or []) and "dropped named series" in str(exc).lower():
        return (
            Receipt(
                packet_id=packet.id,
                written=False,
                findings=list(findings or []),
                causal_links=[],
                disposition="READY",
            ),
            leftover,
            hit_urls,
            spine,
        )
    reason = str(exc).strip() or "foundry hold"
    if rails.missing:
        held = hold_receipt(packet.id, rails)
        prior = (held.hold_reason or "").strip()
        held.hold_reason = f"{prior} {reason}".strip()
        return held, leftover, hit_urls, spine
    return (
        Receipt(
            packet_id=packet.id,
            written=False,
            findings=[],
            causal_links=[],
            disposition="HOLD",
            hold_reason=reason,
            invented_source=False,
            collage=False,
            invented_stamp=False,
            invented_lean=False,
        ),
        leftover,
        hit_urls,
        spine,
    )


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
    if cited.get("independent") and content.get("independent") in {"yes", "no"}:
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


def _research(
    packet: Packet,
    rails: Rails,
    depth: Depth,
    *,
    deeper_history: bool | None = None,
    missing_ask: str | None = None,
) -> tuple[Receipt, list[Exclusion], list[str], str]:
    topic = packet.topic or packet.hook
    if deeper_history is None:
        deeper_history = bool(packet.deeper_history)
    if not rails.parallel:
        held = hold_receipt(packet.id, rails)
        pre = pre1980_fail_closed(packet_id=packet.id, depth=depth, rails=rails, parallel_hits=0)
        return (pre or held), [], [], ""
    try:
        hit = search(
            objective=search_objective(topic, deeper_history=deeper_history),
            search_queries=_search_queries(packet, depth, deeper_history=deeper_history),
        )
        miss = search(
            objective=search_objective(topic, fringe=True),
            search_queries=_fringe_queries(packet),
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
    hit_claim = _hit_claim_from_rows(hit_rows, hit_title)
    if not hit_claim:
        leftover = leftover_hit_exclusions(
            hit_rows + miss_rows,
            set(),
            reason="other",
            detail="Parallel hit had no usable claim text. Not silently dropped.",
        )
        return (
            hold_receipt(packet.id, rails.model_copy(update={"parallel": False})),
            leftover,
            hit_urls,
            "",
        )
    leftover = []
    try:
        extracted = extract(
            urls=hit_urls,
            objective=extract_objective(topic),
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
    try:
        task = run_task(
            prompt=task_research_prompt(
                topic,
                deeper_history=deeper_history,
                missing_ask=missing_ask,
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
    except Exception as exc:
        if not _parallel_credit(exc):
            raise
        return _credit_hold(packet, hit_urls, leftover, "Live Parallel task")
    spine = _spine_from_task(task)
    source_urls = _row_urls(hit_rows) + [
        url for field in (getattr(getattr(task, "output", None), "basis", None) or []) for url in _cited_urls(field)
    ]
    packet.task_spine = spine
    packet.research_pack = "\n".join(
        part
        for part in (
            spine,
            _rows_blob(hit_rows),
            _rows_blob(list(getattr(extracted, "results", None) or [])),
        )
        if part
    )
    bag = cite_bag_from_rows(
        list(hit_rows) + list(getattr(extracted, "results", None) or []),
        spine=spine,
        hit_urls=list(dict.fromkeys((source_urls or []) + list(hit_urls or []))),
    )
    # ponytail: in-memory CiteBag for print/when repair. Upgrade: persist excerpts on Packet.
    object.__setattr__(packet, "_cite_bag", bag)
    foundry_rows: list[Finding] = []
    foundry_exc: FoundryHold | None = None
    try:
        foundry_rows = mint(packet, hit_rows, miss_rows, extracted, spine)
    except FoundryHold as exc:
        foundry_exc = exc
        leftover.extend(
            leftover_hit_exclusions(
                hit_rows + miss_rows,
                set(),
                reason="other",
                detail=str(exc),
            )
        )
    else:
        before_size = list(foundry_rows)
        foundry_rows = _size_live_findings(foundry_rows, packet)
        try:
            require_minted(foundry_rows, spine or packet.research_pack or "")
        except FoundryHold as exc:
            foundry_exc = exc
            leftover.extend(
                leftover_hit_exclusions(
                    hit_rows + miss_rows,
                    set(),
                    reason="other",
                    detail=str(exc),
                )
            )
        kept = {f.id for f in foundry_rows}
        for dropped in before_size:
            if dropped.id in kept:
                continue
            leftover.append(
                Exclusion(
                    what=dropped.id,
                    reason="other",
                    detail=f"cut cap dropped {dropped.id}",
                    url=dropped.parallel_url,
                )
            )
    # Claimer is READY authority when verify says ok. Foundry is a v1 candidate only.
    claims = propose_claims(bag, packet)
    claimer_rows = findings_from_claims(claims, bag)
    used = {f.id for f in claimer_rows}
    fringe = _fringe_from_rows(miss_rows, used)
    if fringe and claimer_rows:
        claimer_rows = list(claimer_rows) + [fringe]
    fiction = invents_frame(cut=packet.cut, tell=packet.tell or "")
    claimer_ready = False
    if claimer_rows:
        probed = apply_verify_gate(
            Receipt(
                packet_id=packet.id,
                written=False,
                findings=claimer_rows,
                causal_links=[],
                disposition="READY",
            ),
            bag,
        )
        claimer_ready = probed.disposition == "READY"
    if claimer_ready:
        findings = claimer_rows
    elif fiction:
        findings = frame_findings(hit_rows, miss_rows, packet)
    elif foundry_rows and not any(
        f.id in leftover_slot_ids() for f in foundry_rows if f.stamp == "grounded"
    ):
        findings = foundry_rows
    elif claimer_rows:
        findings = claimer_rows
    elif foundry_exc is not None:
        return _foundry_outcome(packet, rails, leftover, hit_urls, spine, foundry_exc, foundry_rows)
    else:
        findings = foundry_rows
    findings = [row for row in findings if row.id not in leftover_slot_ids()]
    findings = attach_cites_from_hits(findings, bag)
    if not findings or not any(row.parallel_status == "hit" for row in findings):
        leftover.extend(
            leftover_hit_exclusions(
                hit_rows + miss_rows,
                set(),
                reason="other",
                detail="Parallel hit did not become a finding. Not silently dropped.",
            )
        )
        if fiction:
            findings = frame_findings(hit_rows, miss_rows, packet)
        if not findings or not any(row.parallel_status == "hit" for row in findings):
            return (
                hold_receipt(packet.id, rails.model_copy(update={"parallel": False})),
                leftover,
                hit_urls,
                spine,
            )
    kept_urls = {f.parallel_url for f in findings if f.parallel_url}
    leftover.extend(
        leftover_hit_exclusions(
            hit_rows,
            kept_urls,
            reason="duplicate",
            detail="Same timeline search; not stamped as a finding.",
        )
        + leftover_hit_exclusions(
            miss_rows,
            kept_urls,
            reason="other",
            detail="Returned on the fringe search; not added as a source.",
        )
    )
    leftover.extend(_apply_extract(findings, extracted))
    if getattr(extracted, "results", None):
        try:
            enrich = run_task(
                prompt=f"Enrich the cited source at {hit_url} for {packet.topic or packet.hook}.",
                processor="base",
                task_spec=_ENRICH_SPEC,
            )
            _apply_enrichment(findings, enrich)
            sanitize_stamps(findings)
        except ParallelDownError:
            leftover.append(
                Exclusion(
                    what="Live Parallel enrichment task",
                    reason="rails_down",
                    detail="Enrichment Task down. Stamps stay missing. No invented citation.",
                )
            )
        except Exception as exc:
            if not _parallel_credit(exc):
                raise
            return _credit_hold(packet, hit_urls, leftover, "Live Parallel enrichment task")
    sanitize_stamps(findings)
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
    receipt = apply_verify_gate(
        Receipt(
            packet_id=packet.id,
            written=False,
            findings=findings,
            causal_links=[],
            disposition="READY",
        ),
        bag,
    )
    return receipt, leftover, hit_urls, spine


def _board(packet: Packet, rails: Rails) -> list:
    """Shot list from the timed VO, then Imagen onto those shots."""
    return write_board(packet, rails)


def run_live_packet(shift: ShiftRecord) -> Packet:
    """Spend path. Picks → Parallel pack → ADK writer → ADK room → storyboard on ship."""
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
    fresh_id = resolve_live_packet_id(shift.packet_id, shift.topic, shift.id)
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
        deeper_history=bool(shift.deeper_history),
    )
    bus.emit(shift.id, agent="researcher", kind="plan", message=f"Research {fresh.id} first-trigger")
    if not rails.parallel:
        write_receipt(
            fresh,
            pre1980_fail_closed(
                packet_id=fresh.id, depth=shift.depth, rails=rails, parallel_hits=0
            )
            or hold_receipt(fresh.id, rails),
        )
        write_vo_from_pack(fresh)
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

    receipt, leftover, hit_urls, spine = _research(fresh, rails, shift.depth)
    fresh.task_spine = spine
    fresh.parallel_research_loops = 1
    verify_held = receipt.disposition == "HOLD"
    try:
        write_receipt(fresh, receipt)
    except ReceiptInvalidError as exc:
        missing_cite = "grounded requires a Parallel URL" in str(exc)
        if missing_cite:
            # Cite-repair loop attaches or drops. Do not HOLD solely for missing cite_url.
            receipt.written = False
            receipt.packet_id = fresh.id
            fresh.receipt = receipt
            verify_held = False
        else:
            if receipt.disposition != "HOLD":
                sanitize_stamps(list(receipt.findings or []))
                receipt.disposition = "HOLD"
                leftover = _hold_account_hits(hit_urls, list(leftover or []))
            verify_held = True
            prior = (receipt.hold_reason or "").strip()
            receipt.hold_reason = f"{prior} ReceiptInvalidError: {exc}".strip()
            receipt.written = False
            try:
                write_receipt(fresh, receipt)
            except ReceiptInvalidError:
                receipt.written = True
                receipt.packet_id = fresh.id
                fresh.receipt = receipt
                fresh.status = "hold"
    if verify_held:
        if leftover:
            fresh.exclusions = leftover
        elif not fresh.exclusions:
            leftover = [
                Exclusion(
                    what="Live Parallel search",
                    reason="rails_down" if not rails.parallel else "not_searched",
                    detail=receipt.hold_reason or "Receipt HOLD. No invented source.",
                )
            ]
            fresh.exclusions = leftover
        if "credit" in (receipt.hold_reason or "").lower() or "402" in (
            receipt.hold_reason or ""
        ):
            fresh.collision_hold_reason = (
                "warning, not a clearance. Parallel credit. "
                "Never collision=no without a search of the finished VO."
            )
    write_vo_from_pack(fresh)

    def _cite_repair() -> bool:
        nonlocal leftover, hit_urls
        if not rails.parallel:
            return True
        repair = run_cite_recheck_loop(fresh, bag=getattr(fresh, "_cite_bag", None))
        if repair.hit_urls:
            hit_urls = list(dict.fromkeys([*(hit_urls or []), *repair.hit_urls]))
        if repair.ok:
            return True
        stamp_collisions(fresh, rails)
        attach_frames(fresh, [], rails=rails)
        fresh.exclusions = leftover
        write_research_pack(fresh, hit_urls=hit_urls)
        store.upsert_packet(fresh)
        return False

    if not _cite_repair():
        return fresh

    def _research_again(missing_ask: str | None = None) -> None:
        nonlocal leftover, hit_urls, receipt
        try:
            rec, leftover, hit_urls, again_spine = _research(
                fresh,
                rails,
                shift.depth,
                deeper_history=bool(shift.deeper_history),
                missing_ask=missing_ask,
            )
        except TypeError:
            rec, leftover, hit_urls, again_spine = _research(fresh, rails, shift.depth)
        receipt = rec
        fresh.task_spine = again_spine
        fresh.parallel_research_loops += 1
        if rec.disposition == "READY":
            try:
                write_receipt(fresh, rec)
            except ReceiptInvalidError:
                fresh.receipt = rec
            except ReceiptWriteOnceError:
                # ponytail: write-once already fired. Pack/spine already updated for rewrite.
                pass
        else:
            fresh.receipt = rec

    loop = run_room_loop(
        fresh,
        research=_research_again,
        rewrite=lambda: write_vo_from_pack(fresh),
        grader=getattr(shift, "room_grader", None),
        parallel_already=fresh.parallel_research_loops,
    )
    fresh.grade_artifact = make_grade_artifact(fresh)
    fresh.room_grade = loop.grade
    if loop.disposition == "HOLD":
        if fresh.receipt is not None:
            fresh.receipt.disposition = "HOLD"
            prior = (fresh.receipt.hold_reason or "").strip()
            fresh.receipt.hold_reason = f"{prior} {loop.hold_reason or ''}".strip()
        fresh.status = "hold"
        stamp_collisions(fresh, rails)
        attach_frames(fresh, [], rails=rails)
        fresh.exclusions = leftover
        write_research_pack(fresh, hit_urls=hit_urls)
        store.upsert_packet(fresh)
        return fresh

    if not _cite_repair():
        return fresh

    stamp_collisions(fresh, rails)
    bus.emit(shift.id, agent="boarder", kind="plan", message=f"Storyboard from script, cut={shift.cut}")
    frames = _board(fresh, rails)
    attach_frames(fresh, frames, rails=rails)
    fresh.exclusions = leftover
    write_research_pack(fresh, hit_urls=hit_urls)
    fresh.grade_artifact = make_grade_artifact(fresh)
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
    deeper_history: bool = False,
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
            deeper_history=deeper_history,
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
