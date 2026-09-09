"""Re-check Parallel for cite-faithfulness misses. Cap 3. Never invent a URL."""

from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field

from onecrew.foundry import (
    leftover_slot_ids,
    complete_print,
    clean_cite_url,
    _when,
    _slug,
    _unique_id,
)
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


def _vo_body(beat: ScriptBeat) -> str:
    from onecrew.script import _vo_lines

    return _vo_lines(f"{beat.vo} {beat.frame or ''}")


def _sourced_claim(beat: ScriptBeat) -> bool:
    from onecrew.script import pack_numbers

    vo = _vo_body(beat)
    nums = [n.replace("−", "-") for n in pack_numbers(vo)]
    if any(not _YEAR_TOK.fullmatch(n) for n in nums):
        return True
    return bool(_MONTH_YEAR.search(vo))


def _named_empty_cite_ids(packet: Packet) -> set[str]:
    reason = (packet.receipt.hold_reason or "") if packet.receipt else ""
    ids: set[str] = set()
    for match in _BEAT_NIT.finditer(reason):
        n = int(match.group(1))
        if 1 <= n <= len(_EIGHT_IDS):
            ids.add(_EIGHT_IDS[n - 1])
    for bid in _EIGHT_IDS:
        if re.search(rf"\b{re.escape(bid)}\s+cites nothing", reason, re.I):
            ids.add(bid)
    return ids


def empty_cite_beats(packet: Packet) -> list[ScriptBeat]:
    """Nonfiction VO beats that state a sourced claim but cite no pack finding."""
    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        return []
    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if f.id not in _LEFTOVER
    }
    named = _named_empty_cite_ids(packet)
    out: list[ScriptBeat] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading" or _is_hole(beat):
            continue
        fids = [fid for fid in beat.finding_ids if fid in known]
        if fids:
            continue
        if beat.id in named or _sourced_claim(beat):
            out.append(beat)
    return out


def _queries_for_beats(beats: list[ScriptBeat]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for beat in beats:
        ask = _vo_body(beat).strip()
        if not ask or ask in seen:
            continue
        seen.add(ask)
        out.append(ask[:240])
    return out


def _repair_queries(findings: list[Finding], beats: list[ScriptBeat]) -> list[str]:
    queries: list[str] = []
    if findings:
        for ask in _queries_for(findings):
            if ask == "cite support" and beats:
                continue
            if ask not in queries:
                queries.append(ask)
    for ask in _queries_for_beats(beats):
        if ask not in queries:
            queries.append(ask)
    return queries or ["cite support"]


def _print_in_text(printed: str, text: str) -> bool:
    want = re.sub(r"[^\d.]+", "", (printed or "").replace("−", "-"))
    if not want:
        return False
    blob = (text or "").replace("−", "-").replace(",", "")
    return want in re.sub(r"[^\d.]+", " ", blob)


def _finding_from_beat(beat: ScriptBeat, bag: CiteBag, used: set[str]) -> Finding | None:
    from onecrew.script import pack_numbers

    vo = _vo_body(beat)
    nums = [n for n in pack_numbers(vo) if not _YEAR_TOK.fullmatch(n.replace("−", "-"))]
    for excerpt in bag.excerpts:
        url = clean_cite_url(excerpt.url or "")
        if not url:
            continue
        blob = excerpt.text or ""
        printed = next((n for n in nums if _print_in_text(n, blob)), None)
        if printed is None and _MONTH_YEAR.search(vo) and _MONTH_YEAR.search(blob):
            printed = next((n for n in pack_numbers(blob) if complete_print(n)), None)
        if not printed or not complete_print(printed):
            continue
        when = _when(blob) or _when(vo)
        if not (when or "").strip():
            continue
        fid = _unique_id(_slug(beat.id or "event", when), used)
        return Finding(
            id=fid,
            claim=(blob or vo)[:400],
            stamp="grounded",
            title=(excerpt.title or beat.id),
            print=printed,
            when=when,
            parallel_url=url,
            parallel_status="hit",
            note="Parallel URL on this row.",
        )
    return None


def _attach_empty_cite_beats(packet: Packet, bag: CiteBag | None) -> list[str]:
    if bag is None or not (bag.excerpts or bag.hit_urls):
        return []
    receipt = packet.receipt
    if receipt is None:
        receipt = Receipt(packet_id=packet.id, written=False, findings=[], disposition="READY")
        packet.receipt = receipt
    used = {f.id for f in receipt.findings}
    attached: list[str] = []
    for beat in list(empty_cite_beats(packet)):
        finding = _finding_from_beat(beat, bag, used)
        if finding is None:
            continue
        receipt.findings.append(finding)
        if finding.id not in beat.finding_ids:
            beat.finding_ids.append(finding.id)
        if f"[{finding.id}]" not in beat.vo:
            beat.vo = f"{beat.vo} [{finding.id}]"
        attached.append(finding.id)
    return attached


def drop_empty_cite_beats(packet: Packet) -> list[str]:
    drop_ids = {b.id for b in empty_cite_beats(packet)}
    if not drop_ids or not _can_drop_cleanly(packet, drop_ids):
        return []
    dropped = [b.id for b in packet.beats if b.id in drop_ids]
    packet.beats = [b for b in packet.beats if b.id not in drop_ids]
    rebuild_timed_vo(packet)
    _retire_incomplete_grounded(packet)
    return dropped


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


def _recheck_parallel(
    findings: list[Finding],
    search_fn: SearchFn,
    beats: list[ScriptBeat] | None = None,
) -> tuple[CiteBag, str]:
    """status is ok | empty | down. Down is not a miss — do not drop on rail failure."""
    queries = _repair_queries(findings, beats or [])
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
        if url != have:
            relinked.append(
                finding.model_copy(
                    update={
                        "parallel_url": url or None,
                        "parallel_status": "hit" if url else "miss",
                    }
                )
            )
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


def _retire_incomplete_grounded(packet: Packet) -> None:
    """Grounded rows need a complete print and a Parallel URL. Junk ISM `4,` is not a finding."""
    receipt = packet.receipt
    if receipt is None:
        return
    for finding in receipt.findings:
        if finding.id in _LEFTOVER or finding.stamp != "grounded":
            continue
        printed = finding.print or ""
        official = finding.series in {
            "USREC",
            "BLS payrolls",
            "U-3",
            "GDP",
            "LEI",
            "SAHMREALTIME",
            "ISM",
        }
        incomplete = printed.endswith(",")
        if official:
            incomplete = incomplete or (
                not complete_print(printed) or not (finding.parallel_url or "").strip()
            )
        else:
            incomplete = incomplete or not (finding.parallel_url or "").strip()
        if not incomplete:
            continue
        finding.stamp = "fringe"
        finding.parallel_status = "miss"
        finding.parallel_url = None
        finding.note = "Incomplete stamp. Never sold as fact."


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
    "cites nothing in the pack",
    _EXHAUST_REASON,
)
_EIGHT_IDS = (
    "cold-open",
    "promise",
    "gdp",
    "labor",
    "turn",
    "complication",
    "receipt",
    "close",
)
_YEAR_TOK = re.compile(r"^20\d{2}$")
_MONTH_YEAR = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+20\d{2}\b",
    re.I,
)
_BEAT_NIT = re.compile(r"\bbeat(\d+)\s+cites nothing", re.I)


