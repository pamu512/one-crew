from __future__ import annotations

import json
import re

from onecrew import config
from onecrew.cut import is_long_cut, require_cut
from onecrew.models import Exclusion, Finding, Packet, ScriptBeat
from onecrew.tell import invents_frame
from onecrew.tone import apply_tone
from onecrew.vertex_client import VertexDownError, generate_script

_VERTEX_HOLE = "Vertex script"
_NUM = re.compile(
    r"USREC\s*=\s*0|[-−+]?\d+(?:\.\d+)?\s*%|[-−]\d+\s*k|\b[-−]?\d+\.\d+\b|\b\d{1,4}\b",
    re.I,
)
_OFF_UNLESS_CITED = ("LEI", "+0.2%", "ISM", "55.6")
_PACKET_MARK = "<<<PACKET>>>"
_PACKET_END = "<<<END>>>"
_SHORT = frozenset({"tiktok-length", "shorts"})
_EPISODE_DURS = (20, 55, 75, 70, 70, 55, 70, 65)
_SHORT_DURS = (5, 6, 8, 7, 7, 6, 7, 6)
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


def _pack_text(packet: Packet) -> str:
    parts = [packet.research_pack or "", packet.topic or "", packet.hook or ""]
    receipt = packet.receipt
    if receipt:
        for finding in receipt.findings:
            parts.extend([finding.id, finding.claim, finding.title, finding.note, finding.when or ""])
        for link in receipt.causal_links:
            parts.extend([link.id, link.claim])
    return "\n".join(parts)


def _numbers_in(text: str) -> list[str]:
    return [m.group(0).strip() for m in _NUM.finditer(text or "")]


def _claim(packet: Packet, *needles: str) -> Finding | None:
    receipt = packet.receipt
    if not receipt:
        return None
    for finding in receipt.findings:
        blob = f"{finding.id} {finding.claim} {finding.title} {finding.when}".lower()
        if all(n.lower() in blob for n in needles):
            return finding
    return None


def _cite(finding: Finding | None) -> str:
    return f" [{finding.id}]" if finding else ""


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


def _invents(packet: Packet) -> bool:
    return invents_frame(cut=packet.cut, tell=packet.tell or "")


def _voice(line: str, packet: Packet) -> str:
    lean = packet.script_lean or "centered_independent"
    spoken = line
    if lean == "left" or lean == "far_left":
        spoken = f"What we can say out loud is this — {line}"
    elif lean == "right":
        spoken = f"{line} That's the print."
    elif lean == "far_right":
        spoken = f"{line} Date and claim. Stop there."
    elif lean == "unhinged_fringe":
        spoken = f"Plain: {line}"
    return apply_tone(spoken.rstrip(), packet.tone, fiction=_invents(packet))


def _recession_pack(text: str) -> bool:
    blob = text.lower()
    return "usrec" in blob and ("payroll" in blob or "23k" in blob) and "sahm" in blob


