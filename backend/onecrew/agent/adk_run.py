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
    return _run_sync(_run_agent_async(builder(), prompt))


def artifact_prompt(artifact: GradeArtifact) -> str:
    return (
        "Grade this deliverable. Vote ship or recut.\n"
        "Recut requires why: not_enough_information | other.\n"
        "Bar: cite-faithful script + storyboard for the end user. Floor never posts.\n"
        "Return JSON only: {\"vote\":\"ship\"} or "
        "{\"vote\":\"recut\",\"recut_reason\":\"not_enough_information|other\","
        "\"recut_detail\":\"...\"}.\n"
        f"packet_id={artifact.packet_id}\n"
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
    return RoomGrade(
        vote=vote,
        recut_reason=data.get("recut_reason"),
        recut_detail=str(data.get("recut_detail") or ""),
    )


def live_adk_writer(prompt: str) -> str:
    return live_adk_text("script_writer", prompt)


def live_adk_room(artifact: GradeArtifact) -> RoomGrade:
    return parse_room_grade(live_adk_text("room", artifact_prompt(artifact)))
