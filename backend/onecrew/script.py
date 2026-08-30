from __future__ import annotations

import json
import re

from onecrew import config
from onecrew.cut import event_cap, is_long_cut, require_cut
from onecrew.models import MISSING, Exclusion, Finding, Packet, ScriptBeat
from onecrew.tell import invents_frame
from onecrew.tone import apply_tone
from onecrew.vertex_client import VertexDownError, generate_script

_PACKET_MARK = "<<<PACKET>>>"
_PACKET_END = "<<<END>>>"
_LEFTOVER_NAMES = ("leila", "reza")
_HORMUZ_WORDS = ("hormuz", "jcpoa", "gulf")
_SHORT = frozenset({"tiktok-length", "shorts"})
_VERTEX_HOLE = "Vertex script"


def _cite(finding_id: str) -> str:
    return f" [{finding_id}]"


def _recast(finding: Finding, lean: str, *, long_form: bool) -> str:
    """Spoken line from a claim. Same facts, different emphasis. No invented events."""
    body = finding.claim.rstrip(".")
    when = (finding.when or "").strip()
    after = re.match(r"^(.+?) after (.+)$", body, flags=re.I)
    if lean == "right":
        if after:
            line = f"After {after.group(2)}, {after.group(1)[0].lower() + after.group(1)[1:]}."
        elif when:
            line = f"{when}: {body}."
        else:
            line = f"{body}. That's the print."
        if long_form:
            line += " I'm not stacking anything else on it."
        return line
    if lean in {"left", "far_left"}:
        if after:
            line = f"{after.group(1)} once {after.group(2)} printed."
        elif when:
            line = f"When this lands in {when}: {body}."
        else:
            line = f"What we can say out loud is this — {body}."
        if long_form:
            line += " Stay on that sentence."
        return line
    if lean == "far_right":
        line = f"{when + ': ' if when else ''}{body}."
        if long_form:
            line += " Date and claim. Stop there."
        return line
    if lean == "unhinged_fringe":
        line = f"Plain: {body}."
        if long_form:
            line += " I still don't get to invent the next beat."
        return line
    line = f"{('In ' + when + ', ') if when else ''}{body}."
    if long_form:
        line += " I'm staying on that."
    return line


def _invents_frame(packet: Packet) -> bool:
    return invents_frame(cut=packet.cut, tell=packet.tell or "")


def _host_only(packet: Packet) -> bool:
    return not _invents_frame(packet)


