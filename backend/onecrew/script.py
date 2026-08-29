from __future__ import annotations

import re

from onecrew.cut import event_cap, is_long_cut, require_cut, scene_seconds
from onecrew.models import Finding, Packet, ScriptBeat
from onecrew.picks import require_tell_pairing


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


def _invents_frame(packet: Packet) -> bool:
    return (packet.genre or "nonfiction") != "nonfiction"


def _frame_for(packet: Packet, finding: Finding, lean: str) -> str:
    """Invented room/character only. Labeled (frame). Never a grounded fact."""
    if not _invents_frame(packet):
        return ""
    vantage = packet.vantage or "global_overview"
    theme = _theme(finding)
    if vantage == "one_ship":
        return _ship_frame(theme, lean)
    if vantage == "one_family":
        return _family_frame(theme, lean)
    return _map_table_frame(theme, lean)


def _family_frame(theme: str, lean: str) -> str:
    if theme == "jcpoa":
        if lean == "right":
            return "Leila's brother slaps the table in their Bandar Abbas kitchen. (frame)"
        if lean in {"left", "far_left"}:
            return "Leila keeps the kitchen radio low so the kids stay asleep in Bandar Abbas. (frame)"
        return "Leila shuts the kitchen radio in Bandar Abbas. (frame)"
    if theme == "oil_lane":
        return "From the kitchen window she can see the harbor road, not the lane itself. (frame)"
    if theme == "panic":
        return "A neighbor fills the doorway and talks overnight prices. (frame)"
    if theme == "producer":
        return "The state bulletin plays on the small TV above the sink. (frame)"
    if theme == "mine_rumor":
        return "Someone in the alley repeats a rumor through the open kitchen door. (frame)"
    return "Leila stays at the Bandar Abbas sink with the radio on. (frame)"


def _ship_frame(theme: str, lean: str) -> str:
    if theme == "jcpoa":
        if lean == "right":
            return "Captain Reza pins a 2018 printout under the bridge lamp. (frame)"
        if lean in {"left", "far_left"}:
            return "On the bridge Reza reads the old date out loud to the watch. (frame)"
        return "Captain Reza checks the chart table on a ship crossing the strait. (frame)"
    if theme == "oil_lane":
        return "The lookout calls an open lane from the wing. No blast. (frame)"
    if theme == "panic":
        return "In the mess the radio talks crash. The hull is still quiet. (frame)"
    if theme == "producer":
        return "Shore radio on the bridge speaker talks like the lane is a given. (frame)"
    if theme == "mine_rumor":
        return "A crewman repeats a mine-treaty rumor on the wing. Reza does not change heading for a rumor. (frame)"
    return "Reza keeps the watch. A hit is a scene they fear, not a fact they have. (frame)"


def _map_table_frame(theme: str, lean: str) -> str:
    if theme == "mine_rumor":
        return "At a map table someone repeats a rumor. The map does not grow mines. (frame)"
    return "A narrator stands at a map table with a radio on. (frame)"


def _vo_for(finding: Finding, lean: str, *, long_form: bool, packet: Packet) -> str:
    fact = _vo_body(finding, lean, long_form=long_form).rstrip() + _cite(finding.id)
    frame = _frame_for(packet, finding, lean)
    if not frame:
        return fact
    return f"{frame} {fact}"


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
    spoken = line + "".join(_cite(fid) for fid in cite)
    return spoken


def _close_frame(packet: Packet) -> str:
    if not _invents_frame(packet):
        return ""
    if packet.vantage == "one_ship":
        return "Reza does not log a sourced explosion. The watch just keeps the heading. (frame) "
    if packet.vantage == "one_family":
        return "Leila does not draw an arrow between two dates on the kitchen paper. (frame) "
    return "No arrow gets drawn on the map table. (frame) "


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
    if cut:
        require_tell_pairing(cut, packet.genre or "nonfiction")
    rows = list(receipt.findings)
    if cut:
        rows = rows[: event_cap(cut, packet.platform)]
    long_form = bool(cut and is_long_cut(cut))
    duration = scene_seconds(cut) if cut else 12
    close_s = 180 if long_form else 0
    hours = long_form
    prior = {beat.id: beat for beat in packet.beats}
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
                vo=_vo_for(finding, lean, long_form=long_form, packet=packet),
                finding_ids=[finding.id],
                frame=_frame_for(packet, finding, lean),
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
                    vo=_close_frame(packet) + _close_vo(link.claim, lean, cite),
                    finding_ids=cite,
                    frame=_close_frame(packet).strip(),
                )
            )
            cursor += close_s
    for beat in beats:
        old = prior.get(beat.id)
        if old is None:
            continue
        beat.collision = old.collision
        beat.collision_url = old.collision_url
        beat.collision_title = old.collision_title
        beat.collision_kind = old.collision_kind
    lines = [
        f"Timed VO · {packet.platform or 'missing'} · {packet.cut or 'missing'} · {lean} · {packet.genre or 'nonfiction'} · {packet.vantage or 'global_overview'}",
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
