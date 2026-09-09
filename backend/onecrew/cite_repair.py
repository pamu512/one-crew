"""Re-check Parallel for cite-faithfulness misses. Cap 3. Never invent a URL."""

from __future__ import annotations

import re
from typing import Any, Callable

from pydantic import BaseModel, Field

from onecrew.foundry import (
    complete_print,
    clean_cite_url,
    _when,
    is_excerpt_slot_id,
    is_pack_slot_id,
    keep_official_gdp,
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
    if is_pack_slot_id(finding.id):
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
        if finding.id not in spoken or is_pack_slot_id(finding.id) or finding.stamp != "grounded":
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
    from onecrew.script import is_comparative_vo, pack_numbers

    vo = _vo_body(beat)
    nums = [n.replace("−", "-") for n in pack_numbers(vo)]
    if any(not _YEAR_TOK.fullmatch(n) for n in nums):
        return True
    if _MONTH_YEAR.search(vo):
        return True
    return is_comparative_vo(vo)


def _attachable_claim(beat: ScriptBeat) -> bool:
    if _sourced_claim(beat):
        return True
    from onecrew.timeline import vo_proper_names

    return bool(vo_proper_names(f"{_vo_body(beat)} {beat.frame or ''}"))


def is_cite_faithfulness_hold(reason: str) -> bool:
    """Room/disposition HOLD that must run cite-repair. Not a leftover-slot synonym."""
    blob = (reason or "").lower()
    return any(
        marker in blob
        for marker in ("cite-faithfulness", "cites nothing", "covering miss", "soft-wrong")
    )


def stamp_cite_recheck_attempts(packet: Packet, attempts: int | None = None) -> int:
    """Write the counter on packet AND receipt. Shift persist reads the receipt."""
    n = int(getattr(packet, "cite_recheck_attempts", 0) or 0)
    receipt = packet.receipt
    if receipt is not None:
        n = max(n, int(getattr(receipt, "cite_recheck_attempts", 0) or 0))
    if attempts is not None:
        n = max(n, int(attempts or 0))
    reason = (receipt.hold_reason or "") if receipt else ""
    grade = getattr(packet, "room_grade", None)
    detail = getattr(grade, "recut_detail", "") or ""
    if is_cite_faithfulness_hold(f"{reason} {detail}"):
        n = max(n, 1)
    packet.cite_recheck_attempts = n
    if receipt is not None:
        receipt.cite_recheck_attempts = n
    return n


def _named_empty_cite_ids(packet: Packet) -> set[str]:
    reason = (packet.receipt.hold_reason or "") if packet.receipt else ""
    ids: set[str] = set()
    beats = [b for b in packet.beats if (b.kind or "vo") != "heading"]
    for match in _BEAT_NIT.finditer(reason):
        n = int(match.group(1))
        ids.add(f"beat{n}")
        if 1 <= n <= len(beats):
            ids.add(beats[n - 1].id)
    for i, bid in enumerate(_EIGHT_IDS):
        if re.search(rf"\b{re.escape(bid)}\s+cites nothing", reason, re.I):
            ids.add(f"beat{i + 1}")
            if i < len(beats):
                ids.add(beats[i].id)
    return ids


def faithless_cite_beats(packet: Packet) -> list[ScriptBeat]:
    """Named-entity miss, print skew, or pack/slot chrome VO on a cited stamp."""
    from onecrew.script import (
        has_tone_chrome,
        is_action_chrome_vo,
        is_broad_scope_vo,
        is_hanging_clause_vo,
        is_incomplete_vo,
        is_pack_chrome_vo,
        is_print_hole,
        is_thin_frame,
        is_thin_title_read_vo,
        is_title_read_vo,
        is_unverified_meta_vo,
        stamp_scope,
    )
    from onecrew.timeline import (
        is_chrome_cover_stamp,
        stamp_covers_vo,
        union_supports_prints,
        vo_proper_names,
    )

    receipt = packet.receipt
    if receipt is None or invents_frame(cut=packet.cut, tell=packet.tell or ""):
        return []
    by_id = {f.id: f for f in receipt.findings}
    out: list[ScriptBeat] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading" or _is_hole(beat):
            continue
        if not beat.finding_ids and _attachable_claim(beat):
            # Sourced empty-cite waits for pack attach / Parallel. Not faithless.
            continue
        vo = _vo_body(beat)
        spoken = f"{vo} {beat.frame or ''}"
        tls = [
            by_id[fid]
            for fid in beat.finding_ids
            if fid in by_id and by_id[fid].stamp == "timeline_event"
        ]
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        if any(is_chrome_cover_stamp(f) for f in cited):
            out.append(beat)
            continue
        prior = [
            _vo_body(p)
            for p in packet.beats[: packet.beats.index(beat)]
            if (p.kind or "vo") != "heading"
        ]
        scope_hold = is_broad_scope_vo(vo) and cited and all(
            stamp_scope(f) == "narrow" for f in cited
        ) and any(stamp_scope(f) == "broad" for f in receipt.findings)
        if (
            has_tone_chrome(beat.vo)
            or is_unverified_meta_vo(beat.vo)
            or is_hanging_clause_vo(beat.vo)
            or is_incomplete_vo(beat.vo)
            or is_title_read_vo(beat.vo, cited)
            or is_thin_title_read_vo(beat.vo, cited, prior_prints=prior)
            or is_action_chrome_vo(beat.vo, beat.frame or "")
            or is_print_hole(vo)
            or is_thin_frame(beat.frame or "", list(beat.finding_ids), list(receipt.findings))
            or scope_hold
        ):
            out.append(beat)
            continue
        if is_pack_chrome_vo(vo) and tls:
            out.append(beat)
            continue
        names = vo_proper_names(spoken)
        name_ok = [f for f in tls if stamp_covers_vo(spoken, f)]
        if names and tls and (not name_ok or len(name_ok) != len(tls)):
            out.append(beat)
            continue
        print_rows = name_ok or tls
        if print_rows and not union_supports_prints(spoken, print_rows):
            from onecrew.timeline import _event_nums

            if _event_nums(spoken):
                out.append(beat)
                continue
        from onecrew.script import is_comparative_vo, is_forecast_theater_vo
        from onecrew.tell import wants_no_forecast_theater
        from onecrew.timeline import _event_nums, _print_bearing

        if is_comparative_vo(spoken) and not _event_nums(spoken):
            if not tls or not any(_print_bearing(f) for f in tls):
                out.append(beat)
                continue
        if wants_no_forecast_theater(packet.tell or "") and is_forecast_theater_vo(spoken):
            out.append(beat)
    return out


def empty_cite_beats(packet: Packet) -> list[ScriptBeat]:
    """Nonfiction titled/spoken beats with no pack finding. Chrome slots count."""
    from onecrew.script import is_placeholder_finding_id

    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        return []
    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if not is_pack_slot_id(f.id) and not is_placeholder_finding_id(f.id)
    }
    out: list[ScriptBeat] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading" or _is_hole(beat):
            continue
        if any(fid in known for fid in beat.finding_ids):
            continue
        out.append(beat)
    return out


