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
            id="ranking-hit",
            claim=hit_claim,
            stamp="grounded",
            parallel_url=hit_url,
            parallel_status="hit",
            note="Parallel URL on this row.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
        ),
        Finding(
            id="3am-kitchen",
            claim=mainstream_claim,
            stamp="mainstream",
            parallel_url=None,
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
        ),
        Finding(
            id="nasa-miss",
            claim=miss_claim,
            stamp="fringe",
            parallel_url=None,
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
        ),
    ]


def frames_from_script(packet: Packet, refs: list[str]) -> list[ShotFrame]:
    return [
        ShotFrame(
            id="jar-pour",
            shot="Close-up: refrigerator pickle jar, brine pouring into a shot glass.",
            source_refs=refs,
            image_href="/api/frames/jar-pour",
            imagen=True,
        ),
        ShotFrame(
            id="kitchen-3am",
            shot="Single overhead bulb, kitchen sink, 3:07 on the microwave.",
            source_refs=[],
            image_href="/api/frames/kitchen-3am",
            imagen=True,
        ),
        ShotFrame(
            id="ranking-phone",
            shot="Phone in hand showing the Parallel ranking URL. Not a stock collage.",
            source_refs=refs,
            image_href="/api/frames/ranking-phone",
            imagen=True,
        ),
        ShotFrame(
            id="nasa-empty",
            shot="Search board: NASA pickle juice — no hit. Empty results, not a NASA seal.",
            source_refs=[],
            image_href="/api/frames/nasa-empty",
            imagen=True,
        ),
    ]


# Keep seed id reachable for tools without importing seed (avoids cycle in ADK load).
DEFAULT_PACKET_ID = config.SEED_PACKET_ID
