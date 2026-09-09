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
    r"USREC\s*=\s*0|\$\d[\d,]*(?:\.\d+)?\s*[BbMmKk]?|[-−+]?\d+(?:\.\d+)?\s*%|[-−]\d+\s*k|\b[-−]?\d+\.\d+\b|\b\d{1,4}\b",
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


def _hit_cite_blob(packet: Packet) -> str:
    """Parallel hit URL + excerpt/summary + stamped print. Topic/hook are not cites."""
    parts = [packet.research_pack or "", packet.task_spine or ""]
    receipt = packet.receipt
    if receipt:
        for finding in receipt.findings:
            if finding.parallel_status != "hit" or not (finding.parallel_url or "").strip():
                continue
            printed = "" if finding.print in {MISSING, "", None} else finding.print
            parts.extend(
                [
                    finding.parallel_url or "",
                    finding.claim or "",
                    finding.note or "",
                    printed,
                    finding.when or "",
                ]
            )
    return "\n".join(parts)


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
    "SAHMREALTIME": frozenset({"sahm", "sahm-june-2026", "sahm-july-2026", "sahm-august-2026"}),
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
    from onecrew.foundry import is_pack_slot_id

    for finding in receipt.findings:
        if finding.id in _LEFTOVER_IDS or is_pack_slot_id(finding.id):
            continue
        if finding.series in wanted or finding.id in ids:
            return finding
        if "SAHMREALTIME" in wanted and (finding.id or "").startswith("sahm-"):
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
    from onecrew.foundry import is_pack_slot_id

    rows = [
        f
        for f in receipt.findings
        if f.id not in _LEFTOVER_IDS
        and not is_pack_slot_id(f.id)
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
    from onecrew.foundry import is_pack_slot_id

    return [f for f in receipt.findings if f.id not in _LEFTOVER_IDS and not is_pack_slot_id(f.id)]


def _cite(finding: Finding | None) -> str:
    return f" [{finding.id}]" if finding else ""


def _link_pack_findings(vo: str, fids: list[str], findings: list[Finding]) -> list[str]:
    """Attach stamped finding ids whose print is spoken. Do not invent a cite."""
    from onecrew.foundry import complete_print, is_pack_slot_id, leftover_slot_ids, official_gdp_url
    from onecrew.timeline import spoken_match

    leftover = leftover_slot_ids()
    spoken = {re.sub(r"[^\d.]+", "", n.replace("−", "-")) for n in pack_numbers(vo)}
    out = [fid for fid in fids if not is_pack_slot_id(fid)]
    for finding in findings:
        if is_pack_slot_id(finding.id) or finding.id in leftover or finding.id in out:
            continue
        if finding.series == "GDP" and finding.stamp == "grounded" and not official_gdp_url(
            finding.parallel_url or ""
        ):
            continue
        if finding.stamp == "timeline_event":
            if spoken_match(vo, finding):
                out.append(finding.id)
            continue
        if finding.stamp != "grounded":
            continue
        if not complete_print(finding.print or ""):
            continue
        want = re.sub(r"[^\d.]+", "", (finding.print or "").replace("−", "-"))
        if want and want in spoken:
            out.append(finding.id)
    return out


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
    r"(January|February|March|April|May|June|July|August|September|October|November|December|"
    r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(\d{4})",
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


_MONTH_CANON = {
    "jan": "january",
    "january": "january",
    "feb": "february",
    "february": "february",
    "mar": "march",
    "march": "march",
    "apr": "april",
    "april": "april",
    "may": "may",
    "jun": "june",
    "june": "june",
    "jul": "july",
    "july": "july",
    "aug": "august",
    "august": "august",
    "sep": "september",
    "sept": "september",
    "september": "september",
    "oct": "october",
    "october": "october",
    "nov": "november",
    "november": "november",
    "dec": "december",
    "december": "december",
}


def _month_year(when: str) -> tuple[str, str] | None:
    match = _MONTH_YEAR.search(when or "")
    if not match:
        return None
    name = _MONTH_CANON.get(match.group(1).lower())
    if not name:
        return None
    return (name, match.group(2))


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


_USREC_WHEN_VO = re.compile(
    r"USREC\s*=\s*[01]\s*\(\s*("
    r"January|February|March|April|May|June|July|August|September|October|November|December"
    r")\s+(20\d{2})\s*\)",
    re.I,
)


def _vo_mixed_smash(packet: Packet, vo: str) -> bool:
    """True if VO claims a smash that pairs USREC when with a different payrolls month."""
    if not re.search(r"smash(?:ed)?\s+into", vo or "", re.I):
        return False
    payrolls = _by_series(packet, "BLS payrolls", "payrolls")
    usrec = _by_series(packet, "USREC")
    if payrolls and not (payrolls.when or "").strip():
        return True
    if usrec and payrolls and not _same_month(usrec.when, payrolls.when):
        return True
    spoken = _USREC_WHEN_VO.search(vo or "")
    if spoken and payrolls:
        return not _same_month(f"{spoken.group(1)} {spoken.group(2)}", payrolls.when)
    return False


def _beat_sahm_month_off(packet: Packet, vo: str) -> bool:
    """True if this beat cites a Sahm id and speaks a month other than finding.when."""
    sahm = _by_series(packet, "SAHMREALTIME")
    if not sahm or not (sahm.when or "").strip():
        return False
    if f"[{sahm.id}]" not in (vo or "") and not re.search(r"\[sahm-[^\]]+\]", vo or ""):
        return False
    stamp = _month_year(sahm.when)
    if stamp is None:
        return False
    return any(
        _month_year(match.group(0)) != stamp
        for match in _MONTH_YEAR.finditer(vo or "")
    )


def _units_sahm_month_off(packet: Packet, units: list[dict] | None) -> bool:
    return any(_beat_sahm_month_off(packet, u.get("vo") or "") for u in (units or []))


def _units_sahm_id_off(packet: Packet, units: list[dict] | None) -> bool:
    """True if VO cites a different Sahm id than the stamp while speaking the print."""
    sahm = _by_series(packet, "SAHMREALTIME")
    if not sahm or not (sahm.id or "").strip():
        return False
    want = f"[{sahm.id}]"
    printed = _print_of(sahm, "")
    p_n = (printed or "").replace("−", "-")
    for unit in units or []:
        vo = unit.get("vo") or ""
        if not re.search(r"\[sahm-[^\]]+\]", vo):
            continue
        if want in vo:
            continue
        vo_n = vo.replace("−", "-")
        if p_n and (p_n in vo_n or p_n.lstrip("+-") in vo_n):
            return True
    return False


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
    if sahm:
        printed = _print_of(sahm, "")
        if printed:
            have = printed in vlow or printed.replace("−", "-") in vlow.replace("−", "-")
            if not have:
                holes.append(f"Sahm {printed}")
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
    if _vo_mixed_smash(packet, spoken):
        return False
    if _units_sahm_month_off(packet, units):
        return False
    if _units_sahm_id_off(packet, units):
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
    sahm_when = (sahm.when or "").strip() if sahm else ""
    gdp_print = _print_of(gdp, "")
    gdp_vo, gdp_eyes = _gdp_lines(gdp_print)
    gdp_named = bool(gdp and gdp_print)
    gdp_fallback = gdp or usrec or sahm or payrolls
    trigger = _first_trigger_text(packet)
    if usrec and payrolls:
        labor = (
            f"Labor: payrolls {pay_print} and unemployment {unemp_print}. Named BLS."
            if unemp_print
            else f"Labor: payrolls {pay_print}. Named BLS."
        )
        if _same_month(usrec.when, payrolls.when):
            cold_vo = _voice(
                f"USREC={usrec_print} ({usrec_when}) smashed into payrolls {pay_print}."
                f"{_cite(usrec)}{_cite(payrolls)}",
                packet,
            )
            cold_eyes = f"USREC={usrec_print} and payrolls {pay_print} on screen. Official series cards only."
        else:
            cold_vo = _voice(
                f"USREC={usrec_print} ({usrec_when}). Labor: payrolls {pay_print}. Named BLS."
                f"{_cite(usrec)}{_cite(payrolls)}",
                packet,
            )
            cold_eyes = f"USREC={usrec_print} and payrolls {pay_print} on screen. Official series cards only."
        units = [
            {
                "id": "cold-open",
                "vo": cold_vo,
                "eyes": cold_eyes,
                "finding_ids": [f.id for f in (usrec, payrolls) if f],
            },
            {
                "id": "promise",
                "vo": (
                    _promise_trigger_vo(packet, trigger)
                    if trigger
                    else _voice(
                        (
                            "Three objects: the official call, the GDP prints, the Sahm alarm. "
                            if gdp_named
                            else "Three objects: the official call, the Sahm alarm. "
                        )
                        + "The title is a question we will not answer with a forecast.",
                        packet,
                    )
                ),
                "eyes": (
                    "Dated first-trigger from the pack. Official series stay on later cards."
                    if trigger
                    else (
                        "Three objects labeled: official call, GDP prints, Sahm alarm. No leftover map."
                        if gdp_named
                        else "Three objects labeled: official call, Sahm alarm. No leftover map."
                    )
                ),
                "finding_ids": [f.id for f in (usrec, gdp, sahm) if f],
            },
            {
                "id": "gdp",
                "vo": _voice(
                    (
                        f"{gdp_vo}{_cite(gdp)}"
                        if gdp_vo
                        else f"The official series stay on the cards.{_cite(gdp_fallback)}"
                    ),
                    packet,
                ),
                "eyes": (
                    gdp_eyes
                    if gdp_eyes
                    else "Official series cards only. New art, not a leftover map."
                ),
                "finding_ids": [gdp.id] if gdp else ([gdp_fallback.id] if gdp_fallback else []),
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
                        (
                            f"Turn: Sahm {sahm_print} in {sahm_when} vs the 0.50 trigger.{_cite(sahm)}"
                            if sahm_when
                            else f"Turn: Sahm {sahm_print} vs the 0.50 trigger.{_cite(sahm)}"
                        )
                        if sahm and sahm_print
                        else (
                            f"{(sahm.claim or '').strip()}{_cite(sahm)}"
                            if sahm and (sahm.claim or "").strip()
                            else "The official series stay on the cards."
                        )
                    ),
                    packet,
                ),
                "eyes": (
                    (
                        f"Sahm {sahm_print} in {sahm_when} vs 0.50 trigger."
                        if sahm_when
                        else f"Sahm {sahm_print} vs 0.50 trigger."
                    )
                    if sahm and sahm_print
                    else "Official series card. Named print only."
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
            and _same_month(first.when, second.when)
        )
        timeline_row = first is not None and (first.stamp or "") == "timeline_event"
        if smash_ok:
            smash = f"{first.series}={first.print} smashed into {second.series} {second.print}."
            eyes = f"{first.series}={first.print} and {second.series} {second.print} on screen. Official series cards only."
        elif timeline_row:
            smash = (first.claim or first.print or packet.tell or packet.topic or "").strip()
            eyes = "Cited event on screen."
        elif first and first.print not in {MISSING, "", None} and leftover_costume.isdisjoint({"hormuz", "jcpoa"}):
            smash = f"{first.series}={first.print}."
            eyes = f"{first.series}={first.print} on screen. Official series cards only."
        elif first:
            smash = (first.claim or packet.tell or packet.topic or "").strip()
            eyes = "Cited print on screen."
        else:
            smash = (packet.tell or packet.topic or "").strip()
            eyes = "Cited event on screen."
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
                    (
                        "The title is a question we will not answer with a forecast."
                        if timeline_row
                        else "Three objects from the pack. The title is a question we will not answer with a forecast."
                    ),
                    packet,
                )
            ),
            "eyes": (
                "Dated first-trigger from the pack. Official series stay on later cards."
                if trigger
                else ("Cited events on later cards." if timeline_row else "Three objects labeled from the pack.")
            ),
            "finding_ids": [first.id] if first else [],
        },
        {
            "id": "gdp",
            "vo": _voice(f"{(third or first).claim}{_cite(third)}" if (third or first) else smash, packet),
            "eyes": "New art from the cited print." if timeline_row else "New art from the cited print. Not a leftover map.",
            "finding_ids": [third.id] if third else [],
        },
        {
            "id": "labor",
            "vo": _voice(f"{(second or first).claim}{_cite(second or first)}" if (second or first) else smash, packet),
            "eyes": (
                f"Cited event: {(second or first).claim}."
                if timeline_row and (second or first)
                else (
                    f"Named official series: {(second or first).claim}. Official page only."
                    if (second or first)
                    else "Cited event on screen."
                )
            ),
            "finding_ids": [(second or first).id] if (second or first) else [],
        },
        {
            "id": "turn",
            "vo": _voice(
                (
                    (first.claim or "").strip() or "The cited event stays on the card."
                    if timeline_row
                    else (
                        f"{first.series}={first.print}."
                        if first and first.print not in {MISSING, "", None}
                        else "The official series stay on the cards."
                    )
                ),
                packet,
            ),
            "eyes": (
                "Cited event on screen."
                if timeline_row
                else (
                    f"{first.series}={first.print} on screen."
                    if first and first.print not in {MISSING, "", None}
                    else "Cited event on screen."
                )
            ),
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
            "vo": _voice(
                (
                    "Receipt board: cited events from the pack. Holes labeled."
                    if timeline_row
                    else "Receipt board: named series from the pack. Holes labeled."
                ),
                packet,
            ),
            "eyes": (
                "Receipt board. Cited events. Holes labeled."
                if timeline_row
                else "Receipt board. Named series. Holes labeled."
            ),
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
    cleaned = _tidy_vo(cleaned)
    if not cleaned:
        return "The named print stays on the card.", True
    return cleaned, True


def _tidy_vo(text: str) -> str:
    cleaned = re.sub(r"\s+", " ", text or "")
    cleaned = re.sub(r"\s+([,.;:])", r"\1", cleaned)
    cleaned = re.sub(r"\(\s*\)", "", cleaned)
    cleaned = re.sub(r"\[\s*\]", "", cleaned)
    return cleaned.strip(" ,.;:-")


def _map_brackets(text: str, fn) -> str:
    """Replace top-level [...] spans, including one nested index like field[7]."""
    src = text or ""
    out: list[str] = []
    i = 0
    n = len(src)
    while i < n:
        if src[i] != "[":
            out.append(src[i])
            i += 1
            continue
        depth = 0
        j = i
        closed = False
        while j < n:
            if src[j] == "[":
                depth += 1
            elif src[j] == "]":
                depth -= 1
                if depth == 0:
                    out.append(fn(src[i + 1 : j]))
                    i = j + 1
                    closed = True
                    break
            j += 1
        if not closed:
            out.append(src[i])
            i += 1
    return "".join(out)


# ponytail: snake_case in VO is a pack/spine field path, not a finding id.
# Ceiling: a sourced claim that literally uses snake_case. Upgrade: allowlist from pack prose.
_SNAKE_KEY = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+){1,}\b")
_RISK_TOPIC = re.compile(r"\b(tariffs?)\b", re.I)
_FINDING_LIKE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$", re.I)
_SCHEMA_MARK = re.compile(r"_|\[|\.")
_YEAR_TOK = re.compile(r"^20\d{2}$")
_PERSON_NAME = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b")
_ORG_WORD = frozenset(
    {
        "united",
        "states",
        "federal",
        "reserve",
        "white",
        "house",
        "conference",
        "board",
        "leading",
        "indicators",
        "nuclear",
        "deal",
        "strait",
        "real",
        "gross",
        "domestic",
    }
)


