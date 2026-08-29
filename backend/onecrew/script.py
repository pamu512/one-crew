from __future__ import annotations

import re

from onecrew.cut import event_cap, is_long_cut, require_cut
from onecrew.models import MISSING, Finding, Packet, ScriptBeat
from onecrew.tell import invents_frame, tell_lane
from onecrew.tone import apply_tone


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
    return invents_frame(cut=packet.cut, tell=packet.tell or "")


def _frame_for(packet: Packet, finding: Finding, lean: str) -> str:
    """Invented room/character only. Labeled (frame). Never a grounded fact."""
    if not _invents_frame(packet):
        return ""
    return _frame_for_theme(_theme(finding), tell_lane(packet.tell), lean)


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
    spoken = apply_tone(
        _vo_body(finding, lean, long_form=long_form).rstrip(),
        packet.tone,
        fiction=_invents_frame(packet),
    )
    fact = spoken + _cite(finding.id)
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
    lane = tell_lane(packet.tell)
    if lane == "pilot":
        return "The retired pilot does not log a sourced explosion. The watch just keeps the heading. (frame) "
    if lane == "ship":
        return "Reza does not log a sourced explosion. The watch just keeps the heading. (frame) "
    if lane == "family":
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


_SHORT = frozenset({"tiktok-length", "shorts"})


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


def _slugs(theme: str, *, fiction: bool, vantage: str, n: int) -> list[str]:
    if fiction and vantage == "pilot":
        return [
            "INT. NIGHT WATCH / BRIDGE - NIGHT",
            "INT. WATCH CHAIR - NIGHT",
            "EXT. DARK LANE FROM THE GLASS - NIGHT",
        ][:n]
    if fiction and vantage == "family":
        family = {
            "jcpoa": [
                "INT. BANDAR ABBAS KITCHEN - NIGHT",
                "INT. KITCHEN / SMALL TV - NIGHT",
                "INT. HALL OFF THE KITCHEN - NIGHT",
            ],
            "oil_lane": [
                "INT. KITCHEN WINDOW - NIGHT",
                "EXT. HARBOR ROAD (FROM THE WINDOW) - NIGHT",
                "INT. SINK AND RADIO - NIGHT",
            ],
            "panic": [
                "INT. KITCHEN DOORWAY - NIGHT",
                "INT. KITCHEN - NEIGHBOR IN FRAME - NIGHT",
                "INT. KITCHEN TABLE - NIGHT",
            ],
            "producer": [
                "INT. KITCHEN / STATE BULLETIN TV - NIGHT",
                "INT. ABOVE THE SINK - NIGHT",
                "INT. KITCHEN - NIGHT",
            ],
            "mine_rumor": [
                "INT. OPEN KITCHEN DOOR - NIGHT",
                "EXT. ALLEY (FROM THE DOOR) - NIGHT",
                "INT. KITCHEN - NIGHT",
            ],
        }
        return (family.get(theme) or [
            "INT. BANDAR ABBAS KITCHEN - NIGHT",
            "INT. KITCHEN TABLE - NIGHT",
            "INT. SINK - NIGHT",
        ])[:n]
    if fiction and vantage == "ship":
        ship = {
            "jcpoa": [
                "INT. TANKER BRIDGE - NIGHT",
                "INT. CHART TABLE - NIGHT",
                "INT. BRIDGE WING DOOR - NIGHT",
            ],
            "oil_lane": [
                "EXT. BOW / HORMUZ LANE - NIGHT",
                "EXT. BRIDGE WING - NIGHT",
                "INT. BRIDGE - NIGHT",
            ],
            "panic": [
                "INT. CREW MESS - NIGHT",
                "INT. MESS RADIO - NIGHT",
                "INT. HULL CORRIDOR - NIGHT",
            ],
            "producer": [
                "INT. BRIDGE SPEAKER - NIGHT",
                "INT. CHART TABLE - NIGHT",
                "INT. BRIDGE - NIGHT",
            ],
            "mine_rumor": [
                "EXT. BRIDGE WING - NIGHT",
                "INT. BRIDGE - NIGHT",
                "EXT. DARK WATER - NIGHT",
            ],
        }
        return (ship.get(theme) or [
            "INT. TANKER BRIDGE - NIGHT",
            "EXT. BRIDGE WING - NIGHT",
            "INT. CHART TABLE - NIGHT",
        ])[:n]
    if fiction:
        return [
            "INT. MAP-TABLE ROOM - NIGHT",
            "INT. MAP-TABLE ROOM - RADIO ON - NIGHT",
            "INT. MAP-TABLE ROOM - LATER",
        ][:n]
    studio = {
        "jcpoa": ["STUDIO — GULF MAP", "ARCHIVE — 2018 ANNOUNCEMENT", "STUDIO — THE DATE", "B-ROLL — PODIUM CHYRON"],
        "oil_lane": ["B-ROLL — STRAIT OF HORMUZ", "ENERGY DESK", "B-ROLL — OPEN LANE", "STUDIO — WHO PUBLISHED THE SHARE"],
        "panic": ["NEWSROOM — OVERNIGHT", "STUDIO — SCARE LINE", "WALL MAP — HORMUZ", "STUDIO — NOT A MEASUREMENT"],
        "producer": ["PRODUCER DESK", "SHIPPING BOARD", "STUDIO — INDUSTRY FRAME", "B-ROLL — OPEN LANE MARK"],
        "mine_rumor": ["NIGHT WATER — HORMUZ", "STUDIO — UNSOURCED CLAIM", "EMPTY LANE — NO MINES ON CAMERA", "STUDIO — IT STAYS A CLAIM"],
        "fringe_other": ["STUDIO — FRINGE ROW", "B-ROLL — THE CLAIM ONLY", "STUDIO — NOT FACT", "STUDIO — STILL ON THE LIST"],
        "talking_point": ["STUDIO — TALKING POINT", "NEWSROOM", "STUDIO — WHO DRIVES IT", "B-ROLL — REPEATED LINE"],
        "fact": ["STUDIO", "B-ROLL", "STUDIO — THE SENTENCE", "ARCHIVE"],
    }
    return (studio.get(theme) or studio["fact"])[:n]


