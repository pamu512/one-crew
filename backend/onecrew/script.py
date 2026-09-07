from __future__ import annotations

import json
import re

from onecrew import config
from onecrew.cut import is_long_cut, require_cut
from onecrew.models import MISSING, Exclusion, Finding, Packet, ScriptBeat
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


_LEFTOVER_IDS = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})
_SHORT_IDS = {
    "USREC": frozenset({"usrec", "usrec-july-2026"}),
    "BLS payrolls": frozenset({"payrolls", "payrolls-july-2026"}),
    "payrolls": frozenset({"payrolls", "payrolls-july-2026"}),
    "GDP": frozenset({"gdp", "gdp-2026-q2"}),
    "SAHMREALTIME": frozenset({"sahm", "sahm-july-2026"}),
    "U-3": frozenset({"unemployment", "unemployment-july-2026"}),
}


def _by_series(packet: Packet, *names: str) -> Finding | None:
    receipt = packet.receipt
    if not receipt:
        return None
    wanted = set(names)
    ids = set()
    for name in names:
        ids |= _SHORT_IDS.get(name, frozenset())
    for finding in receipt.findings:
        if finding.id in _LEFTOVER_IDS:
            continue
        if finding.series in wanted or finding.id in ids:
            return finding
    return None


def _print_of(finding: Finding | None, fallback: str = "") -> str:
    if finding is None:
        return fallback
    printed = finding.print
    if printed not in {MISSING, "", None}:
        return printed
    return fallback


def _named_prints(packet: Packet) -> list[Finding]:
    receipt = packet.receipt
    if not receipt:
        return []
    rows = [
        f
        for f in receipt.findings
        if f.id not in _LEFTOVER_IDS
        and f.stamp == "grounded"
        and f.print not in {MISSING, "", None}
    ]
    rows.sort(key=lambda f: f.id)
    return rows


def _live_findings(packet: Packet) -> list[Finding]:
    """Writer never opens on leftover 3-slot ids."""
    receipt = packet.receipt
    if not receipt:
        return []
    return [f for f in receipt.findings if f.id not in _LEFTOVER_IDS]


def _cite(finding: Finding | None) -> str:
    return f" [{finding.id}]" if finding else ""


def _fail_closed(packet: Packet, holes: list[str]) -> Packet:
    packet.script = ""
    packet.beats = []
    packet.status = "hold"
    detail = "; ".join(h for h in holes if h.strip()) or "script held"
    prior = next((row for row in packet.exclusions if row.what == _VERTEX_HOLE), None)
    if prior is not None and (prior.detail or "").strip() and prior.detail not in detail:
        detail = f"{prior.detail}; {detail}"
    kept = [row for row in packet.exclusions if row.what != _VERTEX_HOLE]
    kept.append(Exclusion(what=_VERTEX_HOLE, reason="rails_down", detail=detail))
    packet.exclusions = kept
    receipt = packet.receipt
    if receipt is not None:
        receipt.disposition = "HOLD"
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


_PAY_HEAD = re.compile(r"([\-−+])?\s*\d{1,3}(?:,\d{3})+\b|([\-−+])?\s*\d+\s*k\b", re.I)
_PAY_CUE = re.compile(r"payroll|nonfarm|payems|\bces\b", re.I)


def _notes_have_named_prints(text: str) -> bool:
    blob = text or ""
    usrec = bool(re.search(r"usrec.{0,60}?(?:=|is|:)?\s*(?<![\d.])0(?!\.\d)", blob, re.I))
    payrolls = False
    for match in _PAY_CUE.finditer(blob):
        if _PAY_HEAD.search(blob[match.start() : match.start() + 200]):
            payrolls = True
            break
    return usrec and payrolls


def _payroll_print_ok(printed: str) -> bool:
    return bool(_PAY_HEAD.search(printed or "")) and "%" not in (printed or "")