def _hollow_uncited_beats(packet: Packet) -> list[ScriptBeat]:
    return [beat for beat in empty_cite_beats(packet) if not _attachable_claim(beat)]


def drop_hollow_uncited_beats(packet: Packet) -> list[str]:
    drop_ids = {b.id for b in _hollow_uncited_beats(packet)}
    if not drop_ids or not _can_drop_cleanly(packet, drop_ids):
        return []
    dropped = [b.id for b in packet.beats if b.id in drop_ids]
    packet.beats = [b for b in packet.beats if b.id not in drop_ids]
    rebuild_timed_vo(packet)
    _retire_incomplete_grounded(packet)
    return dropped


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


def _finding_from_beat(
    beat: ScriptBeat,
    bag: CiteBag,
    used: set[str],
    chain_urls: set[str] | None = None,
    pairs: list[tuple[str, str]] | None = None,
    findings: list[Finding] | None = None,
) -> Finding | None:
    from onecrew.script import is_comparative_vo, pack_numbers
    from onecrew.timeline import cite_host_ok, host_under_cap, spoken_basis_url, url_host

    vo = _vo_body(beat)
    nums = [n for n in pack_numbers(vo) if not _YEAR_TOK.fullmatch(n.replace("−", "-"))]
    excerpts = list(bag.excerpts or [])
    prefer = {u for u in (chain_urls or set()) if u}
    rows = list(pairs or [])
    want = spoken_basis_url(vo, rows) if rows else None
    if want:
        ranked = [e for e in excerpts if url_host(e.url or "") == url_host(want)]
        if not ranked:
            return None
        excerpts = ranked
    elif prefer:
        ranked = [e for e in excerpts if clean_cite_url(e.url or "") in prefer]
        if ranked:
            excerpts = ranked
        else:
            return None
    have = list(findings or [])
    for excerpt in excerpts:
        url = clean_cite_url(excerpt.url or "")
        if not url:
            continue
        if not host_under_cap(url, have, vo=vo, pairs=rows):
            continue
        blob = excerpt.text or ""
        printed = next((n for n in nums if _print_in_text(n, blob)), None)
        if printed is None and (
            (_MONTH_YEAR.search(vo) and _MONTH_YEAR.search(blob)) or is_comparative_vo(vo)
        ):
            printed = next((n for n in pack_numbers(blob) if complete_print(n)), None)
        if not printed or not complete_print(printed):
            continue
        when = _when(blob) or _when(vo)
        if not (when or "").strip():
            continue
        from onecrew.timeline import _tl_id

        if rows and not cite_host_ok(vo, url, rows):
            continue
        fid = _tl_id(blob or vo, url, used)
        return Finding(
            id=fid,
            claim=(blob or vo)[:400],
            stamp="timeline_event",
            title="timeline_event",
            series="timeline_event",
            print=printed,
            when=when,
            parallel_url=url,
            parallel_status="hit",
            note="Timeline event. Parallel URL on this row.",
        )
    return None