def _is_schema_slot(token: str) -> bool:
    """Spine/pack field path, not a finding id or a bracketed print."""
    return bool(_SCHEMA_MARK.search(token or ""))


def _vo_lines(text: str) -> str:
    """Drop timecode / shot-list chrome so duration digits are not spoken prints."""
    keep: list[str] = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if re.match(r"^\d{1,2}:\d{2}", stripped):
            continue
        if stripped.startswith(("ACTION:", "Timed VO", "BEAT ", "ACT ")):
            continue
        if stripped in {"WIDE", "MCU", "NARRATOR"}:
            continue
        keep.append(line)
    return "\n".join(keep)


def _trigger_chrome(tok: str, vo: str) -> bool:
    if not tok or not vo:
        return False
    return bool(re.search(rf"{re.escape(tok)}\s+trigger\b", vo, re.I))


def uncited_claim_tokens(packet: Packet, vo: str) -> list[str]:
    """Spoken prints with no Parallel cite / finding support. Fiction skips this bar."""
    from onecrew.verify import _bar_in, _bars

    if _invents(packet):
        return []
    evidence = _hit_cite_blob(packet)
    prints = [
        finding.print
        for finding in (packet.receipt.findings if packet.receipt else [])
        if finding.parallel_status == "hit"
        and (finding.parallel_url or "").strip()
        and finding.print not in {MISSING, "", None}
    ]
    body = _vo_lines(vo)
    bad: list[str] = []
    for tok in pack_numbers(body):
        cleaned = tok.replace("−", "-").strip()
        if _YEAR_TOK.fullmatch(cleaned) or _trigger_chrome(tok, body):
            continue
        if any(_bar_in(tok, bar) or _bar_in(bar, tok) for printed in prints for bar in _bars(printed)):
            continue
        if evidence and _bar_in(tok, evidence):
            continue
        bad.append(tok)
    return bad


