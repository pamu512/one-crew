"""ADK CLI entry (`adk web` / `adk run`)."""

from onecrew.agent.adk_agents import build_root_agent, load_root_agent

root_agent = None


def _load():
    global root_agent
    root_agent = load_root_agent()
    return root_agent


# ADK looks for root_agent. Build lazily so `import` does not call Vertex.
try:
    root_agent = build_root_agent()
except Exception:  # noqa: BLE001
    root_agent = None
