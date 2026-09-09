"""Devpost-review / Vertex discussant room. Ship or recut. One extra Parallel loop max."""

from __future__ import annotations

import re
from typing import Any, Callable, Literal

from pydantic import BaseModel

from onecrew.models import MISSING, GradeArtifact, Packet, RoomGrade, StampedFinding
from onecrew.verify import (
    Claim,
    CiteBag,
    _bag_text,
    _bar_in,
    _bars,
    _url_in,
    _when_in_text,
    verify_print_in_cite,
)

MAX_PARALLEL_RESEARCH = 2
# ponytail: long excerpt so geopolitics-first packs still carry series prints. Upgrade: structured pack pages.
_PACK_EXCERPT = 24_000
ResearchFn = Callable[[str | None], Any]
RewriteFn = Callable[[], None]
GraderFn = Callable[[GradeArtifact], RoomGrade]
_BEAT1_TRIGGER_NIT = re.compile(
    r"(cold[- ]open|beat\s*1|first\s*~?\s*20).{0,80}(first[- ]trigger|transmission)"
    r"|(first[- ]trigger|transmission).{0,80}(cold[- ]open|beat\s*1|first\s*~?\s*20)",
    re.I,
)
_INVENT_FROM_SUMMARY = re.compile(
    r"(invent|absent|missing|not (?:in|found)).{0,160}(summary|research_pack_summary)"
    r"|(summary|research_pack_summary).{0,160}(invent|absent|missing|not (?:in|found))",
    re.I,
)
_INVENT_LANG = re.compile(
    r"\binvent(?:s|ed|ing)?\b|absent from|missing from|not in the (?:pack|summary|cites?)",
    re.I,
)
_TARIFF_TOPIC = re.compile(r"\btariff", re.I)
_TIMECODE_LINE = re.compile(r"^\d{1,2}:\d{2}")
_YEAR_TOK = re.compile(r"^20\d{2}$")


class RoomLoopResult(BaseModel):
    grade: RoomGrade
    parallel_research_calls: int
    disposition: Literal["READY", "HOLD"]
    hold_reason: str | None = None


def _blank_stamp(value: str | None) -> str:
    if value in {MISSING, None}:
        return ""
    return str(value)


def _stamped_findings(packet: Packet) -> list[StampedFinding]:
    from onecrew.foundry import leftover_slot_ids

    leftover = leftover_slot_ids()
    rows: list[StampedFinding] = []
    for finding in (packet.receipt.findings if packet.receipt else []):
        if finding.id in leftover:
            continue
        if finding.parallel_status != "hit" or not (finding.parallel_url or "").strip():
            continue
        rows.append(
            StampedFinding(
                id=finding.id,
                series=_blank_stamp(finding.series),
                print=_blank_stamp(finding.print),
                when=(finding.when or "").strip(),
                claim=(finding.claim or "").strip(),
                title=_blank_stamp(finding.title),
                url=(finding.parallel_url or "").strip(),
                note=(finding.note or "").strip(),
            )
        )
    return rows


def make_grade_artifact(packet: Packet) -> GradeArtifact:
    pack = (packet.research_pack or "").strip()
    excerpt = pack if len(pack) <= _PACK_EXCERPT else pack[:_PACK_EXCERPT].rstrip() + "…"
    stamps = _stamped_findings(packet)
    stamp_block = "\n".join(row.line() for row in stamps)
    cite_block = "\n".join(
        f"{row.url} {row.claim}".strip() for row in stamps if row.url or row.claim
    )
    parts: list[str] = []
    if excerpt:
        parts.append(excerpt)
    if cite_block:
        parts.append("Parallel cites (hit URL + excerpt/summary):\n" + cite_block)
    if stamp_block:
        parts.append("Stamped findings (series/print/when/id):\n" + stamp_block)
    return GradeArtifact(
        packet_id=packet.id,
        research_pack_summary="\n\n".join(parts),
        script=packet.script or "",
        research_pack=excerpt,
        stamped_findings=stamps,
        parallel_cites=cite_block,
        timeline_map=list((packet.receipt.timeline_map if packet.receipt else None) or []),
        tell=packet.tell or "",
    )


