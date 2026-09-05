"""ADK script_writer turns the Parallel pack + picks into timed VO. Parallel does not write VO."""

from __future__ import annotations

from onecrew import config
from onecrew.models import Packet
from onecrew.script import write_script
from onecrew.vertex_client import generate_script


def run_adk_writer(prompt: str) -> str:
    """ADK script_writer. Tests stub this. No ADC → existing Vertex client."""
    if config.has_vertex() and config.has_adc():
        from onecrew.agent.adk_run import live_adk_writer

        return live_adk_writer(prompt)
    return generate_script(prompt)


def write_vo_from_pack(packet: Packet) -> Packet:
    """ADK writer from the pack. Stub run_adk_writer in tests. Pack-faithful, no hardcoded prints."""
    return write_script(packet, writer=run_adk_writer)


__all__ = ["write_vo_from_pack", "run_adk_writer", "generate_script"]