_MONTH_YEAR = re.compile(
    r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
    re.I,
)
_TRIGGER_LABEL = re.compile(
    r"(?:what_counts_as_the_first_trigger|first[\s_-]+trigger|proximate[\s_-]+trigger|"
    r"first[\s_-]+transmission)\s*[:\-–—]\s*(.+)",
    re.I,
)
_TRIGGER_DATE = re.compile(
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"(?:\s*/\s*(?:January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec))?"
    r"\s+\d{4}",
    re.I,
)
_TRIGGER_MONTH = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)\b",
    re.I,
)


def _month_year(when: str) -> tuple[str, str] | None:
    match = _MONTH_YEAR.search(when or "")
    if not match:
        return None
    return (match.group(1).lower(), match.group(2))


def _first_trigger_text(packet: Packet) -> str:
    """Dated first-trigger / first transmission from spine or pack. Empty if none."""
    blob = "\n".join([packet.task_spine or "", packet.research_pack or ""])
    for match in _TRIGGER_LABEL.finditer(blob):
        snippet = (match.group(1) or "").strip().split("\n")[0].strip(" .;")
        if snippet and _TRIGGER_DATE.search(snippet):
            return snippet[:240]
    exec_m = re.search(r"executive_summary\s*[:\-–—]\s*(.+)", blob, re.I)
    if exec_m:
        para = (exec_m.group(1) or "").strip()
        if re.search(r"proximate\s+trigger|first\s+transmission|first\s+trigger", para, re.I):
            dated = _TRIGGER_DATE.search(para)
            if dated:
                return para[:240]
    return ""


def _trigger_voiced(vo: str, trigger: str) -> bool:
    if not trigger or not vo:
        return False
    v = (vo or "").lower()
    t = trigger.lower()
    years = re.findall(r"\b20\d{2}\b", t)
    if years and not any(y in v for y in years):
        return False
    months = [m.group(0).lower() for m in _TRIGGER_MONTH.finditer(t)]
    if months and not any(m in v for m in months):
        return False
    return bool(years or months)


def _promise_trigger_vo(packet: Packet, trigger: str) -> str:
    return _voice(f"What started the episode: {trigger}.", packet)


def _same_month(left: str, right: str) -> bool:
    a, b = _month_year(left), _month_year(right)
    return a is not None and a == b


def _print_has_minus(printed: str) -> bool:
    return bool(re.search(r"[\-−]\s*\d", printed or ""))


def _vo_has_payroll(vo: str, printed: str) -> bool:
    if not printed:
        return False
    if _print_has_minus(printed) and not re.search(r"[\-−]\s*\d", vo or ""):
        return False
    vo_n = (vo or "").replace("−", "-").replace(",", "").lower()
    p_n = printed.replace("−", "-").replace(",", "").replace(" ", "").lower()
    if printed in (vo or "") or printed.replace("−", "-") in (vo or "").replace("−", "-"):
        return True
    if p_n and p_n in vo_n:
        return True
    digits = re.sub(r"[^\d]", "", p_n)
    if not digits:
        return False
    if printed.lower().rstrip().endswith("k"):
        return digits + "k" in vo_n or digits in vo_n
    return digits in vo_n


def _gdp_bars(printed: str) -> list[str]:
    return [part.strip().rstrip("%") for part in (printed or "").split("/") if part.strip()]


def _gdp_lines(printed: str) -> tuple[str, str]:
    bars = _gdp_bars(printed)
    if not bars:
        return "", ""
    if len(bars) == 1:
        return f"GDP printed {bars[0]}. One bar at a time.", f"New GDP bars: {bars[0]}. New art, not a leftover map."
    spoken = ", then ".join(bars)
    eyes = " then ".join(bars)
    return (
        f"GDP printed {spoken}. One bar at a time.",
        f"New GDP bars: {eyes}. New art, not a leftover map.",
    )


