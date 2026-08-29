from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

from onecrew import config
from onecrew.cut import frame_count, require_cut
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.models import MISSING, Finding, Packet, Rails, ScriptBeat, ShotFrame
from onecrew.parallel_client import ParallelDownError, search
from onecrew.tell import invents_frame, tell_lane

FOOTAGE_OBJECTIVE = (
    "Find existing news-archive stills, official video, or a published frame "
    "that matches this shot. Return a media URL if one exists."
)

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def write_shot_list(packet: Packet) -> list[ShotFrame]:
    """One shot per cut in the scene. Not one shot per receipt row. Not leftover stills."""
    if not packet.beats or not packet.script.strip():
        return []
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    shots: list[ShotFrame] = []
    shot_no = 0
    last_scene = None
    short = packet.cut in {"tiktok-length", "shorts"}
    for beat in packet.beats:
        if beat.kind == "heading":
            last_scene = beat.scene
            continue
        rows = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        refs = [f.parallel_url for f in rows if f.parallel_url] or list(beat.finding_ids)
        shot_no += 1
        key = True if short else (beat.scene != last_scene or shot_no == 1)
        last_scene = beat.scene
        picture = _shot_line(beat, rows, packet)
        shots.append(
            ShotFrame(
                id=f"shot-{shot_no:03d}-{beat.id}",
                shot=picture,
                source_refs=refs,
                image_href="",
                imagen=False,
                beat_id=beat.id,
                duration_s=max(1, beat.duration_s),
                key_frame=key,
                shot_no=shot_no,
                camera=beat.camera or ("WIDE" if beat.kind == "action" else "MCU"),
                line=beat.vo.split("\n")[-1][:180],
                footage=MISSING,
                footage_url=None,
                footage_title=MISSING,
                kind=_shot_kind(picture),
            )
        )
    return shots


def _shot_line(beat: ScriptBeat, rows: list[Finding], packet: Packet) -> str:
    prefix = f"{beat.camera}, " if beat.camera else ""
    if beat.kind == "action" and beat.vo.strip():
        return f"{prefix}{beat.vo}".strip()
    if invents_frame(cut=packet.cut, tell=packet.tell or ""):
        lane = tell_lane(packet.tell)
        if lane == "family":
            return prefix + _family_shot(beat)
        if lane == "pilot":
            return prefix + _pilot_shot(beat)
        if lane == "ship":
            return prefix + _ship_shot(beat)
        return prefix + "Map-table room, radio on, a paper Gulf chart. No collage. Not a receipt card."
    blob = " ".join([beat.id, beat.vo] + [f.claim for f in rows]).lower()
    if (
        beat.id == "jcpoa-to-houthi"
        or "connection is not sourced" in blob
        or "will not tell you" in blob
        or "won't draw it" in blob
        or "don't hang a later" in blob
    ):
        return "Two dated cards on a table, 2018 and 2023-2024, with no arrow drawn between them."
    if "jcpoa" in blob or ("2018" in blob and "withdrew" in blob) or ("2018" in blob and "withdrawal" in blob):
        return "2018 announcement: a dated chyron on the JCPOA withdrawal, Gulf map on the wall behind the podium."
    if "mined" in blob or "navy treaty" in blob or "secret-closure" in blob:
        return "Night water in the Strait of Hormuz, empty lane, no mines on camera."
    if "seaborne" in blob or "transits" in blob or ("hormuz" in blob and "oil" in blob and "scare" not in blob and "panic" not in blob):
        return "Tanker in the Strait of Hormuz lane, land close on both sides, open water ahead."
    if "crash" in blob or "scare" in blob or "overnight" in blob or "oil-panic" in blob:
        return "Overnight newsroom, oil ticker running, Hormuz marked on a wall map. No crash proven on screen."
    if "producer" in blob or "oil-market" in blob or "oil-market given" in blob:
        return "Producer-state energy desk, Hormuz lane marked open on a shipping board."
    if "milk" in blob or "dairy" in blob or "auction" in blob:
        return "Spring auction floor and a milk tanker at the dock as the spot price ticks."
    if "jcpoa-to-houthi" in blob or ("connection" in blob and "not sourced" in blob) or "cannot tell you" in blob:
        return "Two dated cards on a table, 2018 and 2023-2024, with no arrow drawn between them."
    claim = rows[0].claim.rstrip(".") if rows else beat.vo.split("[")[0].strip().rstrip(".")
    return f"Photoreal frame of the action just spoken: {claim}."