def _strip_uncited_tokens(text: str, tokens: list[str]) -> str:
    out = text or ""
    for tok in sorted(set(tokens), key=len, reverse=True):
        out = re.sub(rf"(?<![\d.]){re.escape(tok)}(?![\d.])", "", out)
    return _tidy_vo(out) or "The named print stays on the card."


def _org_span(name: str) -> bool:
    return any(part.lower() in _ORG_WORD for part in name.split())


def _strip_pack_names(text: str, pack: str) -> tuple[str, bool]:
    """Fiction: drop real person-name spans that the pack already named."""
    names = sorted(set(_PERSON_NAME.findall(pack or "")), key=len, reverse=True)
    out = text or ""
    hit = False
    for name in names:
        if _org_span(name):
            continue
        nxt = re.sub(rf"\b{re.escape(name)}\b", "", out)
        if nxt == out:
            continue
        hit = True
        out = nxt
        for part in name.split():
            out = re.sub(rf"\b{re.escape(part)}\b", "", out)
    if not hit:
        return text or "", False
    cleaned = _tidy_vo(out)
    return cleaned or "The named print stays on the card.", True


_HOLD_META = re.compile(
    r"(?:GDP|Sahm)\s+hole\s+named\.?|"
    r"No matching URL\.?|"
    r"Hold on the (?:pack number|cite)\.?(?:\s+The spine chart stays\.?)?|"
    r"(?:The\s+)?spine chart stays\.?|"
    r"Hold\.\s*(?:The spine chart stays\.?|Chart stays\.?)?|"
    r"(?<![A-Za-z])Hold(?=\s*\.)",
    re.I,
)
_SPEAKABLE_FALLBACK = "The named print stays on the card."