def _tc(total_s: int, *, hours: bool) -> str:
    if hours:
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def _act_name(index: int, total: int) -> str:
    third = max(1, (total + 2) // 3)
    return f"ACT {min(3, index // third + 1)}"


def _tier(cut: str | None) -> str:
    if cut in _SHORT:
        return "short"
    if cut == "full_length_documentary":
        return "doc"
    if cut == "feature_film":
        return "feature"
    return "episode"


def _durs(tier: str) -> dict[str, int]:
    if tier == "short":
        return {"heading": 1, "action": 3, "vo": 6, "dialogue": 4, "interview": 3, "close": 5}
    if tier == "doc":
        return {"heading": 2, "action": 50, "vo": 70, "dialogue": 40, "interview": 40, "close": 180}
    if tier == "feature":
        return {"heading": 2, "action": 45, "vo": 60, "dialogue": 40, "interview": 30, "close": 180}
    return {"heading": 2, "action": 90, "vo": 150, "dialogue": 40, "interview": 45, "close": 180}


class _Draft:
    def __init__(self, *, hours: bool, long_form: bool, scene_total: int):
        self.hours = hours
        self.long_form = long_form
        self.scene_total = scene_total
        self.beats: list[ScriptBeat] = []
        self.cursor = 0
        self.scene_i = 0

    def add(
        self,
        *,
        kind: str,
        bid: str,
        text: str,
        fids: list[str],
        dur: int,
        scene: str,
        camera: str = "",
        frame: str = "",
    ) -> None:
        act = _act_name(self.scene_i, self.scene_total) if self.long_form else ""
        self.beats.append(
            ScriptBeat(
                id=bid,
                start=_tc(self.cursor, hours=self.hours),
                duration_s=dur,
                act=act,
                scene=scene,
                kind=kind,
                vo=text,
                camera=camera,
                finding_ids=fids,
                frame=frame,
            )
        )
        self.cursor += dur
        if kind == "heading":
            self.scene_i += 1


def _allowed_text(packet: Packet) -> str:
    parts = [
        packet.research_pack or "",
        packet.topic or "",
        packet.tell or "",
        packet.hook or "",
    ]
    receipt = packet.receipt
    if receipt:
        for finding in receipt.findings:
            parts.extend(
                [
                    finding.id,
                    finding.claim,
                    finding.title,
                    finding.note,
                    finding.when or "",
                ]
            )
        for link in receipt.causal_links:
            parts.extend([link.id, link.claim, link.from_id, link.to_id])
    return " ".join(parts).lower()


def _holes_for_vo(vo: str, packet: Packet) -> list[str]:
    allowed = _allowed_text(packet)
    blob = (vo or "").lower()
    holes: list[str] = []
    fiction = _invents_frame(packet)
    for name in _LEFTOVER_NAMES:
        if name in blob and name not in allowed and not fiction:
            holes.append(f"invented character {name}")
    for word in _HORMUZ_WORDS:
        if re.search(rf"\b{word}\b", blob) and word not in allowed:
            holes.append(f"leftover {word} not in pack")
    if _host_only(packet) and "(frame)" in blob:
        holes.append("invented (frame) on a host-only cut")
    return holes


def _fail_closed(packet: Packet, holes: list[str]) -> Packet:
    packet.script = ""
    packet.beats = []
    packet.status = "hold"
    detail = "; ".join(h for h in holes if h.strip()) or "script held"
    kept = [row for row in packet.exclusions if row.what != _VERTEX_HOLE]
    kept.append(Exclusion(what=_VERTEX_HOLE, reason="rails_down", detail=detail))
    packet.exclusions = kept
    receipt = packet.receipt
    if receipt is not None and receipt.disposition == "HOLD":
        prior = (receipt.hold_reason or "").strip()
        receipt.hold_reason = f"{prior} {detail}".strip() if prior else detail
    return packet


def _scene_slugs(finding: Finding, *, fiction: bool, tell: str, n: int) -> list[str]:
    if fiction:
        hint = (tell or "the tell").strip()[:32] or "the tell"
        return [
            f"INT. {hint.upper()} / {finding.id.upper()} - NIGHT",
            f"INT. {hint.upper()} / {finding.id.upper()} - LATER",
            f"EXT. {hint.upper()} / {finding.id.upper()} - NIGHT",
        ][:n]
    when = (finding.when or "").strip()
    archive = f"ARCHIVE — {when}" if when else f"ARCHIVE — {finding.id}"
    studio = f"STUDIO — {finding.id}"
    extra = "B-ROLL — CITED TAPE"
    return [studio, archive, extra, "STUDIO — THE SENTENCE"][:n]


def _visual_for(finding: Finding, *, fiction: bool, tell: str) -> str:
    if fiction:
        return f"{(tell or 'the tell').strip()}. (frame)"
    claim = finding.claim.rstrip(".")
    lower = claim.lower()
    if any(key in lower for key in ("share", "percent", "chart", "index", "payroll", "usrec", "price")):
        return f"Infographic from the cited row: {claim}. Not a photoreal fake room."
    if any(key in lower for key in ("tanker", "strait", "transits", "seaborne", "hormuz")):
        return f"Archive tape: tanker in the cited strait lane. {claim}. Not a photoreal fake room."
    if any(key in lower for key in ("withdrew", "withdrawal", "announcement", "dated")):
        return f"Archive of the cited announcement: {claim}."
    return f"Host/reporter. Archive or cited tape for: {claim}. No photoreal fake event room."


def _hole_line(finding: Finding, lean: str) -> str:
    if finding.stamp == "fringe":
        body = finding.claim.rstrip(".")
        return f"There's a claim that {body[0].lower() + body[1:] if body else body}. I can't run that as fact."
    if finding.lean == "missing" or finding.lean == MISSING:
        return "Who drives that repeated line is not on our list. I am leaving the hole visible."
    if finding.propaganda == "yes":
        issuer = finding.propaganda_issuer if finding.propaganda_issuer != "missing" else "the named issuer"
        return f"{issuer} is on the row as the campaign source. The stamp stays visible."
    return "That is the sentence we have. I am not stacking a later scare on it."


def _interview_line(finding: Finding) -> str:
    if finding.stamp == "fringe":
        return "Ask for a source on this claim. If none lands, it stays a claim."
    if finding.propaganda_issuer and finding.propaganda_issuer != MISSING:
        return f"Ask who is putting that figure out. The named issuer on the row is {finding.propaganda_issuer}."
    return "Ask what we can cite on this beat. Do not invent the next event."


def _close_vo(link_claim: str, lean: str, cite: list[str]) -> str:
    claim = link_claim.rstrip(".")
    lowered = claim[0].lower() + claim[1:] if claim else claim
    if lean == "right":
        line = f"Don't hang a later scare on an earlier date. That connection is not sourced: {claim}."
    elif lean in {"left", "far_left"}:
        line = f"I will not tell you that {lowered}. We do not have that connection."
    elif lean == "unhinged_fringe":
        line = f"I want a clean line that {lowered}. I don't have it, so I won't draw it."
    else:
        line = f"I cannot tell you that {lowered}. That connection is not sourced."
    return line + "".join(_cite(fid) for fid in cite)


def model_payload(packet: Packet) -> dict:
    """Machine block sent to Vertex. Lean/tone/tell voice; they do not restamp rows."""
    receipt = packet.receipt
    findings = []
    links = []
    if receipt:
        for finding in receipt.findings:
            findings.append(
                {
                    "id": finding.id,
                    "when": finding.when,
                    "claim": finding.claim,
                    "stamp": finding.stamp,
                    "note": finding.note,
                    "title": finding.title,
                }
            )
        for link in receipt.causal_links:
            links.append(
                {
                    "id": link.id,
                    "from_id": link.from_id,
                    "to_id": link.to_id,
                    "claim": link.claim,
                    "stamp": link.stamp,
                }
            )
    return {
        "id": packet.id,
        "topic": packet.topic,
        "tell": packet.tell,
        "tone": packet.tone,
        "cut": packet.cut,
        "script_lean": packet.script_lean,
        "platform": packet.platform,
        "host_only": _host_only(packet),
        "invents_frame": _invents_frame(packet),
        "findings": findings,
        "links": links,
        "pack": packet.research_pack or "",
    }


def draft_model_script(packet: Packet) -> dict:
    """Pack-grounded beat JSON. Seed/GET only, or a Vertex-shaped echo. Not a leftover cast."""
    receipt = packet.receipt
    if receipt is None:
        return {"beats": []}
    lean = packet.script_lean or "centered_independent"
    cut = require_cut(packet.cut) if packet.cut else None
    rows = list(receipt.findings)
    if cut:
        rows = rows[: event_cap(cut, packet.platform)]
    tier = _tier(cut)
    long_form = bool(cut and is_long_cut(cut))
    fiction = _invents_frame(packet)
    per = {"short": 1, "episode": 2, "doc": 4, "feature": 3}[tier]
    first = rows[0] if rows else None
    open_scene = (
        f"INT. {(packet.tell or 'the tell').strip().upper()[:48] or 'THE TELL'} - EVENING"
        if fiction
        else "STUDIO — COLD OPEN"
    )
    open_visual = (
        f"{(packet.tell or 'the tell').strip()}. (frame)"
        if fiction
        else "Host at the desk. No invented family."
    )
    units: list[dict] = []
    if first and tier != "short":
        units.append(
            {
                "finding_id": first.id,
                "vo": "",
                "visual": open_visual,
                "scene": open_scene,
                "kind": "open",
            }
        )
    for finding in rows:
        spoken = apply_tone(
            _recast(finding, lean, long_form=True).rstrip(),
            packet.tone,
            fiction=fiction,
        )
        fact = spoken + _cite(finding.id)
        hole = apply_tone(
            _hole_line(finding, lean).rstrip(),
            packet.tone,
            fiction=fiction,
        ) + _cite(finding.id)
        slugs = _scene_slugs(finding, fiction=fiction, tell=packet.tell or "", n=per)
        visual = _visual_for(finding, fiction=fiction, tell=packet.tell or "")
        for si, slug in enumerate(slugs):
            units.append(
                {
                    "finding_id": finding.id,
                    "vo": fact if si == 0 else hole,
                    "visual": visual,
                    "scene": slug,
                    "kind": "vo",
                    "interview": _interview_line(finding) if (not fiction and si == per - 1) else "",
                }
            )
    if tier != "short" and receipt.causal_links:
        link = receipt.causal_links[0]
        known = {f.id for f in receipt.findings}
        cite = [fid for fid in (link.from_id, link.to_id) if fid in known]
        if cite:
            close_scene = (
                f"INT. {(packet.tell or 'the tell').strip().upper()[:48] or 'THE TELL'} - NIGHT"
                if fiction
                else "STUDIO — THE HOLE"
            )
            close_visual = (
                f"{(packet.tell or 'the tell').strip()}. No sourced explosion. (frame)"
                if fiction
                else "Two dated cards on a table. No arrow drawn."
            )
            units.append(
                {
                    "finding_id": cite[0],
                    "finding_ids": cite,
                    "id": link.id,
                    "vo": apply_tone(
                        _close_vo(link.claim, lean, cite),
                        packet.tone,
                        fiction=fiction,
                    ),
                    "visual": close_visual,
                    "scene": close_scene,
                    "kind": "close",
                }
            )
    return {"beats": units}


def _speaker(packet: Packet) -> str:
    return "NARRATOR"


def assemble_script(packet: Packet, model: dict) -> Packet:
    receipt = packet.receipt
    if receipt is None:
        return _fail_closed(packet, ["empty pack"])
    lean = packet.script_lean or "centered_independent"
    cut = require_cut(packet.cut) if packet.cut else None
    tier = _tier(cut)
    long_form = bool(cut and is_long_cut(cut))
    hours = long_form
    durs = _durs(tier)
    units = list(model.get("beats") or [])
    if not units:
        return _fail_closed(packet, ["Vertex returned no beats"])
    known = {f.id for f in receipt.findings}
    prior = {beat.id: beat for beat in packet.beats}
    scene_total = max(1, sum(1 for u in units if u.get("scene")))
    draft = _Draft(hours=hours, long_form=long_form, scene_total=scene_total)
    seen_vo: set[str] = set()
    for unit in units:
        fids = [fid for fid in (unit.get("finding_ids") or [unit.get("finding_id")]) if fid]
        if not fids or any(fid not in known for fid in fids):
            return _fail_closed(packet, ["beat cites a finding that is not in the pack"])
        scene = (unit.get("scene") or "STUDIO").strip()
        visual = (unit.get("visual") or "").strip()
        vo = (unit.get("vo") or "").strip()
        kind = unit.get("kind") or "vo"
        holes = _holes_for_vo(f"{vo} {visual}", packet)
        if holes:
            return _fail_closed(packet, holes)
        fiction = _invents_frame(packet)
        frame = visual if fiction and "(frame)" in visual else ""
        if kind == "open":
            draft.add(kind="heading", bid="open-h", text=scene, fids=fids, dur=durs["heading"], scene=scene)
            draft.add(
                kind="action",
                bid="open-a",
                text=visual or "Host at the desk. No invented family.",
                fids=fids,
                dur=durs["action"],
                scene=scene,
                camera="WIDE",
                frame=frame,
            )
            continue
        bid = unit.get("id") or ""
        if kind == "close":
            bid = bid or fids[0]
            draft.add(kind="heading", bid=f"{bid}-h", text=scene, fids=fids, dur=durs["heading"], scene=scene)
            draft.add(
                kind="action",
                bid=f"{bid}-a",
                text=visual or "Two dated cards on a table. No arrow drawn.",
                fids=fids,
                dur=durs["action"],
                scene=scene,
                camera="INSERT",
                frame=frame,
            )
            spoken = f"{_speaker(packet)}\n{vo}" if vo else f"{_speaker(packet)}\n{visual}"
            draft.add(
                kind="vo",
                bid=bid,
                text=spoken,
                fids=fids,
                dur=durs["close"],
                scene=scene,
                camera="MCU",
                frame=frame,
            )
            continue
        fid = fids[0]
        si = sum(1 for b in draft.beats if b.id.startswith(f"{fid}-h")) + 1
        draft.add(kind="heading", bid=f"{fid}-h{si}", text=scene, fids=fids, dur=durs["heading"], scene=scene)
        draft.add(
            kind="action",
            bid=f"{fid}-a{si}",
            text=visual or f"Host/reporter. Cited tape for {fid}.",
            fids=fids,
            dur=durs["action"],
            scene=scene,
            camera="WIDE" if si == 1 else "CUTAWAY",
            frame=frame,
        )
        if vo:
            vo_id = fid if fid not in seen_vo else f"{fid}-v{si}"
            seen_vo.add(fid)
            spoken = f"{_speaker(packet)}\n{vo}"
            draft.add(
                kind="vo",
                bid=vo_id,
                text=spoken,
                fids=fids,
                dur=durs["vo"],
                scene=scene,
                camera="MCU",
                frame=frame,
            )
        asked = (unit.get("interview") or "").strip()
        if asked and not fiction:
            draft.add(
                kind="interview",
                bid=f"{fid}-q",
                text=asked,
                fids=fids,
                dur=durs["interview"],
                scene=scene,
                camera="TWO-SHOT",
            )
    beats = draft.beats
    for beat in beats:
        old = prior.get(beat.id)
        if old is None:
            continue
        beat.collision = old.collision
        beat.collision_url = old.collision_url
        beat.collision_title = old.collision_title
        beat.collision_kind = old.collision_kind
    lines = [
        f"Timed VO · {packet.platform or 'missing'} · {packet.cut or 'missing'} · {lean} · {packet.tell or 'missing'}"
        + (f" · {packet.tone}" if packet.tone else ""),
        "",
    ]
    last_act = None
    last_scene = None
    elapsed = 0
    for beat in beats:
        if beat.act and beat.act != last_act:
            lines.append(beat.act)
            last_act = beat.act
        if beat.kind == "heading":
            if beat.scene != last_scene:
                lines.append(beat.scene)
                last_scene = beat.scene
            elapsed += beat.duration_s
            continue
        elapsed += beat.duration_s
        lines.append(f"{beat.start}–{_tc(elapsed, hours=hours)}")
        if beat.camera:
            lines.append(beat.camera)
        if beat.kind == "action":
            lines.append(f"ACTION: {beat.vo}")
        elif beat.kind == "interview":
            lines.append(f"INTERVIEW: {beat.vo}")
        else:
            lines.append(beat.vo)
        lines.append("")
    packet.exclusions = [row for row in packet.exclusions if row.what != _VERTEX_HOLE]
    packet.beats = beats
    packet.script = "\n".join(lines).strip() + "\n"
    if packet.receipt is not None and packet.receipt.disposition == "HOLD":
        packet.status = "hold"
    else:
        packet.status = "ready"
    return packet


def _parse_model(raw: str) -> dict:
    text = (raw or "").strip()
    if not text:
        raise ValueError("empty Vertex text")
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Vertex JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("Vertex JSON must be an object")
    return data


def _writer_prompt(packet: Packet) -> str:
    payload = model_payload(packet)
    host = (
        "HOST/REPORTER ONLY. No invented family. No Leila. No Reza. "
        "No Gulf chart unless the pack is about Hormuz."
        if payload["host_only"]
        else "feature_film may invent a frame. Label every invented frame (frame). Do not stamp invented rooms as fact."
    )
    return (
        f"Write a full timed recordable voiceover and beat list from this research pack.\n"
        f"Model rail: {config.GEMINI_MODEL}.\n"
        f"{host}\n"
        "Do not invent sources, numbers, or events that are not in the pack/findings.\n"
        "Lean, tone, and tell voice the pack. They do not restamp source rows.\n"
        "Return JSON only: {\"beats\":[{\"finding_id\",\"vo\",\"visual\",\"scene\",\"kind\",\"interview\"}]}.\n"
        "kind is open|vo|close. Cite finding ids in vo as [id].\n"
        f"{_PACKET_MARK}\n"
        f"{json.dumps(payload, ensure_ascii=True)}\n"
        f"{_PACKET_END}\n"
        "RESEARCH PACK:\n"
        f"{packet.research_pack or ''}\n"
    )


def write_offline_pack_script(packet: Packet) -> Packet:
    """Seed / GET path. Speaks cited claims. Does not call Vertex. Not a leftover cast."""
    receipt = packet.receipt
    if receipt is None or receipt.disposition != "READY" or not receipt.findings:
        holes = []
        if receipt is None or not receipt.findings:
            holes.append("empty pack")
        if receipt is not None and receipt.disposition == "HOLD":
            holes.append(receipt.hold_reason or "HOLD pack")
        return _fail_closed(packet, holes or ["empty pack"])
    return assemble_script(packet, draft_model_script(packet))


def write_script(packet: Packet) -> Packet:
    """Live writer. Vertex only. Fail-closed: no leftover Hormuz VO, no invented numbers."""
    receipt = packet.receipt
    if receipt is None or receipt.disposition != "READY" or not receipt.findings:
        holes = []
        if receipt is None or not (receipt.findings if receipt else []):
            holes.append("empty pack")
        if receipt is not None and receipt.disposition == "HOLD":
            holes.append(receipt.hold_reason or "HOLD pack")
        if not holes:
            holes.append("empty pack")
        return _fail_closed(packet, holes)
    if not (packet.research_pack or "").strip():
        return _fail_closed(packet, ["empty pack"])
    try:
        raw = generate_script(_writer_prompt(packet))
    except VertexDownError as exc:
        return _fail_closed(packet, [f"Vertex missing: {exc}"])
    try:
        model = _parse_model(raw)
    except ValueError as exc:
        return _fail_closed(packet, [f"Vertex unusable: {exc}"])
    return assemble_script(packet, model)
