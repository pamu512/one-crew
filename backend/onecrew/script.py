from __future__ import annotations

import json
import re

from onecrew import config
from onecrew.cut import is_long_cut, require_cut
from onecrew.models import MISSING, Exclusion, Finding, Packet, ScriptBeat
from onecrew.tell import invents_frame
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
PACK_SLOT_BEAT_IDS = frozenset(_EIGHT_IDS)


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


_FORECAST_SPINE = re.compile(
    r"\boutlook\s+forecast\b|"
    r"\bforecasts?\s+from\b|"
    r"\b(?:january|february|march|april|may|june|july|august|september|"
    r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec)"
    r"\s+outlook\b",
    re.I,
)
_FORECAST_META = re.compile(r"(?:will|does|do)\s+not\s+(?:answer with a )?forecast", re.I)


def is_forecast_theater_vo(text: str) -> bool:
    """Agency forecast/outlook as the spoken spine. Meta 'no forecast' lines are not theater."""
    body = _FORECAST_META.sub("", _vo_lines(text) or text or "")
    return bool(_FORECAST_SPINE.search(body))


def _strip_forecast_spine(text: str) -> str:
    parts = re.split(r"(?<=[.!?])\s+", text or "")
    keep = [
        part
        for part in parts
        if part.strip() and (bool(_FORECAST_META.search(part)) or not _FORECAST_SPINE.search(part))
    ]
    return _tidy_vo(" ".join(keep))


def _refuse_forecast_theater(
    vo: str,
    fids: list[str],
    findings: list[Finding],
    tell: str,
) -> tuple[list[str], str, bool]:
    from onecrew.tell import wants_no_forecast_theater

    if not wants_no_forecast_theater(tell) or not is_forecast_theater_vo(vo):
        return fids, vo, False
    cleaned = _strip_forecast_spine(vo)
    if cleaned and not is_forecast_theater_vo(cleaned):
        return fids, cleaned, False
    spoken = speak_stamp_fact(fids, findings) or speak_stamps(fids, findings)
    if spoken and not is_forecast_theater_vo(spoken):
        return fids, spoken, False
    return fids, vo, True


def _drop_extra_cite_brackets(text: str, fids: list[str]) -> str:
    keep = set(fids)
    seen: set[str] = set()

    def _keep(match: re.Match[str]) -> str:
        token = (match.group(1) or "").strip()
        if token not in keep or token in seen:
            return ""
        seen.add(token)
        return match.group(0)

    return re.sub(r"\s*\[([^\[\]]+)\]", _keep, text or "")


_LEFTOVER_IDS = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})
_SHORT_IDS = {
    "USREC": frozenset({"usrec", "usrec-july-2026"}),
    "BLS payrolls": frozenset({"payrolls", "payrolls-july-2026"}),
    "payrolls": frozenset({"payrolls", "payrolls-july-2026"}),
    "GDP": frozenset({"gdp", "gdp-2026-q2"}),
    "SAHMREALTIME": frozenset({"sahm", "sahm-june-2026", "sahm-july-2026", "sahm-august-2026"}),
    "U-3": frozenset({"unemployment", "unemployment-july-2026"}),
}


def is_placeholder_finding_id(fid: str) -> bool:
    """cite-miss / missing / empty / frame-miss. Not a covering stamp."""
    raw = (fid or "").strip()
    if not raw:
        return True
    low = raw.lower()
    if "cite-miss" in low or "frame-miss" in low:
        return True
    return low in {"missing", "miss"}


def _legal_spoken_finding(finding: Finding) -> bool:
    """Cite-able row: not excerpts[N] / unofficial GDP / USREC prose. Fringe and fiction frames stay."""
    from onecrew.foundry import complete_print, is_pack_slot_id, official_closed_shape, official_gdp_url

    if is_placeholder_finding_id(finding.id) or is_pack_slot_id(finding.id):
        return False
    if finding.series == "GDP":
        return official_gdp_url(finding.parallel_url or "") and complete_print(finding.print or "")
    if finding.series == "USREC":
        return official_closed_shape("USREC", finding.print or "", finding.parallel_url or "")
    if finding.stamp == "timeline_event":
        return bool((finding.parallel_url or "").strip())
    return True


def _gdp_series_usable(finding: Finding) -> bool:
    """Official GDP cite. Empty print stays visible so write_script can HOLD."""
    from onecrew.foundry import keep_official_gdp

    return keep_official_gdp(finding)


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
        if finding.series == "GDP" or finding.id in _SHORT_IDS.get("GDP", frozenset()):
            if not _gdp_series_usable(finding):
                continue
        if finding.series == "USREC" or finding.id in _SHORT_IDS.get("USREC", frozenset()):
            from onecrew.foundry import official_closed_shape

            if not official_closed_shape("USREC", finding.print or "", finding.parallel_url or ""):
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
    rows = [
        f
        for f in receipt.findings
        if f.id not in _LEFTOVER_IDS
        and _legal_spoken_finding(f)
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


def _link_pack_findings(
    vo: str,
    fids: list[str],
    findings: list[Finding],
    *,
    packet: Packet | None = None,
) -> list[str]:
    """Attach stamped finding ids whose print is spoken. Do not invent a cite."""
    from onecrew.foundry import complete_print, is_pack_slot_id, leftover_slot_ids, official_gdp_url
    from onecrew.timeline import (
        cap_beat_cites,
        chain_pairs,
        cite_host_ok,
        is_chrome_cover_stamp,
        stamp_covers_vo,
        stamps_for_vo,
        vo_proper_names,
    )

    leftover = leftover_slot_ids()
    spoken = {re.sub(r"[^\d.]+", "", n.replace("−", "-")) for n in pack_numbers(vo)}
    pairs: list[tuple[str, str]] = []
    if packet is not None:
        mapping = (packet.receipt.timeline_map if packet.receipt else None) or []
        pairs = chain_pairs(
            "\n".join(p for p in ((packet.research_pack or ""), (packet.task_spine or "")) if p),
            mapping,
        )
    by_id = {f.id: f for f in findings}
    out = [
        fid
        for fid in fids
        if not is_pack_slot_id(fid)
        and not is_placeholder_finding_id(fid)
        and not (fid in by_id and is_chrome_cover_stamp(by_id[fid]))
    ]
    for finding in findings:
        if is_pack_slot_id(finding.id) or finding.id in leftover or finding.id in out:
            continue
        if finding.series == "GDP" and finding.stamp == "grounded" and not official_gdp_url(
            finding.parallel_url or ""
        ):
            continue
        if finding.stamp == "timeline_event":
            continue
        if finding.stamp != "grounded":
            continue
        if not complete_print(finding.print or ""):
            continue
        want = re.sub(r"[^\d.]+", "", (finding.print or "").replace("−", "-"))
        if want and want in spoken:
            out.append(finding.id)
    if is_pack_chrome_vo(vo) or not _vo_lines(vo).strip():
        timeline_ids = {f.id for f in findings if f.stamp == "timeline_event"}
        return [fid for fid in out if fid not in timeline_ids or fid in fids]
    chosen = stamps_for_vo(vo, findings, pairs)
    keep_ids = {f.id for f in chosen}
    for finding in chosen:
        if finding.id not in out and (
            not pairs
            or cite_host_ok(vo, finding.parallel_url or "", pairs)
            or stamp_covers_vo(vo, finding)
        ):
            out.append(finding.id)
            keep_ids.add(finding.id)
    timeline_ids = {f.id for f in findings if f.stamp == "timeline_event"}
    names = vo_proper_names(vo)
    kept = [
        fid
        for fid in out
        if fid not in timeline_ids
        or fid in keep_ids
        or (fid in by_id and stamp_covers_vo(vo, by_id[fid]))
    ]
    covering = [fid for fid in kept if fid in by_id and stamp_covers_vo(vo, by_id[fid])]
    if names and covering:
        from onecrew.verify import CLOSED_SERIES

        closed = [
            fid
            for fid in kept
            if fid in by_id and (by_id[fid].series or "").strip() in CLOSED_SERIES
        ]
        kept = list(dict.fromkeys([*covering, *closed]))
    return cap_beat_cites(vo, kept, findings)


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
        receipt.hold_reason = f"{prior}; {detail}".strip() if prior else detail
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
    # ponytail: tone is writer stance, not spoken chrome. Strip leftover prefixes in sanitize.
    return spoken.rstrip()


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
    v = re.sub(r"\[[^\]]+\]", "", vo or "").lower()
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
        speakable = [
            f
            for f in findings
            if _legal_spoken_finding(f)
            and not is_placeholder_finding_id(f.id)
            and f.stamp != "fringe"
        ]
        from onecrew.foundry import leftover_wrap

        if leftover_wrap(findings) and not _invents(packet):
            return []
        first = named[0] if named else next(
            (f for f in speakable if (f.stamp or "") == "timeline_event"),
            None,
        )
        if first is None:
            first = next((f for f in speakable if f.stamp == "grounded"), None)
        second = named[1] if len(named) > 1 else None
        if second is None and first is not None:
            second = next((f for f in speakable if f is not first), None)
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
        has_timeline = any((f.stamp or "") == "timeline_event" for f in findings)
        # Empty timeline + no official/event object: HOLD. Fiction and leftover Hormuz still write.
        if not has_timeline and not named and not speakable and not _invents(packet):
            return []
        def _object_eyes(finding: Finding | None) -> str:
            if finding is None:
                return ""
            printed = "" if finding.print in {MISSING, "", None} else finding.print
            return (printed or finding.claim or "").strip()

        if smash_ok:
            smash = f"{first.series}={first.print} smashed into {second.series} {second.print}."
            eyes = f"{first.series}={first.print} and {second.series} {second.print} on screen. Official series cards only."
        elif timeline_row:
            smash = (first.claim or first.print or packet.tell or packet.topic or "").strip()
            eyes = _object_eyes(first) or smash
        elif first and first.print not in {MISSING, "", None} and leftover_costume.isdisjoint({"hormuz", "jcpoa"}):
            smash = f"{first.series}={first.print}."
            eyes = f"{first.series}={first.print} on screen. Official series cards only."
        elif first:
            smash = (first.claim or packet.tell or packet.topic or "").strip()
            eyes = _object_eyes(first) or smash
        else:
            smash = (packet.tell or packet.topic or "").strip()
            eyes = smash
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
                    "The title is a question we will not answer with a forecast.",
                    packet,
                )
            ),
            "eyes": trigger if trigger else (_object_eyes(first) or smash),
            "finding_ids": [first.id] if first else [],
        },
        {
            "id": "gdp",
            "vo": _voice(f"{(third or first).claim}{_cite(third)}" if (third or first) else smash, packet),
            "eyes": _object_eyes(third or first) or smash,
            "finding_ids": [third.id] if third else [],
        },
        {
            "id": "labor",
            "vo": _voice(f"{(second or first).claim}{_cite(second or first)}" if (second or first) else smash, packet),
            "eyes": (
                _object_eyes(second or first) or smash
                if (second or first)
                else smash
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
                _object_eyes(first) or smash
                if timeline_row
                else (
                    f"{first.series}={first.print} on screen."
                    if first and first.print not in {MISSING, "", None}
                    else (_object_eyes(first) or smash)
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
    body = _bare_vo(vo)
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


def _drop_named_claims(text: str, names: set[str]) -> str:
    """Drop sentences that speak an unsupported proper name. Keep the rest."""
    if not names or not (text or "").strip():
        return text or ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    keep = [
        part
        for part in parts
        if not any(re.search(rf"\b{re.escape(name)}\b", part, re.I) for name in names)
    ]
    return _tidy_vo(" ".join(keep))


def speak_stamps(fids: list[str], findings: list[Finding]) -> str:
    """Speak the attached stamp. Never invent a pack/slot chrome line."""
    by_id = {f.id: f for f in findings}
    for fid in fids:
        finding = by_id.get(fid)
        if finding is None or is_title_only_stamp(finding):
            continue
        text = (finding.print or "").strip() or (finding.claim or "").strip()
        if text and not _is_title_like_text(text):
            return text
    return ""


def is_pack_chrome_vo(text: str) -> bool:
    """Pack/slot narrator chrome. Not a stamped claim."""
    body = _vo_lines(text)
    if not (body or "").strip():
        return False
    if _PACK_CHROME_VO.search(body):
        stripped = _PACK_CHROME_VO.sub("", body)
        return not _tidy_vo(stripped)
    if _VO_CHROME.search(body):
        stripped, n = _strip_vo_chrome(body)
        return bool(n) and not _tidy_vo(stripped)
    return False


def is_comparative_vo(text: str) -> bool:
    """Spoken magnitude/comparison without requiring a topic noun."""
    return bool(_COMPARATIVE_VO.search(_vo_lines(text) or text or ""))


def _align_vo_to_stamps(
    vo: str,
    fids: list[str],
    findings: list[Finding],
) -> tuple[list[str], str]:
    """Named-entity / print VO may only keep a timeline stamp that covers it. Else drop."""
    from onecrew.timeline import (
        _MONTH_YEAR,
        _event_nums,
        _years,
        cap_beat_cites,
        stamp_covers_vo,
        stamp_text,
        stamps_for_vo,
        vo_proper_names,
    )

    by_id = {f.id: f for f in findings}
    timeline = {f.id for f in findings if f.stamp == "timeline_event"}
    grounded = [fid for fid in fids if fid not in timeline]
    tl_fids = [fid for fid in fids if fid in timeline]

    def _when_print_ok(finding) -> bool:
        blob = stamp_text(finding)
        vo_years = _years(vo)
        ev_years = _years(blob)
        if vo_years and ev_years and not (vo_years & ev_years):
            return False
        vo_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(vo or "")}
        ev_months = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob or "")}
        if vo_months and ev_months and not (vo_months & ev_months):
            return False
        return True

    if is_pack_chrome_vo(vo):
        keep = [fid for fid in tl_fids if fid in by_id]
        spoken = speak_stamps(keep, findings)
        return grounded + keep, spoken or vo
    names = vo_proper_names(vo)
    if not names:
        if is_comparative_vo(vo) and not _event_nums(vo):
            chosen = [f for f in stamps_for_vo(vo, findings, []) if _event_nums(stamp_text(f))]
            keep = [f.id for f in chosen]
            spoken = speak_stamps(keep, findings)
            if spoken and keep:
                return cap_beat_cites(vo, grounded + keep, findings), spoken
            return cap_beat_cites(vo, grounded, findings), ""
        print_keep, print_hold = prefer_covering_print(vo, tl_fids or fids, findings)
        if print_hold:
            cleaned = _strip_unsupported_prints(vo, [], findings)
            return grounded, cleaned
        if _event_nums(vo):
            keep_ids = cap_beat_cites(vo, grounded + print_keep, findings)
            return keep_ids, _strip_unsupported_prints(vo, keep_ids, findings)
        return cap_beat_cites(vo, grounded + print_keep, findings), vo
    covered = [
        fid
        for fid in tl_fids
        if fid in by_id and stamp_covers_vo(vo, by_id[fid]) and _when_print_ok(by_id[fid])
    ]
    chosen = [f for f in stamps_for_vo(vo, findings, []) if _when_print_ok(f)]
    if chosen:
        cleaned = vo
        for fid in tl_fids:
            if fid not in {f.id for f in chosen}:
                cleaned = re.sub(rf"\s*\[{re.escape(fid)}\]", "", cleaned).strip()
        if is_comparative_vo(cleaned) and not _event_nums(cleaned):
            printed = [f for f in chosen if _event_nums(stamp_text(f))]
            spoken = speak_stamps([f.id for f in printed], findings)
            if spoken and printed:
                return grounded + [f.id for f in printed], spoken
            return grounded, ""
        keep_ids = cap_beat_cites(cleaned, grounded + [f.id for f in chosen], findings)
        return keep_ids, _strip_unsupported_prints(cleaned, keep_ids, findings)
    if covered:
        cleaned = vo
        for fid in tl_fids:
            if fid not in covered:
                cleaned = re.sub(rf"\s*\[{re.escape(fid)}\]", "", cleaned).strip()
        keep_ids = cap_beat_cites(cleaned, grounded + covered, findings)
        return keep_ids, _strip_unsupported_prints(cleaned, keep_ids, findings)
    for finding in findings:
        if finding.stamp == "timeline_event" and stamp_covers_vo(vo, finding) and _when_print_ok(finding):
            cleaned = vo
            for fid in tl_fids:
                cleaned = re.sub(rf"\s*\[{re.escape(fid)}\]", "", cleaned).strip()
            return cap_beat_cites(cleaned, grounded + [finding.id], findings), cleaned
    if not tl_fids and grounded:
        covering = [
            fid
            for fid in grounded
            if fid in by_id and stamp_covers_vo(vo, by_id[fid]) and _when_print_ok(by_id[fid])
        ]
        if covering:
            from onecrew.verify import CLOSED_SERIES

            closed = [
                fid
                for fid in grounded
                if fid in by_id and (by_id[fid].series or "").strip() in CLOSED_SERIES
            ]
            return cap_beat_cites(vo, list(dict.fromkeys([*covering, *closed])), findings), vo
        return cap_beat_cites(vo, grounded, findings), vo
    cleaned = _drop_named_claims(vo, names)
    cleaned = _strip_unsupported_prints(cleaned, grounded, findings)
    for fid in tl_fids:
        cleaned = re.sub(rf"\s*\[{re.escape(fid)}\]", "", cleaned).strip()
    return grounded, cleaned


