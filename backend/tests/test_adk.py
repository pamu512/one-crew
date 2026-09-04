from pathlib import Path

import pytest

from onecrew import config
from onecrew.parallel_client import search

pytest.importorskip("google.adk")

from onecrew.agent.adk_agents import build_claimer, build_critic, build_root_agent  # noqa: E402


def test_adk_crew_builds_with_vertex_flash() -> None:
    assert config.GEMINI_MODEL == "gemini-3.5-flash"
    src = Path(config.__file__).read_text()
    assert "gemini-3.5-flash" in src
    agent = build_root_agent()
    assert agent.name == "one_crew"
    names = [child.name for child in agent.sub_agents]
    assert names == ["researcher", "boarder"]
    assert "floor" not in names
    # Claimer + Critic are on the live shift path; ADK builders stay loadable.
    claimer = build_claimer()
    critic = build_critic()
    assert claimer.name == "claimer"
    assert critic.name == "critic"
    assert "floor" not in {claimer.name, critic.name}
    client_src = Path(search.__code__.co_filename).read_text()
    assert "from parallel import Parallel" in client_src
    assert "client.search(" in client_src
    assert "client.extract(" in client_src
    assert "client.task_run.create(" in client_src
    assert 'processor="pro"' in client_src or "processor: str = \"pro\"" in client_src
    assert "monitors.create" not in client_src
    assert "monitor.create" not in client_src