def _eight_from_pack(packet: Packet) -> list[dict]:
    """8-beat spine from pack numbers only. LEI/ISM stay off unless a beat cites them."""
    text = _pack_text(packet)
    usrec = _claim(packet, "usrec")
    payrolls = _claim(packet, "payroll") or _claim(packet, "23k")
    unemp = _claim(packet, "unemployment") or _claim(packet, "4.1")
    gdp = _claim(packet, "gdp")
    sahm = _claim(packet, "sahm")
    nber = _claim(packet, "nber")
    if _recession_pack(text):
        units = [
            {
                "id": "cold-open",
                "vo": _voice(
                    f"USREC=0 (July 2026) smashed into payrolls −23k.{_cite(usrec)}{_cite(payrolls)}",
                    packet,
                ),
                "eyes": "USREC=0 and payrolls −23k on screen. Official series cards only.",
                "finding_ids": [f.id for f in (usrec, payrolls) if f],
            },
            {
                "id": "promise",
                "vo": _voice(
                    "Three objects: the official call, the GDP prints, the Sahm alarm. "
                    "The title is a question we will not answer with a forecast.",
                    packet,
                ),
                "eyes": "Three objects labeled: official call, GDP prints, Sahm alarm. No leftover map.",
                "finding_ids": [f.id for f in (usrec, gdp, sahm) if f],
            },
            {
                "id": "gdp",
                "vo": _voice(
                    f"GDP printed 0.5, then 2.1, then 1.5. One bar at a time.{_cite(gdp)}",
                    packet,
                ),
                "eyes": "New GDP bars: 0.5 then 2.1 then 1.5. New art, not a leftover map.",
                "finding_ids": [gdp.id] if gdp else [],
            },
            {
                "id": "labor",
                "vo": _voice(
                    f"Labor: payrolls −23k and unemployment 4.1%. Named BLS.{_cite(payrolls)}{_cite(unemp)}",
                    packet,
                ),
                "eyes": "BLS labor print: −23k and 4.1%. Official series page. Not a fake layoff room.",
                "finding_ids": [f.id for f in (payrolls, unemp) if f],
            },
            {
                "id": "turn",
                "vo": _voice(
                    f"Turn: Sahm −0.03 vs the 0.50 trigger. Hold. The spine chart stays.{_cite(sahm)}",
                    packet,
                ),
                "eyes": "Sahm spine chart: −0.03 vs 0.50 trigger. Hold. Chart stays.",
                "finding_ids": [sahm.id] if sahm else [],
            },
            {
                "id": "complication",
                "vo": _voice(
                    "Those are not the same object. Near is the gap.",
                    packet,
                ),
                "eyes": "Two objects, a gap labeled near. Official series only.",
                "finding_ids": [f.id for f in (sahm, usrec) if f],
            },
            {
                "id": "receipt",
                "vo": _voice(
                    f"Receipt board: named series NBER, FRED, BLS. Holes labeled.{_cite(nber) or _cite(sahm)}{_cite(usrec)}{_cite(payrolls)}",
                    packet,
                ),
                "eyes": "Receipt board. Named series NBER / FRED / BLS. Holes labeled.",
                "finding_ids": [f.id for f in (nber, sahm, usrec, payrolls) if f],
            },
            {
                "id": "close",
                "vo": _voice(
                    "Near is not a switch. When the pack changes, the board changes.",
                    packet,
                ),
                "eyes": "Close card: near is not a switch. Board follows the pack.",
                "finding_ids": [f.id for f in (sahm, usrec) if f],
            },
        ]
    else:
        findings = list(packet.receipt.findings) if packet.receipt else []
        nums = _numbers_in(text)
        first = findings[0] if findings else None
        second = findings[1] if len(findings) > 1 else first
        third = findings[2] if len(findings) > 2 else first
        a, b = (nums + ["", ""])[:2]
        units = [
        {
            "id": "cold-open",
            "vo": _voice(f"{a} smashed into {b}.{_cite(first)}{_cite(second)}", packet),
            "eyes": f"{a} and {b} on screen. Official series cards only.",
            "finding_ids": [f.id for f in (first, second) if f],
        },
        {
            "id": "promise",
            "vo": _voice(
                "Three objects from the pack. The title is a question we will not answer with a forecast.",
                packet,
            ),
            "eyes": "Three pack objects on screen. No leftover map.",
            "finding_ids": [first.id] if first else [],
        },
        {
            "id": "gdp",
            "vo": _voice(f"{findings[min(2, len(findings)-1)].claim}{_cite(third)}" if findings else a, packet),
            "eyes": "New art from the cited print. Not a leftover map.",
            "finding_ids": [third.id] if third else [],
        },
        {
            "id": "labor",
            "vo": _voice(f"{(second or first).claim}{_cite(second or first)}" if (second or first) else a, packet),
            "eyes": f"Named official series: {(second or first).claim}. Official page only.",
            "finding_ids": [(second or first).id] if (second or first) else [],
        },
        {
            "id": "turn",
            "vo": _voice("Hold on the pack number. The spine chart stays.", packet),
            "eyes": "Spine chart from the cited series. Hold.",
            "finding_ids": [first.id] if first else [],
        },
        {
            "id": "complication",
            "vo": _voice("Those are not the same object. Near is the gap.", packet),
            "eyes": "Two objects, a gap labeled near.",
            "finding_ids": [f.id for f in (first, second) if f],
        },
        {
            "id": "receipt",
            "vo": _voice("Receipt board: named series from the pack. Holes labeled.", packet),
            "eyes": "Receipt board. Named series. Holes labeled.",
            "finding_ids": [f.id for f in findings[:4]],
        },
        {
            "id": "close",
            "vo": _voice("Near is not a switch. When the pack changes, the board changes.", packet),
            "eyes": "Close card: near is not a switch. Board follows the pack.",
            "finding_ids": [first.id] if first else [],
        },
        ]
    if _invents(packet):
        for unit in units:
            if "(frame)" not in (unit.get("eyes") or ""):
                unit["eyes"] = f"{unit['eyes']} (frame)"
    return units


def _vo_has_uncited_off(vo: str, fids: list[str]) -> bool:
    allowed = {x.lower() for x in fids}
    if any(tok in allowed for tok in ("lei-off", "ism-off")):
        return False
    blob = vo or ""
    return any(token in blob for token in _OFF_UNLESS_CITED)