def _clear_cite_only_hold(packet: Packet, bag: CiteBag | None = None) -> None:
    """Successful attach/drop must not leave a cite-only HOLD."""
    if unsupported_cite_beats(packet, bag) or empty_cite_beats(packet):
        return
    _retire_incomplete_grounded(packet)
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
            if (finding.series or "") not in {"LEI", "U-3"}:
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
    """Scan missing URLs, print/when misses, and empty-cite sourced beats. Re-query up to 3. Attach or drop. HOLD on 4th."""
    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        return CiteRepairResult(ok=True, attempts=int(getattr(packet, "cite_recheck_attempts", 0) or 0))
    search_fn = search_fn or search
    attempts = int(getattr(packet, "cite_recheck_attempts", 0) or 0)
    attached_all: list[str] = []
    dropped_all: list[str] = []
    hit_urls: list[str] = []
    current_bag = _packet_bag(packet, bag)
    while True:
        if current_bag and (current_bag.hit_urls or current_bag.excerpts):
            attached_all.extend(_attach_from_bag(packet, current_bag))
            attached_all.extend(_attach_empty_cite_beats(packet, current_bag))
        missing = unsupported_cite_findings(packet, current_bag)
        empty = empty_cite_beats(packet)
        if not empty and (not missing or not unsupported_cite_beats(packet, current_bag)):
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
        fresh_bag, status = _recheck_parallel(missing, search_fn, empty)
        if fresh_bag.hit_urls or fresh_bag.excerpts:
            current_bag = _merge_bags(current_bag, fresh_bag)
            object.__setattr__(packet, "_cite_bag", current_bag)
        hit_urls.extend(u for u in fresh_bag.hit_urls if u not in hit_urls)
        attached_all.extend(_attach_from_bag(packet, current_bag or fresh_bag))
        attached_all.extend(_attach_empty_cite_beats(packet, current_bag or fresh_bag))
        still = {f.id for f in unsupported_cite_findings(packet, current_bag)}
        if still and status != "down":
            dropped_all.extend(drop_unsupported_beats(packet, still))
        if empty_cite_beats(packet) and status != "down":
            dropped_all.extend(drop_empty_cite_beats(packet))