def _action_line(theme: str, *, fiction: bool, vantage: str, lean: str, finding: Finding) -> str:
    if fiction:
        return _frame_for_theme(theme, vantage, lean) or "A narrator stands at a map table. (frame)"
    if theme == "jcpoa":
        return "Host at a Gulf map. A dated chyron waits. No family in the shot."
    if theme == "oil_lane":
        return "Tanker in an open Hormuz lane, land close on both sides. The water is quiet."
    if theme == "panic":
        return "Overnight newsroom. Oil ticker running. A scare is not a measurement on screen."
    if theme == "producer":
        return "Producer-state energy desk. Hormuz marked open on a shipping board."
    if theme == "mine_rumor":
        return "Night water in the strait. Empty lane. No mines on camera."
    if "milk" in finding.claim.lower() or "dairy" in finding.claim.lower():
        return "Spring auction floor. A milk tanker at the dock as the spot price ticks."
    return f"Photoreal B-roll of the cited beat: {finding.claim.rstrip('.')}."


def _pilot_frame(theme: str, lean: str) -> str:
    if theme == "jcpoa":
        return "The retired pilot pins a 2018 note under the night-watch lamp. (frame)"
    if theme == "oil_lane":
        return "From the glass he can see an open lane. No blast. (frame)"
    if theme == "panic":
        return "The mess radio talks crash. The hull stays quiet. (frame)"
    if theme == "producer":
        return "Shore radio talks like the lane is a given. The pilot does not change the watch for a frame. (frame)"
    if theme == "mine_rumor":
        return "Someone repeats a mine-treaty rumor. The retired pilot does not change heading for a rumor. (frame)"
    return "The retired pilot keeps the night watch. A hit is a scene they fear, not a fact they have. (frame)"


def _frame_for_theme(theme: str, vantage: str, lean: str) -> str:
    if vantage == "pilot":
        return _pilot_frame(theme, lean)
    if vantage == "ship":
        return _ship_frame(theme, lean)
    if vantage == "family":
        return _family_frame(theme, lean)
    return _map_table_frame(theme, lean)