_VO_CHROME = re.compile(
    r"official series cards only\.?|"
    r"three pack objects on screen\.?|"
    r"(?:new art,?\s+)?not a leftover map\.?|"
    r"no leftover map\.?",
    re.I,
)


def _strip_hold_meta(text: str) -> tuple[str, list[str]]:
    """Drop production/hold notes. Same class as pack slot-token strip."""
    cleaned, n = _HOLD_META.subn("", text or "")
    if not n:
        return text or "", []
    return cleaned, ["hold meta stripped from VO"]


def _strip_vo_chrome(text: str) -> tuple[str, list[str]]:
    cleaned, n = _VO_CHROME.subn("", text or "")
    if not n:
        return text or "", []
    return _tidy_vo(cleaned), ["leftover VO chrome stripped"]


_EXCERPT_TOKEN = re.compile(r"excerpts\[\d+\]", re.I)
_GDP_EQ_TRILLION = re.compile(r"\bGDP\s*=\s*\$?[\d,.]+\s*(?:trillion|tn)?", re.I)


def _sanitize_vo(text: str, known: set[str], pack_blob: str) -> tuple[str, list[str]]:
    """Strip pack schema/slot cites and hold-meta. Keep real finding ids."""
    from onecrew.foundry import is_pack_slot_id

    nits: list[str] = []

    def keep_or_drop(inner: str) -> str:
        token = (inner or "").strip()
        if is_pack_slot_id(token) or _EXCERPT_TOKEN.fullmatch(token):
            nits.append("pack slot token stripped from VO")
            return ""
        if token in known:
            return f"[{token}]"
        if _is_schema_slot(token) or _FINDING_LIKE.match(token):
            nits.append("pack slot token stripped from VO")
            return ""
        return f"[{token}]"

    cleaned = _map_brackets(text or "", keep_or_drop)

    def drop_snake(match: re.Match[str]) -> str:
        word = match.group(0)
        if word in known:
            return word
        nits.append("pack slot token stripped from VO")
        return ""

    cleaned = _SNAKE_KEY.sub(drop_snake, cleaned)
    pack_l = (pack_blob or "").lower()

    def drop_topic(match: re.Match[str]) -> str:
        word = match.group(0)
        if "tariff" in pack_l:
            return word
        nits.append(f"invented topic absent from pack: {word.lower()}")
        return ""

    cleaned = _RISK_TOPIC.sub(drop_topic, cleaned)
    if _EXCERPT_TOKEN.search(cleaned):
        cleaned = _EXCERPT_TOKEN.sub("", cleaned)
        nits.append("pack slot token stripped from VO")
    if _GDP_EQ_TRILLION.search(cleaned):
        cleaned = _GDP_EQ_TRILLION.sub("", cleaned)
        nits.append("junk GDP print stripped from VO")
    cleaned, meta_nits = _strip_hold_meta(cleaned)
    cleaned, chrome_nits = _strip_vo_chrome(cleaned)
    if not nits and not meta_nits and not chrome_nits:
        return text or "", []
    cleaned = _tidy_vo(cleaned)
    if not cleaned:
        cleaned = _SPEAKABLE_FALLBACK
    # ponytail: hold-meta/chrome is cleaned, not a HOLD nit. Slot/topic nits still warn.
    return cleaned, list(dict.fromkeys(nits))


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
    if _vo_mixed_smash(packet, spoken):
        return False
    if _units_sahm_month_off(packet, units):
        return False
    if _units_sahm_id_off(packet, units):
        return False
    if _missing_pack_marks(packet, spoken) and not _mint_held(packet, mint_holes):
        return False
    from onecrew.foundry import is_pack_slot_id

    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if not is_pack_slot_id(f.id)
    }
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