def run_adk_room(artifact: GradeArtifact) -> RoomGrade:
    """ADK room reviewer. Tests stub this. No ADC → ship (cannot invent a recut)."""
    from onecrew import config

    if not config.has_vertex() or not config.has_adc():
        return RoomGrade(vote="ship")
    from onecrew.agent.adk_run import live_adk_room
    from onecrew.vertex_client import VertexDownError

    try:
        return live_adk_room(artifact)
    except (VertexDownError, ValueError) as exc:
        return RoomGrade(vote="recut", recut_reason="other", recut_detail=f"ADK room down: {exc}")


def _beat1_trigger_nit(grade: RoomGrade, artifact: GradeArtifact) -> bool:
    """Placement-only nit. Outcome-first weave allows first-trigger after beat 1."""
    if grade.vote != "recut":
        return False
    if not (artifact.script or "").strip():
        return False
    return bool(_BEAT1_TRIGGER_NIT.search(grade.recut_detail or ""))


def _vo_body(script: str) -> str:
    """Drop timecode / shot-list chrome so duration digits are not spoken prints."""
    keep: list[str] = []
    for line in (script or "").splitlines():
        stripped = line.strip()
        if _TIMECODE_LINE.match(stripped):
            continue
        if stripped.startswith(("ACTION:", "Timed VO", "BEAT ", "ACT ")):
            continue
        if stripped in {"WIDE", "MCU", "NARRATOR"}:
            continue
        keep.append(line)
    return "\n".join(keep)


def _tok_on_evidence(tok: str, prints: list[str], pack: str) -> bool:
    for printed in prints:
        for bar in _bars(printed):
            if _bar_in(tok, bar) or _bar_in(bar, tok):
                return True
    return bool(pack) and _bar_in(tok, pack)


def _trigger_chrome(tok: str, vo: str) -> bool:
    """Rule threshold next to 'trigger' is definition chrome, not a minted series print."""
    if not tok or not vo:
        return False
    return bool(re.search(rf"{re.escape(tok)}\s+trigger\b", vo, re.I))


def _spoken_prints_map_to_findings(artifact: GradeArtifact) -> bool:
    """Every spoken print is on a stamped finding or in the pack. Years/timecodes are not prints."""
    from onecrew.script import pack_numbers

    prints = [row.print for row in artifact.stamped_findings if row.print]
    pack = "\n".join(
        part
        for part in (
            artifact.research_pack or "",
            artifact.parallel_cites or "",
            artifact.findings_block(),
        )
        if part
    )
    vo = _vo_body(artifact.script)
    for tok in pack_numbers(vo):
        cleaned = tok.replace("−", "-").strip()
        if _YEAR_TOK.fullmatch(cleaned):
            continue
        if _trigger_chrome(tok, vo):
            continue
        if _tok_on_evidence(tok, prints, pack):
            continue
        return False
    return True


def _prints_pack_faithful(artifact: GradeArtifact) -> bool:
    script = (artifact.script or "").strip()
    if not script:
        return False
    if not _leftover_free(script):
        return False
    return _spoken_prints_map_to_findings(artifact)


def _leftover_free(script: str) -> bool:
    from onecrew.script import _leftover_vo

    return not _leftover_vo(script)


def _unsupported_topic_recut(grade: RoomGrade, artifact: GradeArtifact) -> bool:
    if not _TARIFF_TOPIC.search(grade.recut_detail or ""):
        return False
    evidence = (
        f"{artifact.research_pack or ''} {artifact.parallel_cites or ''} "
        f"{artifact.findings_block()}"
    )
    return "tariff" not in evidence.lower()


def _false_invent_recut(grade: RoomGrade, artifact: GradeArtifact) -> bool:
    """Invent = not in Parallel cites. Coerce recut→ship when every spoken print maps."""
    if grade.vote != "recut":
        return False
    if _cite_host_mismatch(artifact):
        return False
    if not _prints_pack_faithful(artifact):
        return False
    if _unsupported_topic_recut(grade, artifact):
        return False
    detail = grade.recut_detail or ""
    if _INVENT_FROM_SUMMARY.search(detail):
        return True
    if _INVENT_LANG.search(detail):
        return True
    return False


def _cite_windows(script: str) -> list[str]:
    parts = re.split(r"(?=^BEAT\s+\d+)", script or "", flags=re.M)
    return [p for p in parts if p.strip()] or [script or ""]


def _cited_ids(text: str) -> list[str]:
    return re.findall(r"\[([^\[\]]+)\]", text or "")


