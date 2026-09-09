from __future__ import annotations

from typing import Any

from onecrew import config
from onecrew.imagen_client import ImagenDownError, generate_frames
from onecrew.parallel_client import ParallelDownError, extract, run_task, search
from onecrew.store import store


def get_packet(packet_id: str) -> dict[str, Any]:
    packet = store.get_packet(packet_id)
    if packet is None:
        return {"error": "packet not found"}
    return packet.model_dump()


def parallel_search(objective: str, query: str) -> dict[str, Any]:
    """Researcher tool. Official Parallel Search. Spends."""
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


def parallel_extract(urls: list[str], objective: str) -> dict[str, Any]:
    """Researcher tool. Official Parallel Extract after Search URLs. Spends."""
    try:
        result = extract(urls=urls, objective=objective)
    except ParallelDownError as exc:
        return {"ok": False, "error": str(exc), "results": [], "errors": []}
    rows = []
    for item in getattr(result, "results", None) or []:
        rows.append(
            {
                "url": getattr(item, "url", None),
                "title": getattr(item, "title", None),
                "excerpts": list(getattr(item, "excerpts", None) or []),
            }
        )
    fails = []
    for err in getattr(result, "errors", None) or []:
        fails.append(
            {
                "url": getattr(err, "url", None),
                "error_type": getattr(err, "error_type", "error"),
            }
        )
    return {"ok": True, "results": rows, "errors": fails}


def parallel_task(prompt: str) -> dict[str, Any]:
    """Researcher tool. Official Parallel Task (pro). Spends. No ultra."""
    try:
        result = run_task(prompt=prompt, processor="pro")
    except ParallelDownError as exc:
        return {"ok": False, "error": str(exc), "content": "", "basis": []}
    output = getattr(result, "output", None)
    content = getattr(output, "content", "") if output else ""
    basis = []
    for field in getattr(output, "basis", None) or []:
        cites = []
        for citation in getattr(field, "citations", None) or []:
            cites.append(getattr(citation, "url", None) or getattr(citation, "title", None))
        basis.append({"field": getattr(field, "field", ""), "citations": [c for c in cites if c]})
    return {"ok": True, "content": str(content or ""), "basis": basis}


def imagen_shots(script: str, refs: str) -> dict[str, Any]:
    """Boarder tool. Vertex Imagen. Spends. Uses the returned images."""
    prompt = (
        f"One official-series still or infographic from this timed VO beat, not photoreal event B-roll. "
        f"Script: {script}. Refs: {refs}"
    )
    try:
        result = generate_frames(prompt=prompt, number_of_images=1)
    except ImagenDownError as exc:
        return {"ok": False, "error": str(exc), "frames": 0}
    images = getattr(result, "generated_images", None) or getattr(result, "images", None) or []
    return {"ok": True, "frames": len(images), "used_return": True}


def verify_print_in_cite_tool(claim: dict, bag: dict) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_print_in_cite

    return verify_print_in_cite(Claim(**claim), CiteBag(**bag)).model_dump()


def verify_payrolls_realized_ces_tool(claim: dict, bag: dict) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_payrolls_realized_ces

    return verify_payrolls_realized_ces(Claim(**claim), CiteBag(**bag)).model_dump()


def verify_usrec_smash_tool(usrec_claim: dict, bag: dict, payrolls_claim: dict | None = None) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_usrec_smash

    payrolls = Claim(**payrolls_claim) if payrolls_claim else None
    return verify_usrec_smash(Claim(**usrec_claim), payrolls, CiteBag(**bag)).model_dump()


def verify_gdp_bars_tool(claim: dict, bag: dict) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_gdp_bars

    return verify_gdp_bars(Claim(**claim), CiteBag(**bag)).model_dump()


def verify_u3_ces_tool(claim: dict, bag: dict) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_u3_ces

    return verify_u3_ces(Claim(**claim), CiteBag(**bag)).model_dump()


def verify_sahm_cell_tool(claim: dict, bag: dict) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_sahm_cell

    return verify_sahm_cell(Claim(**claim), CiteBag(**bag)).model_dump()


def verify_claim_set_tool(claims: list[dict], bag: dict) -> dict[str, Any]:
    from onecrew.verify import Claim, CiteBag, verify_claim_set

    return verify_claim_set([Claim(**row) for row in claims], CiteBag(**bag)).model_dump()


RESEARCHER_TOOLS = [get_packet, parallel_search, parallel_extract, parallel_task]
BOARDER_TOOLS = [get_packet, imagen_shots]
CRITIC_TOOLS = [
    verify_print_in_cite_tool,
    verify_payrolls_realized_ces_tool,
    verify_usrec_smash_tool,
    verify_gdp_bars_tool,
    verify_u3_ces_tool,
    verify_sahm_cell_tool,
    verify_claim_set_tool,
]


# Keep seed id reachable for tools without importing seed (avoids cycle in ADK load).
DEFAULT_PACKET_ID = config.SEED_PACKET_ID
