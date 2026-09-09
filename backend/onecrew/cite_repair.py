"""Re-check Parallel for cite-faithfulness misses. Cap 3. Never invent a URL."""

from __future__ import annotations

from typing import Any, Callable

from pydantic import BaseModel, Field

from onecrew.foundry import leftover_slot_ids
from onecrew.models import MISSING, Finding, Packet, Receipt, ScriptBeat
from onecrew.parallel_client import ParallelCreditError, ParallelDownError, search
from onecrew.tell import invents_frame
from onecrew.verify import (
    CiteBag,
    attach_cites_from_hits,
    cite_bag_from_rows,
    claims_from_findings,
    relink_unsupported_cite,
    verify_print_in_cite,
)

MAX_CITE_RECHECKS = 3
_EXHAUST_REASON = "cite-repair loop exhausted"
SearchFn = Callable[..., Any]
_LEFTOVER = leftover_slot_ids()


class CiteRepairResult(BaseModel):
    ok: bool
    attempts: int = 0
    attached_ids: list[str] = Field(default_factory=list)
    dropped_beat_ids: list[str] = Field(default_factory=list)
    hold_reason: str | None = None
    hit_urls: list[str] = Field(default_factory=list)


def _tc(total_s: int, *, hours: bool = False) -> str:
    if hours:
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def _is_hole(beat: ScriptBeat) -> bool:
    blob = f"{beat.vo} {beat.frame or ''}".lower()
    return "sahm hole" in blob or "no matching url" in blob


def _grounded_uncited(finding: Finding) -> bool:
    if finding.id in _LEFTOVER:
        return False
    if finding.stamp != "grounded":
        return False
    return not (finding.parallel_url or "").strip()


def missing_cite_findings(packet: Packet) -> list[Finding]:
    receipt = packet.receipt
    if receipt is None:
        return []
    return [f for f in receipt.findings if _grounded_uncited(f)]


def missing_cite_beats(packet: Packet) -> list[ScriptBeat]:
    return _spoken_beats_for(packet, {f.id for f in missing_cite_findings(packet)})


def _packet_bag(packet: Packet, bag: CiteBag | None = None) -> CiteBag | None:
    if bag is not None:
        return bag
    stored = getattr(packet, "_cite_bag", None)
    return stored if isinstance(stored, CiteBag) else None


def _finding_supported(finding: Finding, bag: CiteBag) -> bool:
    if _grounded_uncited(finding):
        return False
    claims = claims_from_findings([finding])
    if not claims:
        return True
    return verify_print_in_cite(claims[0], bag).ok


def unsupported_cite_findings(packet: Packet, bag: CiteBag | None = None) -> list[Finding]:
    """Spoken grounded rows missing a URL, or whose Parallel excerpt lacks print/when."""
    receipt = packet.receipt
    if receipt is None:
        return []
    bag = _packet_bag(packet, bag)
    spoken = {
        fid
        for beat in packet.beats
        if (beat.kind or "vo") != "heading" and not _is_hole(beat)
        for fid in beat.finding_ids
    }
    out: list[Finding] = []
    for finding in receipt.findings:
        if finding.id not in spoken or finding.id in _LEFTOVER or finding.stamp != "grounded":
            continue
        if _grounded_uncited(finding):
            out.append(finding)
            continue
        if bag is None:
            continue
        if not _finding_supported(finding, bag):
            out.append(finding)
    return out


def _spoken_beats_for(packet: Packet, finding_ids: set[str]) -> list[ScriptBeat]:
    out: list[ScriptBeat] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        if _is_hole(beat):
            continue
        if any(fid in finding_ids for fid in beat.finding_ids):
            out.append(beat)
    return out


def unsupported_cite_beats(packet: Packet, bag: CiteBag | None = None) -> list[ScriptBeat]:
    return _spoken_beats_for(packet, {f.id for f in unsupported_cite_findings(packet, bag)})