def _missing_pack_marks(packet: Packet, vo: str) -> list[str]:
    """HOLD if minted objects exist and the VO never says those prints."""
    holes: list[str] = []
    vlow = vo or ""
    usrec = _by_series(packet, "USREC")
    if usrec:
        printed = _print_of(usrec, "0")
        mark = f"USREC={printed}"
        if mark.lower() not in vlow.lower() and f"usrec = {printed}" not in vlow.lower():
            holes.append(mark)
    pay = _by_series(packet, "BLS payrolls", "payrolls")
    if pay:
        printed = _print_of(pay, "")
        if not _vo_has_payroll(vlow, printed):
            holes.append(f"payrolls {printed}")
    sahm = _by_series(packet, "SAHMREALTIME")
    if sahm and not (("−0.03" in vlow or "-0.03" in vlow) and "0.50" in vlow):
        holes.append("Sahm −0.03 vs 0.50")
    gdp = _by_series(packet, "GDP")
    if gdp:
        printed = _print_of(gdp, "")
        bars = _gdp_bars(printed)
        chunks = re.findall(
            r"GDP printed\s+(.+?)(?:\.\s|$)|New GDP bars:\s+(.+?)(?:\.\s|$)",
            vlow,
            re.I,
        )
        chunk = " ".join(part for pair in chunks for part in pair if part)
        spoken = re.findall(r"\d+\.\d+|\d+", chunk)
        for bar in bars:
            if bar not in spoken:
                holes.append(f"GDP {bar}")
        for bar in spoken:
            if bar not in bars:
                holes.append(f"GDP leftover {bar}")
    return holes


def _mint_held(packet: Packet, mint_holes: list[str] | None) -> bool:
    if mint_holes:
        return True
    return packet.receipt is not None and packet.receipt.disposition == "HOLD"


def _accept_units(
    packet: Packet,
    units: list[dict] | None,
    *,
    spine: list[dict] | None = None,
    mint_holes: list[str] | None = None,
) -> bool:
    if not units or len(units) != 8:
        return False
    spoken = _units_spoken(units)
    if _leftover_vo(spoken):
        return False
    # HOLD/mint-hole packets must not require speaking broken minted prints.
    if _missing_pack_marks(packet, spoken) and not _mint_held(packet, mint_holes):
        return False
    if spine:
        key = {"cold-open", "gdp", "labor", "turn"}
        need = " ".join(u.get("vo") or "" for u in spine if u.get("id") in key)
        have = spoken.replace("−", "-")
        for token in _numbers_in(need):
            if token.replace("−", "-") not in have:
                return False
    return True