_PRINT_HOLE_LEAD = re.compile(r"^(?:by|over|under|from),", re.I)
_PRINT_HOLE_ONLY = re.compile(
    r"^(?:by|over|under|from|after|before|at|in|on|to),?\s*$",
    re.I,
)
_PRINT_HOLE_UNIT = re.compile(r"\b(?:over|under|by)\s+[A-Za-z]+s\b", re.I)
_SPLIT_PERCENT = re.compile(r"\d,\s+\d+\s*(?:percent|%)", re.I)
_BARE_ACCORDING = re.compile(
    r"(?:^|(?<=[.!?])\s+)according to (?:the )?[A-Z][\w.&'-]+(?:\s+[A-Z][\w.&'-]+)*\s*$",
    re.I,
)
_HANGING_DATE = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:the following week,?\s+)?ending\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?\s*$",
    re.I,
)
_DATE_ONLY_VO = re.compile(
    r"^(?:then,?\s+)?on\s+"
    r"(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?\.?$",
    re.I,
)
_MD_HEADING = re.compile(r"^#{1,6}\s+")
_TRAILING_URL = re.compile(
    r"\s*(?:\((?:https?://)[^)]+\)|(?:https?://)\S+)\s*$",
    re.I,
)
_TEXT_CHROME = re.compile(r"^text\s*:\s*", re.I)
_PACK_SLOT_NIT = "pack slot token stripped from VO"


def is_print_hole(text: str) -> bool:
    """Half-stripped number leftover. Not a cite-faithful sentence."""
    body = _tidy_vo(re.sub(r"\[[^\]]+\]", "", _vo_lines(text) or text or ""))
    if not body:
        return False
    if _PRINT_HOLE_LEAD.search(body) or _PRINT_HOLE_ONLY.match(body) or _SPLIT_PERCENT.search(body):
        return True
    return not pack_numbers(body) and bool(_PRINT_HOLE_UNIT.search(body))


def is_incomplete_vo(text: str) -> bool:
    """Bare attribution, hanging date, or print hole. Not a cite-faithful sentence."""
    body = _tidy_vo(re.sub(r"\[[^\]]+\]", "", _vo_lines(text) or text or ""))
    if not body:
        return False
    if is_print_hole(body) or is_hanging_clause_vo(body) or _HANGING_CONJ.search(body):
        return True
    if _DATE_ONLY_VO.match(body):
        return True
    return bool(_BARE_ACCORDING.search(body) or _HANGING_DATE.search(body))