def _hole_line(finding: Finding, lean: str) -> str:
    if finding.stamp == "fringe":
        return _vo_body(finding, lean, long_form=True)
    if finding.lean == "missing" or finding.lean == MISSING:
        return "Who drives that repeated line is not on our list. I am leaving the hole visible."
    if finding.propaganda == "yes":
        issuer = finding.propaganda_issuer if finding.propaganda_issuer != "missing" else "the named issuer"
        return f"{issuer} is on the row as the campaign source. The stamp stays visible."
    return "That is the sentence we have. I am not stacking a later scare on it."


def _interview_line(theme: str, finding: Finding) -> str:
    if theme == "oil_lane" and finding.propaganda_issuer and finding.propaganda_issuer != "missing":
        return f"Ask who is putting that share out. The named issuer on the row is {finding.propaganda_issuer}."
    if finding.stamp == "fringe":
        return "Ask for a source on this claim. If none lands, it stays a claim."
    if theme == "jcpoa":
        return "Ask for the public date only. Do not let a later scare rewrite 2018."
    return "Ask what we can cite on this beat. Do not invent the next event."


def _dialogue(theme: str, vantage: str, lean: str, fact: str) -> str:
    if vantage == "pilot":
        name = "THE RETIRED PILOT"
    elif vantage == "ship":
        name = "REZA"
    elif vantage == "family":
        name = "LEILA"
    else:
        name = "NARRATOR"
    return f"{name}\n{fact}"


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


def _scene_count(tier: str, finding_n: int, *, with_open: bool, with_close: bool) -> int:
    per = {"short": 1, "episode": 2, "doc": 4, "feature": 3}[tier]
    return (1 if with_open else 0) + finding_n * per + (1 if with_close else 0)


