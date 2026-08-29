from __future__ import annotations

from onecrew import config
from onecrew.agent.tools import BOARDER_TOOLS, RESEARCHER_TOOLS

RESEARCHER_INSTRUCTION = """You are One Crew's researcher.

Call the official Parallel search tool. Write findings for a write-once receipt.
Stamp each finding exactly one of: grounded, mainstream, fringe.
- grounded: Parallel URL must be on the row
- mainstream: widely repeated, may be bias, not a source
- fringe: included and tagged, never sold as fact
The same receipt MUST show a Parallel hit AND a Parallel miss.
If Parallel is down: HOLD. Do not invent a source. Do not invent a stamp.
You do not post. You do not publish.
"""

BOARDER_INSTRUCTION = """You are One Crew's boarder.

Make four real shot frames from the script plus the Parallel refs on the receipt.
Real camera setups. Not a mood dump. Not a collage.
If Vertex or Imagen is down: HOLD. Do not invent frames.
You do not post. You do not publish.
"""


def build_researcher():
    from google.adk.agents.llm_agent import Agent

    return Agent(
        model=config.GEMINI_MODEL,
        name="researcher",
        description="Calls Parallel Web. Stamps grounded / mainstream / fringe. Write-once receipt.",
        instruction=RESEARCHER_INSTRUCTION,
        tools=RESEARCHER_TOOLS,
    )


def build_boarder():
    from google.adk.agents.llm_agent import Agent

    return Agent(
        model=config.GEMINI_MODEL,
        name="boarder",
        description="Imagen frames from script + Parallel refs. Real shots, not a mood dump.",
        instruction=BOARDER_INSTRUCTION,
        tools=BOARDER_TOOLS,
    )


def build_root_agent():
    """Gemini ADK crew: researcher then boarder. Floor is not in the crew."""
    from google.adk.agents.sequential_agent import SequentialAgent

    return SequentialAgent(
        name="one_crew",
        description="Researcher (Parallel) then boarder (Imagen). Floor never posts.",
        sub_agents=[build_researcher(), build_boarder()],
    )


root_agent = None


def load_root_agent():
    global root_agent
    if root_agent is None:
        root_agent = build_root_agent()
    return root_agent