def _pack_text(packet: Packet) -> str:
    return "\n".join(p for p in ((packet.research_pack or ""), (packet.task_spine or "")) if p)


_GDP_EQ_TRILLION = re.compile(r"\bGDP\s*=\s*\$?[\d,.]+\s*(?:trillion|tn)\b", re.I)
_EXCERPT_TOKEN = re.compile(r"excerpts\[\d+\]", re.I)


def _chain_urls(packet: Packet) -> set[str]:
    return {u for _t, u in _chain_pairs(packet) if u}


def _chain_pairs(packet: Packet) -> list[tuple[str, str]]:
    from onecrew.timeline import chain_pairs

    mapping = (packet.receipt.timeline_map if packet.receipt else None) or []
    return chain_pairs(_pack_text(packet), mapping)


def _strip_excerpt_vo(text: str) -> str:
    cleaned = _EXCERPT_TOKEN.sub("", text or "")
    cleaned = re.sub(r"\[(?:\s*)\]", "", cleaned)
    cleaned = _GDP_EQ_TRILLION.sub("", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def drop_excerpt_slot_findings(packet: Packet) -> list[str]:
    """Drop pack excerpts[N] chrome and unofficial/fantasy GDP. Not a closed-series balloon."""
    receipt = packet.receipt
    if receipt is None:
        return []
    drop: set[str] = set()
    kept: list[Finding] = []
    for finding in receipt.findings:
        junk = is_excerpt_slot_id(finding.id)
        if finding.series == "GDP" and finding.stamp == "grounded":
            junk = junk or not keep_official_gdp(finding)
        if junk:
            drop.add(finding.id)
            continue
        kept.append(finding)
    if not drop:
        return []
    receipt.findings = kept
    for beat in packet.beats:
        beat.finding_ids = [fid for fid in beat.finding_ids if fid not in drop]
        beat.vo = _strip_excerpt_vo(beat.vo)
        if beat.frame:
            beat.frame = _strip_excerpt_vo(beat.frame)
    return list(drop)


def _stamp_pack_timeline(packet: Packet) -> list[str]:
    from onecrew.timeline import apply_timeline, cap_url_reuse, chain_pairs, plan_timeline

    receipt = packet.receipt
    if receipt is None:
        receipt = Receipt(packet_id=packet.id, written=False, findings=[], disposition="READY")
        packet.receipt = receipt
    pairs = chain_pairs(_pack_text(packet), receipt.timeline_map)
    receipt.findings = cap_url_reuse(list(receipt.findings), pairs)
    used = {f.id for f in receipt.findings}
    seen = {(f.parallel_url or "").strip() for f in receipt.findings if (f.parallel_url or "").strip()}
    planned = plan_timeline(
        _pack_text(packet),
        used=used,
        seen_urls=seen,
        hit_rows=list(getattr(packet, "exclusions", None) or []),
    )
    apply_timeline(receipt.findings, planned)
    receipt.findings = cap_url_reuse(list(receipt.findings), pairs or [(r.thesis, r.url) for r in planned.mapping])
    if planned.mapping:
        have = {(row.thesis, row.url, row.finding_id) for row in receipt.timeline_map}
        receipt.timeline_map = list(receipt.timeline_map) + [
            row for row in planned.mapping if (row.thesis, row.url, row.finding_id) not in have
        ]
    return [row.finding_id for row in planned.mapping]


def _attach_timeline_beats(packet: Packet) -> list[str]:
    from onecrew.timeline import (
        _event_nums,
        cite_host_ok,
        is_chrome_cover_stamp,
        stamp_covers_vo,
        stamp_supports_prints,
        stamps_for_vo,
    )

    receipt = packet.receipt
    if receipt is None:
        return []
    tls = [
        f
        for f in receipt.findings
        if f.stamp == "timeline_event"
        and (f.parallel_url or "").strip()
        and not is_chrome_cover_stamp(f)
    ]
    pairs = _chain_pairs(packet)
    by_id = {f.id: f for f in receipt.findings}
    attached: list[str] = []
    changed = False
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading" or _is_hole(beat):
            continue
        from onecrew.script import _vo_lines

        spoken = _vo_lines(beat.vo)
        vo = _vo_body(beat)
        keep: list[str] = []
        from onecrew.script import is_placeholder_finding_id

        for fid in beat.finding_ids:
            if is_placeholder_finding_id(fid):
                beat.vo = re.sub(rf"\s*\[{re.escape(fid)}\]", "", beat.vo).strip()
                continue
            finding = by_id.get(fid)
            if finding is None or finding.stamp != "timeline_event":
                keep.append(fid)
                continue
            covered = stamp_covers_vo(vo, finding)
            if is_chrome_cover_stamp(finding):
                beat.vo = re.sub(rf"\s*\[{re.escape(fid)}\]", "", beat.vo).strip()
                continue
            if pairs and not cite_host_ok(vo, finding.parallel_url or "", pairs) and not covered:
                beat.vo = re.sub(rf"\s*\[{re.escape(fid)}\]", "", beat.vo).strip()
                continue
            if not covered:
                beat.vo = re.sub(rf"\s*\[{re.escape(fid)}\]", "", beat.vo).strip()
                continue
            if _event_nums(vo) and not stamp_supports_prints(vo, finding):
                beat.vo = re.sub(rf"\s*\[{re.escape(fid)}\]", "", beat.vo).strip()
                continue
            keep.append(fid)
        from onecrew.timeline import host_under_cap

        for finding in stamps_for_vo(vo, tls, pairs):
            if pairs and not cite_host_ok(vo, finding.parallel_url or "", pairs) and not stamp_covers_vo(vo, finding):
                continue
            if not host_under_cap(
                finding.parallel_url or "",
                list(receipt.findings),
                vo=vo,
                pairs=pairs,
            ) and not stamp_covers_vo(vo, finding):
                continue
            if finding.id not in keep:
                keep.append(finding.id)
            if f"[{finding.id}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{finding.id}]"
            attached.append(finding.id)
        had_ids = bool(beat.finding_ids)
        if beat.finding_ids != keep:
            changed = True
        beat.finding_ids = keep
        if not keep and not had_ids:
            # Empty-cite VO stays searchable. Align-strip here would hollow
            # named/print claims and skip Parallel (attempts stay 0).
            continue
        from onecrew.script import (
            _align_vo_to_stamps,
            _drop_extra_cite_brackets,
            _refuse_forecast_theater,
            is_pack_chrome_vo,
            is_print_hole,
            is_thin_frame,
            speak_stamp_fact,
            speak_stamps,
        )
        from onecrew.timeline import cap_beat_cites

        keep, new_vo = _align_vo_to_stamps(spoken, keep, list(receipt.findings))
        _, new_frame = _align_vo_to_stamps(beat.frame or "", list(keep), list(receipt.findings))
        keep, new_vo, _ = _refuse_forecast_theater(new_vo, keep, list(receipt.findings), packet.tell or "")
        _, new_frame, _ = _refuse_forecast_theater(
            new_frame, keep, list(receipt.findings), packet.tell or ""
        )
        keep = cap_beat_cites(new_vo, keep, list(receipt.findings))
        new_vo = _drop_extra_cite_brackets(new_vo, keep)
        new_frame = _drop_extra_cite_brackets(new_frame, keep)
        if is_pack_chrome_vo(new_vo) or is_print_hole(new_vo) or not (new_vo or "").strip():
            fact = speak_stamp_fact(keep, list(receipt.findings)) or speak_stamps(
                keep, list(receipt.findings)
            )
            if fact:
                new_vo = fact
            elif is_pack_chrome_vo(new_vo):
                new_vo = ""
        if is_thin_frame(new_frame, keep, list(receipt.findings)) or not (new_frame or "").strip():
            if keep:
                new_frame = (
                    speak_stamp_fact(keep, list(receipt.findings))
                    or speak_stamps(keep, list(receipt.findings))
                    or new_frame
                )
        if new_vo != spoken:
            beat.vo = f"NARRATOR\n{new_vo}" if (beat.vo or "").startswith("NARRATOR") else new_vo
            changed = True
        for fid in list(keep):
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"
                changed = True
        if new_frame != (beat.frame or ""):
            beat.frame = new_frame
            changed = True
        if beat.finding_ids != keep:
            changed = True
        beat.finding_ids = keep
    if attached or changed:
        rebuild_timed_vo(packet)
    return attached


def _attach_empty_cite_beats(packet: Packet, bag: CiteBag | None) -> list[str]:
    if bag is None or not (bag.excerpts or bag.hit_urls):
        return []
    receipt = packet.receipt
    if receipt is None:
        receipt = Receipt(packet_id=packet.id, written=False, findings=[], disposition="READY")
        packet.receipt = receipt
    used = {f.id for f in receipt.findings}
    attached: list[str] = []
    pairs = _chain_pairs(packet)
    chain = {u for _t, u in pairs if u}
    for beat in list(empty_cite_beats(packet)):
        if not _attachable_claim(beat):
            continue
        finding = _finding_from_beat(
            beat, bag, used, chain_urls=chain, pairs=pairs, findings=list(receipt.findings)
        )
        if finding is None:
            continue
        receipt.findings.append(finding)
        if finding.id not in beat.finding_ids:
            beat.finding_ids.append(finding.id)
        if f"[{finding.id}]" not in beat.vo:
            beat.vo = f"{beat.vo} [{finding.id}]"
        if finding.stamp == "timeline_event" and (finding.parallel_url or "").strip():
            from onecrew.models import TimelineMapRow
            from onecrew.timeline import log as timeline_log

            thesis = _vo_body(beat)
            row = TimelineMapRow(
                thesis=thesis, url=finding.parallel_url or "", finding_id=finding.id
            )
            timeline_log.info("timeline map: %s -> %s -> %s", row.thesis, row.url, row.finding_id)
            receipt.timeline_map = list(receipt.timeline_map) + [row]
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
        beat.scene = f"BEAT {i + 1}"
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
    from onecrew.script import neutralize_pack_slot_beats

    neutralize_pack_slot_beats(packet)


def _retire_incomplete_grounded(packet: Packet) -> None:
    """Grounded rows need a complete print and a Parallel URL. Junk ISM `4,` is not a finding."""
    receipt = packet.receipt
    if receipt is None:
        return
    for finding in receipt.findings:
        if is_pack_slot_id(finding.id) or finding.stamp != "grounded":
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
        if finding.series == "GDP":
            incomplete = incomplete or not keep_official_gdp(finding)
        elif official:
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


_RECEIPT_INVALID = re.compile(r"^receiptinvaliderror:\s*", re.I)


def _hold_clauses(reason: str) -> list[str]:
    return [p.strip() for p in (reason or "").replace("\n", ";").split(";") if p.strip()]


_BEAT_CITE_NOTHING = re.compile(
    r"^(?:beat\d+|[a-z][a-z0-9-]*)\s+cites nothing in the pack$",
    re.I,
)


def _clause_is_cite_marker(
    part: str, markers: tuple[str, ...], *, extra: tuple[str, ...] = ()
) -> bool:
    """Cite markers are whole clauses. Extra (gone GDP/dupes) may prefix a mashed clause."""
    raw = (part or "").strip()
    core = _RECEIPT_INVALID.sub("", raw).strip().lower()
    if not core:
        return False
    prefixed = bool(_RECEIPT_INVALID.match(raw))
    for marker in markers:
        ml = marker.lower()
        if core == ml:
            return True
        if ml == "cites nothing in the pack" and _BEAT_CITE_NOTHING.fullmatch(core):
            return True
        if ml == "cite-faithfulness" and "cite-faithfulness" in core:
            return True
        if prefixed and (core.startswith(ml + " ") or core.startswith(ml + ":") or core.startswith(ml)):
            return True
    for marker in extra:
        ml = marker.lower()
        if core == ml or core.startswith(ml + " ") or core.startswith(ml + ":"):
            return True
    return False


_EMPTY_BEAT_REASON = "empty beat has no pack finding"
_CITE_HOLD_MARKERS = (
    "grounded requires a Parallel URL",
    "grounded claim missing cite_url",
    "cite_url not in hits",
    "cite_url series mismatch",
    "print not in cite",
    "when not in cite",
    "cites nothing in the pack",
    "uncited claim",
    "cite-faithfulness",
    "pack slot token stripped from VO",
    _EMPTY_BEAT_REASON,
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


def _repair_faithless_beats(packet: Packet) -> list[str]:
    from onecrew.script import (
        _align_vo_to_stamps,
        _drop_extra_cite_brackets,
        _refuse_forecast_theater,
        _speech_norm,
        _strip_tone_chrome,
        _vo_lines,
        drop_thin_title_read_beats,
        has_tone_chrome,
        is_action_chrome_vo,
        is_hanging_clause_vo,
        is_incomplete_vo,
        is_pack_chrome_vo,
        is_placeholder_finding_id,
        is_print_hole,
        is_thin_frame,
        is_thin_title_read_vo,
        is_title_read_vo,
        is_unverified_meta_vo,
        strip_hanging_clause_vo,
        strip_unverified_meta_vo,
        prefer_covering_print,
        prefer_covering_scope,
        speak_stamp_fact,
        speak_stamps,
        strip_action_chrome_vo,
    )
    from onecrew.timeline import cap_beat_cites

    receipt = packet.receipt
    if receipt is None:
        return []
    changed = False
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading" or _is_hole(beat):
            continue
        if not beat.finding_ids and _attachable_claim(beat):
            continue
        orig_vo = _vo_lines(beat.vo)
        vo = strip_action_chrome_vo(orig_vo, beat.frame or "")
        keep, _ = prefer_covering_scope(
            vo,
            [fid for fid in beat.finding_ids if not is_placeholder_finding_id(fid)],
            list(receipt.findings),
        )
        keep, print_hold = prefer_covering_print(vo, keep, list(receipt.findings))
        if print_hold:
            keep = []
        keep, new_vo = _align_vo_to_stamps(vo, keep, list(receipt.findings))
        _, new_frame = _align_vo_to_stamps(beat.frame or "", list(keep), list(receipt.findings))
        keep, new_vo, _ = _refuse_forecast_theater(new_vo, keep, list(receipt.findings), packet.tell or "")
        _, new_frame, _ = _refuse_forecast_theater(
            new_frame, keep, list(receipt.findings), packet.tell or ""
        )
        keep = cap_beat_cites(new_vo, keep, list(receipt.findings))
        new_vo = _drop_extra_cite_brackets(new_vo, keep)
        new_frame = _drop_extra_cite_brackets(new_frame, keep)
        new_vo, _ = _strip_tone_chrome(new_vo)
        if is_unverified_meta_vo(new_vo):
            new_vo = strip_unverified_meta_vo(new_vo)
        if is_hanging_clause_vo(new_vo) or is_incomplete_vo(new_vo):
            from onecrew.script import strip_incomplete_vo

            new_vo = strip_incomplete_vo(new_vo)
        cited = [f for f in receipt.findings if f.id in keep]
        prior = [_vo_lines(p.vo) for p in packet.beats[: packet.beats.index(beat)] if (p.kind or "vo") != "heading"]
        if is_title_read_vo(new_vo, cited) or is_print_hole(new_vo) or is_incomplete_vo(new_vo):
            spoken = speak_stamp_fact(keep, list(receipt.findings))
            if spoken and not is_thin_title_read_vo(spoken, cited, prior_prints=prior):
                new_vo = spoken
            elif is_thin_title_read_vo(new_vo, cited, prior_prints=prior):
                new_vo = ""
                keep = []
        elif (
            has_tone_chrome(new_vo)
            or is_unverified_meta_vo(new_vo)
            or is_hanging_clause_vo(new_vo)
            or is_incomplete_vo(new_vo)
            or is_pack_chrome_vo(new_vo)
            or is_action_chrome_vo(new_vo, beat.frame or "")
        ):
            new_vo = speak_stamps(keep, list(receipt.findings))
        elif not (new_vo or "").strip():
            new_vo = speak_stamps(keep, list(receipt.findings))
        elif is_thin_title_read_vo(new_vo, cited, prior_prints=prior):
            spoken = speak_stamp_fact(keep, list(receipt.findings))
            if spoken and not is_thin_title_read_vo(spoken, cited, prior_prints=prior):
                new_vo = spoken
            else:
                new_vo = ""
                keep = []
        if keep and not _speech_norm(new_vo):
            new_vo = speak_stamp_fact(keep, list(receipt.findings)) or speak_stamps(
                keep, list(receipt.findings)
            )
        if is_pack_chrome_vo(new_frame) or is_thin_frame(new_frame, keep, list(receipt.findings)):
            new_frame = speak_stamp_fact(keep, list(receipt.findings)) or ""
        beat.finding_ids = keep
        if new_vo != orig_vo:
            beat.vo = f"NARRATOR\n{new_vo}" if (beat.vo or "").startswith("NARRATOR") else new_vo
            changed = True
        for fid in keep:
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"
                changed = True
        if new_frame != (beat.frame or ""):
            beat.frame = new_frame
            changed = True
    dropped = drop_thin_title_read_beats(packet)
    if changed or dropped:
        rebuild_timed_vo(packet)
    return dropped


def _clear_cite_only_hold(packet: Packet, bag: CiteBag | None = None) -> None:
    """Successful attach/drop must not leave a cite-only HOLD."""
    from onecrew.script import _legal_spoken_finding, vo_has_pack_slot_token

    if unsupported_cite_beats(packet, bag) or empty_cite_beats(packet) or faithless_cite_beats(packet):
        return
    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if _legal_spoken_finding(f)
    }
    if any(
        vo_has_pack_slot_token(b.vo, known) or vo_has_pack_slot_token(b.frame or "", known)
        for b in packet.beats
        if (b.kind or "vo") != "heading"
    ):
        return
    _retire_incomplete_grounded(packet)
    _retire_uncited_grounded(packet)
    receipt = packet.receipt
    if receipt is None:
        packet.status = "ready"
        return
    from onecrew.timeline import clear_empty_mint_hold

    clear_empty_mint_hold(
        receipt,
        notes="\n".join(
            p for p in ((packet.research_pack or ""), (packet.task_spine or "")) if p
        ),
    )
    # ponytail: print/when stays HOLD until a CiteBag proves remaining spoken beats.
    markers = _CITE_HOLD_MARKERS if bag is not None else tuple(
        m for m in _CITE_HOLD_MARKERS if m not in {"print not in cite", "when not in cite"}
    )
    remaining_gdp = [
        f
        for f in receipt.findings
        if f.series == "GDP" and f.stamp == "grounded" and keep_official_gdp(f)
    ]
    series_counts: dict[str, int] = {}
    for finding in receipt.findings:
        if finding.stamp != "grounded" or is_pack_slot_id(finding.id):
            continue
        series = (finding.series or "").strip()
        if series in {"USREC", "BLS payrolls", "U-3", "GDP", "LEI", "SAHMREALTIME"}:
            series_counts[series] = series_counts.get(series, 0) + 1
    extra: list[str] = []
    if not remaining_gdp:
        extra.append("gdp bars mismatch")
    if not any(n > 1 for n in series_counts.values()):
        extra.append("duplicate series")
    extra_t = tuple(extra)
    reason = (receipt.hold_reason or "").strip()
    if receipt.disposition == "HOLD" and reason:
        kept = [
            part
            for part in _hold_clauses(reason)
            if not _clause_is_cite_marker(part, markers, extra=extra_t)
        ]
        if not kept and any(
            _clause_is_cite_marker(p, markers, extra=extra_t) for p in _hold_clauses(reason)
        ):
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


def _board_gate_reason(packet: Packet) -> str | None:
    from collections import Counter

    from onecrew.script import is_forecast_theater_vo
    from onecrew.tell import wants_no_forecast_theater
    from onecrew.timeline import MAX_CITES_PER_BEAT, URL_REUSE_CAP, url_host
    from onecrew.verify import CLOSED_SERIES

    if wants_no_forecast_theater(packet.tell or ""):
        for beat in packet.beats:
            if is_forecast_theater_vo(f"{beat.vo} {beat.frame or ''}"):
                return "forecast theater"
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    used: Counter[str] = Counter()
    seen: set[str] = set()
    for beat in packet.beats:
        other = [
            fid
            for fid in beat.finding_ids
            if fid in by_id and (by_id[fid].series or "").strip() not in CLOSED_SERIES
        ]
        if len(other) > MAX_CITES_PER_BEAT:
            return "over-cite"
        for fid in other:
            if fid in seen:
                continue
            seen.add(fid)
            host = url_host(by_id[fid].parallel_url or "")
            if host:
                used[host] += 1
    if any(n > URL_REUSE_CAP for n in used.values()):
        return "host reuse"
    from onecrew.script import is_broad_scope_vo, stamp_scope

    covering = [f for f in (receipt.findings if receipt else []) if stamp_scope(f) == "broad"]
    if covering:
        for beat in packet.beats:
            cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
            if is_broad_scope_vo(beat.vo) and cited and all(stamp_scope(f) == "narrow" for f in cited):
                return "cite-faithfulness"
    from onecrew.script import ensure_topic_axes, refuse_thin_episode

    thin = refuse_thin_episode(packet)
    axis = ensure_topic_axes(packet)
    if thin or axis:
        rebuild_timed_vo(packet)
        return thin or axis
    return None


def _hold_reason(packet: Packet, attempts: int, reason: str) -> CiteRepairResult:
    stamp_cite_recheck_attempts(packet, attempts)
    receipt = packet.receipt
    if receipt is None:
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            findings=[],
            causal_links=[],
            disposition="HOLD",
            hold_reason=reason,
        )
        packet.receipt = receipt
    else:
        receipt.disposition = "HOLD"
        prior = (receipt.hold_reason or "").strip()
        if reason not in prior.lower():
            receipt.hold_reason = f"{prior}; {reason}".strip() if prior else reason
    packet.status = "hold"
    return CiteRepairResult(ok=False, attempts=attempts, hold_reason=reason)


