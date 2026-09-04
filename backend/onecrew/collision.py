from __future__ import annotations

import re

from onecrew.models import MISSING, CollisionRow, Packet, Rails, ScriptBeat
from onecrew.parallel_client import ParallelDownError, search

_CITE = re.compile(r"\[[a-z0-9-]+\]")
_FRAME_NAME = re.compile(r"\b(Leila|Reza)\b", re.I)
_SPACE = re.compile(r"\s+")
_SERIES_HOSTS = (
    "fred.stlouisfed.org",
    "stlouisfed.org",
    "bls.gov",
    "bea.gov",
    "cbo.gov",
    "conference-board.org",
    "ismworld.org",
    "nber.org",
    "congress.gov",
    "wikipedia.org",
)
_MEDIA_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")
_WARN_REASON = (
    "warning, not a clearance. Citation pages and news hits are not colliding narration. "
    "The floor does not post."
)

COLLISION_OBJECTIVE = (
    "Find existing YouTube videos, documentaries, news packages, or films "
    "whose narration, voiceover, script, or transcript is the same or "
    "substantially the same as this spoken line."
)

_HOLD_REASON = (
    "Collision rail HOLD: Parallel missing — no search, no invented title, "
    "never collision=no without a search."
)


def _url_ok(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


def _is_series_citation(url: str | None) -> bool:
    """Official series / encyclopedia / CRS pages are citations, not colliding media."""
    low = (url or "").lower()
    if any(host in low for host in _SERIES_HOSTS):
        return True
    if "translate.goog" in low and any(
        token in low for token in ("fred", "stlouisfed", "bls", "bea", "nber", "cbo")
    ):
        return True
    return False


def _is_media(url: str | None, title: str = "") -> bool:
    blob = f"{url or ''} {title or ''}".lower()
    return any(host in blob for host in _MEDIA_HOSTS) or "documentary" in blob


def _clear_beat(beat: ScriptBeat) -> None:
    beat.collision = MISSING
    beat.collision_url = None
    beat.collision_title = MISSING
    beat.collision_kind = MISSING


def hold_collisions(packet: Packet) -> Packet:
    """Fail-closed. No search, no invented title, never collision=no."""
    for beat in packet.beats:
        _clear_beat(beat)
    packet.collisions = []
    packet.collision_disposition = "HOLD"
    packet.collision_hold_reason = _HOLD_REASON
    return packet


def _strip_frame(vo: str) -> str:
    kept: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", vo):
        if "(frame)" in part.lower():
            continue
        kept.append(part)
    text = _CITE.sub("", " ".join(kept))
    text = _FRAME_NAME.sub("", text)
    return _SPACE.sub(" ", text).strip(" .")


def search_text(beat: ScriptBeat, packet: Packet) -> str:
    """Factual claim / distinctive narration. Not invented names."""
    receipt = packet.receipt
    if receipt:
        for link in receipt.causal_links:
            if link.id == beat.id:
                return (link.claim or "").strip()
        by_id = {f.id: f for f in receipt.findings}
        for fid in beat.finding_ids:
            finding = by_id.get(fid)
            if finding and finding.claim.strip():
                return finding.claim.strip()
    return _strip_frame(beat.vo)


def _same_script(line: str, excerpts: list[str]) -> bool:
    words = _SPACE.sub(" ", line.lower()).split()
    blob = _SPACE.sub(" ", " ".join(excerpts).lower())
    if not words or not blob:
        return False
    for n in range(min(8, len(words)), 5, -1):
        for i in range(0, len(words) - n + 1):
            if " ".join(words[i : i + n]) in blob:
                return True
    return False


def _apply_hit(beat: ScriptBeat, url: str, title: str, excerpts: list[str], query: str) -> CollisionRow:
    sourced_title = title.strip() if title and title.strip() and title.strip() != MISSING else MISSING
    kind = "same_script" if _same_script(query, excerpts) else "near_script"
    beat.collision = "yes"
    beat.collision_url = url
    beat.collision_title = sourced_title
    beat.collision_kind = kind
    return CollisionRow(
        beat_id=beat.id,
        collision="yes",
        url=url,
        title=sourced_title,
        kind=kind,
    )


def stamp_collisions(packet: Packet, rails: Rails) -> Packet:
    """Search existing media after VO exists. Do not rewrite the VO. Do not drop beats."""
    if not packet.script.strip() or not packet.beats:
        if rails.parallel:
            for beat in packet.beats:
                _clear_beat(beat)
            packet.collisions = []
            packet.collision_disposition = "HOLD"
            packet.collision_hold_reason = _WARN_REASON
            return packet
        return hold_collisions(packet)
    if not rails.parallel:
        return hold_collisions(packet)
    hits: list[CollisionRow] = []
    try:
        cached: dict[str, tuple[str | None, str, list[str]]] = {}
        for beat in packet.beats:
            if (beat.kind or "vo") != "vo":
                continue
            query = search_text(beat, packet)
            if not query:
                _clear_beat(beat)
                continue
            if query in cached:
                url, title, excerpts = cached[query]
                if url:
                    hits.append(_apply_hit(beat, url, title, excerpts, query))
                else:
                    beat.collision = "no"
                    beat.collision_url = None
                    beat.collision_title = MISSING
                    beat.collision_kind = MISSING
                continue
            result = search(objective=COLLISION_OBJECTIVE, search_queries=[query])
            rows = list(getattr(result, "results", None) or [])
            url = None
            title = ""
            excerpts: list[str] = []
            for row in rows:
                candidate = getattr(row, "url", None)
                row_title = getattr(row, "title", None) or ""
                if not _url_ok(candidate) or _is_series_citation(candidate):
                    continue
                if not _is_media(candidate, row_title):
                    continue
                excerpts = [str(x) for x in (getattr(row, "excerpts", None) or [])]
                if not _same_script(query, excerpts):
                    continue
                url = candidate
                title = row_title
                break
            cached[query] = (url, title, excerpts)
            if url:
                hits.append(_apply_hit(beat, url, title, excerpts, query))
                continue
            beat.collision = "no"
            beat.collision_url = None
            beat.collision_title = MISSING
            beat.collision_kind = MISSING
    except ParallelDownError:
        return hold_collisions(packet)
    media_same = any(
        beat.collision == "yes" and beat.collision_kind == "same_script"
        for beat in packet.beats
        if (beat.kind or "vo") == "vo"
    )
    if media_same:
        packet.collisions = hits
        packet.collision_disposition = "READY"
        packet.collision_hold_reason = _WARN_REASON
        return packet
    packet.collisions = []
    packet.collision_disposition = "HOLD"
    packet.collision_hold_reason = _WARN_REASON
    return packet