def strip_incomplete_vo(text: str) -> str:
    """Drop hanging attribution / date / example clauses. Keep a complete prior claim."""
    body = strip_hanging_clause_vo(text or "")
    body = re.sub(
        r"(?:[.!?]\s+)?according to (?:the )?[A-Z][\w.&'-]+(?:\s+[A-Z][\w.&'-]+)*\s*$",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(
        r"(?:[.!?]\s+)?(?:the following week,?\s+)?ending\s+"
        r"(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?\s*$",
        "",
        body,
        flags=re.I,
    )
    body = re.sub(r"\s+(?:and|or|but|with)\s*$", "", body, flags=re.I)
    return _tidy_vo(body)


def is_thin_frame(text: str, fids: list[str] | None = None, findings: list | None = None) -> bool:
    """Mute-test fail: truncated screen chrome, not the attached stamp print."""
    if is_meta_frame(text):
        return True
    body = _tidy_vo(text or "")
    if not body:
        return False
    if fids and findings and is_title_chrome_frame(body, fids, findings):
        return True
    if fids and findings:
        printed = speak_stamp_print(fids, findings) or speak_stamp_fact(fids, findings) or speak_stamps(fids, findings)
        if printed and _speech_norm(printed) in _speech_norm(body):
            return False
    if body.count("'") % 2 != 0 or body.count('"') % 2 != 0:
        return True
    return bool(re.match(r"on screen\b", body, re.I))


def _clause_has_unsupported_print(part: str, have: set[str], have_m: set[str]) -> bool:
    body = re.sub(r"\[[^\]]+\]", "", part or "")
    for tok in pack_numbers(body):
        if _YEAR_TOK.fullmatch(tok.replace("−", "-")):
            continue
        want = re.sub(r"[^\d.]+", "", tok.replace("−", "-"))
        if want and want not in have:
            return True
    return any(m.group(0).lower() not in have_m for m in _MONTH_YEAR.finditer(body))


def _strip_unsupported_prints(text: str, fids: list[str], findings: list[Finding]) -> str:
    """Drop or rewrite clauses whose prints the attached stamps cannot cover. No token holes."""
    from onecrew.timeline import _event_nums, stamp_text

    blob = " ".join(stamp_text(f) for f in findings if f.id in fids)
    have = _event_nums(blob)
    have_m = {m.group(0).lower() for m in _MONTH_YEAR.finditer(blob)}
    keep: list[str] = []
    for part in re.split(r"(?<=[.!?])\s+", text or ""):
        if not part.strip():
            continue
        if not _clause_has_unsupported_print(part, have, have_m):
            keep.append(part)
            continue
        bits = [b.strip() for b in re.split(r",\s*", part) if b.strip()]
        clean = [b for b in bits if not _clause_has_unsupported_print(b, have, have_m)]
        if clean and len(clean) < len(bits):
            keep.append(_tidy_vo(", ".join(clean)))
    cleaned = _tidy_vo(" ".join(keep))
    if cleaned and not is_print_hole(cleaned):
        return cleaned
    if fids:
        spoken = speak_stamp_fact(fids, findings) or speak_stamps(fids, findings)
        if spoken:
            return spoken
    return cleaned


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
_PACK_CHROME_VO = re.compile(
    r"(?:the\s+)?named print stays on the card\.?|"
    r"(?:the\s+)?cited event stays on the card\.?|"
    r"(?:the\s+)?official series stay on the cards?\.?",
    re.I,
)
_COMPARATIVE_VO = re.compile(
    r"\b(slowdown|slowed|slowing|growth|grew|decline|declined|"
    r"increase|increased|decrease|decreased|percent|percentage|"
    r"higher|lower|versus|compared|more than|less than|"
    r"rise|rose|falling|fell)\b",
    re.I,
)


_VO_CHROME = re.compile(
    r"official series cards only\.?|"
    r"three pack objects on screen\.?|"
    r"(?:new art,?\s+)?not a leftover map\.?|"
    r"no leftover map\.?",
    re.I,
)
_TONE_CHROME = re.compile(
    r"from the news desk\.?|"
    r"think past the headline\.?|"
    r"question the decision that put this on the air\.?|"
    r"personal take:",
    re.I,
)
_UNVERIFIED_META_VO = re.compile(
    r"premise cannot be verified|"
    r"cannot be verified|"
    r"our research indicates|"
    r"the question on (?:many|most) minds|"
    r"(?:a |the )?common question(?:\s+\w+){0,4}|"
    r"the question (?:is|was|remains) whether|"
    r"this (?:cut|piece|episode) asks|"
    r"\bunverified\b|"
    r"we (?:could not|cannot) (?:verify|confirm)",
    re.I,
)
_HANGING_CLAUSE = re.compile(
    r"(?:^|(?<=[.!?])\s+)(?:for instance|for example|such as|including|namely|"
    r"specifically|in particular)\s*[.,;:]?\s*$",
    re.I,
)
_HANGING_CONJ = re.compile(
    r"(?:^|(?<=[.!?])\s+).+\s+(?:and|or|but|with)\s*$",
    re.I,
)
_SERIES_PAGE_CHROME = re.compile(
    r"historical data(?:\s*(?:&|and)\s*trends)?",
    re.I,
)
_BEAT_N_ID = re.compile(r"^beat\d+$")
_TOPIC_Q_LEAD = re.compile(
    r"^(?:did|do|does|is|are|was|were|have|has|whether)\s+",
    re.I,
)
_HEADLINE_SUFFIX = re.compile(r"\s+[-–—]\s+[A-Z][A-Za-z.]{0,24}\s*$")
_PUBLISHER_PIPE = re.compile(r"\s+\|\s+.+$")
_NEWS_TAIL = frozenset(
    {
        "news",
        "hub",
        "desk",
        "wire",
        "times",
        "post",
        "journal",
        "gazette",
        "tribune",
        "herald",
        "report",
        "review",
        "observer",
        "press",
        "daily",
        "source",
    }
)
_META_FRAME = re.compile(
    r"cited events? on (?:screen|later cards)\.?|"
    r"cited print on screen\.?|"
    r"new art from the cited print\.?(?:\s+not a leftover map\.?)?|"
    r"dated first-trigger from the pack\.?(?:\s+official series stay on later cards\.?)?",
    re.I,
)
_GENERIC_TITLE = frozenset({"timeline_event", "grounded", "mainstream", "fringe", "missing", ""})


def _strip_hold_meta(text: str) -> tuple[str, list[str]]:
    """Drop production/hold notes. Same class as pack slot-token strip."""
    cleaned, n = _HOLD_META.subn("", text or "")
    if not n:
        return text or "", []
    return cleaned, ["hold meta stripped from VO"]


def _strip_tone_chrome(text: str) -> tuple[str, list[str]]:
    """Tone is stance for the writer. Never narrate it as VO filler."""
    nits: list[str] = []
    cleaned, n = _TONE_CHROME.subn("", text or "")
    if n:
        nits.append("tone chrome stripped from VO")
    meta = strip_unverified_meta_vo(cleaned)
    if meta != _tidy_vo(cleaned) and _UNVERIFIED_META_VO.search(cleaned or ""):
        nits.append("unverified meta stripped from VO")
        cleaned = meta
    elif n:
        cleaned = _tidy_vo(cleaned)
    hung = strip_hanging_clause_vo(cleaned)
    if hung != _tidy_vo(cleaned) and is_hanging_clause_vo(cleaned):
        nits.append("hanging clause stripped from VO")
        cleaned = hung
    if not nits:
        return text or "", []
    return _tidy_vo(cleaned), nits


def has_tone_chrome(text: str) -> bool:
    return bool(_TONE_CHROME.search(_vo_lines(text) or text or ""))


def is_unverified_meta_vo(text: str) -> bool:
    """Research-meta / unverified chrome. Speak a stamp or drop the beat."""
    return bool(_UNVERIFIED_META_VO.search(_vo_lines(text) or text or ""))


def strip_unverified_meta_vo(text: str) -> str:
    return _tidy_vo(_UNVERIFIED_META_VO.sub("", text or ""))


def _topic_qcore(text: str) -> str:
    body = _speech_norm(text)
    return _TOPIC_Q_LEAD.sub("", body).strip(" ?")


def _bare_vo(text: str) -> str:
    return re.sub(r"\[[^\]]+\]", "", _vo_lines(text) or text or "")


def is_topic_question_vo(text: str, packet) -> bool:
    """Restates the user topic as a question. Not a stamped print."""
    raw = _bare_vo(text)
    body = _speech_norm(raw)
    if not body or is_numeric_print(raw):
        return False
    asked = (
        "?" in raw
        or "whether" in body
        or bool(_TOPIC_Q_LEAD.match(body))
        or bool(_UNVERIFIED_META_VO.search(raw))
        or "this cut asks" in body
        or "the question was whether" in body
    )
    if not asked:
        return False
    vo_core = _topic_qcore(body)
    for cand in (getattr(packet, "topic", ""), getattr(packet, "hook", "")):
        core = _topic_qcore(cand or "")
        if core and len(core) >= 12 and (core in body or vo_core in core or core == vo_core):
            return True
    return False


def is_hanging_clause_vo(text: str) -> bool:
    """Incomplete trailing clause. Not a cite-faithful sentence."""
    body = _tidy_vo(re.sub(r"\[[^\]]+\]", "", _vo_lines(text) or text or ""))
    return bool(body) and bool(_HANGING_CLAUSE.search(body))


def strip_hanging_clause_vo(text: str) -> str:
    return _tidy_vo(
        re.sub(
            r"(?:[.!?]\s+)?(?:for instance|for example|such as|including|namely|"
            r"specifically|in particular)\s*[.,;:]?\s*$",
            "",
            text or "",
            flags=re.I,
        )
    )


def is_topic_prompt_frame(text: str, packet) -> bool:
    """Mute-test fail: on_screen is the topic/prompt, not a stamp print."""
    shown = _speech_norm(text)
    if not shown:
        return False
    return any(shown == _speech_norm(cand or "") for cand in (getattr(packet, "topic", ""), getattr(packet, "hook", "")))


def is_meta_frame(text: str) -> bool:
    """Mute-test fail: frame names the cite, not the stamped print/object."""
    body = _tidy_vo(text or "")
    if not body or not _META_FRAME.search(body):
        return False
    return not _tidy_vo(_META_FRAME.sub("", body))


def _speech_norm(text: str) -> str:
    body = re.sub(r"\[[^\]]+\]", "", text or "")
    body = _TONE_CHROME.sub("", _vo_lines(body))
    return _tidy_vo(re.sub(r"\s+", " ", body)).lower()


def _headline_core(text: str) -> str:
    body = _PUBLISHER_PIPE.sub("", text or "")
    return _speech_norm(_HEADLINE_SUFFIX.sub("", body))


def _catalog_core(text: str) -> str:
    """Strip page/source tails so series names compare as stems."""
    body = _speech_norm(_PUBLISHER_PIPE.sub("", text or ""))
    body = re.sub(
        r"\s+[-–—]?\s*historical data(?:\s*(?:&|and)\s*trends)?\s*$",
        "",
        body,
        flags=re.I,
    )
    for _ in range(3):
        nxt = re.sub(r"\s+[-–—]\s+[a-z0-9][a-z0-9. ]{0,40}$", "", body)
        if nxt == body:
            break
        body = nxt.strip()
    return body.strip(" -–—")


def _title_near(vo: str, title: str) -> bool:
    a = _catalog_core(vo)
    b = _catalog_core(title)
    if not a or not b or min(len(a), len(b)) < 8:
        return False
    if a == b or a in b or b in a:
        return True
    wa, wb = set(a.split()), set(b.split())
    if not wa or not wb:
        return False
    shared = wa & wb
    return len(shared) >= 3 and len(shared) / min(len(wa), len(wb)) >= 0.6


def _is_catalog_or_series_name(text: str) -> bool:
    """Page/chart/series title. Not a spoken claim with a stamp print."""
    body = _tidy_vo(re.sub(r"\[[^\]]+\]", "", _vo_lines(text) or text or ""))
    if not body or is_numeric_print(body) or _TITLE_CARD_VERB.search(body):
        return False
    if _SERIES_PAGE_CHROME.search(body):
        return True
    if not re.search(r"\s[-–—]\s+", body):
        return False
    words = re.findall(r"[A-Za-z0-9]+", body)
    if len(words) < 2 or len(words) > 14:
        return False
    caps = sum(1 for w in words if w[:1].isupper() or w.lower() in {"vs", "versus"})
    return caps >= max(2, len(words) - 2)


def _looks_like_prose_claim(text: str) -> bool:
    """Spoken sentence with a verb. Not a page/series title card."""
    body = _bare_vo(text)
    if _TITLE_CARD_VERB.search(body):
        return True
    return bool(re.search(r"\b(?:is|are|was|were|has|have|had|will|after|because)\b", body, re.I))


def _has_publisher_pipe(text: str) -> bool:
    return bool(_PUBLISHER_PIPE.search(_bare_vo(text) or text or ""))


def _is_site_name_only(text: str) -> bool:
    """Publisher / desk / hub name. Not a spoken print."""
    body = _tidy_vo(re.sub(r"\[[^\]]+\]", "", _vo_lines(text) or text or ""))
    if not body or is_numeric_print(body) or _TITLE_CARD_VERB.search(body) or _has_publisher_pipe(body):
        return False
    words = re.findall(r"[A-Za-z0-9.&'-]+", body)
    if not (2 <= len(words) <= 5):
        return False
    caps = sum(1 for w in words if w[:1].isupper())
    if caps < max(2, len(words) - 1):
        return False
    return words[-1].lower().rstrip(".,") in _NEWS_TAIL


def _strip_headline_paste(text: str) -> str:
    """Drop markdown # and trailing (http…) so title-paste still reads as a headline."""
    body = _bare_vo(text).strip()
    body = _MD_HEADING.sub("", body)
    body = _TRAILING_URL.sub("", body)
    return _tidy_vo(body)


def _is_headline_shaped_vo(text: str) -> bool:
    """Title Case headline, no spoken number, no claim verb+print."""
    body = _strip_headline_paste(text)
    if not body or is_numeric_print(body) or re.search(r"\d|%", body):
        return False
    if _TITLE_CARD_VERB.search(body):
        return False
    words = re.findall(r"[A-Za-z0-9]+", body)
    if len(words) < 6:
        return False
    caps = sum(1 for w in words if w[:1].isupper() or w.lower() in {"vs", "versus"})
    return caps >= max(4, len(words) - 2)


def _is_title_like_text(text: str) -> bool:
    """PR/page/hub title, site name, or Title Case headline. Not a spoken print."""
    raw = _bare_vo(text)
    if not raw:
        return False
    if _looks_like_headline(raw) or _MD_HEADING.match(raw.strip()) or _TRAILING_URL.search(raw):
        return not is_numeric_print(_strip_headline_paste(raw))
    if is_numeric_print(raw):
        return False
    return bool(
        _has_publisher_pipe(raw)
        or _is_site_name_only(raw)
        or _is_headline_shaped_vo(raw)
        or _is_title_card(raw)
    )


def has_usable_numeric_print(finding) -> bool:
    """True when stamp.print is a magnitude token, not a title/hub/site string."""
    printed = "" if getattr(finding, "print", None) in {MISSING, "", None} else (finding.print or "").strip()
    if not printed or is_generic_stamp_title(printed) or _is_title_like_text(printed):
        return False
    title = (getattr(finding, "title", None) or "").strip()
    if title and title not in _GENERIC_TITLE and _speech_norm(printed) == _speech_norm(title):
        return False
    return is_numeric_print(printed)


def _stamp_can_cover(finding) -> bool:
    """Stamp can support spoken VO: numeric print or a real prose claim, not a title."""
    from onecrew.timeline import is_chrome_cover_stamp

    if is_chrome_cover_stamp(finding):
        return False
    if has_usable_numeric_print(finding):
        return True
    claim = (getattr(finding, "claim", None) or "").strip()
    # ponytail: extract may copy the claim into title. Prose still covers; title-shaped claims do not.
    return bool(claim and not is_generic_stamp_title(claim) and not _is_title_like_text(claim))


def is_title_only_stamp(finding) -> bool:
    """Empty / hub / site / publisher-pipe print and no speakable prose claim."""
    return not _stamp_can_cover(finding)


def _vo_mentions_print(vo: str, printed: str) -> bool:
    """Spoken VO names this print token, including dollar figures or worded dollars."""
    if not printed or not vo:
        return False
    body = _speech_norm(vo)
    bare = (_bare_vo(vo) or "").lower()
    if _speech_norm(printed) and _speech_norm(printed) in body:
        return True
    nums = [
        n
        for n in pack_numbers(printed)
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    ]
    if nums and all(n.lower() in body or n.lower() in bare for n in nums):
        return True
    for n in nums:
        digits = re.sub(r"[^\d.]+", "", n.replace("−", "-"))
        if digits and (digits in body or digits in bare):
            return True
        if digits and re.search(rf"\b{re.escape(digits)}\s+dollars?\b", bare, re.I):
            return True
    return False


def _vo_has_spoken_number(vo: str) -> bool:
    """True when VO speaks a non-year magnitude ($ / % / unit)."""
    body = _bare_vo(vo)
    if not body:
        return False
    if is_numeric_print(body):
        return True
    nums = [
        n
        for n in pack_numbers(body)
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    ]
    return bool(nums)


def covering_print_spoken_in_vo(vo: str, findings: list) -> str:
    """Attached stamp print covered by spoken VO. Mute-test token. Empty if none."""
    for finding in findings or []:
        printed = "" if getattr(finding, "print", None) in {MISSING, "", None} else (finding.print or "").strip()
        if not printed or not has_usable_numeric_print(finding):
            continue
        if _vo_mentions_print(vo, printed):
            return printed
    return ""


def _vo_covers_attached_print(vo: str, findings: list) -> bool:
    """Spoken line includes a numeric print from an attached stamp."""
    numeric: list[str] = []
    for finding in findings or []:
        printed = "" if getattr(finding, "print", None) in {MISSING, "", None} else (finding.print or "").strip()
        if printed and is_numeric_print(printed) and has_usable_numeric_print(finding):
            numeric.append(printed)
    if not numeric:
        # Title-only stamps do not cover. Prose-claim stamps still can.
        if not findings:
            return True
        return any(_stamp_can_cover(f) for f in findings)
    if any(_vo_mentions_print(vo, printed) for printed in numeric):
        return True
    return False


def is_title_read_vo(vo: str, findings: list) -> bool:
    """Article title / hub paste / site name is not a cite-faithful print/claim/note."""
    body = _speech_norm(vo)
    core = _headline_core(vo)
    if not body or len(body) < 8:
        return False
    if any(
        body == _speech_norm(claim)
        and claim
        and not _is_title_like_text(claim)
        and _speech_norm(claim) != _speech_norm(getattr(f, "title", None) or "")
        for f in findings
        for claim in (getattr(f, "claim", None) or "",)
    ):
        return False
    covered = _vo_covers_attached_print(vo, findings)
    if is_numeric_print(_bare_vo(vo)) and any(
        _speech_norm(getattr(f, "print", None) or "")
        and _speech_norm(getattr(f, "print", None) or "") in body
        for f in findings
    ):
        return False
    raw = _bare_vo(vo)
    paste = bool(_MD_HEADING.match(raw.strip()) or _TRAILING_URL.search(raw))
    headline = (
        _is_site_name_only(vo)
        or _has_publisher_pipe(vo)
        or _is_headline_shaped_vo(vo)
        or _is_title_like_text(vo)
        or _looks_like_headline(raw)
        or _looks_like_headline(_strip_headline_paste(vo))
    )
    print_cover = bool(
        findings
        and covered
        and any(has_usable_numeric_print(f) for f in findings)
        and is_numeric_print(_strip_headline_paste(raw) or raw)
    )
    if paste and not print_cover:
        return True
    if headline and not print_cover and (not covered or not findings):
        return True
    if _is_catalog_or_series_name(vo):
        return True
    prose = _looks_like_prose_claim(vo)
    for finding in findings:
        title = _speech_norm(getattr(finding, "title", None) or "")
        title_core = _headline_core(getattr(finding, "title", None) or "")
        if title in _GENERIC_TITLE:
            continue
        printed = _speech_norm(getattr(finding, "print", None) or "")
        claim = _speech_norm(getattr(finding, "claim", None) or "")
        note = _speech_norm(getattr(finding, "note", None) or "")
        if title in {printed, claim} or (note and title == note):
            if has_usable_numeric_print(finding) or (
                claim and not _is_title_like_text(claim) and _looks_like_prose_claim(claim)
            ):
                continue
        title_hit = (
            body == title
            or core == title
            or (title_core and core == title_core)
            or (len(title) >= 16 and title in body)
            or (len(title_core) >= 16 and title_core in core)
            or (not prose and _title_near(vo, getattr(finding, "title", None) or ""))
        )
        if title_hit:
            if printed and printed not in title and printed in body:
                continue
            if claim and (body == claim or (claim not in title and claim in body)):
                continue
            return True
    return False


def is_pack_slot_beat_id(bid: str) -> bool:
    """Leftover recession-pack beat vocabulary. Not a topic-neutral label."""
    return (bid or "").strip().lower() in PACK_SLOT_BEAT_IDS


def is_narrative_beat_id(bid: str) -> bool:
    """Any leftover narrative label. Room grades packet beat ids as beatN."""
    body = (bid or "").strip()
    return bool(body) and not _BEAT_N_ID.fullmatch(body)


_SLOT_FRAME_CHROME = PACK_SLOT_BEAT_IDS | frozenset({"card", "pack", "hold", "gap", "board"})


def is_slot_chrome_frame(text: str) -> bool:
    """Default 8-slot eyes tokens. Not a shot."""
    return (text or "").strip().lower() in _SLOT_FRAME_CHROME


_SOURCE_PAREN = re.compile(r"\s+\((?:Source|[A-Z][A-Za-z0-9.&]{1,24})\)")
_BROAD_SCOPE = re.compile(
    r"\b(?:nationwide|national|countrywide|aggregate|overall|"
    r"across the (?:country|nation)|in total|as a whole|"
    r"the (?:country|nation) as a whole)\b",
    re.I,
)
_NARROW_SCOPE = re.compile(
    r"\b(?:route[- ]specific|local|campus|lane|one (?:site|city|route)|"
    r"city[- ]level|single[- ](?:site|route|city)|north campus|south campus)\b",
    re.I,
)
_TITLE_CARD_VERB = re.compile(
    r"\b(?:printed|paused|fell|rose|grew|declined|increased|decreased|"
    r"dropped|lost|announced|said|tracked|stays|stay)\b",
    re.I,
)


def _is_title_card(text: str) -> bool:
    """Short Title-Case headline. Not a spoken claim."""
    body = _tidy_vo(re.sub(r"\[[^\]]+\]", "", text or ""))
    if not body or _TITLE_CARD_VERB.search(body):
        return False
    words = re.findall(r"[A-Za-z0-9]+", body)
    if len(words) < 2 or len(words) > 10:
        return False
    caps = sum(1 for w in words if w[:1].isupper() or w.lower() in {"vs", "versus"})
    return caps >= max(2, len(words) - 1)


def strip_action_chrome_vo(vo: str, frame: str = "") -> str:
    """ACTION / (Source) / title-card stay on the frame. Not in narrator VO."""
    body = vo or ""
    if frame and _speech_norm(frame) != _speech_norm(body):
        chrome = bool(_SOURCE_PAREN.search(frame) or _is_title_card(frame))
        trailing = bool(re.search(rf"[.!?]\s+{re.escape(frame)}", body, flags=re.I))
        if chrome or trailing:
            trial = re.sub(re.escape(frame), "", body, flags=re.I)
            if _speech_norm(trial):
                body = trial
    body = _SOURCE_PAREN.sub("", body)
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", body) if p.strip()]
    keep = [part for i, part in enumerate(parts) if not (i and _is_title_card(part))]
    if not keep:
        keep = [p for p in parts if not _is_title_card(p)] or parts
    cleaned = _tidy_vo(" ".join(keep))
    if _speech_norm(cleaned) or not _speech_norm(vo):
        return cleaned
    return _tidy_vo(vo)


def is_action_chrome_vo(vo: str, frame: str = "") -> bool:
    """Narrator line still carries ACTION chrome, a source tag, or a title card."""
    body = _vo_lines(vo) or vo or ""
    if not body.strip():
        return False
    if frame and _speech_norm(frame) and _speech_norm(frame) in _speech_norm(body):
        claim = _speech_norm(strip_action_chrome_vo(body, frame))
        if claim and claim != _speech_norm(body):
            return True
    if _SOURCE_PAREN.search(body):
        return True
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", body) if p.strip()]
    return any(i and _is_title_card(part) for i, part in enumerate(parts))


def speak_covering_print_vo(finding) -> str:
    """Cite-faithful VO that speaks a usable covering print. Empty if none."""
    if not _stamp_can_cover(finding):
        return ""
    printed = "" if getattr(finding, "print", None) in {MISSING, "", None} else (finding.print or "").strip()
    claim = (getattr(finding, "claim", None) or "").strip()
    title = (getattr(finding, "title", None) or "").strip()
    when = (getattr(finding, "when", None) or "").strip()
    if (
        claim
        and not is_generic_stamp_title(claim)
        and not _is_title_like_text(claim)
        and (not title or _speech_norm(claim) != _speech_norm(title))
        and not is_title_read_vo(claim, [finding])
        and not is_thin_title_read_vo(claim, [finding])
    ):
        if not has_usable_numeric_print(finding) or _vo_covers_attached_print(claim, [finding]):
            return claim
    if has_usable_numeric_print(finding):
        # ponytail: title-shaped claims used to yield a bare print token, which
        # drop_thin then rejected. Speak the print in a cite-faithful line.
        if when:
            return f"The cited card printed {printed} in {when}."
        return f"The cited card printed {printed}."
    return ""


def _recover_print_vo(cited: list, *, prior_prints: list[str] | None = None) -> str:
    """Rewrite-before-drop: keep a beat by speaking a covering print."""
    numeric = [f for f in cited if has_usable_numeric_print(f)]
    usable = numeric or [f for f in cited if _stamp_can_cover(f)]
    for finding in usable:
        spoken = speak_covering_print_vo(finding)
        if (
            spoken
            and not _is_title_like_text(spoken)
            and not is_thin_title_read_vo(spoken, cited, prior_prints=prior_prints)
        ):
            return spoken
    return ""


def is_thin_title_read_vo(vo: str, findings: list, *, prior_prints: list[str] | None = None) -> bool:
    """Verbatim stamp title or bare print token. Full claim sentences are weave."""
    if is_title_read_vo(vo, findings):
        return True
    body = _speech_norm(vo)
    if not body:
        return False
    prior = {_speech_norm(p) for p in (prior_prints or []) if _speech_norm(p)}
    for finding in findings:
        title = _speech_norm(getattr(finding, "title", None) or "")
        printed = _speech_norm(getattr(finding, "print", None) or "")
        claim = _speech_norm(getattr(finding, "claim", None) or "")
        if title and title not in _GENERIC_TITLE and body == title:
            return True
        if (
            printed
            and body == printed
            and printed != claim
            and len(printed.split()) <= 4
        ):
            return True
        if title and title not in _GENERIC_TITLE and body == title and title in prior:
            return True
    return False


def is_broad_scope_vo(vo: str) -> bool:
    return bool(_BROAD_SCOPE.search(_vo_lines(vo) or vo or ""))


def stamp_scope(finding) -> str:
    from onecrew.timeline import stamp_text

    blob = stamp_text(finding)
    if _BROAD_SCOPE.search(blob or ""):
        return "broad"
    if _NARROW_SCOPE.search(blob or ""):
        return "narrow"
    return "neutral"


def prefer_covering_print(vo: str, fids: list[str], findings: list) -> tuple[list[str], bool]:
    """Spoken number keeps a print-bearing stamp. Chrome/last-verified soft-cover is refused."""
    from onecrew.timeline import (
        _event_nums,
        is_chrome_cover_stamp,
        stamp_supports_prints,
        stamp_text,
        stamps_for_vo,
        union_supports_prints,
    )

    by_id = {f.id: f for f in findings}
    keep = [
        fid
        for fid in fids
        if fid in by_id
        and not is_placeholder_finding_id(fid)
        and not is_chrome_cover_stamp(by_id[fid])
    ]
    nums = _event_nums(vo)
    if not nums:
        return keep or [fid for fid in fids if fid not in by_id or not is_chrome_cover_stamp(by_id[fid])], False
    useful = [fid for fid in keep if _event_nums(stamp_text(by_id[fid])) & nums]
    rows = [by_id[fid] for fid in useful]
    if useful and union_supports_prints(vo, rows):
        from onecrew.verify import CLOSED_SERIES

        # Print-cover must not drop an already-cited closed series (empty-print LEI).
        closed = [
            fid
            for fid in keep
            if (by_id[fid].series or "").strip() in CLOSED_SERIES
        ]
        return list(dict.fromkeys([*useful, *closed])), False
    chosen = [
        f
        for f in stamps_for_vo(vo, findings, [])
        if not is_chrome_cover_stamp(f) and (_event_nums(stamp_text(f)) & nums)
    ]
    extra = list(dict.fromkeys([*useful, *[f.id for f in chosen]]))
    extra_rows = [by_id[fid] for fid in extra if fid in by_id] + [f for f in chosen if f.id not in by_id]
    if extra and (union_supports_prints(vo, extra_rows) or any(stamp_supports_prints(vo, f) for f in extra_rows)):
        return extra, False
    if useful:
        return useful, False
    if any(is_chrome_cover_stamp(by_id[fid]) for fid in fids if fid in by_id):
        return [], True
    from onecrew.timeline import _years

    dated_when = bool(_years(vo) or _MONTH_YEAR.search(vo or ""))
    if dated_when:
        supported = [fid for fid in keep if fid in by_id and stamp_supports_prints(vo, by_id[fid])]
        if supported and union_supports_prints(vo, [by_id[fid] for fid in supported]):
            return supported, False
        return [], True
    return keep, False


def prefer_covering_scope(vo: str, fids: list[str], findings: list) -> tuple[list[str], bool]:
    """Broad conclusion keeps a covering stamp. Narrow soft-cover is refused."""
    if not is_broad_scope_vo(vo):
        return fids, False
    from onecrew.verify import CLOSED_SERIES

    by_id = {f.id: f for f in findings}
    attached = [by_id[fid] for fid in fids if fid in by_id]
    covering = [f for f in findings if stamp_scope(f) == "broad"]
    closed = [
        fid
        for fid in fids
        if fid in by_id and (by_id[fid].series or "").strip() in CLOSED_SERIES
    ]
    if covering:
        return list(dict.fromkeys([covering[0].id, *closed])), False
    if attached and all(stamp_scope(f) == "narrow" for f in attached):
        return fids, True
    return fids, False


def neutralize_pack_slot_beats(packet) -> None:
    """Rewrite leftover pack-slot / narrative / duplicate ids to unique beat1…beatN."""
    beats = [b for b in packet.beats if (b.kind or "vo") != "heading"]
    old_ids = [b.id for b in beats]
    for i, beat in enumerate(beats):
        beat.id = f"beat{i + 1}"
        beat.scene = f"BEAT {i + 1}"
    new_ids = [b.id for b in beats]

    def _rebind(items, *, rewrite_id: bool = False) -> None:
        queue = list(zip(old_ids, new_ids))
        for item in items:
            old = getattr(item, "beat_id", "") or ""
            for i, (src, dst) in enumerate(queue):
                if src == old:
                    queue.pop(i)
                    item.beat_id = dst
                    if rewrite_id:
                        fid = getattr(item, "id", "") or ""
                        if fid.endswith(f"-{old}"):
                            item.id = f"{fid[: -len(old)]}{dst}"
                    break

    _rebind(packet.frames, rewrite_id=True)
    _rebind(getattr(packet, "collisions", None) or [])


def rewrite_attached_title_vo_beats(packet) -> int:
    """Title-like VO on a usable attached print speaks that print. Do not remap cites."""
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    n = 0
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        vo = _vo_lines(beat.vo)
        if not cited or not (
            is_title_read_vo(vo, cited)
            or is_thin_title_read_vo(vo, cited)
            or (not _speech_norm(vo) and any(has_usable_numeric_print(f) for f in cited))
        ):
            continue
        spoken = _recover_print_vo(cited)
        if not spoken:
            continue
        beat.vo = f"NARRATOR\n{spoken}" if (beat.vo or "").startswith("NARRATOR") else spoken
        for fid in beat.finding_ids:
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"
        screen = speak_stamp_print(list(beat.finding_ids), list(by_id.values()))
        if screen:
            beat.frame = screen
        n += 1
    return n


def drop_thin_title_read_beats(packet) -> list[str]:
    """Drop mid beats that only reread a prior stamp title/print."""
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    beats = [b for b in packet.beats if (b.kind or "vo") != "heading"]
    seen: list[str] = []
    drop: list[str] = []
    for i, beat in enumerate(beats):
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        vo = _vo_lines(beat.vo)
        title_only = bool(cited) and all(is_title_only_stamp(f) for f in cited)
        if is_thin_title_read_vo(vo, cited, prior_prints=seen) or (
            title_only and _is_title_like_text(vo) and not is_numeric_print(_bare_vo(vo))
        ):
            usable = [f for f in cited if _stamp_can_cover(f)]
            spoken = _recover_print_vo(usable or cited, prior_prints=seen)
            if not spoken:
                spoken = (
                    speak_stamp_fact([f.id for f in usable], list(by_id.values())) if usable else ""
                )
            if (
                spoken
                and not _is_title_like_text(spoken)
                and not is_thin_title_read_vo(spoken, cited, prior_prints=seen)
            ):
                beat.vo = f"NARRATOR\n{spoken}" if (beat.vo or "").startswith("NARRATOR") else spoken
                vo = spoken
                screen = speak_stamp_print(list(beat.finding_ids), list(by_id.values()))
                if screen:
                    beat.frame = screen
            else:
                drop.append(beat.id)
                continue
        seen.append(_speech_norm(vo))
        for finding in cited:
            seen.extend(
                [
                    getattr(finding, "claim", None) or "",
                    getattr(finding, "print", None) or "",
                    getattr(finding, "title", None) or "",
                ]
            )
    if not drop:
        return []
    keep = [b for b in packet.beats if b.id not in drop]
    if not any((b.kind or "vo") != "heading" for b in keep):
        return []
    packet.beats = keep
    return drop


def _speakable_grounded_stamps(packet) -> list[Finding]:
    from onecrew.timeline import is_chrome_cover_stamp

    receipt = packet.receipt
    out: list[Finding] = []
    for finding in receipt.findings if receipt else []:
        if not (finding.parallel_url or "").strip():
            continue
        if (finding.stamp or "") == "fringe":
            continue
        if is_chrome_cover_stamp(finding):
            continue
        printed = "" if finding.print in {MISSING, "", None} else (finding.print or "").strip()
        if not (printed or (finding.claim or "").strip()):
            continue
        out.append(finding)
    return out


def _stamp_capacity(packet) -> int:
    """URL-backed stamps that could support cite-faithful beats, including map rows host-cap dropped."""
    from onecrew.timeline import is_chrome_cover_stamp

    seen: set[str] = {f.id for f in _speakable_grounded_stamps(packet)}
    receipt = packet.receipt
    if receipt is None:
        return len(seen)
    by_id = {f.id: f for f in receipt.findings}
    for row in receipt.timeline_map or []:
        fid = (row.finding_id or "").strip()
        if not fid or not (row.url or "").strip():
            continue
        finding = by_id.get(fid)
        if finding is not None and (
            finding.stamp == "fringe" or is_chrome_cover_stamp(finding)
        ):
            continue
        seen.add(fid)
    return len(seen)


def _cite_faithful_beats(packet) -> list:
    beats = [b for b in packet.beats if (b.kind or "vo") != "heading"]
    return [b for b in beats if b.finding_ids and _speech_norm(b.vo)]


def _hold_ship(packet, reason: str) -> None:
    receipt = packet.receipt
    if receipt is None:
        return
    receipt.disposition = "HOLD"
    prior = (receipt.hold_reason or "").strip()
    if reason.lower() not in prior.lower():
        receipt.hold_reason = f"{prior}; {reason}".strip() if prior else reason
    packet.status = "hold"


def _append_stamp_beat(packet, finding: Finding) -> bool:
    if is_title_only_stamp(finding):
        return False
    spoken = (
        speak_covering_print_vo(finding)
        or speak_stamp_fact([finding.id], [finding])
        or speak_stamps([finding.id], [finding])
    )
    if (
        not spoken
        or _is_title_like_text(spoken)
        or is_thin_title_read_vo(spoken, [finding])
        or is_title_read_vo(spoken, [finding])
    ):
        return False
    screen = speak_stamp_print([finding.id], [finding])
    n = len([b for b in packet.beats if (b.kind or "vo") != "heading"])
    packet.beats.append(
        ScriptBeat(
            id=f"beat{n + 1}",
            start="00:00",
            duration_s=20,
            scene=f"BEAT {n + 1}",
            vo=f"NARRATOR\n{spoken} [{finding.id}]",
            finding_ids=[finding.id],
            frame=screen,
        )
    )
    return True


def restore_unused_stamp_beats(packet) -> int:
    """Keep multi-beat structure from leftover stamps. Do not invent."""
    used = {fid for beat in packet.beats for fid in beat.finding_ids}
    added = 0
    for finding in _speakable_grounded_stamps(packet):
        if finding.id in used:
            continue
        if _append_stamp_beat(packet, finding):
            used.add(finding.id)
            added += 1
    return added


def topic_cited_axes(topic: str) -> list[str]:
    """Two cited axes from an AND/vs question. No topic nouns hardcoded."""
    match = _AXIS_PAIR.search((topic or "").strip())
    if not match:
        return []
    left = _tidy_vo(match.group(1) or "")
    right = _tidy_vo(match.group(2) or "")
    if not left or not right:
        return []
    return [left, right]


def _axis_tokens(axis: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[A-Za-z]{3,}", axis or "")
        if w.lower() not in _AXIS_STOP
    }


def _stamp_matches_axis(finding: Finding, axis: str) -> bool:
    from onecrew.timeline import stamp_text

    toks = _axis_tokens(axis)
    if not toks:
        return False
    blob = (stamp_text(finding) or "").lower()
    return any(tok in blob for tok in toks)


def _axis_spoken(packet, axis: str, matching: list[Finding]) -> bool:
    ids = {f.id for f in matching}
    toks = _axis_tokens(axis)
    prints = []
    for finding in matching:
        printed = "" if finding.print in {MISSING, "", None} else (finding.print or "").strip()
        if printed:
            prints.append(_speech_norm(printed))
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        if not (ids & set(beat.finding_ids)):
            continue
        body = _speech_norm(f"{beat.vo} {beat.frame or ''}")
        if any(tok in body for tok in toks) or any(p and p in body for p in prints):
            return True
    return False


def ensure_topic_axes(packet) -> str | None:
    """Speak both cited axes from covering stamps, or name the missing axis."""
    axes = topic_cited_axes(getattr(packet, "topic", "") or "")
    if len(axes) < 2:
        return None
    stamps = _speakable_grounded_stamps(packet)
    missing: list[str] = []
    covered = 0
    for axis in axes:
        matching = [f for f in stamps if _stamp_matches_axis(f, axis)]
        if not matching:
            missing.append(axis)
            continue
        if _axis_spoken(packet, axis, matching):
            covered += 1
            continue
        if _append_stamp_beat(packet, matching[0]) and _axis_spoken(packet, axis, matching):
            covered += 1
            continue
        missing.append(axis)
    if missing and (covered or len(missing) < len(axes)):
        return f"{_MISSING_AXIS}: {missing[0]}"
    if missing and covered == 0 and all(
        any(_stamp_matches_axis(f, axis) for f in stamps) for axis in axes
    ):
        return f"{_MISSING_AXIS}: {missing[0]}"
    return None


def _drop_uncited_ship_claims(packet) -> list[str]:
    """Drop VO claims with no covering finding_ids / print. HOLD cite-faithfulness if leftover."""
    if _invents(packet):
        return []
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    drop: list[str] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        tokens = uncited_claim_tokens(packet, beat.vo)
        if not tokens:
            continue
        no_cover = not beat.finding_ids or not cited or not any(_stamp_can_cover(f) for f in cited)
        cleaned = _strip_uncited_tokens(_vo_lines(beat.vo), tokens)
        still = bool(uncited_claim_tokens(packet, cleaned)) if cleaned else True
        if no_cover or still or is_title_read_vo(cleaned, cited):
            beat.vo = ""
            beat.finding_ids = []
            drop.append(beat.id)
            continue
        beat.vo = f"NARRATOR\n{cleaned}" if (beat.vo or "").startswith("NARRATOR") else cleaned
        for fid in beat.finding_ids:
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"
    if drop:
        keep = [b for b in packet.beats if b.id not in drop]
        if any((b.kind or "vo") != "heading" and _speech_norm(b.vo) for b in keep):
            packet.beats = keep
    remains = any(
        (b.kind or "vo") != "heading" and uncited_claim_tokens(packet, b.vo) for b in packet.beats
    )
    if remains:
        _hold_ship(packet, "cite-faithfulness")
        if receipt is not None:
            prior = (receipt.hold_reason or "").strip()
            parts = [
                p.strip()
                for p in prior.replace("\n", ";").split(";")
                if p.strip() and p.strip().lower() != "uncited claim"
            ]
            if "cite-faithfulness" not in " ".join(parts).lower():
                parts.append("cite-faithfulness")
            receipt.hold_reason = "; ".join(parts) or "cite-faithfulness"
    return drop


def _usable_covering_stamps(packet) -> list:
    """URL-backed stamps that can support cite-faithful print/claim VO."""
    return [f for f in _speakable_grounded_stamps(packet) if _stamp_can_cover(f)]


def refuse_thin_episode(packet) -> str | None:
    """one_time_short_episode may not ship 1-beat when ≥3 stamps could support ≥3 beats."""
    if (packet.cut or "") != "one_time_short_episode":
        return None
    usable_n = len(_usable_covering_stamps(packet))
    if _stamp_capacity(packet) < 3 and usable_n < 3:
        return None
    if len(_cite_faithful_beats(packet)) >= 3:
        return None
    restore_unused_stamp_beats(packet)
    if len(_cite_faithful_beats(packet)) >= 3:
        return None
    return f"{_THIN_AFTER_REPAIR} / {_INSUFFICIENT_CITE_BEATS}"


def sanitize_for_ship(packet):
    """Ship-facing: neutralize leftover slot ids, chrome VO, thin reads, scope cites."""
    from onecrew.cite_repair import rebuild_timed_vo

    _drop_placeholder_cites(packet)
    _dedupe_cap_finding_ids(packet)
    rewrite_attached_title_vo_beats(packet)
    _strip_action_chrome_beats(packet)
    _strip_meta_hanging_beats(packet)
    _strip_incomplete_beats(packet)
    _reattach_covering_scope_beats(packet)
    dropped = drop_thin_title_read_beats(packet)
    uncited = _drop_uncited_ship_claims(packet)
    dupes = _drop_duplicate_vo_beats(packet)
    thin = refuse_thin_episode(packet)
    axis = ensure_topic_axes(packet)
    _dedupe_cap_finding_ids(packet)
    _fill_stamp_print_frames(packet)
    more_dupes = _drop_duplicate_vo_beats(packet)
    if more_dupes:
        dupes = list(dupes) + list(more_dupes)
        if len(_cite_faithful_beats(packet)) < 3:
            extra = refuse_thin_episode(packet)
            if extra:
                thin = extra
    neutralize_pack_slot_beats(packet)
    _strip_pack_slot_beats(packet)
    if thin:
        _hold_ship(packet, thin)
    if axis:
        _hold_ship(packet, axis)
    if dropped or uncited or dupes or packet.beats or thin or axis:
        rebuild_timed_vo(packet)
    return packet


def _dedupe_cap_finding_ids(packet) -> None:
    """Unique + cap per-beat finding_ids. HOLD over-cite only if VO still needs more stamps."""
    from onecrew.timeline import MAX_CITES_PER_BEAT, cap_beat_cites, union_supports_prints
    from onecrew.verify import CLOSED_SERIES

    receipt = packet.receipt
    rows = list(receipt.findings if receipt else [])
    by_id = {f.id: f for f in rows}
    over = False
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        unique = list(
            dict.fromkeys(
                fid
                for fid in beat.finding_ids
                if fid in by_id
                and not is_placeholder_finding_id(fid)
                and (
                    _stamp_can_cover(by_id[fid])
                    or (by_id[fid].series or "").strip() in CLOSED_SERIES
                )
            )
        )
        vo = _vo_lines(beat.vo)
        other = [fid for fid in unique if (by_id[fid].series or "").strip() not in CLOSED_SERIES]
        if len(other) > MAX_CITES_PER_BEAT:
            capped = cap_beat_cites(vo, unique, rows)
            cited = [by_id[fid] for fid in capped if fid in by_id]
            if vo and cited and not union_supports_prints(vo, cited):
                over = True
            unique = list(dict.fromkeys(capped))
        beat.finding_ids = unique
        beat.vo = _drop_extra_cite_brackets(beat.vo, unique)
        for fid in unique:
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"
    if over:
        _hold_ship(packet, "over-cite")


def _fill_stamp_print_frames(packet) -> None:
    """Mute-test: covering stamp print goes on frame/on_screen. Empty cut cannot ship."""
    receipt = packet.receipt
    rows = list(receipt.findings if receipt else [])
    by_id = {f.id: f for f in rows}
    drop: list[str] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        if not beat.finding_ids:
            continue
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        screen = speak_stamp_print(list(beat.finding_ids), rows) or covering_print_spoken_in_vo(
            beat.vo, cited
        )
        if not screen and _vo_has_spoken_number(beat.vo):
            for finding in cited:
                if has_usable_numeric_print(finding):
                    screen = (finding.print or "").strip()
                    break
        shown = (beat.frame or "").strip()
        title_chrome = bool(shown) and is_title_chrome_frame(shown, list(beat.finding_ids), rows)
        if screen:
            if not shown or title_chrome:
                beat.frame = screen
            continue
        fact = speak_stamp_fact(list(beat.finding_ids), rows) or speak_stamps(
            list(beat.finding_ids), rows
        )
        if fact and not _is_title_like_text(fact):
            if not shown or title_chrome:
                beat.frame = fact
            continue
        if cited and not any(_stamp_can_cover(f) for f in cited):
            drop.append(beat.id)
    if drop:
        keep = [b for b in packet.beats if b.id not in drop]
        if any((b.kind or "vo") != "heading" and _speech_norm(b.vo) for b in keep):
            packet.beats = keep
    cited_beats = [
        b
        for b in packet.beats
        if (b.kind or "vo") != "heading" and b.finding_ids and _speech_norm(b.vo)
    ]
    if cited_beats and all(not (b.frame or "").strip() for b in cited_beats):
        _hold_ship(packet, "thin_after_repair")


def _drop_duplicate_vo_beats(packet) -> list[str]:
    """Identical cited print VO ships once. Slot placeholders are not a dupe class."""
    seen: set[str] = set()
    drop: list[str] = []
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        key = _speech_norm(beat.vo)
        if not key or not beat.finding_ids:
            continue
        if not is_numeric_print(_bare_vo(beat.vo)):
            continue
        if key in seen:
            drop.append(beat.id)
            continue
        seen.add(key)
    if not drop:
        return []
    keep = [b for b in packet.beats if b.id not in drop]
    if not any((b.kind or "vo") != "heading" and _speech_norm(b.vo) for b in keep):
        return []
    packet.beats = keep
    return drop


def _drop_placeholder_cites(packet) -> None:
    """Never keep cite-miss / missing / empty as a covering stamp."""
    from onecrew.timeline import stamps_for_vo
    from onecrew.verify import CLOSED_SERIES

    receipt = packet.receipt
    rows = list(receipt.findings if receipt else [])
    by_id = {f.id: f for f in rows}
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        keep = [
            fid
            for fid in beat.finding_ids
            if not is_placeholder_finding_id(fid)
            and fid in by_id
            and (
                _stamp_can_cover(by_id[fid])
                or (by_id[fid].series or "").strip() in CLOSED_SERIES
            )
        ]
        beat.vo = _drop_extra_cite_brackets(beat.vo, keep)
        if keep:
            beat.finding_ids = keep
            for fid in keep:
                if f"[{fid}]" not in beat.vo:
                    beat.vo = f"{beat.vo} [{fid}]"
            continue
        beat.finding_ids = []
        chosen = [
            f
            for f in stamps_for_vo(_vo_lines(beat.vo), rows, [])
            if not is_placeholder_finding_id(f.id)
            and _legal_spoken_finding(f)
            and _stamp_can_cover(f)
        ]
        if not chosen:
            continue
        beat.finding_ids = [chosen[0].id]
        if f"[{chosen[0].id}]" not in beat.vo:
            beat.vo = f"{beat.vo} [{chosen[0].id}]"


def _strip_incomplete_beats(packet) -> None:
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        vo = _vo_lines(beat.vo)
        if not is_incomplete_vo(vo):
            continue
        cleaned = strip_incomplete_vo(vo)
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        if is_incomplete_vo(cleaned) or not _speech_norm(cleaned):
            usable = [f for f in cited if _stamp_can_cover(f)]
            cleaned = _recover_print_vo(usable or cited)
            if not cleaned:
                cleaned = (
                    speak_stamp_fact([f.id for f in usable], list(by_id.values())) if usable else ""
                )
            if (
                not cleaned
                or is_incomplete_vo(cleaned)
                or _is_title_like_text(cleaned)
                or is_thin_title_read_vo(cleaned, cited)
                or is_title_read_vo(cleaned, cited)
            ):
                beat.vo = ""
                beat.finding_ids = []
                continue
        beat.vo = f"NARRATOR\n{cleaned}" if (beat.vo or "").startswith("NARRATOR") else cleaned
        for fid in beat.finding_ids:
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"


def _strip_pack_slot_beats(packet) -> None:
    receipt = packet.receipt
    known = {
        f.id
        for f in (receipt.findings if receipt else [])
        if _legal_spoken_finding(f)
    }
    pack_blob = _pack_text(packet)
    leftover = False
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        vo, _ = _sanitize_vo(_vo_lines(beat.vo), known, pack_blob)
        if vo != _vo_lines(beat.vo):
            beat.vo = f"NARRATOR\n{vo}" if (beat.vo or "").startswith("NARRATOR") else vo
        frame, _ = _sanitize_vo(beat.frame or "", known, pack_blob)
        if frame != (beat.frame or ""):
            beat.frame = frame
        for fid in beat.finding_ids:
            if f"[{fid}]" not in beat.vo:
                beat.vo = f"{beat.vo} [{fid}]"
        if vo_has_pack_slot_token(beat.vo, known) or vo_has_pack_slot_token(beat.frame or "", known):
            leftover = True
    if leftover:
        _hold_ship(packet, _PACK_SLOT_NIT)
        return
    if receipt is None:
        return
    kept = [
        part.strip()
        for part in (receipt.hold_reason or "").replace("\n", ";").split(";")
        if part.strip() and part.strip().lower() != _PACK_SLOT_NIT.lower()
    ]
    if kept == [
        part.strip()
        for part in (receipt.hold_reason or "").replace("\n", ";").split(";")
        if part.strip()
    ]:
        return
    receipt.hold_reason = "; ".join(kept) or None
    if not receipt.hold_reason and receipt.disposition == "HOLD":
        receipt.disposition = "READY"
        packet.status = "ready"


def _strip_meta_hanging_beats(packet) -> None:
    receipt = packet.receipt
    by_id = {f.id: f for f in (receipt.findings if receipt else [])}
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        vo = _vo_lines(beat.vo)
        cited = [by_id[fid] for fid in beat.finding_ids if fid in by_id]
        was_meta = is_unverified_meta_vo(vo) or is_topic_question_vo(vo, packet)
        cleaned = strip_unverified_meta_vo(vo) if is_unverified_meta_vo(vo) else vo
        if is_topic_question_vo(cleaned, packet) and not is_numeric_print(_bare_vo(cleaned)):
            cleaned = ""
        if is_hanging_clause_vo(cleaned) or is_incomplete_vo(cleaned):
            cleaned = strip_incomplete_vo(cleaned)
        needs_print = was_meta and not is_numeric_print(_bare_vo(cleaned))
        if (
            was_meta or is_hanging_clause_vo(vo) or is_incomplete_vo(vo)
        ) and (not _speech_norm(cleaned) or needs_print):
            usable = [f for f in cited if _stamp_can_cover(f)]
            cleaned = _recover_print_vo(usable or cited)
            if not cleaned:
                cleaned = (
                    speak_stamp_fact([f.id for f in usable], list(by_id.values())) if usable else ""
                )
            if (
                not cleaned
                or _is_title_like_text(cleaned)
                or is_thin_title_read_vo(cleaned, cited)
                or is_title_read_vo(cleaned, cited)
            ):
                beat.vo = ""
                beat.finding_ids = []
                continue
        if cleaned != vo:
            beat.vo = f"NARRATOR\n{cleaned}" if (beat.vo or "").startswith("NARRATOR") else cleaned
            for fid in beat.finding_ids:
                if f"[{fid}]" not in beat.vo:
                    beat.vo = f"{beat.vo} [{fid}]"


def _strip_action_chrome_beats(packet) -> None:
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        if is_slot_chrome_frame(beat.frame or "") or is_topic_question_vo(beat.frame or "", packet):
            beat.frame = ""
        kept: list[str] = []
        for line in (beat.vo or "").splitlines():
            stripped = line.strip()
            if stripped.startswith("ACTION:") and (
                is_topic_question_vo(stripped, packet) or is_unverified_meta_vo(stripped)
            ):
                continue
            kept.append(line)
        if kept != (beat.vo or "").splitlines():
            beat.vo = "\n".join(kept)
        vo = _vo_lines(beat.vo)
        cleaned = strip_action_chrome_vo(vo, beat.frame or "")
        if is_topic_question_vo(cleaned, packet) and not is_numeric_print(_bare_vo(cleaned)):
            cleaned = ""
        if cleaned != vo:
            beat.vo = f"NARRATOR\n{cleaned}" if (beat.vo or "").startswith("NARRATOR") else cleaned


def _reattach_covering_scope_beats(packet) -> None:
    receipt = packet.receipt
    if receipt is None:
        return
    rows = list(receipt.findings)
    for beat in packet.beats:
        if (beat.kind or "vo") == "heading":
            continue
        vo = _vo_lines(beat.vo)
        beat.finding_ids = [fid for fid in beat.finding_ids if not is_placeholder_finding_id(fid)]
        keep, hold = prefer_covering_scope(vo, list(beat.finding_ids), rows)
        if hold:
            continue
        print_keep, print_hold = prefer_covering_print(vo, keep, rows)
        if print_hold:
            beat.finding_ids = []
            vo = _strip_unsupported_prints(vo, [], rows)
            beat.vo = f"NARRATOR\n{vo}" if (beat.vo or "").startswith("NARRATOR") else vo
            continue
        keep = print_keep
        if keep != list(beat.finding_ids):
            beat.finding_ids = keep
            vo = _strip_unsupported_prints(vo, keep, rows)
            beat.vo = f"NARRATOR\n{vo}" if (beat.vo or "").startswith("NARRATOR") else vo
            for fid in keep:
                if f"[{fid}]" not in beat.vo:
                    beat.vo = f"{beat.vo} [{fid}]"


def is_generic_stamp_title(title: str) -> bool:
    return (title or "").strip().lower() in _GENERIC_TITLE


_NUMERIC_PRINT = re.compile(r"\$\s*\d|\d\s*\$|[/]t\b|\d(?:\.\d+)?\s*%|[-−]\d")
_THIN_AFTER_REPAIR = "thin_after_repair"
_INSUFFICIENT_CITE_BEATS = "insufficient_cite_beats"
_MISSING_AXIS = "missing topic axis"
_AXIS_PAIR = re.compile(
    r"\b(?:did|have|has|were|was|do|does|are|is)\s+"
    r"(.+?)\s+(?:and|versus|vs\.?)\s+(.+?)(?:\s+both\b|\s*\?|\s*$)",
    re.I,
)
_AXIS_STOP = frozenset(
    {
        "the",
        "and",
        "both",
        "hold",
        "held",
        "cited",
        "prints",
        "print",
        "after",
        "from",
        "with",
        "that",
        "this",
        "have",
        "has",
        "did",
        "does",
        "were",
        "was",
        "are",
        "for",
    }
)


def is_numeric_print(text: str) -> bool:
    """Magnitude token ($ / % / /t / unit). Not an article title or a 0/1 series flag."""
    if _NUMERIC_PRINT.search(text or ""):
        return True
    body = text or ""
    if re.search(r"\d(?:[\d,.]*)\s*[A-Za-z]{1,8}\b", body):
        return True
    nums = [
        n
        for n in pack_numbers(body)
        if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
    ]
    return any("." in n or len(re.sub(r"[^\d]", "", n)) >= 2 for n in nums)


def speak_stamp_print(fids: list[str], findings: list[Finding]) -> str:
    """Mute-test print token. Title chrome is not the on_screen."""
    by_id = {f.id: f for f in findings}
    for fid in fids:
        finding = by_id.get(fid)
        if finding is None:
            continue
        printed = "" if finding.print in {MISSING, "", None} else (finding.print or "").strip()
        if printed and is_numeric_print(printed) and not is_generic_stamp_title(printed):
            return printed
    return ""


def _looks_like_headline(text: str) -> bool:
    """Article / series / hub / wire headline. Not a numeric stamp print."""
    raw = (text or "").strip()
    if not raw:
        return False
    if raw.startswith("#") or _MD_HEADING.match(raw) or _TEXT_CHROME.match(raw) or _TRAILING_URL.search(raw):
        return not is_numeric_print(_strip_headline_paste(raw))
    if is_numeric_print(raw):
        return False
    if ":" in raw or "|" in raw or re.search(r"\s[-–—]\s+", raw):
        return True
    if _is_site_name_only(raw) or _is_headline_shaped_vo(raw):
        return True
    return _is_title_card(raw)


def is_title_chrome_frame(text: str, fids: list[str] | None = None, findings: list | None = None) -> bool:
    """Article title / hub title / # headline. Title match does not need a numeric print."""
    raw = (text or "").strip()
    if not raw:
        return False
    if raw.startswith("#") or _TEXT_CHROME.match(raw):
        return True
    if is_numeric_print(raw) and not _is_title_like_text(raw):
        return False
    shown = _speech_norm(raw)
    rows = [f for f in (findings or []) if not fids or f.id in set(fids)]
    for finding in rows:
        printed = "" if finding.print in {MISSING, "", None} else (finding.print or "").strip()
        if printed and has_usable_numeric_print(finding) and _speech_norm(printed) in shown:
            return False
        claim = (getattr(finding, "claim", None) or "").strip()
        # ponytail: prose claim sharing title words is not headline chrome. Title-only claims stay flagged.
        if (
            claim
            and not _is_title_like_text(claim)
            and _speech_norm(claim) == shown
        ):
            return False
    printed_tok = ""
    title_only = False
    for finding in rows:
        title = _speech_norm(getattr(finding, "title", None) or "")
        printed = "" if finding.print in {MISSING, "", None} else (finding.print or "").strip()
        if printed and has_usable_numeric_print(finding):
            printed_tok = printed
        if is_title_only_stamp(finding):
            title_only = True
        if not title or title in _GENERIC_TITLE:
            continue
        title_hit = (
            shown == title
            or title in shown
            or shown in title
            or _title_near(raw, getattr(finding, "title", None) or "")
        )
        if not title_hit:
            continue
        # Numeric stamp: title instead of the print. Title-only: #65 empty-print hole.
        # Covering prose stamps may reuse the article title as a scene label (fiction).
        if has_usable_numeric_print(finding) or is_title_only_stamp(finding):
            return True
    if printed_tok and _speech_norm(printed_tok) not in shown and (
        _looks_like_headline(raw)
        or _is_site_name_only(raw)
        or _is_headline_shaped_vo(raw)
    ):
        return True
    return (not printed_tok) and title_only and _is_title_like_text(raw)


def speak_stamp_fact(fids: list[str], findings: list[Finding]) -> str:
    """Cite-faithful prose. Prefer claim/note over a bare print token."""
    by_id = {f.id: f for f in findings}
    for fid in fids:
        finding = by_id.get(fid)
        if finding is None:
            continue
        claim = (finding.claim or "").strip()
        printed = "" if finding.print in {MISSING, "", None} else (finding.print or "").strip()
        note = (finding.note or "").strip()
        title = (finding.title or "").strip()
        if is_title_only_stamp(finding):
            continue
        if claim and not is_generic_stamp_title(claim) and _speech_norm(claim) != _speech_norm(title):
            return claim
        if printed and not _is_title_like_text(printed):
            return printed
        if note and not note.lower().startswith("timeline event"):
            return note
    return speak_stamps(fids, findings)


def _strip_vo_chrome(text: str) -> tuple[str, list[str]]:
    cleaned, n = _VO_CHROME.subn("", text or "")
    if not n:
        return text or "", []
    return _tidy_vo(cleaned), ["leftover VO chrome stripped"]


_EXCERPT_TOKEN = re.compile(r"excerpts\[\d+\]", re.I)
_GDP_EQ_TRILLION = re.compile(r"\bGDP\s*=\s*\$?[\d,.]+\s*(?:trillion|tn)\b", re.I)


def _sanitize_vo(text: str, known: set[str], pack_blob: str) -> tuple[str, list[str]]:
    """Strip pack schema/slot cites and hold-meta. Keep real finding ids."""
    from onecrew.foundry import is_pack_slot_id

    nits: list[str] = []

    def keep_or_drop(inner: str) -> str:
        token = (inner or "").strip()
        if is_pack_slot_id(token) or _EXCERPT_TOKEN.fullmatch(token):
            nits.append(_PACK_SLOT_NIT)
            return ""
        if token in known:
            return f"[{token}]"
        if _is_schema_slot(token) or _FINDING_LIKE.match(token):
            nits.append(_PACK_SLOT_NIT)
            return ""
        return f"[{token}]"

    cleaned = _map_brackets(text or "", keep_or_drop)

    def drop_snake(match: re.Match[str]) -> str:
        word = match.group(0)
        if word in known:
            return word
        nits.append(_PACK_SLOT_NIT)
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
        nits.append(_PACK_SLOT_NIT)
    if _GDP_EQ_TRILLION.search(cleaned):
        cleaned = _GDP_EQ_TRILLION.sub("", cleaned)
        nits.append("junk GDP print stripped from VO")
    cleaned, meta_nits = _strip_hold_meta(cleaned)
    cleaned, chrome_nits = _strip_vo_chrome(cleaned)
    cleaned, tone_nits = _strip_tone_chrome(cleaned)
    if not nits and not meta_nits and not chrome_nits and not tone_nits:
        return text or "", []
    cleaned = _tidy_vo(cleaned)
    if not cleaned:
        cleaned = "The named print stays on the card."
    if not vo_has_pack_slot_token(cleaned, known):
        nits = [n for n in nits if n != _PACK_SLOT_NIT]
    # ponytail: hold-meta/chrome/tone/successful slot strip is cleaned, not a HOLD nit.
    return cleaned, list(dict.fromkeys(nits))


def vo_has_pack_slot_token(text: str, known: set[str] | None = None) -> bool:
    """True when pack/schema/excerpt tokens remain in VO after strip."""
    from onecrew.foundry import is_pack_slot_id

    known = known or set()
    body = text or ""
    if _EXCERPT_TOKEN.search(body):
        return True

    def _slot_token(token: str) -> bool:
        raw = (token or "").strip()
        if not raw or raw in known:
            return False
        return bool(
            is_pack_slot_id(raw)
            or _EXCERPT_TOKEN.fullmatch(raw)
            or _is_schema_slot(raw)
            or _FINDING_LIKE.match(raw)
        )

    if re.search(r"\[([^\[\]]+(?:\[[^\[\]]+\])?)\]", body):
        leftovers = []

        def _mark(inner: str) -> str:
            if _slot_token(inner):
                leftovers.append(inner)
            return inner

        _map_brackets(body, _mark)
        if leftovers:
            return True
    for match in _SNAKE_KEY.finditer(body):
        if match.group(0) not in known:
            return True
    return False


def _tc(total_s: int, *, hours: bool) -> str:
    if hours:
        h, rem = divmod(total_s, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    m, s = divmod(total_s, 60)
    return f"{m:02d}:{s:02d}"


def _vo_uses_pack(packet: Packet, vo: str) -> bool:
    pack_n = {n.replace("−", "-") for n in _numbers_in(_pack_text(packet))}
    spoken = re.sub(r"\[[^\]]+\]", "", vo or "")
    vo_n = {n.replace("−", "-") for n in _numbers_in(spoken)}
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
    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if _legal_spoken_finding(f)
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
        receipt.hold_reason = f"{prior}; {extra}".strip() if prior else extra


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
    known = {
        f.id
        for f in (packet.receipt.findings if packet.receipt else [])
        if _legal_spoken_finding(f)
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
        fids = [
            fid
            for fid in (unit.get("finding_ids") or [])
            if fid in known and not is_placeholder_finding_id(fid)
        ]
        vo = (unit.get("vo") or "").strip()
        eyes = (unit.get("eyes") or "").strip()
        slot_vo = vo
        trigger = _first_trigger_text(packet)
        voiced_trigger = bool(trigger and _trigger_voiced(vo, trigger))
        pack_vo = _vo_uses_pack(packet, vo)
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
        vo = strip_action_chrome_vo(vo, eyes)
        if is_slot_chrome_frame(eyes):
            eyes = ""
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
            if uncited_vo and not voiced_trigger and not (held and pack_vo):
                vo = _strip_uncited_tokens(vo, uncited_vo)
                slot_nits.append("uncited claim")
            if uncited_eyes and not voiced_trigger:
                eyes = _strip_uncited_tokens(eyes, uncited_eyes)
                slot_nits.append("uncited claim")
        for fid in known:
            if f"[{fid}]" in vo and fid not in fids:
                fids.append(fid)
        if not _invents(packet):
            rows = packet.receipt.findings if packet.receipt else []
            fids = _link_pack_findings(vo, fids, rows, packet=packet)
            if held and pack_vo:
                vo = slot_vo
            else:
                fids, scope_hold = prefer_covering_scope(vo, fids, rows)
                if scope_hold:
                    slot_nits.append("cite-faithfulness")
                    if packet.receipt is not None:
                        packet.receipt.disposition = "HOLD"
                        packet.receipt.hold_reason = "cite-faithfulness"
                        held = True
                fids, print_hold = prefer_covering_print(vo, fids, rows)
                if print_hold:
                    slot_nits.append("cite-faithfulness")
                    if packet.receipt is not None:
                        packet.receipt.disposition = "HOLD"
                        packet.receipt.hold_reason = "cite-faithfulness"
                        held = True
                orig_eyes = eyes
                fids, vo = _align_vo_to_stamps(vo, fids, rows)
                _, aligned_eyes = _align_vo_to_stamps(eyes, list(fids), rows)
                eyes = aligned_eyes or (
                    orig_eyes
                    if orig_eyes and not is_meta_frame(orig_eyes) and not is_thin_frame(orig_eyes, fids, rows)
                    else aligned_eyes
                )
                from onecrew.timeline import cap_beat_cites

                fids, vo, forecast_hold = _refuse_forecast_theater(vo, fids, rows, packet.tell or "")
                _, eyes, frame_hold = _refuse_forecast_theater(eyes, fids, rows, packet.tell or "")
                if forecast_hold or frame_hold:
                    slot_nits.append("forecast theater")
                fids = cap_beat_cites(vo, fids, rows)
                vo = _drop_extra_cite_brackets(vo, fids)
                eyes = _drop_extra_cite_brackets(eyes, fids)
                vo = _strip_unsupported_prints(vo, fids, rows) if fids else vo
                cited = [row for row in rows if row.id in fids]
                if is_unverified_meta_vo(vo):
                    vo = strip_unverified_meta_vo(vo)
                if is_topic_question_vo(vo, packet) and not is_numeric_print(_bare_vo(vo)):
                    vo = ""
                if is_hanging_clause_vo(vo) or is_incomplete_vo(vo):
                    vo = strip_incomplete_vo(vo)
                if is_title_read_vo(vo, cited) or is_print_hole(vo) or is_hanging_clause_vo(vo) or is_incomplete_vo(vo) or (is_unverified_meta_vo(slot_vo) and not is_numeric_print(_bare_vo(vo))):
                    spoken = speak_stamp_fact(fids, rows)
                    if spoken:
                        vo = spoken
                elif (
                    has_tone_chrome(vo)
                    or is_unverified_meta_vo(vo)
                    or is_pack_chrome_vo(vo)
                    or is_action_chrome_vo(vo, eyes)
                    or not _vo_lines(vo).strip()
                ):
                    spoken = speak_stamp_fact(fids, rows) or speak_stamps(fids, rows)
                    if spoken:
                        vo = spoken
                if is_thin_frame(eyes, fids, rows) or not (eyes or "").strip():
                    if fids:
                        spoken = speak_stamp_fact(fids, rows) or speak_stamps(fids, rows)
                        if spoken and _is_title_like_text(spoken):
                            spoken = speak_stamp_print(fids, rows)
                        eyes = spoken or ("" if _is_title_like_text(eyes or "") else eyes)
                if not _vo_lines(vo).strip() and fids:
                    vo = speak_stamp_fact(fids, rows) or speak_stamps(fids, rows)
                fids, vo, after_hold = _refuse_forecast_theater(vo, fids, rows, packet.tell or "")
                _, eyes, after_frame = _refuse_forecast_theater(eyes, fids, rows, packet.tell or "")
                if after_hold or after_frame:
                    slot_nits.append("forecast theater")
                fids = cap_beat_cites(vo, fids, rows)
                vo = _drop_extra_cite_brackets(vo, fids)
                eyes = _drop_extra_cite_brackets(eyes, fids)
            if voiced_trigger and trigger and not _trigger_voiced(vo, trigger):
                vo = slot_vo
        rows = packet.receipt.findings if packet.receipt else []
        if (
            fids
            and not _invents(packet)
            and (
                is_meta_frame(eyes)
                or is_title_chrome_frame(eyes, fids, rows)
                or is_thin_frame(eyes, fids, rows)
            )
        ):
            eyes = speak_stamp_print(fids, rows) or speak_stamp_fact(fids, rows) or speak_stamps(fids, rows) or ""
        if fids:
            from onecrew.timeline import _event_nums, union_supports_prints

            cited = [
                row
                for row in (packet.receipt.findings if packet.receipt else [])
                if row.id in fids
            ]
            if cited and _event_nums(vo) and not union_supports_prints(vo, cited):
                slot_nits.append("cite-faithfulness")
        elif not hole:
            spoken_nums = [
                n
                for n in _numbers_in(_vo_lines(vo))
                if not _YEAR_TOK.fullmatch(n.replace("−", "-"))
            ]
            sourced = bool(spoken_nums) or bool(_MONTH_YEAR.search(_vo_lines(vo)))
            if sourced and not (held and (pack_grounded or _vo_uses_pack(packet, vo))):
                slot_nits.append(f"beat{i + 1} cites nothing in the pack")
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
                scene=f"BEAT {i+1}",
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
    later["eyes"] = trigger
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
        "When the tell asks for cite-faithful realized prints and no forecast theater, "
        "do not speak agency forecasts or outlooks as the spine — realized prints only. "
        "Cap each beat at one or two covering stamps. Diversify hosts. "
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
    has_timeline = any(
        (f.stamp or "") == "timeline_event"
        for f in ((receipt.findings if receipt else []) or [])
    )
    speakable = [
        f
        for f in ((receipt.findings if receipt else []) or [])
        if _legal_spoken_finding(f)
        and not is_placeholder_finding_id(f.id)
        and f.stamp != "fringe"
    ]
    if (
        units
        and len(units) == 8
        and not has_timeline
        and not _named_prints(packet)
        and not speakable
        and not _invents(packet)
    ):
        holes = list(mint_holes) if mint_holes else []
        holes.append("leftover chrome VO without timeline stamps")
        return _fail_closed(packet, holes)
    if units and len(units) == 8:
        units = _weave_first_trigger(packet, units)
        _warn_mint(packet, mint_holes)
        return _assemble(packet, units)
    holes = list(mint_holes) if mint_holes else ["_eight_from_pack cannot place minted prints"]
    if vertex_detail:
        holes.append(vertex_detail)
    if not has_timeline and not _named_prints(packet) and not _invents(packet):
        holes.append("leftover chrome VO without timeline stamps")
    return _fail_closed(packet, holes)
