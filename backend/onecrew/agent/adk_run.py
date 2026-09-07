"""Run Google ADK Agent / SequentialAgent. Live when Vertex+ADC is up."""

from __future__ import annotations

import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor

from onecrew import config
from onecrew.models import GradeArtifact, RoomGrade
from onecrew.vertex_client import VertexDownError

_APP = "onecrew"


def _builders() -> dict:
    from onecrew.agent.adk_agents import build_room, build_script_writer, build_writer_room

    return {
        "script_writer": build_script_writer,
        "room": build_room,
        "writer_room": build_writer_room,
    }


async def _run_agent_async(agent, prompt: str) -> str:
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=agent, app_name=_APP)
    session = await runner.session_service.create_session(app_name=_APP, user_id="shift")
    msg = types.Content(role="user", parts=[types.Part(text=prompt)])
    chunks: list[str] = []
    async for event in runner.run_async(user_id="shift", session_id=session.id, new_message=msg):
        content = getattr(event, "content", None)
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if text and not getattr(part, "thought", False):
                chunks.append(str(text))
    text = "".join(chunks).strip()
    if not text:
        raise VertexDownError("ADK returned empty text")
    return text


def _run_sync(coro: object) -> str:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # type: ignore[arg-type]
    # ponytail: FastAPI may already own the loop. Thread isolate one ADK turn.
    # Ceiling: one extra thread per call. Upgrade: native async shift.
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result(timeout=180)


def live_adk_text(name: str, prompt: str) -> str:
    """Real InMemoryRunner when Vertex+ADC is up. Tests do not call this."""
    if not (prompt or "").strip():
        raise VertexDownError("empty prompt")
    if not config.has_vertex() or not config.has_adc():
        raise VertexDownError("Vertex/ADC missing")
    builder = _builders().get(name)
    if builder is None:
        raise VertexDownError(f"unknown ADK agent {name}")
    try:
        return _run_sync(_run_agent_async(builder(), prompt))
    except VertexDownError:
        raise
    except Exception as exc:
        raise VertexDownError(f"ADK {name} down: {exc}") from exc


def artifact_prompt(artifact: GradeArtifact) -> str:
    pack = (artifact.research_pack or artifact.research_pack_summary or "").strip()
    stamps = artifact.findings_block()
    return (
        "Grade this deliverable. Vote ship or recut.\n"
        "Recut requires why: not_enough_information | other.\n"
        "Bar: compelling cite-faithful timed VO. Producer/director grades quality + cites. "
        "Mint READY is not the ship bar. Floor never posts.\n"
        "Invent means not in Parallel cites (hit URL + excerpt/summary) and not on a stamped finding from those cites. "
        "If VO prints or finding ids match a Parallel cite or stamped finding, ship. "
        "A series nickname or rule name is pack-faithful when a cite or finding carries that series print. "
        "Absence from a short research_pack_summary is not invention.\n"
        "Flexible weave is correct (chronological, outcome-first, or tell/tone stance). "
        "Do not recut because first trigger is missing from cold-open or beat 1.\n"
        "Do not speak or require pack schema/slot ids in narration.\n"
        "Recut only for inventing stats, empty script, leftover templates, or claims without "
        "research_pack or finding support.\n"
        "Prefer ship when the script is non-empty, leftover-free, and cites resolve to findings.\n"
        "Return JSON only, one of:\n"
        "{\"vote\":\"ship\"}\n"
        "{\"vote\":\"recut\",\"recut_reason\":\"not_enough_information\",\"recut_detail\":\"...\"}\n"
        "{\"vote\":\"recut\",\"recut_reason\":\"other\",\"recut_detail\":\"...\"}\n"
        f"packet_id={artifact.packet_id}\n"
        f"research_pack:\n{pack}\n"
        f"parallel_cites:\n{artifact.parallel_cites or ''}\n"
        f"stamped_findings:\n{stamps}\n"
        f"research_pack_summary:\n{artifact.research_pack_summary}\n"
        f"script:\n{artifact.script}\n"
    )


def parse_room_grade(raw: str) -> RoomGrade:
    text = (raw or "").strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("ADK room returned no vote JSON") from None
        data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("ADK room vote must be an object")
    vote = data.get("vote")
    if vote not in {"ship", "recut"}:
        raise ValueError("ADK room vote must be ship or recut")
    reason = data.get("recut_reason")
    detail = str(data.get("recut_detail") or "")
    if vote == "recut" and reason not in {"not_enough_information", "other"}:
        # ponytail: model may copy the enum pipe. Coerce so RoomGrade cannot crash the spend.
        if reason:
            detail = f"{reason} {detail}".strip()
        reason = "other"
    return RoomGrade(
        vote=vote,
        recut_reason=reason,
        recut_detail=detail,
    )


def live_adk_writer(prompt: str) -> str:
    return live_adk_text("script_writer", prompt)


def live_adk_room(artifact: GradeArtifact) -> RoomGrade:
    return parse_room_grade(live_adk_text("room", artifact_prompt(artifact)))