def _voice_stamped_marks(packet: Packet, units: list[dict]) -> list[dict]:
    """Speak stamped prints the cut asked for. Do not HOLD with a silent finding."""
    spoken = _units_spoken(units)
    holes = _missing_pack_marks(packet, spoken)
    if not holes:
        return units
    out = [dict(unit) for unit in units]
    by_id = {unit.get("id"): unit for unit in out}

    def _put(bid: str, line: str, finding: Finding | None) -> None:
        unit = by_id.get(bid)
        if unit is None:
            return
        unit["vo"] = _voice(f"{line}{_cite(finding)}", packet)
        if finding is None:
            return
        fids = list(unit.get("finding_ids") or [])
        if finding.id not in fids:
            fids.append(finding.id)
        unit["finding_ids"] = fids

    sahm = _by_series(packet, "SAHMREALTIME")
    if sahm and any(h.startswith("Sahm ") for h in holes):
        printed = _print_of(sahm, "")
        when = (sahm.when or "").strip()
        if printed:
            line = (
                f"Turn: Sahm {printed} in {when} vs the 0.50 trigger."
                if when
                else f"Turn: Sahm {printed} vs the 0.50 trigger."
            )
            _put("turn", line, sahm)
    pay = _by_series(packet, "BLS payrolls", "payrolls")
    if pay and any(h.startswith("payrolls ") for h in holes):
        printed = _print_of(pay, "")
        if printed:
            _put("labor", f"Labor: payrolls {printed}. Named BLS.", pay)
    usrec = _by_series(packet, "USREC")
    if usrec and any(h.startswith("USREC=") for h in holes):
        _put("cold-open", f"USREC={_print_of(usrec, '0')}.", usrec)
    gdp = _by_series(packet, "GDP")
    if gdp and any(h.startswith("GDP ") for h in holes):
        line, _eyes = _gdp_lines(_print_of(gdp, ""))
        if line:
            _put("gdp", line, gdp)
    return out