def _queries_for(findings: list[Finding]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for finding in findings:
        parts = [finding.series, finding.print, finding.when, finding.claim]
        ask = " ".join(
            p for p in parts if p and p not in {MISSING, None, ""}
        ).strip() or (finding.id or "cite support")
        if ask in seen:
            continue
        seen.add(ask)
        out.append(ask)
    return out or ["cite support"]


def _bag_from_search(result: Any) -> CiteBag:
    rows = list(getattr(result, "results", None) or [])
    urls = [url for url in (getattr(row, "url", None) for row in rows) if url]
    return cite_bag_from_rows(rows, spine="", hit_urls=urls)


def _merge_bags(prior: CiteBag | None, new: CiteBag) -> CiteBag:
    """Keep already-backed excerpts when a re-query returns a narrower hit set."""
    if prior is None:
        return new
    if not (new.hit_urls or new.excerpts):
        return prior
    urls = list(dict.fromkeys([*(prior.hit_urls or []), *(new.hit_urls or [])]))
    excerpts = list(prior.excerpts)
    seen = {(e.url, e.text) for e in excerpts}
    for excerpt in new.excerpts:
        key = (excerpt.url, excerpt.text)
        if key in seen:
            continue
        excerpts.append(excerpt)
        seen.add(key)
    return CiteBag(excerpts=excerpts, spine=new.spine or prior.spine, hit_urls=urls)


def _recheck_parallel(findings: list[Finding], search_fn: SearchFn) -> tuple[CiteBag, str]:
    """status is ok | empty | down. Down is not a miss — do not drop on rail failure."""
    queries = _queries_for(findings)
    objective = queries[0]
    try:
        result = search_fn(objective=objective, search_queries=queries)
    except (ParallelDownError, ParallelCreditError):
        return CiteBag(), "down"
    bag = _bag_from_search(result)
    return bag, ("ok" if bag.hit_urls else "empty")


def _attach_from_bag(packet: Packet, bag: CiteBag) -> list[str]:
    receipt = packet.receipt
    if receipt is None or not bag.hit_urls:
        return []
    before = {f.id: (f.parallel_url or "") for f in receipt.findings}
    receipt.findings = attach_cites_from_hits(list(receipt.findings), bag)
    relinked: list[Finding] = []
    for finding in receipt.findings:
        claims = claims_from_findings([finding])
        if not claims:
            relinked.append(finding)
            continue
        linked = relink_unsupported_cite(claims[0], bag)
        url = (linked.cite_url or "").strip()
        have = (finding.parallel_url or "").strip()
        if url and url != have:
            relinked.append(finding.model_copy(update={"parallel_url": url, "parallel_status": "hit"}))
            continue
        relinked.append(finding)
    receipt.findings = relinked
    attached: list[str] = []
    for finding in receipt.findings:
        now = (finding.parallel_url or "").strip()
        if now and now != (before.get(finding.id) or "").strip():
            attached.append(finding.id)
    return attached


def _beat_ids_for_findings(packet: Packet, finding_ids: set[str]) -> list[str]:
    out: list[str] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        if _is_hole(beat):
            continue
        if any(fid in finding_ids for fid in beat.finding_ids):
            out.append(beat.id)
    return out


def _can_drop_cleanly(packet: Packet, drop_ids: set[str]) -> bool:
    remaining = [
        b
        for b in packet.beats
        if (b.kind or "vo") != "heading" and b.id not in drop_ids
    ]
    return bool(remaining)


def rebuild_timed_vo(packet: Packet) -> None:
    """Retime remaining VO beats. Prefer a coherent remaining timed script."""
    from onecrew.cut import is_long_cut

    beats = [b for b in packet.beats if (b.kind or "vo") != "heading"]
    short = packet.cut in {"tiktok-length", "shorts"}
    hours = bool(packet.cut and is_long_cut(packet.cut) and not short)
    lean = packet.script_lean or "centered_independent"
    cursor = 0
    for i, beat in enumerate(beats):
        beat.start = _tc(cursor, hours=hours)
        beat.scene = f"BEAT {i + 1} — {beat.id}"
        cursor += max(1, beat.duration_s)
    lines = [
        f"Timed VO · {packet.platform or 'missing'} · {packet.cut or 'missing'} · {lean}"
        + (f" · {packet.tell}" if packet.tell else "")
        + (f" · {packet.tone}" if packet.tone else ""),
        "",
    ]
    elapsed = 0
    last_act = None
    for beat in beats:
        if beat.act and beat.act != last_act:
            lines.append(beat.act)
            last_act = beat.act
        lines.append(beat.scene)
        elapsed += max(1, beat.duration_s)
        lines.append(f"{beat.start}–{_tc(elapsed, hours=hours)}")
        if beat.camera:
            lines.append(beat.camera)
        if beat.frame:
            lines.append(f"ACTION: {beat.frame}")
        lines.append(beat.vo)
        lines.append("")
    packet.beats = beats
    packet.script = ("\n".join(lines).strip() + "\n") if beats else ""
    kept = {b.id for b in beats}
    packet.frames = [f for f in packet.frames if f.beat_id in kept]


def _retire_uncited_grounded(packet: Packet) -> None:
    """Unspoken grounded rows without a URL are not shipped. Tag fringe — do not invent a cite."""
    receipt = packet.receipt
    if receipt is None:
        return
    cited = {fid for beat in packet.beats for fid in beat.finding_ids}
    for finding in receipt.findings:
        if finding.id in cited or not _grounded_uncited(finding):
            continue
        finding.stamp = "fringe"
        finding.parallel_status = "miss"
        finding.parallel_url = None
        finding.note = "Parallel miss. Included and tagged fringe. Never sold as fact."


_CITE_HOLD_MARKERS = (
    "grounded requires a Parallel URL",
    "grounded claim missing cite_url",
    "cite_url not in hits",
    "cite_url series mismatch",
    "print not in cite",
    "when not in cite",
    _EXHAUST_REASON,
)


def _clear_cite_only_hold(packet: Packet, bag: CiteBag | None = None) -> None:
    """Successful attach/drop must not leave a cite-only HOLD."""
    if unsupported_cite_beats(packet, bag):
        return
    _retire_uncited_grounded(packet)
    receipt = packet.receipt
    if receipt is None:
        packet.status = "ready"
        return
    # ponytail: print/when stays HOLD until a CiteBag proves remaining spoken beats.
    markers = _CITE_HOLD_MARKERS if bag is not None else tuple(
        m for m in _CITE_HOLD_MARKERS if m not in {"print not in cite", "when not in cite"}
    )
    reason = (receipt.hold_reason or "").strip()
    if receipt.disposition == "HOLD" and reason:
        kept = [
            part.strip()
            for part in reason.replace("\n", ";").split(";")
            if part.strip() and not any(m.lower() in part.lower() for m in markers)
        ]
        # ReceiptInvalidError prefixes a cite-only reason as one clause.
        if not kept and any(m.lower() in reason.lower() for m in markers):
            receipt.hold_reason = None
            receipt.disposition = "READY"
        elif kept:
            receipt.hold_reason = "; ".join(kept)
        else:
            receipt.hold_reason = None
            receipt.disposition = "READY"
    elif receipt.disposition != "HOLD":
        receipt.disposition = "READY"
    if receipt.disposition == "READY":
        packet.status = "ready"


def drop_unsupported_beats(packet: Packet, finding_ids: set[str]) -> list[str]:
    drop_ids = set(_beat_ids_for_findings(packet, finding_ids))
    if not drop_ids or not _can_drop_cleanly(packet, drop_ids):
        return []
    dropped = [b.id for b in packet.beats if b.id in drop_ids]
    packet.beats = [b for b in packet.beats if b.id not in drop_ids]
    rebuild_timed_vo(packet)
    _retire_uncited_grounded(packet)
    receipt = packet.receipt
    cited = {fid for beat in packet.beats for fid in beat.finding_ids}
    if receipt is not None:
        for finding in receipt.findings:
            if finding.id not in finding_ids or finding.id in cited:
                continue
            if (finding.series or "") != "LEI":
                continue
            finding.stamp = "fringe"
            finding.parallel_status = "miss"
            finding.parallel_url = None
            finding.note = "Cite-repair dropped this beat. Never sold as fact."
    return dropped


def _hold_exhausted(packet: Packet, attempts: int) -> CiteRepairResult:
    packet.cite_recheck_attempts = attempts
    receipt = packet.receipt
    if receipt is None:
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            findings=[],
            causal_links=[],
            disposition="HOLD",
            hold_reason=_EXHAUST_REASON,
        )
        packet.receipt = receipt
    else:
        receipt.disposition = "HOLD"
        prior = (receipt.hold_reason or "").strip()
        if _EXHAUST_REASON not in prior:
            receipt.hold_reason = f"{prior} {_EXHAUST_REASON}".strip() if prior else _EXHAUST_REASON
    packet.status = "hold"
    return CiteRepairResult(
        ok=False,
        attempts=attempts,
        hold_reason=_EXHAUST_REASON,
    )


