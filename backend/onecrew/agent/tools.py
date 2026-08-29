from __future__ import annotations

from typing import Any

from onecrew import config
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.models import MISSING, Finding
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
    """Boarder tool. Vertex Imagen. Spends. Uses the returned images."""
    prompt = (
        f"One photoreal shot from this timed VO beat, not a mood collage. "
        f"Script: {script}. Refs: {refs}"
    )
    try:
        result = generate_frames(prompt=prompt, number_of_images=1)
    except ImagenDownError as exc:
        return {"ok": False, "error": str(exc), "frames": 0}
    images = getattr(result, "generated_images", None) or getattr(result, "images", None) or []
    return {"ok": True, "frames": len(images), "used_return": True}


RESEARCHER_TOOLS = [get_packet, parallel_search]
BOARDER_TOOLS = [get_packet, imagen_shots]


def findings_from_parallel_rows(
    *,
    hit_url: str | None,
    hit_claim: str,
    mainstream_claim: str,
    miss_claim: str,
    hit_title: str = MISSING,
) -> list[Finding]:
    """Stamp exactly one of grounded / mainstream / fringe. Hit + miss on the same receipt."""
    if not hit_url:
        return []
    return [
        Finding(
            id="timeline-hit",
            claim=hit_claim,
            stamp="grounded",
            title=hit_title or MISSING,
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


# Keep seed id reachable for tools without importing seed (avoids cycle in ADK load).
DEFAULT_PACKET_ID = config.SEED_PACKET_ID
