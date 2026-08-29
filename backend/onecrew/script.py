from __future__ import annotations

from onecrew.cut import event_cap, is_long_cut, require_cut, scene_seconds
from onecrew.models import MISSING, Finding, Packet, ScriptBeat

# Lean changes spoken wording only. The claim text stays the receipt row.
_LEAN = {
    "centered_independent": "{when}on the receipt: {claim}",
    "left": "{when}the public file, not the talking-point version: {claim}",
    "right": "{when}the state-file read: {claim}",
    "far_left": "{when}read against the official line: {claim}",
    "far_right": "{when}read against the coastal consensus: {claim}",
    "unhinged_fringe": "{when}receipt only, still not inventing: {claim}",
}


def _when_prefix(finding: Finding) -> str:
    when = (finding.when or "").strip()
    return f"In {when}, " if when else ""


def _stamp_tags(finding: Finding) -> str:
    bits: list[str] = []
    if finding.stamp == "fringe":
        bits.append("Tagged fringe, never sold as fact.")
    elif finding.stamp == "mainstream":
        lean = finding.lean if finding.lean != MISSING else "missing"
        bits.append(f"Mainstream, not a source. Source lean {lean}.")
    else:
        bits.append("Grounded.")
        if finding.propaganda == "yes":
            bits.append(f"Propaganda yes, issuer {finding.propaganda_issuer}.")
        if finding.independent == "no":
            bits.append("Not independent.")
        if finding.independent == MISSING:
            bits.append("Independent on that row is missing.")
    bits.append(f"[{finding.id}]")
    return " ".join(bits)


def _spoken(lean: str, *, when: str, claim: str) -> str:
    frame = _LEAN.get(lean, _LEAN["centered_independent"])
    spoken = frame.format(when=when, claim=claim.rstrip("."))
    return spoken[0].upper() + spoken[1:] if spoken else spoken


def _vo_for(finding: Finding, lean: str, *, long_form: bool) -> str:
    spoken = _spoken(lean, when=_when_prefix(finding), claim=finding.claim)
    hold = " Hold on this card. Do not add a fact that is not on the row." if long_form else ""
    return f"{spoken}. {_stamp_tags(finding)}{hold}"


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


def write_script(packet: Packet) -> Packet:
    """Timed VO from the receipt. Lean changes wording, not stamps."""
    receipt = packet.receipt
    if receipt is None or receipt.disposition != "READY" or not receipt.findings:
        packet.script = ""
        packet.beats = []
        return packet
    lean = packet.script_lean or "centered_independent"
    cut = require_cut(packet.cut) if packet.cut else None
    rows = list(receipt.findings)
    if cut:
        rows = rows[: event_cap(cut, packet.platform)]
    long_form = bool(cut and is_long_cut(cut))
    duration = scene_seconds(cut) if cut else 12
    close_s = 180 if long_form else 0
    hours = long_form
    beats: list[ScriptBeat] = []
    cursor = 0
    scene_total = len(rows) + (1 if long_form and receipt.causal_links else 0)
    for index, finding in enumerate(rows):
        start = _tc(cursor, hours=hours)
        act = _act_name(index, scene_total) if long_form else ""
        beats.append(
            ScriptBeat(
                id=finding.id,
                start=start,
                duration_s=duration,
                act=act,
                vo=_vo_for(finding, lean, long_form=long_form),
                finding_ids=[finding.id],
            )
        )
        cursor += duration
    if long_form and receipt.causal_links:
        link = receipt.causal_links[0]
        from_id, to_id = link.from_id, link.to_id
        known = {f.id for f in receipt.findings}
        cite = [fid for fid in (from_id, to_id) if fid in known]
        if cite:
            spoken = _spoken(
                lean,
                when="",
                claim=(
                    f"Causal link {from_id} to {to_id} is missing. {link.claim} "
                    "Parallel did not source this. Not invented"
                ),
            )
            vo = f"{spoken}. [{cite[0]}]" + (f" [{cite[1]}]" if len(cite) > 1 else "")
            beats.append(
                ScriptBeat(
                    id=link.id,
                    start=_tc(cursor, hours=hours),
                    duration_s=close_s,
                    act=_act_name(len(rows), scene_total),
                    vo=vo,
                    finding_ids=cite,
                )
            )
            cursor += close_s
    lines = [
        f"Timed VO · {packet.platform or 'missing'} · {packet.cut or 'missing'} · {lean}",
        "",
    ]
    last_act = None
    elapsed = 0
    for beat in beats:
        if beat.act and beat.act != last_act:
            lines.append(beat.act)
            last_act = beat.act
        elapsed += beat.duration_s
        lines.append(f"{beat.start}–{_tc(elapsed, hours=hours)}")
        lines.append(beat.vo)
        lines.append("")
    packet.beats = beats
    packet.script = "\n".join(lines).strip() + "\n"
    return packet