def _stamped_named_series(packet: Packet) -> set[str]:
    from onecrew.foundry import complete_print, is_pack_slot_id, official_gdp_url

    receipt = packet.receipt
    if not receipt:
        return set()
    out: set[str] = set()
    for finding in receipt.findings:
        if finding.stamp != "grounded" or is_pack_slot_id(finding.id):
            continue
        if not (finding.print or "").strip() or finding.print == MISSING:
            continue
        if not complete_print(finding.print or ""):
            continue
        if finding.series == "GDP" and not official_gdp_url(finding.parallel_url or ""):
            continue
        if finding.series:
            out.add(finding.series)
    return out


def _strip_unstamped_series_name(text: str, word: str) -> str:
    """Remove a series nickname that has no stamped print. No leftover comma pile."""
    blob = text or ""
    blob = re.sub(rf",?\s*the {word} prints,?", ",", blob, flags=re.I)
    blob = re.sub(rf"\b{word} prints\b,?", "", blob, flags=re.I)
    blob = re.sub(rf"\b{word}\b", "", blob, flags=re.I)
    blob = re.sub(r"\s+,", ",", blob)
    blob = re.sub(r",\s*,+", ",", blob)
    blob = re.sub(r"\s{2,}", " ", blob)
    return blob.strip(" ,")