def _hold_cite_faithfulness(packet: Packet, attempts: int) -> CiteRepairResult:
    stamp_cite_recheck_attempts(packet, attempts)
    receipt = packet.receipt
    reason = "cite-faithfulness"
    if receipt is None:
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            findings=[],
            causal_links=[],
            disposition="HOLD",
            hold_reason=reason,
        )
        packet.receipt = receipt
    else:
        receipt.disposition = "HOLD"
        prior = (receipt.hold_reason or "").strip()
        if "cite-faithfulness" not in prior.lower():
            receipt.hold_reason = f"{prior}; {reason}".strip() if prior else reason
    packet.status = "hold"
    return CiteRepairResult(ok=False, attempts=attempts, hold_reason=reason)


def _hold_empty_beats(packet: Packet, attempts: int) -> CiteRepairResult:
    stamp_cite_recheck_attempts(packet, attempts)
    receipt = packet.receipt
    if receipt is None:
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            findings=[],
            causal_links=[],
            disposition="HOLD",
            hold_reason=_EMPTY_BEAT_REASON,
        )
        packet.receipt = receipt
    else:
        receipt.disposition = "HOLD"
        prior = (receipt.hold_reason or "").strip()
        if _EMPTY_BEAT_REASON not in prior:
            receipt.hold_reason = (
                f"{prior}; {_EMPTY_BEAT_REASON}".strip() if prior else _EMPTY_BEAT_REASON
            )
    packet.status = "hold"
    return CiteRepairResult(ok=False, attempts=attempts, hold_reason=_EMPTY_BEAT_REASON)


