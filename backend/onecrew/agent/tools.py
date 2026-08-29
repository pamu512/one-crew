from __future__ import annotations

from typing import Any

from onecrew import config
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.models import MISSING, Finding, Packet, ShotFrame
from onecrew.parallel_client import ParallelDownError, search
from onecrew.store import store


def get_packet(packet_id: str) -> dict[str, Any]:
    packet = store.get_packet(packet_id)
    if packet is None:
        return {"error": "packet not found"}
    return packet.model_dump()


def parallel_search(objective: str, query: str) -> dict[str, Any]:
    """Researcher tool. Official Parallel SDK. Spends."""
    try:
        result = search(objective=objective, search_queries=[query])
    except ParallelDownError as exc:
        return {"ok": False, "miss": True, "error": str(exc), "results": []}
    rows = []
    for item in getattr(result, "results", None) or []:
        rows.append(
            {
                "url": getattr(item, "url", None),
                "title": getattr(item, "title", None),
                "excerpts": list(getattr(item, "excerpts", None) or []),
            }
        )
    return {"ok": True, "miss": len(rows) == 0, "results": rows}


def imagen_shots(script: str, refs: str) -> dict[str, Any]:
    """Boarder tool. Vertex Imagen. Spends. Real shots, not a mood dump."""
    prompt = (
        f"Four photoreal shot frames from this short-form script, using only these refs. "
        f"Real camera setups, not a mood board. Script: {script}. Refs: {refs}"
    )
    try:
        generate_frames(prompt=prompt, number_of_images=4)
    except ImagenDownError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, "frames": 4}


RESEARCHER_TOOLS = [get_packet, parallel_search]
BOARDER_TOOLS = [get_packet, imagen_shots]


def findings_from_parallel_rows(
    *,
    hit_url: str | None,
    hit_claim: str,
    mainstream_claim: str,
    miss_claim: str,
) -> list[Finding]:
    """Stamp exactly one of grounded / mainstream / fringe. Hit + miss on the same receipt."""
    if not hit_url:
        return []
    return [
        Finding(
            id="timeline-hit",
            claim=hit_claim,
            stamp="grounded",
            parallel_url=hit_url,
            parallel_status="hit",
            note="Parallel URL on this row.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
            independent=MISSING,
            vested_interest=MISSING,
        ),
        Finding(
            id="timeline-frame",
            claim=mainstream_claim,
            stamp="mainstream",
            parallel_url=None,
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
            independent=MISSING,
            vested_interest=MISSING,
        ),
        Finding(
            id="timeline-miss",
            claim=miss_claim,
            stamp="fringe",
            parallel_url=None,
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
            independent=MISSING,
            vested_interest=MISSING,
        ),
    ]


def frames_from_script(packet: Packet, refs: list[str]) -> list[ShotFrame]:
    from onecrew.cut import frame_count, require_cut

    frames = [
        ShotFrame(
            id="tanker-lane",
            shot="Tanker in a narrow lane, land on both sides.",
            source_refs=refs,
            image_href="/api/frames/tanker-lane",
            imagen=True,
        ),
        ShotFrame(
            id="strait-map",
            shot="Chart table with a strait map and a 2018 date chip.",
            source_refs=refs,
            image_href="/api/frames/strait-map",
            imagen=True,
        ),
        ShotFrame(
            id="oil-share",
            shot="Phone showing the Parallel oil-share URL. Not a collage.",
            source_refs=refs,
            image_href="/api/frames/oil-share",
            imagen=True,
        ),
        ShotFrame(
            id="link-empty",
            shot="Timeline board: causal link missing. No invented chain.",
            source_refs=[],
            image_href="/api/frames/link-empty",
            imagen=True,
        ),
    ]
    if packet.cut:
        return frames[: frame_count(require_cut(packet.cut))]
    return frames


# Keep seed id reachable for tools without importing seed (avoids cycle in ADK load).
DEFAULT_PACKET_ID = config.SEED_PACKET_ID