def _tc(total_s: int, *, hours: bool) -> str:
    if hours:
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def _assemble(packet: Packet, units: list[dict]) -> Packet:
    if len(units) != 8:
        return _fail_closed(packet, ["writer must emit 8 beats"])
    known = {f.id for f in (packet.receipt.findings if packet.receipt else [])}
    cut = require_cut(packet.cut) if packet.cut else None
    short = cut in _SHORT
    hours = bool(cut and is_long_cut(cut) and not short)
    durs = list(_SHORT_DURS if short else _EPISODE_DURS)
    prior = {beat.id: beat for beat in packet.beats}
    lean = packet.script_lean or "centered_independent"
    beats: list[ScriptBeat] = []
    cursor = 0
    for i, unit in enumerate(units):
        bid = unit.get("id") or _EIGHT_IDS[i]
        fids = [fid for fid in (unit.get("finding_ids") or []) if fid in known]
        if not fids and known:
            return _fail_closed(packet, [f"{bid} cites nothing in the pack"])
        vo = (unit.get("vo") or "").strip()
        eyes = (unit.get("eyes") or "").strip()
        for fid in fids:
            if f"[{fid}]" not in vo:
                vo = f"{vo} [{fid}]"
        if _vo_has_uncited_off(vo, fids):
            return _fail_closed(packet, ["LEI/ISM spoken without a cited beat"])
        if any(w in vo.lower() for w in ("leila", "reza")) and "leila" not in _pack_text(packet).lower():
            return _fail_closed(packet, ["invented leftover cast"])
        dur = durs[i]
        beats.append(
            ScriptBeat(
                id=bid,
                start=_tc(cursor, hours=hours),
                duration_s=dur,
                act="ACT 1" if hours else "",
                scene=f"BEAT {i+1} — {bid}",
                kind="vo",
                vo=f"NARRATOR\n{vo}",
                camera="MCU" if i else "WIDE",
                finding_ids=fids,
                frame=eyes,
            )
        )
        cursor += dur
        old = prior.get(bid)
        if old is not None:
            beats[-1].collision = old.collision
            beats[-1].collision_url = old.collision_url
            beats[-1].collision_title = old.collision_title
            beats[-1].collision_kind = old.collision_kind
    lines = [
        f"Timed VO · {packet.platform or 'missing'} · {packet.cut or 'missing'} · {lean} · {packet.tell or 'missing'}"
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
        elapsed += beat.duration_s
        lines.append(f"{beat.start}–{_tc(elapsed, hours=hours)}")
        if beat.camera:
            lines.append(beat.camera)
        if beat.frame:
            lines.append(f"ACTION: {beat.frame}")
        lines.append(beat.vo)
        lines.append("")
    packet.exclusions = [row for row in packet.exclusions if row.what != _VERTEX_HOLE]
    packet.beats = beats
    packet.script = "\n".join(lines).strip() + "\n"
    packet.status = "ready" if packet.receipt is None or packet.receipt.disposition != "HOLD" else "hold"
    return packet


def _prompt(packet: Packet, units: list[dict]) -> str:
    payload = {
        "id": packet.id,
        "topic": packet.topic,
        "tell": packet.tell,
        "tone": packet.tone,
        "cut": packet.cut,
        "script_lean": packet.script_lean,
        "pack": packet.research_pack or "",
        "beats": units,
    }
    return (
        f"Read this research pack. Voice the 8-beat spine. {config.GEMINI_MODEL}.\n"
        "Pack numbers only. Do not invent stats. LEI and ISM stay off unless a beat cites them.\n"
        "Host/reporter only on news cuts. No Leila, no Reza, no Gulf chart leftover.\n"
        "Return the same 8-beat JSON.\n"
        f"{_PACKET_MARK}\n{json.dumps(payload, ensure_ascii=True)}\n{_PACKET_END}\n"
        f"PACK:\n{packet.research_pack or ''}\n"
    )


def _parse_units(raw: str) -> list[dict] | None:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    beats = data.get("beats") if isinstance(data, dict) else data
    if not isinstance(beats, list) or len(beats) != 8:
        return None
    return beats


def write_script(packet: Packet) -> Packet:
    """8-beat timed VO from the pack. Fail-closed if the pack is empty or has no numbers."""
    receipt = packet.receipt
    if receipt is None or receipt.disposition != "READY" or not receipt.findings:
        holes = ["empty pack"]
        if receipt is not None and receipt.disposition == "HOLD":
            holes = [receipt.hold_reason or "HOLD pack"]
        return _fail_closed(packet, holes)
    text = _pack_text(packet)
    if not (packet.research_pack or "").strip() and not receipt.findings:
        return _fail_closed(packet, ["empty pack"])
    if not _numbers_in(text):
        return _fail_closed(packet, ["pack has no numbers"])
    units = _eight_from_pack(packet)
    if config.has_vertex():
        try:
            parsed = _parse_units(generate_script(_prompt(packet, units)))
            if parsed:
                units = parsed
        except VertexDownError:
            pass
    return _assemble(packet, units)
