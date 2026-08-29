from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

from onecrew import config
from onecrew.cut import frame_count, require_cut
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.models import Finding, Packet, Rails, ScriptBeat, ShotFrame

_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def write_shot_list(packet: Packet) -> list[ShotFrame]:
    """One shot per script beat. Descriptions come from that VO, not leftover stills."""
    if not packet.beats or not packet.script.strip():
        return []
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    shots: list[ShotFrame] = []
    for beat in packet.beats:
        rows = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        refs = [f.parallel_url for f in rows if f.parallel_url] or list(beat.finding_ids)
        shots.append(
            ShotFrame(
                id=f"shot-{beat.id}",
                shot=_shot_line(beat, rows),
                source_refs=refs,
                image_href="",
                imagen=False,
                beat_id=beat.id,
                duration_s=beat.duration_s,
                key_frame=True,
            )
        )
    return shots


def _shot_line(beat: ScriptBeat, rows: list[Finding]) -> str:
    claim = rows[0].claim if rows else beat.vo
    cites = " ".join(f"[{fid}]" for fid in beat.finding_ids)
    return (
        f"Single locked-off receipt card for {beat.id}: {claim} "
        f"On-screen {cites}. Duration {beat.duration_s}s. No collage."
    )


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


def apply_imagen(shots: list[ShotFrame], packet: Packet, *, rails: Rails) -> list[ShotFrame]:
    if not rails.imagen or not rails.vertex:
        for shot in shots:
            shot.image_href = ""
            shot.imagen = False
        return shots
    cap = frame_count(require_cut(packet.cut), packet.platform) if packet.cut else len(shots)
    spent = 0
    for shot in shots:
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
            continue
        shot.image_href = persist_generated_image(shot.id, result)
        shot.imagen = bool(shot.image_href)
        spent += 1
    return shots


def write_board(packet: Packet, rails: Rails) -> list[ShotFrame]:
    """Shot list from the timed VO, then Imagen onto those shots. Never leftover stills."""
    shots = write_shot_list(packet)
    if not shots:
        return []
    return apply_imagen(shots, packet, rails=rails)


def apply_seed_placeholders(shots: list[ShotFrame]) -> list[ShotFrame]:
    """Deterministic SVGs for first-open. imagen=false. Not the old tanker-lane set."""
    config.FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    for shot in shots:
        if not _SAFE_ID.match(shot.id):
            continue
        path = config.FRAMES_DIR / f"{shot.id}.svg"
        if not path.is_file():
            path.write_bytes(_placeholder_svg(shot.id, shot.shot))
        shot.image_href = f"/api/frames/{shot.id}"
        shot.imagen = False
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
