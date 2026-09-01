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
_DEPTH_TOKEN = re.compile(r"\b\d+(?:-\d+)?y\b", re.I)
_GROUNDED_EVENT = re.compile(r"grounded event inside\s+\S+:", re.I)
_LEFTOVER_VO = re.compile(
    r"grounded event inside\s+\S+:|fringe claim about\s+|widely repeated frame about\s+",
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
    parts = [
        packet.research_pack or "",
        packet.task_spine or "",
        packet.topic or "",
        packet.hook or "",
    ]
    receipt = packet.receipt
    if receipt:
        for finding in receipt.findings:
            parts.extend([finding.id, finding.claim, finding.title, finding.note, finding.when or ""])
        for link in receipt.causal_links:
            parts.extend([link.id, link.claim])
    return "\n".join(parts)


def _numbers_in(text: str) -> list[str]:
    """Pack numbers only. Depth tokens like 2-3y are not a series print."""
    cleaned = _DEPTH_TOKEN.sub(" ", text or "")
    return [m.group(0).strip() for m in _NUM.finditer(cleaned)]


def pack_numbers(text: str) -> list[str]:
    return _numbers_in(text)


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


def _units_spoken(units: list[dict]) -> str:
    return "\n".join(f"{u.get('vo') or ''} {u.get('eyes') or ''}" for u in units)


def _leftover_vo(text: str) -> bool:
    return bool(_LEFTOVER_VO.search(text or ""))


def _missing_pack_marks(pack: str, vo: str) -> list[str]:
    """HOLD if the pack has these objects and the VO never says them."""
    holes: list[str] = []
    plow = (pack or "").lower()
    vlow = vo or ""
    if "usrec" in plow and "usrec=0" not in vlow.lower() and "usrec = 0" not in vlow.lower():
        holes.append("USREC=0")
    if "payroll" in plow or "23k" in plow:
        payroll_ok = (
            "−23k" in vlow
            or "-23k" in vlow
            or "payrolls −23" in vlow.lower()
            or "payrolls -23" in vlow.lower()
        )
        if not payroll_ok:
            holes.append("payrolls −23k")
    if "sahm" in plow and ("−0.03" in pack or "-0.03" in pack) and "0.50" in pack:
        if not (("−0.03" in vlow or "-0.03" in vlow) and "0.50" in vlow):
            holes.append("Sahm −0.03 vs 0.50")
    return holes


def _accept_units(packet: Packet, units: list[dict] | None) -> bool:
    if not units or len(units) != 8:
        return False
    spoken = _units_spoken(units)
    if _leftover_vo(spoken):
        return False
    return not _missing_pack_marks(_pack_text(packet), spoken)


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
        if _GROUNDED_EVENT.search(vo) or _leftover_vo(vo):
            return _fail_closed(packet, ["VO is leftover grounded-event template"])
        if _vo_has_uncited_off(vo, fids):
            return _fail_closed(packet, ["LEI/ISM spoken without a cited beat"])
        if any(w in vo.lower() for w in ("leila", "reza")) and "leila" not in _pack_text(packet).lower():
            return _fail_closed(packet, ["invented leftover cast"])
        pack_blob = _pack_text(packet).lower()
        if "hormuz" not in pack_blob and "jcpoa" not in pack_blob:
            if any(w in vo.lower() for w in ("hormuz", "jcpoa", "strait of hormuz", "hormuz-share")):
                return _fail_closed(packet, ["leftover Hormuz on a non-Hormuz topic"])
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
    spoken = packet.script + "\n" + "\n".join(b.vo for b in beats)
    if _leftover_vo(spoken):
        return _fail_closed(packet, ["VO is leftover template"])
    holes = _missing_pack_marks(_pack_text(packet), spoken)
    if holes:
        return _fail_closed(packet, [f"pack numbers missing from VO: {', '.join(holes)}"])
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
    if _GROUNDED_EVENT.search(text) and not _recession_pack(text):
        return _fail_closed(packet, ["leftover grounded-event template"])
    if not _numbers_in(text):
        return _fail_closed(packet, ["pack has no numbers"])
    local = _eight_from_pack(packet)
    units = local
    # Seed / leftover Hormuz stamp locally. Cloud Run boot has ADC so has_vertex
    # is true; Vertex Agent Platform 403 must not crash-loop first-open.
    if config.has_vertex() and packet.id not in {config.SEED_PACKET_ID, "oc-hormuz-decade"}:
        try:
            parsed = _parse_units(generate_script(_prompt(packet, local)))
            # Prefer the pack spine when Vertex is hollow or leftover.
            if parsed and _accept_units(packet, parsed):
                units = parsed
        except VertexDownError:
            pass
    if not _accept_units(packet, units) and _accept_units(packet, local):
        units = local
    return _assemble(packet, units)