def write_script(packet: Packet) -> Packet:
    """Full recordable script from the receipt. Lean changes the argument, not the stamps or the thickness."""
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
    tier = _tier(cut)
    long_form = bool(cut and is_long_cut(cut))
    hours = long_form
    durs = _durs(tier)
    fiction = _invents_frame(packet)
    vantage = tell_lane(packet.tell)
    per = {"short": 1, "episode": 2, "doc": 4, "feature": 3}[tier]
    with_open = tier != "short"
    with_close = tier != "short" and bool(receipt.causal_links)
    prior = {beat.id: beat for beat in packet.beats}
    draft = _Draft(
        hours=hours,
        long_form=long_form,
        scene_total=_scene_count(tier, len(rows), with_open=with_open, with_close=with_close),
    )
    first = rows[0]
    if with_open:
        open_slug = (
            "INT. NIGHT WATCH / BRIDGE - DUSK"
            if fiction and vantage == "pilot"
            else "INT. BANDAR ABBAS KITCHEN - EVENING"
            if fiction and vantage == "family"
            else "INT. TANKER BRIDGE - DUSK"
            if fiction and vantage == "ship"
            else "INT. MAP-TABLE ROOM - EVENING"
            if fiction
            else "STUDIO — COLD OPEN"
        )
        open_action = (
            "The retired pilot takes the night watch. Dusk. The glass is already up. (frame)"
            if fiction and vantage == "pilot"
            else "Leila at the Bandar Abbas sink. Evening. The radio is already on. (frame)"
            if fiction and vantage == "family"
            else "Reza at the bridge window. Dusk. The lane is ahead. No blast. (frame)"
            if fiction and vantage == "ship"
            else "A narrator at a map table. Radio on. No collage. (frame)"
            if fiction
            else "Host at a map table. Gulf chart on the wall. No invented family."
        )
        draft.add(kind="heading", bid="open-h", text=open_slug, fids=[first.id], dur=durs["heading"], scene=open_slug)
        draft.add(
            kind="action",
            bid="open-a",
            text=open_action,
            fids=[first.id],
            dur=durs["action"],
            scene=open_slug,
            camera="WIDE",
            frame=open_action if fiction else "",
        )
    for finding in rows:
        theme = _theme(finding)
        slugs = _slugs(theme, fiction=fiction, vantage=vantage, n=per)
        fact = _vo_for(finding, lean, long_form=True, packet=packet)
        hole = _hole_line(finding, lean).rstrip() + _cite(finding.id)
        asked = _interview_line(theme, finding)
        for si, slug in enumerate(slugs):
            draft.add(kind="heading", bid=f"{finding.id}-h{si+1}", text=slug, fids=[finding.id], dur=durs["heading"], scene=slug)
            action = _action_line(theme, fiction=fiction, vantage=vantage, lean=lean, finding=finding)
            draft.add(
                kind="action",
                bid=f"{finding.id}-a{si+1}",
                text=action,
                fids=[finding.id],
                dur=durs["action"],
                scene=slug,
                camera="WIDE" if si == 0 else "CUTAWAY",
                frame=action if fiction and "(frame)" in action else "",
            )
            if si == 0:
                spoken = _dialogue(theme, vantage, lean, fact) if fiction else f"NARRATOR\n{fact}"
                draft.add(
                    kind="vo",
                    bid=finding.id,
                    text=spoken,
                    fids=[finding.id],
                    dur=durs["vo"],
                    scene=slug,
                    camera="MCU",
                    frame=_frame_for(packet, finding, lean),
                )
            elif si == 1 and fiction:
                extra = _dialogue(theme, vantage, lean, hole)
                draft.add(
                    kind="dialogue",
                    bid=f"{finding.id}-d{si+1}",
                    text=extra,
                    fids=[finding.id],
                    dur=durs["dialogue"],
                    scene=slug,
                    camera="OTS",
                    frame=_frame_for_theme(theme, vantage, lean),
                )
            else:
                spoken = f"NARRATOR\n{hole}" if not fiction else _dialogue(theme, vantage, lean, hole)
                draft.add(
                    kind="vo",
                    bid=f"{finding.id}-v{si+1}",
                    text=spoken,
                    fids=[finding.id],
                    dur=durs["vo"],
                    scene=slug,
                    camera="MCU",
                    frame=_frame_for(packet, finding, lean) if fiction else "",
                )
            if not fiction and si == per - 1:
                draft.add(
                    kind="interview",
                    bid=f"{finding.id}-q",
                    text=asked,
                    fids=[finding.id],
                    dur=durs["interview"],
                    scene=slug,
                    camera="TWO-SHOT",
                )
    if with_close:
        link = receipt.causal_links[0]
        known = {f.id for f in receipt.findings}
        cite = [fid for fid in (link.from_id, link.to_id) if fid in known]
        if cite:
            close_slug = (
                "INT. WATCH CLIPBOARD - NIGHT"
                if fiction and vantage == "pilot"
                else "INT. KITCHEN TABLE - NIGHT"
                if fiction and vantage == "family"
                else "INT. BRIDGE / CLIPBOARD - NIGHT"
                if fiction and vantage == "ship"
                else "INT. MAP-TABLE ROOM - NIGHT"
                if fiction
                else "STUDIO — THE HOLE"
            )
            close_vo = _close_frame(packet) + _close_vo(link.claim, lean, cite)
            draft.add(kind="heading", bid=f"{link.id}-h", text=close_slug, fids=cite, dur=durs["heading"], scene=close_slug)
            draft.add(
                kind="action",
                bid=f"{link.id}-a",
                text=_close_frame(packet).strip() or "Two dated cards on a table. No arrow drawn.",
                fids=cite,
                dur=durs["action"],
                scene=close_slug,
                camera="INSERT",
                frame=_close_frame(packet).strip(),
            )
            spoken = _dialogue("fact", vantage, lean, close_vo) if fiction else f"NARRATOR\n{close_vo}"
            draft.add(
                kind="vo",
                bid=link.id,
                text=spoken,
                fids=cite,
                dur=durs["close"],
                scene=close_slug,
                camera="MCU",
                frame=_close_frame(packet).strip(),
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
    packet.beats = beats
    packet.script = "\n".join(lines).strip() + "\n"
    return packet