def run_cite_recheck_loop(
    packet: Packet,
    *,
    search_fn: SearchFn | None = None,
    bag: CiteBag | None = None,
) -> CiteRepairResult:
    """Scan missing URLs and print/when misses. Re-query up to 3 times. Attach or drop. HOLD on 4th."""
    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        return CiteRepairResult(ok=True, attempts=int(getattr(packet, "cite_recheck_attempts", 0) or 0))
    search_fn = search_fn or search
    attempts = int(getattr(packet, "cite_recheck_attempts", 0) or 0)
    attached_all: list[str] = []
    dropped_all: list[str] = []
    hit_urls: list[str] = []
    current_bag = _packet_bag(packet, bag)
    while True:
        if current_bag and current_bag.hit_urls:
            attached_all.extend(_attach_from_bag(packet, current_bag))
        missing = unsupported_cite_findings(packet, current_bag)
        if not missing or not unsupported_cite_beats(packet, current_bag):
            packet.cite_recheck_attempts = attempts
            _clear_cite_only_hold(packet, current_bag)
            return CiteRepairResult(
                ok=True,
                attempts=attempts,
                attached_ids=attached_all,
                dropped_beat_ids=dropped_all,
                hit_urls=hit_urls,
            )
        if attempts >= MAX_CITE_RECHECKS:
            result = _hold_exhausted(packet, attempts)
            result.attached_ids = attached_all
            result.dropped_beat_ids = dropped_all
            result.hit_urls = hit_urls
            return result
        attempts += 1
        packet.cite_recheck_attempts = attempts
        fresh_bag, status = _recheck_parallel(missing, search_fn)
        if fresh_bag.hit_urls or fresh_bag.excerpts:
            current_bag = _merge_bags(current_bag, fresh_bag)
            object.__setattr__(packet, "_cite_bag", current_bag)
        hit_urls.extend(u for u in fresh_bag.hit_urls if u not in hit_urls)
        attached_all.extend(_attach_from_bag(packet, current_bag or fresh_bag))
        still = {f.id for f in unsupported_cite_findings(packet, current_bag)}
        if still and status != "down":
            dropped = drop_unsupported_beats(packet, still)
            dropped_all.extend(dropped)