def _hold_exhausted(packet: Packet, attempts: int) -> CiteRepairResult:
    stamp_cite_recheck_attempts(packet, attempts)
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
            receipt.hold_reason = f"{prior}; {_EXHAUST_REASON}".strip() if prior else _EXHAUST_REASON
    packet.status = "hold"
    return CiteRepairResult(
        ok=False,
        attempts=attempts,
        hold_reason=_EXHAUST_REASON,
    )


def _credit_hold(packet: Packet) -> bool:
    reason = (packet.receipt.hold_reason or "") if packet.receipt else ""
    return "credit" in reason.lower() or "402" in reason


def _hits_present(packet: Packet) -> bool:
    from onecrew.timeline import parse_parallel_hits

    rows = list(getattr(packet, "exclusions", None) or [])
    if parse_parallel_hits(_pack_text(packet), rows):
        return True
    if any((getattr(row, "url", None) or "").startswith("http") for row in rows):
        return True
    blob = _pack_text(packet)
    return "Left out:" in blob and "URL: http" in blob


def _hold_if_hits_unstamped(packet: Packet, attempts: int) -> CiteRepairResult | None:
    """Do not burn 3 empty repair loops on blank VO when hits never became stamps."""
    from onecrew.timeline import UNSTAMPED_HITS, has_timeline_url

    receipt = packet.receipt
    if receipt is None:
        return None
    if has_timeline_url(receipt.findings):
        return None
    if any((f.parallel_url or "").strip() for f in receipt.findings):
        return None
    if empty_cite_beats(packet) or unsupported_cite_findings(packet):
        return None
    if not _hits_present(packet):
        return None
    receipt.disposition = "HOLD"
    prior = (receipt.hold_reason or "").strip()
    if UNSTAMPED_HITS not in prior:
        receipt.hold_reason = f"{prior}; {UNSTAMPED_HITS}".strip("; ") if prior else UNSTAMPED_HITS
    packet.status = "hold"
    stamp_cite_recheck_attempts(packet, attempts)
    return CiteRepairResult(ok=False, attempts=attempts, hold_reason=UNSTAMPED_HITS)