def _assemble(packet: Packet, units: list[dict]) -> Packet:
    if len(units) != 8:
        return _fail_closed(packet, ["writer must emit 8 beats"])
    if _units_sahm_month_off(packet, units) or _units_sahm_id_off(packet, units):
        return _fail_closed(packet, ["sahm when print mismatch"])
    held = packet.receipt is not None and packet.receipt.disposition == "HOLD"
    if not held:
        units = _voice_stamped_marks(packet, units)
    from onecrew.foundry import is_pack_slot_id

    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if not is_pack_slot_id(f.id)
    }
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
    slot_nits: list[str] = []
    pack_blob = _pack_text(packet)
    cite_blob = _hit_cite_blob(packet)
    pack_l = pack_blob.lower()
    stamped = _stamped_named_series(packet)
    for i, unit in enumerate(units):
        bid = unit.get("id") or _EIGHT_IDS[i]
        fids = [fid for fid in (unit.get("finding_ids") or []) if fid in known]
        vo = (unit.get("vo") or "").strip()
        eyes = (unit.get("eyes") or "").strip()
        hole = "sahm hole" in f"{vo} {eyes}".lower() or "no matching url" in f"{vo} {eyes}".lower()
        if _GROUNDED_EVENT.search(vo) or _leftover_vo(vo):
            return _fail_closed(packet, ["VO is leftover grounded-event template"])
        if any(w in vo.lower() for w in ("leila", "reza")) and "leila" not in pack_l:
            return _fail_closed(packet, ["invented leftover cast"])
        if "hormuz" not in pack_l and "jcpoa" not in pack_l:
            if any(w in vo.lower() for w in ("hormuz", "jcpoa", "strait of hormuz", "hormuz-share")):
                return _fail_closed(packet, ["leftover Hormuz on a non-Hormuz topic"])
        vo, vo_nits = _sanitize_vo(vo, known, pack_blob)
        eyes, eye_nits = _sanitize_vo(eyes, known, pack_blob)
        if "GDP" not in stamped:
            vo = _strip_unstamped_series_name(vo, "gdp")
            eyes = _strip_unstamped_series_name(eyes, "gdp")
        slot_nits.extend(vo_nits)
        slot_nits.extend(eye_nits)
        if _invents(packet):
            vo, named_vo = _strip_pack_names(vo, cite_blob)
            eyes, named_eyes = _strip_pack_names(eyes, cite_blob)
            if named_vo or named_eyes:
                slot_nits.append("pack person name stripped from fiction VO")
        else:
            uncited_vo = uncited_claim_tokens(packet, vo)
            uncited_eyes = uncited_claim_tokens(packet, eyes)
            if uncited_vo:
                vo = _strip_uncited_tokens(vo, uncited_vo)
                slot_nits.append("uncited claim")
            if uncited_eyes:
                eyes = _strip_uncited_tokens(eyes, uncited_eyes)
                slot_nits.append("uncited claim")
        for fid in known:
            if f"[{fid}]" in vo and fid not in fids:
                fids.append(fid)
        if not _invents(packet):
            fids = _link_pack_findings(vo, fids, packet.receipt.findings if packet.receipt else [])
        if not fids and not hole:
            spoken_nums = [
                n
                for n in _numbers_in(_vo_lines(vo))
                if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
            ]
            sourced = bool(spoken_nums) or bool(_MONTH_YEAR.search(_vo_lines(vo)))
            if sourced and not (held and (pack_grounded or _vo_uses_pack(packet, vo))):
                slot_nits.append(f"{bid} cites nothing in the pack")
        for fid in fids:
            if f"[{fid}]" not in vo:
                vo = f"{vo} [{fid}]"
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
    if holes and not held and not _invents(packet):
        return _fail_closed(packet, [f"pack numbers missing from VO: {', '.join(holes)}"])
    warn = list(dict.fromkeys([*lei_nits, *slot_nits]))
    if warn:
        _warn_mint(packet, warn)
        packet.exclusions.append(Exclusion(what=_VERTEX_HOLE, reason="other", detail="; ".join(warn)))
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
        "Pack-faithful only. Pack text is the authority. Do not treat foundry mint stamps as the VO source.\n"
        "Never speak pack schema or slot ids (chronological_events, executive_summary, "
        "missing_causal_links, what_counts_as_the_first_trigger, [field[n]]). "
        "Finding cites stay only when they are real finding ids.\n"
        "Never speak production notes: Hold., GDP hole named, Sahm hole named, "
        "No matching URL, or the spine chart stays.\n"
        "Flexible weave: chronological OR outcome-first OR tell/tone stance "
        "(humor / disprove / question / facts-only). "
        "Outcome-first: cold-open is the current named print (USREC×payrolls or other pack print). "
        "Smash USREC into payrolls only when both share the same observation month. "
        "Never pair USREC when with a different payrolls month as a smash.\n"
        "First trigger / first transmission may appear in a later beat, not beat 1.\n"
        f"Pack first trigger (voice later if present): {trigger or '(none — series cold-open is allowed)'}\n"
        "Pack numbers only. Do not invent stats or topics absent from the pack. "
        "LEI and ISM stay off unless a beat cites them. "
        "Uncited LEI/ISM is a warning, not a blank draft.\n"
        "Nonfiction: nothing uncited from Parallel cites. "
        "Every sourced beat must attach real finding ids or pack cite URLs. "
        "Fiction: research is reference only; no real person names from the cites.\n"
        "Host/reporter only on news cuts. No Leila, no Reza, no Gulf chart leftover.\n"
        "Return 8-beat JSON from the pack.\n"
        f"{_PACKET_MARK}\n{json.dumps(payload, ensure_ascii=True)}\n{_PACKET_END}\n"
        f"PACK:\n{packet.research_pack or ''}\n"
        f"CITES:\n{_hit_cite_blob(packet)}\n"
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