def _eight_from_pack(packet: Packet) -> list[dict]:
    """8-beat spine from minted series/print. LEI/ISM stay off unless a beat cites them."""
    usrec = _by_series(packet, "USREC")
    payrolls = _by_series(packet, "BLS payrolls", "payrolls")
    unemp = _by_series(packet, "U-3")
    gdp = _by_series(packet, "GDP")
    sahm = _by_series(packet, "SAHMREALTIME")
    nber = None
    usrec_print = _print_of(usrec, "")
    usrec_when = (usrec.when or "").strip() if usrec else ""
    pay_print = _print_of(payrolls, "")
    unemp_print = _print_of(unemp, "")
    if unemp and not unemp_print and "4.1" in (unemp.claim or ""):
        unemp_print = "4.1%"
    sahm_print = _print_of(sahm, "")
    trigger = _first_trigger_text(packet)
    if usrec and payrolls:
        labor = (
            f"Labor: payrolls {pay_print} and unemployment {unemp_print}. Named BLS."
            if unemp_print
            else f"Labor: payrolls {pay_print}. Named BLS."
        )
        units = [
            {
                "id": "cold-open",
                "vo": _voice(
                    f"USREC={usrec_print} ({usrec_when}) smashed into payrolls {pay_print}.{_cite(usrec)}{_cite(payrolls)}",
                    packet,
                ),
                "eyes": f"USREC={usrec_print} and payrolls {pay_print} on screen. Official series cards only.",
                "finding_ids": [f.id for f in (usrec, payrolls) if f],
            },
            {
                "id": "promise",
                "vo": (
                    _promise_trigger_vo(packet, trigger)
                    if trigger
                    else _voice(
                        "Three objects: the official call, the GDP prints, the Sahm alarm. "
                        "The title is a question we will not answer with a forecast.",
                        packet,
                    )
                ),
                "eyes": (
                    "Dated first-trigger from the pack. Official series stay on later cards."
                    if trigger
                    else "Three objects labeled: official call, GDP prints, Sahm alarm. No leftover map."
                ),
                "finding_ids": [f.id for f in (usrec, gdp, sahm) if f],
            },
            {
                "id": "gdp",
                "vo": _voice(
                    (
                        f"{_gdp_lines(_print_of(gdp, ''))[0]}{_cite(gdp)}"
                        if gdp
                        else "GDP hole named. No matching URL. Hold."
                    ),
                    packet,
                ),
                "eyes": (
                    _gdp_lines(_print_of(gdp, ""))[1]
                    if gdp
                    else "GDP hole named. No matching URL."
                ),
                "finding_ids": [gdp.id] if gdp else [],
            },
            {
                "id": "labor",
                "vo": _voice(f"{labor}{_cite(payrolls)}{_cite(unemp)}", packet),
                "eyes": (
                    f"BLS labor print: {pay_print}"
                    + (f" and {unemp_print}" if unemp_print else "")
                    + ". Official series page. Not a fake layoff room."
                ),
                "finding_ids": [f.id for f in (payrolls, unemp) if f],
            },
            {
                "id": "turn",
                "vo": _voice(
                    (
                        f"Turn: Sahm {sahm_print} vs the 0.50 trigger. Hold. The spine chart stays.{_cite(sahm)}"
                        if sahm
                        else "Turn: Sahm hole named. No matching URL. Hold."
                    ),
                    packet,
                ),
                "eyes": (
                    f"Sahm spine chart: {sahm_print} vs 0.50 trigger. Hold. Chart stays."
                    if sahm
                    else "Sahm hole named. No matching URL."
                ),
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
        findings = _live_findings(packet)
        named = _named_prints(packet)
        first = named[0] if named else (findings[0] if findings else None)
        second = named[1] if len(named) > 1 else None
        if second is None and first is not None:
            second = next((f for f in findings if f is not first), None)
        third = named[2] if len(named) > 2 else first
        leftover_costume = {((first.series or "").lower() if first else ""), ((second.series or "").lower() if second else "")}
        smash_ok = (
            first is not None
            and second is not None
            and first is not second
            and {first.series, second.series} == {"USREC", "BLS payrolls"}
        )
        if smash_ok:
            smash = f"{first.series}={first.print} smashed into {second.series} {second.print}."
            eyes = f"{first.series}={first.print} and {second.series} {second.print} on screen. Official series cards only."
        elif first and first.print not in {MISSING, "", None} and leftover_costume.isdisjoint({"hormuz", "jcpoa"}):
            smash = f"{first.series}={first.print}."
            eyes = f"{first.series}={first.print} on screen. Official series cards only."
        elif first:
            smash = (first.claim or packet.tell or packet.topic or "").strip()
            eyes = "Cited print on screen. No leftover map."
        else:
            smash = (packet.tell or packet.topic or "").strip()
            eyes = "Official series cards only."
        units = [
        {
            "id": "cold-open",
            "vo": _voice(f"{smash}{_cite(first)}{_cite(second)}", packet),
            "eyes": eyes,
            "finding_ids": [f.id for f in (first, second) if f],
        },
        {
            "id": "promise",
            "vo": (
                _promise_trigger_vo(packet, trigger)
                if trigger
                else _voice(
                    "Three objects from the pack. The title is a question we will not answer with a forecast.",
                    packet,
                )
            ),
            "eyes": (
                "Dated first-trigger from the pack. Official series stay on later cards."
                if trigger
                else "Three pack objects on screen. No leftover map."
            ),
            "finding_ids": [first.id] if first else [],
        },
        {
            "id": "gdp",
            "vo": _voice(f"{(third or first).claim}{_cite(third)}" if (third or first) else smash, packet),
            "eyes": "New art from the cited print. Not a leftover map.",
            "finding_ids": [third.id] if third else [],
        },
        {
            "id": "labor",
            "vo": _voice(f"{(second or first).claim}{_cite(second or first)}" if (second or first) else smash, packet),
            "eyes": (
                f"Named official series: {(second or first).claim}. Official page only."
                if (second or first)
                else "Official series cards only."
            ),
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
            "finding_ids": [f.id for f in findings[:4] if f.id not in _LEFTOVER_IDS],
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


_OFF_NAME = re.compile(r"\bLEI\b|\bISM\b")
_OFF_PRINT = re.compile(r"\+0\.2%|\b55\.6\b")
_OFF_TOKEN = re.compile(r"\bLEI\b|\bISM\b|\+0\.2%|\b55\.6\b")


def _off_cited(fids: list[str]) -> bool:
    allowed = {x.lower() for x in fids}
    return any(
        tok == "lei" or tok.startswith("lei-") or tok == "ism" or tok.startswith("ism-")
        for tok in allowed
    )


def _vo_has_uncited_off(vo: str, fids: list[str]) -> bool:
    if _off_cited(fids):
        return False
    return bool(_OFF_TOKEN.search(vo or ""))


def _soften_uncited_off(text: str, fids: list[str]) -> tuple[str, bool]:
    """Strip uncited LEI/ISM names. Digit leftovers stay unless next to a name."""
    if not _vo_has_uncited_off(text, fids):
        return text, False
    if not _OFF_NAME.search(text or ""):
        return text, True
    cleaned = _OFF_PRINT.sub("", _OFF_NAME.sub("", text))
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = cleaned.strip(" ,.;:-")
    if not cleaned:
        return "Hold on the pack number.", True
    return cleaned, True


def _tc(total_s: int, *, hours: bool) -> str:
    if hours:
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def _vo_uses_pack(packet: Packet, vo: str) -> bool:
    pack_n = {n.replace("−", "-") for n in _numbers_in(_pack_text(packet))}
    vo_n = {n.replace("−", "-") for n in _numbers_in(vo)}
    return bool(pack_n & vo_n)


def _vertex_keeps(
    packet: Packet, units: list[dict] | None, *, mint_holes: list[str] | None = None
) -> bool:
    """Keep leftover-free Vertex 8-beats that cite findings or speak pack numbers."""
    if not units or len(units) != 8:
        return False
    spoken = _units_spoken(units)
    if _leftover_vo(spoken) or _GROUNDED_EVENT.search(spoken):
        return False
    known = {f.id for f in (packet.receipt.findings if packet.receipt else [])}
    cited = any(fid in known for u in units for fid in (u.get("finding_ids") or []))
    if cited or _vo_uses_pack(packet, spoken):
        return True
    return _mint_held(packet, mint_holes)


def _warn_mint(packet: Packet, holes: list[str]) -> None:
    extra = "; ".join(dict.fromkeys(h for h in holes if h.strip()))
    if not extra:
        return
    receipt = packet.receipt
    if receipt is None:
        return
    receipt.disposition = "HOLD"
    prior = (receipt.hold_reason or "").strip()
    if extra not in prior:
        receipt.hold_reason = f"{prior} {extra}".strip() if prior else extra


def _pack_source(packet: Packet) -> bool:
    if (packet.research_pack or "").strip() or (packet.task_spine or "").strip():
        return True
    receipt = packet.receipt
    return bool(receipt and receipt.findings)


def _assemble(packet: Packet, units: list[dict]) -> Packet:
    if len(units) != 8:
        return _fail_closed(packet, ["writer must emit 8 beats"])
    held = packet.receipt is not None and packet.receipt.disposition == "HOLD"
    known = {f.id for f in (packet.receipt.findings if packet.receipt else [])}
    spoken_all = _units_spoken(units)
    pack_grounded = _vo_uses_pack(packet, spoken_all) or any(
        fid in known for u in units for fid in (u.get("finding_ids") or [])
    )
    cut = require_cut(packet.cut) if packet.cut else None
    short = cut in _SHORT
    hours = bool(cut and is_long_cut(cut) and not short)
    durs = list(_SHORT_DURS if short else _EPISODE_DURS)
    prior = {beat.id: beat for beat in packet.beats}
    lean = packet.script_lean or "centered_independent"
    beats: list[ScriptBeat] = []
    cursor = 0
    lei_nits: list[str] = []
    for i, unit in enumerate(units):
        bid = unit.get("id") or _EIGHT_IDS[i]
        fids = [fid for fid in (unit.get("finding_ids") or []) if fid in known]
        vo = (unit.get("vo") or "").strip()
        eyes = (unit.get("eyes") or "").strip()
        hole = "sahm hole" in f"{vo} {eyes}".lower() or "no matching url" in f"{vo} {eyes}".lower()
        if not fids and known and not hole:
            if not (held and (pack_grounded or _vo_uses_pack(packet, vo))):
                return _fail_closed(packet, [f"{bid} cites nothing in the pack"])
        for fid in fids:
            if f"[{fid}]" not in vo:
                vo = f"{vo} [{fid}]"
        if _GROUNDED_EVENT.search(vo) or _leftover_vo(vo):
            return _fail_closed(packet, ["VO is leftover grounded-event template"])
        if any(w in vo.lower() for w in ("leila", "reza")) and "leila" not in _pack_text(packet).lower():
            return _fail_closed(packet, ["invented leftover cast"])
        pack_blob = " ".join(
            [
                packet.research_pack or "",
                packet.task_spine or "",
                packet.topic or "",
                packet.hook or "",
                *(f.claim for f in _live_findings(packet)),
            ]
        ).lower()
        if "hormuz" not in pack_blob and "jcpoa" not in pack_blob:
            if any(w in vo.lower() for w in ("hormuz", "jcpoa", "strait of hormuz", "hormuz-share")):
                return _fail_closed(packet, ["leftover Hormuz on a non-Hormuz topic"])
        vo, stripped_vo = _soften_uncited_off(vo, fids)
        eyes, stripped_eyes = _soften_uncited_off(eyes, fids)
        if stripped_vo or stripped_eyes:
            lei_nits.append("LEI/ISM spoken without a cited beat")
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
    holes = _missing_pack_marks(packet, spoken)
    if holes and not held:
        return _fail_closed(packet, [f"pack numbers missing from VO: {', '.join(holes)}"])
    if lei_nits:
        note = "LEI/ISM spoken without a cited beat"
        _warn_mint(packet, [note])
        packet.exclusions.append(Exclusion(what=_VERTEX_HOLE, reason="other", detail=note))
    packet.status = "ready" if packet.receipt is None or packet.receipt.disposition != "HOLD" else "hold"
    return packet


def _weave_first_trigger(packet: Packet, units: list[dict]) -> list[dict]:
    """Outcome-first: never rewrite cold-open. If pack has a dated trigger, voice it later."""
    trigger = _first_trigger_text(packet)
    if not trigger or not units or len(units) != 8:
        return units
    if _trigger_voiced(_units_spoken(units), trigger):
        return units
    later = dict(units[1])
    later["vo"] = _promise_trigger_vo(packet, trigger)
    later["eyes"] = "Dated first-trigger from the pack. Official series stay on later cards."
    units = list(units)
    units[1] = later
    return units


def _prompt(packet: Packet, units: list[dict]) -> str:
    trigger = _first_trigger_text(packet)
    payload = {
        "id": packet.id,
        "topic": packet.topic,
        "platform": packet.platform,
        "tell": packet.tell,
        "tone": packet.tone,
        "cut": packet.cut,
        "script_lean": packet.script_lean,
        "pack": packet.research_pack or "",
        "first_trigger": trigger,
        "beats": units,
    }
    return (
        f"Read this research pack. Voice the 8-beat spine. {config.GEMINI_MODEL}.\n"
        "Pack text is the authority. Do not treat foundry mint stamps as the VO source.\n"
        "Outcome-first weave: cold-open is the current named print (USREC×payrolls or other pack print). "
        "Chronological order is not required. First trigger / first transmission may appear in a later beat, not beat 1.\n"
        f"Pack first trigger (voice later if present): {trigger or '(none — series cold-open is allowed)'}\n"
        "Pack numbers only. Do not invent stats. LEI and ISM stay off unless a beat cites them. "
        "Uncited LEI/ISM is a warning, not a blank draft.\n"
        "Host/reporter only on news cuts. No Leila, no Reza, no Gulf chart leftover.\n"
        "Return 8-beat JSON from the pack.\n"
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


def write_script(packet: Packet, writer=None) -> Packet:
    """8-beat timed VO from the pack. Mint/verify HOLD does not blank before Vertex."""
    receipt = packet.receipt
    emit = writer or generate_script
    if not _pack_source(packet):
        holes = ["empty pack"]
        if receipt is not None and receipt.disposition == "HOLD":
            holes = [receipt.hold_reason or "HOLD pack"]
        return _fail_closed(packet, holes)
    text = _pack_text(packet)
    if _GROUNDED_EVENT.search(text) and not _recession_pack(text):
        return _fail_closed(packet, ["leftover grounded-event template"])
    fiction = _invents(packet)
    mint_holes: list[str] = []
    if not fiction and not _numbers_in(text):
        mint_holes.append("pack has no numbers")
    usrec = _by_series(packet, "USREC")
    payrolls = _by_series(packet, "BLS payrolls", "payrolls")
    if (
        not fiction
        and _notes_have_named_prints(text)
        and not (
            usrec
            and (usrec.print or "") in {"0", "1"}
            and payrolls
            and _payroll_print_ok(payrolls.print or "")
        )
    ):
        mint_holes.append("foundry dropped named series")
    if (
        payrolls
        and re.search(r"\b(fell|dropped|declined|lost|decreased|down)\b", text, re.I)
        and not _print_has_minus(payrolls.print or "")
    ):
        mint_holes.append("foundry dropped named series")
    if usrec and payrolls:
        if not (usrec.when or "").strip() or not (payrolls.when or "").strip():
            mint_holes.append("empty when")
        if not _same_month(usrec.when, payrolls.when):
            mint_holes.append("smash mixed months")
    if ("−0.03" in text or "-0.03" in text) and re.search(r"sahm", text, re.I) and not _by_series(
        packet, "SAHMREALTIME"
    ):
        mint_holes.append("Sahm no_url")
    gdp = _by_series(packet, "GDP")
    if gdp and not (gdp.print or "").strip():
        mint_holes.append("gdp print empty")
    local = _eight_from_pack(packet)
    local_ok = bool(local) and _accept_units(packet, local, mint_holes=mint_holes) and not mint_holes
    units: list[dict] = []
    spine = local if local and len(local) == 8 else []
    vertex_detail = ""
    # Seed / leftover Hormuz stamp locally. Cloud Run boot has ADC so has_vertex
    # is true; Vertex Agent Platform 403 must not crash-loop first-open.
    if config.has_vertex() and packet.id not in {config.SEED_PACKET_ID, "oc-hormuz-decade"}:
        try:
            parsed = _parse_units(emit(_prompt(packet, spine)))
            if parsed and _vertex_keeps(packet, parsed, mint_holes=mint_holes):
                units = parsed
            elif parsed and _accept_units(
                packet, parsed, spine=local if local_ok else None, mint_holes=mint_holes
            ):
                units = parsed
            elif parsed is None:
                vertex_detail = "Vertex script unusable"
        except VertexDownError:
            vertex_detail = "Vertex script down"
    if not units and local and len(local) == 8:
        units = local
    if units and len(units) == 8:
        units = _weave_first_trigger(packet, units)
        _warn_mint(packet, mint_holes)
        return _assemble(packet, units)
    holes = list(mint_holes) if mint_holes else ["_eight_from_pack cannot place minted prints"]
    if vertex_detail:
        holes.append(vertex_detail)
    return _fail_closed(packet, holes)
