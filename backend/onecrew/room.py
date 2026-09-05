"""Devpost-review / Vertex discussant room. Ship or recut. One extra Parallel loop max."""

from __future__ import annotations

from typing import Any, Callable, Literal

from pydantic import BaseModel

from onecrew.models import GradeArtifact, Packet, RoomGrade
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
ResearchFn = Callable[[str | None], Any]
RewriteFn = Callable[[], None]
GraderFn = Callable[[GradeArtifact], RoomGrade]


class RoomLoopResult(BaseModel):
    grade: RoomGrade
    parallel_research_calls: int
    disposition: Literal["READY", "HOLD"]
    hold_reason: str | None = None


def make_grade_artifact(packet: Packet) -> GradeArtifact:
    pack = (packet.research_pack or "").strip()
    # ponytail: first ~400 chars of the pack. Upgrade: structured abstract field.
    summary = pack[:400].rstrip()
    if len(pack) > 400:
        summary += "…"
    return GradeArtifact(
        packet_id=packet.id,
        research_pack_summary=summary,
        script=packet.script or "",
    )


def grade_room(artifact: GradeArtifact, *, grader: GraderFn | None = None) -> RoomGrade:
    """Default ships so existing live tests stay on the first Parallel pass."""
    if grader is not None:
        grade = grader(artifact)
    else:
        grade = RoomGrade(vote="ship")
    if grade.vote == "recut" and grade.recut_reason not in {"not_enough_information", "other"}:
        raise ValueError("recut requires why: not_enough_information | other")
    if grade.vote == "recut" and grade.recut_reason == "other" and not (grade.recut_detail or "").strip():
        raise ValueError("recut other requires a short reason")
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
        return RoomLoopResult(grade=grade, parallel_research_calls=calls, disposition="READY")
    if grade.vote == "recut" and grade.recut_reason == "not_enough_information":
        if calls >= MAX_PARALLEL_RESEARCH:
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
            return RoomLoopResult(grade=grade, parallel_research_calls=calls, disposition="READY")
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
        return RoomLoopResult(grade=grade, parallel_research_calls=calls, disposition="READY")
    return RoomLoopResult(
        grade=grade,
        parallel_research_calls=calls,
        disposition="HOLD",
        hold_reason=f"room recut other: {(grade.recut_detail or '').strip() or 'short reason required'}",
    )