def _family_shot(beat: ScriptBeat) -> str:
    blob = f"{beat.id} {beat.vo} {beat.frame}".lower()
    if beat.id == "jcpoa-2018" or ("2018" in blob and "jcpoa" in blob):
        return "Bandar Abbas kitchen, radio on, 2018 news on a small TV, dishes in the sink."
    if beat.id == "secret-closure" or "alley" in blob:
        return "Open kitchen door onto an alley in Bandar Abbas. No minefield on camera."
    if beat.id == "hormuz-share" or "harbor" in blob:
        return "Kitchen window over a harbor road, tankers only as distant lights."
    if beat.id == "oil-panic" or "neighbor" in blob:
        return "Neighbor in a Bandar Abbas kitchen doorway, overhead bulb, street quiet."
    if "jcpoa-to-houthi" in blob or "arrow" in blob:
        return "Kitchen table, two dates on scrap paper, no arrow drawn."
    return "Family kitchen in Bandar Abbas, radio on, evening light."


def _pilot_shot(beat: ScriptBeat) -> str:
    blob = f"{beat.id} {beat.vo} {beat.frame}".lower()
    if beat.id == "jcpoa-2018" or "2018" in blob:
        return "Night-watch chair, 2018 note under a lamp, glass on the lane."
    if "mine" in blob or "secret-closure" in blob:
        return "Retired pilot at the glass. Dark water. No mines visible."
    if "lane" in blob or "hormuz-share" in blob:
        return "Night watch glass, open Hormuz lane, hull unhit."
    if "crash" in blob or "oil-panic" in blob:
        return "Watch room radio on. No fire and no blast."
    if "explosion" in blob or "heading" in blob:
        return "Watch clipboard with two dates. No explosion on screen."
    return "Night watch. Retired pilot at the window. Threat only."


def _ship_shot(beat: ScriptBeat) -> str:
    blob = f"{beat.id} {beat.vo} {beat.frame}".lower()
    if beat.id == "jcpoa-2018":
        return "Bridge chart table, 2018 printout under a lamp, strait on the radar ring."
    if beat.id == "secret-closure":
        return "Lookout on the wing, dark Hormuz water, no mines visible."
    if beat.id == "hormuz-share":
        return "Bow of a ship in the Hormuz lane, land close on both sides, hull unhit."
    if beat.id == "oil-panic":
        return "Crew mess, radio on, coffee cups, no fire and no blast."
    if "jcpoa-to-houthi" in blob or "explosion" in blob or "heading" in blob:
        return "Bridge watch clock and a clipboard with two dates. No explosion on screen."
    return "Tanker bridge at night, watch officer at the window, threat only."


def persist_generated_image(frame_id: str, result: Any) -> str:
    """Map generate_frames output onto a shot. Empty return → no invented picture."""
    if not _SAFE_ID.match(frame_id):
        return ""
    images = getattr(result, "generated_images", None) or getattr(result, "images", None) or []
    if not images:
        return ""
    first = images[0]
    blob = (
        getattr(getattr(first, "image", None), "image_bytes", None)
        or getattr(first, "image_bytes", None)
        or getattr(first, "data", None)
    )
    if not blob:
        return ""
    if isinstance(blob, str):
        blob = blob.encode()
    folder = config.DATA_DIR / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    ext = ".svg" if blob.lstrip()[:5] in (b"<?xml", b"<svg ", b"<svg>") or blob.lstrip().startswith(b"<svg") else ".png"
    path = folder / f"{frame_id}{ext}"
    path.write_bytes(blob)
    return f"/api/frames/{frame_id}"


def _shot_kind(line: str) -> str:
    blob = (line or "").lower()
    if any(key in blob for key in ("troop-movement", "troop movement", "motion graphic", "animation")):
        return "motion_graphic"
    if any(key in blob for key in ("infographic", "chart", "gulf map", "wall map")):
        return "infographic"
    return "event"


def _allows_imagen(shot: ShotFrame, *, fiction: bool) -> bool:
    if shot.footage == "sourced":
        return False
    if fiction:
        return True
    return shot.kind in {"motion_graphic", "infographic"}