def _spoken_window(window: str) -> str:
    """Narrator + ACTION. Drop beat/timecode chrome so those tokens are not names."""
    keep: list[str] = []
    for line in (window or "").splitlines():
        stripped = line.strip()
        if _TIMECODE_LINE.match(stripped):
            continue
        if stripped.startswith(("Timed VO", "BEAT ", "ACT ")):
            continue
        if stripped in {"WIDE", "MCU", "NARRATOR"}:
            continue
        if stripped.startswith("ACTION:"):
            keep.append(stripped.split(":", 1)[1].strip())
            continue
        keep.append(line)
    return "\n".join(keep)


def _row_covers_names(vo: str, rows: list) -> bool:
    from onecrew.timeline import pair_covers_vo, stamp_text, vo_proper_names

    names = vo_proper_names(vo)
    if not names or not rows:
        return not names
    for row in rows:
        url = getattr(row, "url", None) or getattr(row, "parallel_url", None) or ""
        if not pair_covers_vo(vo, stamp_text(row), url):
            return False
    return True


def _row_supports_prints(vo: str, rows: list) -> bool:
    from onecrew.timeline import _MONTH_YEAR, _event_nums, stamp_text

    nums = _event_nums(vo)
    blob = " ".join(stamp_text(row) for row in rows)
    if nums and not nums <= _event_nums(blob):
        return False
    vo_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(vo or "")}
    ev_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob or "")}
    if vo_months and not (vo_months & ev_months):
        return False
    return True


def _chrome_cited(artifact: GradeArtifact) -> bool:
    from onecrew.script import is_pack_chrome_vo

    by_id = {row.id: row for row in artifact.stamped_findings}
    map_ids = {row.finding_id for row in artifact.timeline_map}
    for window in _cite_windows(artifact.script):
        vo = _spoken_window(window)
        cited = [
            fid
            for fid in _cited_ids(window)
            if fid in by_id
            and (
                fid.startswith("te-")
                or by_id[fid].series == "timeline_event"
                or fid in map_ids
            )
        ]
        if cited and is_pack_chrome_vo(vo):
            return True
    return False


def _attached_print_or_name_hole(artifact: GradeArtifact) -> bool:
    by_id = {row.id: row for row in artifact.stamped_findings}
    map_ids = {row.finding_id for row in artifact.timeline_map}
    for window in _cite_windows(artifact.script):
        vo = _spoken_window(window)
        rows = []
        for fid in _cited_ids(window):
            row = by_id.get(fid)
            if row is None or not (row.url or "").strip():
                continue
            if not (fid.startswith("te-") or row.series == "timeline_event" or fid in map_ids):
                continue
            rows.append(row)
        if not rows:
            continue
        if not _row_covers_names(vo, rows):
            return True
        if not _row_supports_prints(vo, rows):
            return True
    return False


def _empty_titled_uncited(artifact: GradeArtifact) -> bool:
    """Titled spine beat with no pack cite."""
    by_id = {row.id: row for row in artifact.stamped_findings}
    map_ids = {row.finding_id for row in artifact.timeline_map}
    for window in _cite_windows(artifact.script):
        if not re.search(r"^BEAT\s+\d+", window, re.I | re.M):
            continue
        cited = [fid for fid in _cited_ids(window) if fid in by_id or fid in map_ids]
        if cited:
            continue
        return True
    return False


