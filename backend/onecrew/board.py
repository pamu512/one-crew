from __future__ import annotations

import re
from typing import Any
from xml.sax.saxutils import escape

from onecrew import config
from onecrew.cut import frame_count, require_cut
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.models import MISSING, Finding, Packet, Rails, ScriptBeat, ShotFrame
from onecrew.parallel_client import search
from onecrew.tell import invents_frame

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
            last_scene = None
            continue
        rows = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        hole = "sahm hole" in f"{beat.vo} {beat.frame or ''}".lower() or "no matching url" in f"{beat.vo} {beat.frame or ''}".lower()
        refs = [] if hole else ([f.parallel_url for f in rows if f.parallel_url] or list(beat.finding_ids))
        shot_no += 1
        key = True if short else (last_scene is None or beat.scene != last_scene or shot_no == 1)
        last_scene = beat.scene
        on_screen = _mute_on_screen(beat, rows, packet)
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
                on_screen=on_screen,
            )
        )
    return shots


def _pack_blob(packet: Packet) -> str:
    parts = [packet.research_pack or "", packet.topic or ""]
    if packet.receipt:
        parts.extend(f.claim for f in packet.receipt.findings)
    return " ".join(parts).lower()


def _mute_on_screen(beat: ScriptBeat, rows: list[Finding], packet: Packet | None = None) -> str:
    """Stamp print on the frame/on_screen. Shot ACTION chrome is not the mute-test."""
    from onecrew.script import (
        _looks_like_headline,
        is_numeric_print,
        is_thin_frame,
        is_title_chrome_frame,
        is_topic_prompt_frame,
        speak_stamp_fact,
        speak_stamp_print,
        speak_stamps,
    )

    screen = speak_stamp_print(list(beat.finding_ids), rows)
    shown = (beat.frame or "").strip()
    topic_frame = bool(packet is not None and is_topic_prompt_frame(shown, packet))
    title_chrome = is_title_chrome_frame(shown, list(beat.finding_ids), rows)
    headline = bool(shown and not is_numeric_print(shown) and _looks_like_headline(shown))
    if topic_frame or title_chrome or headline or (screen and shown and not is_numeric_print(shown)):
        shown = ""
    if screen:
        beat.frame = screen
        return screen
    printed = speak_stamp_fact(list(beat.finding_ids), rows) or speak_stamps(
        list(beat.finding_ids), rows
    )
    if printed and (not shown or is_thin_frame(shown, list(beat.finding_ids), rows) or not is_numeric_print(shown)):
        beat.frame = printed
        return printed
    if shown and not is_numeric_print(shown):
        beat.frame = ""
        return ""
    return shown


def mute_test_shows_stamp(shot: ShotFrame, findings: list[Finding] | None = None, beat: ScriptBeat | None = None) -> bool:
    """Mute-test: cited print is on on_screen/frame. ACTION shot chrome alone does not pass."""
    from onecrew.script import _YEAR_TOK, _speech_norm, pack_numbers, speak_stamp_fact, speak_stamps

    rows = list(findings or [])
    fids = list(beat.finding_ids) if beat is not None else [f.id for f in rows]
    printed = speak_stamp_fact(fids, rows) or speak_stamps(fids, rows)
    if not printed:
        return False
    shown = " ".join(
        part
        for part in (
            getattr(shot, "on_screen", None) or "",
            (beat.frame if beat is not None else "") or "",
        )
        if part
    )
    if not shown.strip():
        return False
    if _speech_norm(printed) in _speech_norm(shown):
        return True
    nums = [
        re.sub(r"[^\d.]+", "", n.replace("−", "-"))
        for n in pack_numbers(printed)
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    ]
    blob = _speech_norm(shown)
    return bool(nums) and all(n in blob for n in nums if n)


def _shot_line(beat: ScriptBeat, rows: list[Finding], packet: Packet) -> str:
    """One idea. Eyes from the written beat. Archive or official series first. No leftover Hormuz."""
    from onecrew.script import is_topic_prompt_frame

    eyes = (beat.frame or "").strip()
    if eyes and is_topic_prompt_frame(eyes, packet):
        eyes = ""
    if eyes:
        return eyes
    claim = rows[0].claim.rstrip(".") if rows else beat.vo.split("\n")[-1].split("[")[0].strip()
    if "milk" in claim.lower() or "dairy" in claim.lower() or "auction" in claim.lower():
        return f"Official auction print: {claim}."
    return f"Official series or archive still for: {claim}."


def _footage_query(text: str, packet: Packet) -> str:
    q = text or ""
    q = re.sub(r"\bgrounded\b", " ", q, flags=re.I)
    pack = _pack_blob(packet)
    if "hormuz" not in pack and "jcpoa" not in pack:
        q = re.sub(r"\bgulf chart\b|\bgulf map\b|\bgulf of mexico\b", " ", q, flags=re.I)
    q = re.sub(r"\bvideo game\b", " ", q, flags=re.I)
    return re.sub(r"\s+", " ", q).strip()


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
    if any(key in blob for key in ("announcement", "tanker", "presser", "withdrawal", "podium")):
        return "event"
    if any(key in blob for key in ("troop-movement", "troop movement", "motion graphic", "animation")):
        return "motion_graphic"
    if any(
        key in blob
        for key in (
            "infographic",
            "chart",
            "bar",
            "series",
            "usrec",
            "sahm",
            "gdp",
            "receipt board",
            "gulf map",
            "wall map",
            "close card",
            "board follows the pack",
            "near is not a switch",
        )
    ):
        return "infographic"
    return "event"


