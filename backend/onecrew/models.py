from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Stamp = Literal["grounded", "mainstream", "fringe"]
ParallelStatus = Literal["hit", "miss", "n/a"]
Independent = Literal["yes", "no", "missing"]
Propaganda = Literal["yes", "no", "missing"]
Collision = Literal["yes", "no", "missing"]
CollisionKind = Literal["same_script", "near_script", "missing"]
Footage = Literal["sourced", "imagen", "missing"]
Depth = Literal["1y", "2-3y", "5y", "decade", "few_decades", "pre-1980_pre-internet"]
Cut = Literal[
    "tiktok-length",
    "shorts",
    "weekly_update",
    "one_time_short_episode",
    "full_length_documentary",
    "feature_film",
]
Platform = Literal[
    "tiktok",
    "youtube",
    "youtube_shorts",
    "instagram_reels",
    "instagram_stories",
    "instagram_feed",
    "facebook_reels",
    "facebook_feed",
    "threads",
    "podcast",
]
ScriptLean = Literal[
    "centered_independent",
    "left",
    "right",
    "far_right",
    "far_left",
    "unhinged_fringe",
]
LinkStamp = Literal["grounded", "missing"]
Disposition = Literal["READY", "HOLD"]
PacketStatus = Literal["ready", "hold", "running"]
ShiftStatus = Literal["running", "completed", "failed"]

STAMPS = frozenset({"grounded", "mainstream", "fringe"})
INDEPENDENT = frozenset({"yes", "no", "missing"})
PROPAGANDA = frozenset({"yes", "no", "missing"})
COLLISIONS = frozenset({"yes", "no", "missing"})
COLLISION_KINDS = frozenset({"same_script", "near_script", "missing"})
FOOTAGES = frozenset({"sourced", "imagen", "missing"})
DEPTHS = ("1y", "2-3y", "5y", "decade", "few_decades", "pre-1980_pre-internet")
CUTS = (
    "tiktok-length",
    "shorts",
    "weekly_update",
    "one_time_short_episode",
    "full_length_documentary",
    "feature_film",
)
PLATFORMS = (
    "tiktok",
    "youtube",
    "youtube_shorts",
    "instagram_reels",
    "instagram_stories",
    "instagram_feed",
    "facebook_reels",
    "facebook_feed",
    "threads",
    "podcast",
)
SCRIPT_LEANS = (
    "centered_independent",
    "left",
    "right",
    "far_right",
    "far_left",
    "unhinged_fringe",
)
NONFICTION_CUTS = ("weekly_update", "full_length_documentary")
FEATURE_CUTS = ("feature_film",)
MISSING = "missing"


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Rails(BaseModel):
    """Live rails. Missing Parallel, Vertex, or Imagen → fail-closed HOLD."""

    parallel: bool
    vertex: bool
    imagen: bool

    @property
    def missing(self) -> list[str]:
        out: list[str] = []
        if not self.parallel:
            out.append("parallel")
        if not self.vertex:
            out.append("vertex")
        if not self.imagen:
            out.append("imagen")
        return out

    @property
    def present(self) -> list[str]:
        out: list[str] = []
        if self.parallel:
            out.append("parallel")
        if self.vertex:
            out.append("vertex")
        if self.imagen:
            out.append("imagen")
        return out

    @property
    def ok(self) -> bool:
        return not self.missing


class Finding(BaseModel):
    id: str
    claim: str
    stamp: Stamp
    parallel_url: str | None = None
    parallel_status: ParallelStatus
    note: str
    # Mainstream attribution. Separate fields — not Gemini note text.
    # Filled only when Parallel returned a sourceable hit. Otherwise "missing".
    lean: str = MISSING
    lean_url: str | None = None
    interests: str | list[str] = MISSING
    interests_url: str | None = None
    who_repeats: str | list[str] = MISSING
    who_repeats_url: str | None = None
    # Cited-source ownership. Parallel-sourced or missing. Not Gemini note text.
    independent: Independent = MISSING
    independent_url: str | None = None
    vested_interest: str | list[str] = MISSING
    vested_interest_url: str | None = None
    # Campaign line. Parallel-sourced issuer or missing. Not Gemini tone.
    propaganda: Propaganda = MISSING
    propaganda_url: str | None = None
    propaganda_issuer: str = MISSING
    when: str = ""


class CausalLink(BaseModel):
    """This-led-to-that. Grounded only if Parallel sourced the link. Else missing."""

    id: str
    from_id: str
    to_id: str
    claim: str
    stamp: LinkStamp
    parallel_url: str | None = None


class ScriptBeat(BaseModel):
    id: str
    start: str
    duration_s: int
    act: str = ""
    scene: str = ""
    kind: str = "vo"
    vo: str
    camera: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    frame: str = ""
    collision: Collision = MISSING
    collision_url: str | None = None
    collision_title: str = MISSING
    collision_kind: CollisionKind = MISSING


class CollisionRow(BaseModel):
    """Existing media whose script/narration matches a VO beat. Not a clearance."""

    beat_id: str
    collision: Collision = MISSING
    url: str | None = None
    title: str = MISSING
    kind: CollisionKind = MISSING


class ShotFrame(BaseModel):
    id: str
    shot: str
    source_refs: list[str] = Field(default_factory=list)
    image_href: str = ""
    imagen: bool = False
    beat_id: str = ""
    duration_s: int = 0
    key_frame: bool = False
    shot_no: int = 0
    camera: str = ""
    line: str = ""
    footage: Footage = MISSING
    footage_url: str | None = None
    footage_title: str = MISSING
    kind: str = ""


class Receipt(BaseModel):
    packet_id: str
    written: bool = False
    findings: list[Finding] = Field(default_factory=list)
    disposition: Disposition
    hold_reason: str | None = None
    invented_source: bool = False
    collage: bool = False
    invented_stamp: bool = False
    invented_lean: bool = False
    causal_links: list[CausalLink] = Field(default_factory=list)

    @property
    def parallel_hit(self) -> bool:
        return any(f.parallel_status == "hit" for f in self.findings)

    @property
    def parallel_miss(self) -> bool:
        return any(f.parallel_status == "miss" for f in self.findings)


class Packet(BaseModel):
    id: str
    topic: str = ""
    platform: Platform | None = None
    depth: Depth | None = None
    cut: Cut | None = None
    script_lean: ScriptLean | None = None
    tell: str = ""
    tone: str = ""
    hook: str
    script: str
    status: PacketStatus = "ready"
    receipt: Receipt | None = None
    beats: list[ScriptBeat] = Field(default_factory=list)
    frames: list[ShotFrame] = Field(default_factory=list)
    shift_id: str | None = None
    collisions: list[CollisionRow] = Field(default_factory=list)
    collision_disposition: Disposition = "HOLD"
    collision_hold_reason: str | None = None


class ShiftRecord(BaseModel):
    id: str
    goal: str
    status: ShiftStatus = "running"
    started_at: str
    finished_at: str | None = None
    engine: str
    model: str
    packet_id: str
    platform: Platform | None = None
    depth: Depth | None = None
    cut: Cut | None = None
    script_lean: ScriptLean | None = None
    tell: str = ""
    tone: str = ""
    topic: str = ""
    rails: Rails | None = None
    error: str | None = None
    store_backend: str = "memory"
