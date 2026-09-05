"""Vertex writes the timed VO from the Parallel research pack + picks. Parallel does not write VO."""

from __future__ import annotations

from onecrew.models import Packet
from onecrew.script import write_script
from onecrew.vertex_client import generate_script


def write_vo_from_pack(packet: Packet) -> Packet:
    """Existing Vertex client. Stub generate_script in tests. Pack-faithful, no hardcoded prints."""
    return write_script(packet)


__all__ = ["write_vo_from_pack", "generate_script"]