def _url_ok(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


def prefer_footage(shots: list[ShotFrame], rails: Rails) -> bool:
    """Search Parallel for existing pictures. Not a license. Not a collision/script check."""
    if not rails.parallel:
        for shot in shots:
            shot.footage = MISSING
            shot.footage_url = None
            shot.footage_title = MISSING
        return False
    searched = False
    try:
        for shot in shots:
            result = search(
                objective=FOOTAGE_OBJECTIVE,
                search_queries=[shot.shot, shot.line or shot.beat_id],
            )
            searched = True
            rows = list(getattr(result, "results", None) or [])
            url = None
            title = ""
            for row in rows:
                candidate = getattr(row, "url", None)
                if _url_ok(candidate):
                    url = candidate
                    title = (getattr(row, "title", None) or "").strip()
                    break
            if url:
                shot.footage = "sourced"
                shot.footage_url = url
                shot.footage_title = title or MISSING
                shot.imagen = False
                shot.image_href = ""
            else:
                shot.footage = MISSING
                shot.footage_url = None
                shot.footage_title = MISSING
    except ParallelDownError:
        for shot in shots:
            if shot.footage != "sourced":
                shot.footage = MISSING
                shot.footage_url = None
                shot.footage_title = MISSING
        return False
    return searched


def apply_imagen(shots: list[ShotFrame], packet: Packet, *, rails: Rails) -> list[ShotFrame]:
    fiction = invents_frame(cut=packet.cut, tell=packet.tell or "")
    if not rails.imagen or not rails.vertex:
        for shot in shots:
            if shot.footage != "sourced":
                shot.image_href = ""
                shot.imagen = False
                if not fiction and shot.kind == "event":
                    shot.footage = MISSING
        return shots
    if packet.cut in {"tiktok-length", "shorts"}:
        cap = len(shots)
    else:
        cap = frame_count(require_cut(packet.cut), packet.platform) if packet.cut else len(shots)
    spent = 0
    for shot in shots:
        if shot.footage == "sourced":
            continue
        if not _allows_imagen(shot, fiction=fiction):
            shot.image_href = ""
            shot.imagen = False
            if shot.footage != "sourced":
                shot.footage = MISSING
            continue
        if not shot.key_frame or spent >= cap:
            continue
        prompt = (
            f"One photoreal storyboard frame, not a collage. Cut={packet.cut}. "
            f"Shot: {shot.shot}. VO beat {shot.beat_id}."
        )
        try:
            result = generate_frames(prompt=prompt, number_of_images=1)
        except ImagenDownError:
            shot.image_href = ""
            shot.imagen = False
            if shot.footage != "sourced":
                shot.footage = MISSING
            continue
        shot.image_href = persist_generated_image(shot.id, result)
        shot.imagen = bool(shot.image_href)
        if shot.imagen:
            shot.footage = "imagen"
        spent += 1
    return shots


def write_board(packet: Packet, rails: Rails) -> list[ShotFrame]:
    """Shot list, then prefer sourced footage, then Imagen only on misses."""
    shots = write_shot_list(packet)
    if not shots:
        return []
    searched = prefer_footage(shots, rails)
    if not searched:
        return shots
    return apply_imagen(shots, packet, rails=rails)


def apply_seed_placeholders(shots: list[ShotFrame]) -> list[ShotFrame]:
    """Deterministic SVGs for first-open. imagen=false. Not the old tanker-lane set."""
    config.FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    for shot in shots:
        if not _SAFE_ID.match(shot.id):
            continue
        path = config.FRAMES_DIR / f"{shot.id}.svg"
        path.write_bytes(_placeholder_svg(shot.id, shot.shot))
        shot.image_href = f"/api/frames/{shot.id}"
        shot.imagen = False
        shot.footage = MISSING
        shot.footage_url = None
        shot.footage_title = MISSING
    return shots


def _placeholder_svg(shot_id: str, label: str) -> bytes:
    title = escape(shot_id)
    body = escape(label[:120])
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 360" '
        f'width="640" height="360" role="img" aria-label="{title}">'
        '<rect width="640" height="360" fill="#1a1410"/>'
        f'<text x="40" y="80" fill="#f0c27a" font-family="ui-monospace, monospace" '
        f'font-size="16">{title}</text>'
        f'<text x="40" y="160" fill="#f3e6d4" font-family="ui-sans-serif, system-ui, sans-serif" '
        f'font-size="16">{body}</text>'
        "</svg>\n"
    ).encode()


def resolve_frame_file(frame_id: str):
    if not _SAFE_ID.match(frame_id):
        return None
    folders = (config.FRAMES_DIR, config.DATA_DIR / "frames")
    for folder in folders:
        for ext in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
            path = folder / f"{frame_id}{ext}"
            if path.is_file():
                return path
    return None
