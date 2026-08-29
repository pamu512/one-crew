from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Stamp = Literal["grounded", "mainstream", "fringe"]
ParallelStatus = Literal["hit", "miss", "n/a"]
Independent = Literal["yes", "no", "missing"]
Depth = Literal["current", "2-3-years", "5-years", "decade", "few-decades", "pre-1980"]
LinkStamp = Literal["grounded", "missing"]
Disposition = Literal["READY", "HOLD"]
PacketStatus = Literal["ready", "hold", "running"]
ShiftStatus = Literal["running", "completed", "failed"]

STAMPS = frozenset({"grounded", "mainstream", "fringe"})
INDEPENDENT = frozenset({"yes", "no", "missing"})
DEPTHS = ("current", "2-3-years", "5-years", "decade", "few-decades", "pre-1980")
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
    when: str = ""


class CausalLink(BaseModel):
    """This-led-to-that. Grounded only if Parallel sourced the link. Else missing."""

    id: str
    from_id: str
    to_id: str
    claim: str
    stamp: LinkStamp
    parallel_url: str | None = None


class ShotFrame(BaseModel):
    id: str
    shot: str
    source_refs: list[str] = Field(default_factory=list)
    image_href: str
    imagen: bool = False


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
    depth: Depth | None = None
    hook: str
    script: str
    status: PacketStatus = "ready"
    receipt: Receipt | None = None
    frames: list[ShotFrame] = Field(default_factory=list)
    shift_id: str | None = None


class ShiftRecord(BaseModel):
    id: str
    goal: str
    status: ShiftStatus = "running"
    started_at: str
    finished_at: str | None = None
    engine: str
    model: str
    packet_id: str
    depth: Depth | None = None
    topic: str = ""
    rails: Rails | None = None
    error: str | None = None
    store_backend: str = "memory"