def _hormuz_on_foreign(packet: Packet, vo: str) -> bool:
    pack_l = _pack_text(packet).lower()
    if "hormuz" in pack_l or "jcpoa" in pack_l:
        return False
    return any(w in (vo or "").lower() for w in ("hormuz", "jcpoa", "strait of hormuz", "hormuz-share"))


def write_script(packet: Packet, writer=None) -> Packet:
    """8-beat timed VO from the pack. Mint/verify HOLD does not blank before Vertex."""
    receipt = packet.receipt
    if receipt is not None and receipt.findings:
        from onecrew.foundry import align_sahm_findings

        receipt.findings = align_sahm_findings(
            list(receipt.findings),
            "\n".join([_pack_text(packet), *(f.claim or "" for f in receipt.findings)]),
        )
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
        and re.search(
            r"\b(fell|dropped|declined|lost|decreased|down)\b",
            payrolls.claim or "",
            re.I,
        )
        and not _print_has_minus(payrolls.print or "")
    ):
        mint_holes.append("foundry dropped named series")
    if usrec and payrolls:
        if not (usrec.when or "").strip() or not (payrolls.when or "").strip():
            mint_holes.append("empty when")
        from onecrew.verify import CiteBag, CiteExcerpt, smash_mixed_months

        bag = CiteBag(
            excerpts=[CiteExcerpt(url="", title="", text=_pack_text(packet))],
            spine=packet.task_spine or "",
        )
        spoken = "\n".join(
            [
                packet.script or "",
                usrec.claim or "",
                payrolls.claim or "",
                *(b.vo for b in packet.beats),
            ]
        )
        if smash_mixed_months(usrec.when or "", payrolls.when or "", bag, spoken=spoken):
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
            if parsed and _hormuz_on_foreign(packet, _units_spoken(parsed)):
                return _fail_closed(packet, ["leftover Hormuz on a non-Hormuz topic"])
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
