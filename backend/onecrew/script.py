from __future__ import annotations

import re

from onecrew.cut import event_cap, is_long_cut, require_cut, scene_seconds
from onecrew.models import Finding, Packet, ScriptBeat


def _cite(finding_id: str) -> str:
    return f" [{finding_id}]"


def _theme(finding: Finding) -> str:
    claim = finding.claim.lower()
    if finding.id == "jcpoa-2018" or "jcpoa" in claim:
        return "jcpoa"
    if finding.id == "hormuz-share" or "seaborne" in claim or "transits" in claim:
        return "oil_lane"
    if finding.id == "oil-panic" or "crashes the world" in claim or "scare means oil" in claim:
        return "panic"
    if finding.id == "producer-frame" or "producer states" in claim:
        return "producer"
    if finding.id == "secret-closure" or "mined shut" in claim or "hidden navy" in claim:
        return "mine_rumor"
    if finding.stamp == "fringe":
        return "fringe_other"
    if finding.stamp == "mainstream":
        return "talking_point"
    return "fact"


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
    if lean in {"far_right"}:
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


def _vo_body(finding: Finding, lean: str, *, long_form: bool) -> str:
    theme = _theme(finding)
    if theme == "jcpoa":
        return _vo_jcpoa(lean, long_form=long_form)
    if theme == "oil_lane":
        return _vo_oil_lane(finding, lean, long_form=long_form)
    if theme == "panic":
        return _vo_panic(lean, long_form=long_form)
    if theme == "producer":
        return _vo_producer(finding, lean, long_form=long_form)
    if theme == "mine_rumor":
        return _vo_mine(lean, long_form=long_form)
    if theme == "fringe_other":
        body = finding.claim.rstrip(".")
        if lean == "unhinged_fringe":
            line = f"The wild one: {body}. I don't have it, so I'm not running it."
        else:
            line = f"There's a claim that {body[0].lower() + body[1:]}. I can't run that as fact."
        if long_form:
            line += " It stays on the list. It does not become the story."
        return line
    if theme == "talking_point":
        body = finding.claim.rstrip(".")
        if lean == "right":
            line = f"The take you'll hear is that {body[0].lower() + body[1:]}. Treat it as a take."
        elif lean in {"left", "far_left"}:
            line = f"The line that {body[0].lower() + body[1:]} gets repeated. Who drives it is not on our list."
        else:
            line = f"You'll hear that {body[0].lower() + body[1:]}."
        if long_form:
            line += " I'm not converting a talking point into a measurement."
        return line
    return _recast(finding, lean, long_form=long_form)


def _vo_jcpoa(lean: str, *, long_form: bool) -> str:
    if lean == "right":
        line = "Twenty-eighteen: the United States withdrew from the JCPOA and the Iran file around the Gulf tightened."
        extra = " That's the withdrawal on the date. I'm not stretching it."
    elif lean == "far_right":
        line = "In 2018 the United States left the JCPOA. The Gulf file on Iran tightened."
        extra = " Withdrawal. Tighter file. Stop."
    elif lean == "left":
        line = "When the United States withdrew from the JCPOA in 2018, the Iran file around the Gulf got tighter."
        extra = " Stay with the public date and that tighter file."
    elif lean == "far_left":
        line = "In 2018 the United States withdrew from the JCPOA. The Iran file around the Gulf tightened with it."
        extra = " Hold the date. Don't let a later scare rewrite 2018."
    elif lean == "unhinged_fringe":
        line = "2018, plain: the United States withdrew from the JCPOA and the Iran file around the Gulf tightened. That's all I've got on this beat."
        extra = " I'm not hanging a secret treaty on it."
    else:
        line = "In 2018 the United States withdrew from the JCPOA, tightening the Iran file around the Gulf."
        extra = " I'm staying on that withdrawal and that tighter file."
    return line + (extra if long_form else "")


def _vo_oil_lane(finding: Finding, lean: str, *, long_form: bool) -> str:
    issuer = (finding.propaganda_issuer or "").strip()
    named = issuer and issuer != "missing"
    if lean == "right":
        line = "Most seaborne oil still has to run the Strait of Hormuz. The lane is still open."
        extra = " That's why this waterway sits on every energy desk."
    elif lean in {"left", "far_left"}:
        line = "A large share of seaborne oil still transits the Strait of Hormuz."
        if named:
            line += f" {issuer} is the one putting that share out."
        extra = " Follow the lane, and follow who is publishing the number."
    elif lean == "far_right":
        line = "A large share of seaborne oil still transits Hormuz. The strait is still the choke."
        extra = " Keep the map up."
    elif lean == "unhinged_fringe":
        line = "A huge share of seaborne oil still goes through Hormuz. That's the lane."
        extra = " I'm not closing it from a rumor."
    else:
        line = "A large share of seaborne oil still transits the Strait of Hormuz."
        extra = " Tankers still use that lane."
        if named and long_form:
            extra += f" {issuer} published that share."
    return line + (extra if long_form else "")


