from __future__ import annotations

from onecrew.cut import event_cap, require_cut
from onecrew.models import MISSING, Finding, Packet

# Voice changes wording only. It does not restamp sources.
_VOICE = {
    "centered_independent": "Straight read.",
    "left": "Left-leaning read.",
    "right": "Right-leaning read.",
    "far_right": "Far-right read.",
    "far_left": "Far-left read.",
    "unhinged_fringe": "Unhinged-fringe voice — still citing the receipt, not inventing.",
}


def _cite(finding: Finding) -> str:
    tag = f"[{finding.id}]"
    if finding.stamp == "fringe":
        return f"{finding.claim} Tagged fringe, never sold as fact. {tag}"
    if finding.stamp == "mainstream":
        lean = finding.lean if finding.lean != MISSING else "missing"
        return f"{finding.claim} Mainstream, not a source. Source lean {lean}. {tag}"
    extra = ""
    if finding.propaganda == "yes":
        extra = f" Propaganda yes, issuer {finding.propaganda_issuer}."
    if finding.independent == "no":
        extra += " Not independent."
    if finding.independent == MISSING:
        extra += " Independent missing."
    return f"{finding.claim} Grounded.{extra} {tag}"


def write_script(packet: Packet) -> Packet:
    """Write the script from the receipt. Does not mutate findings."""
    receipt = packet.receipt
    if receipt is None or receipt.disposition != "READY" or not receipt.findings:
        packet.script = ""
        return packet
    voice = packet.script_lean or "centered_independent"
    opener = _VOICE.get(voice, _VOICE["centered_independent"])
    cut = require_cut(packet.cut) if packet.cut else None
    rows = list(receipt.findings)
    if cut:
        rows = rows[: event_cap(cut)]
    bits = [f"{opener} Platform {packet.platform or 'missing'}. Cut {packet.cut or 'missing'}."]
    for finding in rows:
        bits.append(_cite(finding))
    if any(f.lean == MISSING for f in rows):
        bits.append("Centered note: some source lean fields are missing.")
    if any(f.stamp == "fringe" for f in rows):
        bits.append("Fringe stays on the list. Not hidden to match a centered ask.")
    if any(f.propaganda == "yes" for f in rows):
        bits.append("Propaganda stays marked. Not hidden.")
    packet.script = " ".join(bits)
    return packet