_CLOSE_CARD = ("close card", "board follows the pack", "near is not a switch")


def _is_close_card(shot: ShotFrame) -> bool:
    blob = f"{shot.shot} {shot.line or ''}".lower()
    return any(key in blob for key in _CLOSE_CARD)


def _allows_imagen(shot: ShotFrame, *, fiction: bool) -> bool:
    if shot.footage == "sourced":
        return False
    if _is_close_card(shot):
        return False
    if fiction:
        return True
    return shot.kind in {"motion_graphic", "infographic"}


def _url_ok(url: str | None) -> bool:
    return bool(url) and url.startswith(("http://", "https://"))


_OFFICIAL_FOOTAGE = ("stlouisfed.org", "bls.gov", "bea.gov")


def _official_series_url(url: str | None) -> bool:
    low = (url or "").lower()
    return bool(url) and any(host in low for host in _OFFICIAL_FOOTAGE)


_EMPSIT = re.compile(r"empsit_(\d{2})(\d{2})(\d{4})", re.I)
_MONTH_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}


def _when_month_year(when: str) -> tuple[int, int] | None:
    match = re.search(
        r"(january|february|march|april|may|june|july|august|september|october|november|december)\s+(\d{4})",
        when or "",
        re.I,
    )
    if not match:
        return None
    return _MONTH_NUM[match.group(1).lower()], int(match.group(2))


def _empsit_ok(url: str, when: str) -> bool:
    stamp = _EMPSIT.search(url or "")
    if not stamp:
        return True
    data = _when_month_year(when)
    if data is None:
        return False
    rel_m, rel_y = int(stamp.group(1)), int(stamp.group(3))
    month, year = data
    month += 1
    if month == 13:
        month, year = 1, year + 1
    return (rel_m, rel_y) == (month, year)


def _is_hole_shot(shot: ShotFrame) -> bool:
    blob = f"{shot.shot} {shot.line or ''}".lower()
    return "sahm hole" in blob or "no matching url" in blob


def _cited_official_url(shot: ShotFrame, packet: Packet | None) -> str | None:
    if _is_hole_shot(shot):
        return None
    findings = list(packet.receipt.findings) if packet and packet.receipt else []
    by_id = {f.id: f for f in findings}
    by_url = {f.parallel_url: f for f in findings if f.parallel_url}
    for ref in shot.source_refs or []:
        if _official_series_url(ref):
            finding = by_url.get(ref)
            when = (finding.when or "") if finding else ""
            if "empsit_" in ref.lower() and not _empsit_ok(ref, when):
                continue
            return ref
        if ref in by_id:
            finding = by_id[ref]
            url = finding.parallel_url
            if _official_series_url(url) and _empsit_ok(url or "", finding.when or ""):
                return url
    return None


def _ban_missing_event(shots: list[ShotFrame], packet: Packet | None) -> None:
    fiction = invents_frame(cut=packet.cut, tell=packet.tell or "") if packet else False
    if fiction:
        return
    for shot in shots:
        if shot.footage == MISSING and shot.kind == "event":
            shot.kind = "infographic"


def prefer_footage(shots: list[ShotFrame], rails: Rails, packet: Packet | None = None) -> bool:
    """Bind cited official finding URLs. Search must not override vintage."""
    if not rails.parallel:
        for shot in shots:
            shot.footage = MISSING
            shot.footage_url = None
            shot.footage_title = MISSING
        _ban_missing_event(shots, packet)
        return False
    fiction = invents_frame(cut=packet.cut, tell=packet.tell or "") if packet else False
    for shot in shots:
        if fiction or _is_close_card(shot) or _is_hole_shot(shot):
            shot.footage = MISSING
            shot.footage_url = None
            shot.footage_title = MISSING
            continue
        bound = _cited_official_url(shot, packet)
        if bound:
            shot.footage = "sourced"
            shot.footage_url = bound
            shot.footage_title = MISSING
            shot.imagen = False
            shot.image_href = ""
            continue
        shot.footage = MISSING
        shot.footage_url = None
        shot.footage_title = MISSING
    _ban_missing_event(shots, packet)
    return True


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
        if not fiction and shot.kind in {"motion_graphic", "infographic"}:
            prompt = (
                f"Motion graphic or infographic explainer, not photoreal archive tape. "
                f"Cut={packet.cut}. Shot: {shot.shot}. VO beat {shot.beat_id}."
            )
        else:
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
    _ban_missing_event(shots, packet)
    return shots


def write_board(packet: Packet, rails: Rails) -> list[ShotFrame]:
    """Shot list, then prefer sourced footage, then Imagen only on misses."""
    from onecrew.script import sanitize_for_ship

    sanitize_for_ship(packet)
    shots = write_shot_list(packet)
    if not shots:
        return []
    searched = prefer_footage(shots, rails, packet)
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