def _vo_panic(lean: str, *, long_form: bool) -> str:
    if lean == "right":
        line = "The scare take is that any Hormuz jolt crashes oil overnight. Treat it as a take."
        extra = " A scare is not a measurement."
    elif lean in {"left", "far_left"}:
        line = "The line that any Hormuz scare crashes oil overnight gets repeated. Who drives it is not on our list."
        extra = " Don't let a talking point stand in for a source."
    elif lean == "far_right":
        line = "You'll hear any Hormuz scare means oil crashes the world overnight. That's the panic line."
        extra = " Leave it as a line."
    elif lean == "unhinged_fringe":
        line = "The panic version: any Hormuz scare and oil crashes overnight. I don't get to promote it."
        extra = " Repeat is not proof."
    else:
        line = "You'll hear that any Hormuz scare means oil crashes the world overnight."
        extra = " That's the scare. I'm not proving a crash from this beat."
    return line + (extra if long_form else "")


def _vo_producer(finding: Finding, lean: str, *, long_form: bool) -> str:
    repeats = finding.who_repeats
    names = ""
    if isinstance(repeats, list) and repeats:
        names = ", ".join(str(x) for x in repeats if str(x).strip() and str(x) != "missing")
    if lean == "right":
        line = "Producer states treat an open Hormuz as given for the oil market."
        extra = " Open lane, open market — that's their frame."
    elif lean in {"left", "far_left"}:
        line = "Producer states treat an open Hormuz as an oil-market given."
        if names:
            line += f" {names} repeats that frame."
        extra = " A given for them is still a frame."
    elif lean == "unhinged_fringe":
        line = "Producer states talk like an open Hormuz is just the weather."
        extra = " That's their given. Not a secret."
    else:
        line = "Producer states treat an open Hormuz as an oil-market given."
        extra = " That's the industry frame."
    return line + (extra if long_form else "")


def _vo_mine(lean: str, *, long_form: bool) -> str:
    if lean == "right":
        line = "Someone says Hormuz is already mined shut under a hidden navy treaty. I don't have it."
        extra = " If I can't show it, I don't run it."
    elif lean in {"left", "far_left"}:
        line = "A claim is out there that Hormuz was mined shut under a hidden navy treaty. I'm not selling it."
        extra = " It stays audible. It does not become the close."
    elif lean == "unhinged_fringe":
        line = "The wild one: Hormuz already mined shut under a hidden navy treaty. I still don't have it, so I'm not running it."
        extra = " I can say the claim. I cannot dress it as fact."
    else:
        line = "There's a claim that Hormuz has already been mined shut under a hidden navy treaty. I can't run that as fact."
        extra = " You still hear the claim. You don't get a minefield from me."
    return line + (extra if long_form else "")


def _vo_for(finding: Finding, lean: str, *, long_form: bool) -> str:
    return _vo_body(finding, lean, long_form=long_form).rstrip() + _cite(finding.id)


def _close_vo(link_claim: str, lean: str, cite: list[str]) -> str:
    claim = link_claim.rstrip(".")
    lowered = claim[0].lower() + claim[1:] if claim else claim
    if lean == "right":
        line = "Don't hang a later Hormuz panic on the 2018 JCPOA exit. That connection is not sourced."
    elif lean in {"left", "far_left"}:
        line = f"I will not tell you that {lowered}. We do not have that connection."
    elif lean == "unhinged_fringe":
        line = f"I want a clean line that {lowered}. I don't have it, so I won't draw it."
    else:
        line = f"I cannot tell you that {lowered}. That connection is not sourced."
    return line + "".join(_cite(fid) for fid in cite)


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
    """Timed spoken VO from the receipt. Lean changes the argument, not the stamps."""
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
        beats.append(
            ScriptBeat(
                id=finding.id,
                start=_tc(cursor, hours=hours),
                duration_s=duration,
                act=_act_name(index, scene_total) if long_form else "",
                vo=_vo_for(finding, lean, long_form=long_form),
                finding_ids=[finding.id],
            )
        )
        cursor += duration
    if long_form and receipt.causal_links:
        link = receipt.causal_links[0]
        known = {f.id for f in receipt.findings}
        cite = [fid for fid in (link.from_id, link.to_id) if fid in known]
        if cite:
            beats.append(
                ScriptBeat(
                    id=link.id,
                    start=_tc(cursor, hours=hours),
                    duration_s=close_s,
                    act=_act_name(len(rows), scene_total),
                    vo=_close_vo(link.claim, lean, cite),
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