def _action_line(window: str) -> str:
    for line in (window or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("ACTION:"):
            return stripped.split(":", 1)[1].strip()
    return ""


def _tone_title_meta_hole(artifact: GradeArtifact) -> bool:
    """Tone chrome, title-read VO, or mute-test meta frames are not cite-faithful speech."""
    from onecrew.script import (
        has_tone_chrome,
        is_action_chrome_vo,
        is_broad_scope_vo,
        is_hanging_clause_vo,
        is_print_hole,
        is_thin_frame,
        is_thin_title_read_vo,
        is_title_read_vo,
        is_unverified_meta_vo,
        stamp_scope,
    )

    by_id = {row.id: row for row in artifact.stamped_findings}
    prior: list[str] = []
    covering = [row for row in artifact.stamped_findings if stamp_scope(row) == "broad"]
    for window in _cite_windows(artifact.script):
        vo = _vo_body(window)
        cited = [by_id[fid] for fid in _cited_ids(window) if fid in by_id]
        fids = [row.id for row in cited]
        if has_tone_chrome(vo) or is_unverified_meta_vo(vo) or is_hanging_clause_vo(vo) or is_print_hole(vo):
            return True
        if is_action_chrome_vo(vo, _action_line(window)):
            return True
        if cited and is_title_read_vo(vo, cited):
            return True
        if cited and is_thin_title_read_vo(vo, cited, prior_prints=prior):
            return True
        if is_broad_scope_vo(vo) and cited and all(stamp_scope(row) == "narrow" for row in cited) and covering:
            return True
        if is_thin_frame(_action_line(window), fids, cited):
            return True
        prior.append(vo)
    return False


def _forecast_theater_hole(artifact: GradeArtifact) -> bool:
    from onecrew.script import is_forecast_theater_vo
    from onecrew.tell import wants_no_forecast_theater

    if not wants_no_forecast_theater(artifact.tell or ""):
        return False
    return any(is_forecast_theater_vo(_spoken_window(window)) for window in _cite_windows(artifact.script))


def _over_cite_hole(artifact: GradeArtifact) -> bool:
    from onecrew.timeline import MAX_CITES_PER_BEAT
    from onecrew.verify import CLOSED_SERIES

    by_id = {row.id: row for row in artifact.stamped_findings}
    for window in _cite_windows(artifact.script):
        other = [
            fid
            for fid in _cited_ids(window)
            if fid in by_id and (by_id[fid].series or "").strip() not in CLOSED_SERIES
        ]
        if len(other) > MAX_CITES_PER_BEAT:
            return True
    return False


def _host_reuse_hole(artifact: GradeArtifact) -> bool:
    from collections import Counter

    from onecrew.timeline import URL_REUSE_CAP, url_host
    from onecrew.verify import CLOSED_SERIES

    by_id = {row.id: row for row in artifact.stamped_findings}
    seen: set[str] = set()
    used: Counter[str] = Counter()
    for window in _cite_windows(artifact.script):
        for fid in _cited_ids(window):
            row = by_id.get(fid)
            if row is None or fid in seen or (row.series or "").strip() in CLOSED_SERIES:
                continue
            seen.add(fid)
            host = url_host(row.url or "")
            if host:
                used[host] += 1
    return any(n > URL_REUSE_CAP for n in used.values())


def _cite_host_mismatch(artifact: GradeArtifact) -> bool:
    """Fail-closed: named-host / entity / print must sit on the attached stamp."""
    from onecrew.timeline import chain_pairs, cite_host_ok, pair_covers_vo, stamp_text

    if (
        _chrome_cited(artifact)
        or _attached_print_or_name_hole(artifact)
        or _empty_titled_uncited(artifact)
        or _tone_title_meta_hole(artifact)
    ):
        return True
    pairs = chain_pairs(artifact.research_pack or "", artifact.timeline_map)
    by_id = {row.id: row for row in artifact.stamped_findings}
    map_ids = {row.finding_id for row in artifact.timeline_map}
    for window in _cite_windows(artifact.script):
        vo = _spoken_window(window)
        for fid in _cited_ids(window):
            row = by_id.get(fid)
            if row is None or not (row.url or "").strip():
                continue
            if not (fid.startswith("te-") or row.series == "timeline_event" or fid in map_ids):
                continue
            url = row.url
            blob = stamp_text(row)
            if pairs and not cite_host_ok(vo, url, pairs):
                if not pair_covers_vo(vo, blob, url):
                    return True
            if not pair_covers_vo(vo, blob, url):
                return True
    return False


def grade_room(artifact: GradeArtifact, *, grader: GraderFn | None = None) -> RoomGrade:
    """ADK room when Vertex is up. grader= is the test stub hook."""
    if grader is not None:
        grade = grader(artifact)
    else:
        grade = run_adk_room(artifact)
    if grade.vote == "recut" and grade.recut_reason not in {"not_enough_information", "other"}:
        raise ValueError("recut requires why: not_enough_information | other")
    if grade.vote == "recut" and grade.recut_reason == "other" and not (grade.recut_detail or "").strip():
        raise ValueError("recut other requires a short reason")
    if _forecast_theater_hole(artifact):
        return RoomGrade(vote="recut", recut_reason="other", recut_detail="forecast theater")
    if _over_cite_hole(artifact):
        return RoomGrade(vote="recut", recut_reason="other", recut_detail="over-cite")
    if _host_reuse_hole(artifact):
        return RoomGrade(vote="recut", recut_reason="other", recut_detail="host reuse")
    if _cite_host_mismatch(artifact):
        return RoomGrade(vote="recut", recut_reason="other", recut_detail="cite-faithfulness")
    if (
        grade.vote == "recut"
        and "cite-faithfulness" in (grade.recut_detail or "").lower()
    ):
        return RoomGrade(vote="ship")
    if _beat1_trigger_nit(grade, artifact):
        return RoomGrade(vote="ship")
    if _false_invent_recut(grade, artifact):
        return RoomGrade(vote="ship")
    return grade


def _print_and_when_in_bag(claim: Claim, bag: CiteBag) -> bool:
    blob = _bag_text(bag)
    bars = _bars(claim.print)
    if bars and not all(_bar_in(bar, blob) for bar in bars):
        return False
    if (claim.when or "").strip() and not _when_in_text(claim.when, blob):
        return False
    return True


def claim_supported_after_churn(claim: Claim, bag: CiteBag) -> bool:
    """Claim still stands if print/when live in the new bag. URL may change."""
    if _print_and_when_in_bag(claim, bag):
        return True
    relinked = relink_cite_if_supported(claim, bag)
    return verify_print_in_cite(relinked, bag).ok


def relink_cite_if_supported(claim: Claim, bag: CiteBag) -> Claim:
    """If print+when still in the bag, accept a new hit URL. Do not fail on URL churn."""
    if _url_in(claim.cite_url, bag.hit_urls) and verify_print_in_cite(claim, bag).ok:
        return claim
    if not _print_and_when_in_bag(claim, bag):
        return claim
    for excerpt in bag.excerpts:
        url = (excerpt.url or "").strip()
        if not url or not _url_in(url, bag.hit_urls):
            continue
        trial = claim.model_copy(update={"cite_url": url})
        if verify_print_in_cite(trial, bag).ok:
            return trial
    return claim


def run_room_loop(
    packet: Packet,
    *,
    research: ResearchFn,
    rewrite: RewriteFn,
    grader: GraderFn | None = None,
    parallel_already: int = 1,
) -> RoomLoopResult:
    """Grade after script. Recut not_enough_information → at most one more Parallel + rewrite."""
    artifact = make_grade_artifact(packet)
    packet.grade_artifact = artifact
    grade = grade_room(artifact, grader=grader)
    packet.room_grade = grade
    calls = max(0, int(parallel_already))
    if grade.vote == "ship":
        from onecrew.script import sanitize_for_ship

        sanitize_for_ship(packet)
        return RoomLoopResult(grade=grade, parallel_research_calls=calls, disposition="READY")
    if grade.vote == "recut" and grade.recut_reason == "not_enough_information":
        if calls >= MAX_PARALLEL_RESEARCH:
            from onecrew.script import sanitize_for_ship

            sanitize_for_ship(packet)
            held = RoomLoopResult(
                grade=grade,
                parallel_research_calls=calls,
                disposition="HOLD",
                hold_reason="room recut not_enough_information; Parallel already used its extra loop",
            )
            return held
        research(grade.recut_detail or None)
        calls += 1
        rewrite()
        artifact = make_grade_artifact(packet)
        packet.grade_artifact = artifact
        grade = grade_room(artifact, grader=grader)
        packet.room_grade = grade
        if grade.vote == "ship":
            from onecrew.script import sanitize_for_ship

            sanitize_for_ship(packet)
            return RoomLoopResult(grade=grade, parallel_research_calls=calls, disposition="READY")
        from onecrew.script import sanitize_for_ship

        sanitize_for_ship(packet)
        return RoomLoopResult(
            grade=grade,
            parallel_research_calls=calls,
            disposition="HOLD",
            hold_reason=(
                "room recut not_enough_information after one extra Parallel loop; "
                "no third research call"
            ),
        )
    # recut other: Vertex rewrite only, no Parallel
    rewrite()
    artifact = make_grade_artifact(packet)
    packet.grade_artifact = artifact
    grade = grade_room(artifact, grader=grader)
    packet.room_grade = grade
    if grade.vote == "ship":
        from onecrew.script import sanitize_for_ship

        sanitize_for_ship(packet)
        return RoomLoopResult(grade=grade, parallel_research_calls=calls, disposition="READY")
    from onecrew.script import sanitize_for_ship

    sanitize_for_ship(packet)
    return RoomLoopResult(
        grade=grade,
        parallel_research_calls=calls,
        disposition="HOLD",
        hold_reason=f"room recut other: {(grade.recut_detail or '').strip() or 'short reason required'}",
    )