def run_cite_recheck_loop(
    packet: Packet,
    *,
    search_fn: SearchFn | None = None,
    bag: CiteBag | None = None,
) -> CiteRepairResult:
    """Scan missing URLs, print/when misses, and empty-cite sourced beats. Re-query up to 3. Attach or drop. HOLD on 4th."""
    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        n = stamp_cite_recheck_attempts(packet)
        return CiteRepairResult(ok=True, attempts=n)
    search_fn = search_fn or search
    attempts = stamp_cite_recheck_attempts(packet)
    attached_all: list[str] = []
    dropped_all: list[str] = []
    hit_urls: list[str] = []
    current_bag = _packet_bag(packet, bag)
    if _credit_hold(packet):
        stamp_cite_recheck_attempts(packet, attempts)
        return CiteRepairResult(
            ok=False,
            attempts=attempts,
            hold_reason=(packet.receipt.hold_reason if packet.receipt else None),
        )
    dropped_all.extend(drop_excerpt_slot_findings(packet))
    entered_empty = bool(empty_cite_beats(packet))
    entered_faithless = bool(faithless_cite_beats(packet))
    stamped = _stamp_pack_timeline(packet)
    attached_all.extend(stamped)
    attached_all.extend(_attach_timeline_beats(packet))
    dropped_all.extend(_repair_faithless_beats(packet))
    dropped_all.extend(drop_excerpt_slot_findings(packet))
    dropped_all.extend(drop_hollow_uncited_beats(packet))
    if (stamped or attached_all) and empty_cite_beats(packet):
        # Pack already yielded stamps. Leftover empty-cite is a drop, not a second Parallel.
        dropped_all.extend(drop_empty_cite_beats(packet))
    if entered_empty or entered_faithless or faithless_cite_beats(packet) or dropped_all:
        attempts = max(attempts, 1)
        stamp_cite_recheck_attempts(packet, attempts)
    hollow = _hollow_uncited_beats(packet)
    if hollow and not any(_attachable_claim(b) for b in empty_cite_beats(packet)):
        early_empty = _hold_empty_beats(packet, attempts)
        early_empty.attached_ids = attached_all
        early_empty.dropped_beat_ids = dropped_all
        return early_empty
    if packet.receipt is not None:
        from onecrew.timeline import clear_empty_mint_hold

        clear_empty_mint_hold(
            packet.receipt,
            notes="\n".join(
                p for p in ((packet.research_pack or ""), (packet.task_spine or "")) if p
            ),
        )
    early = _hold_if_hits_unstamped(packet, attempts)
    if early is not None:
        early.attached_ids = attached_all
        early.dropped_beat_ids = dropped_all
        return early
    while True:
        if current_bag and (current_bag.hit_urls or current_bag.excerpts):
            attached_all.extend(_attach_from_bag(packet, current_bag))
            attached_all.extend(_attach_timeline_beats(packet))
            attached_all.extend(_attach_empty_cite_beats(packet, current_bag))
        dropped_all.extend(drop_hollow_uncited_beats(packet))
        missing = unsupported_cite_findings(packet, current_bag)
        empty = empty_cite_beats(packet)
        faithless = faithless_cite_beats(packet)
        if faithless:
            dropped_all.extend(_repair_faithless_beats(packet))
            dropped_all.extend(drop_hollow_uncited_beats(packet))
            faithless = faithless_cite_beats(packet)
        missing_beats = bool(missing) and bool(unsupported_cite_beats(packet, current_bag))
        if not empty and not missing_beats:
            if faithless:
                result = _hold_cite_faithfulness(packet, attempts)
                result.attached_ids = attached_all
                result.dropped_beat_ids = dropped_all
                result.hit_urls = hit_urls
                return result
            gate = _board_gate_reason(packet)
            if gate:
                result = _hold_reason(packet, attempts, gate)
                result.attached_ids = attached_all
                result.dropped_beat_ids = dropped_all
                result.hit_urls = hit_urls
                return result
            stamp_cite_recheck_attempts(packet, attempts)
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
        stamp_cite_recheck_attempts(packet, attempts)
        fresh_bag, status = _recheck_parallel(
            missing, search_fn, [b for b in empty if _attachable_claim(b)]
        )
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
