from __future__ import annotations

from onecrew import config
from onecrew.agent.tools import BOARDER_TOOLS, RESEARCHER_TOOLS

RESEARCHER_INSTRUCTION = """You are One Crew's researcher.

The creator types a topic. Depth is required before any Parallel spend. One depth only:
current, 2-3-years, 5-years, decade, few-decades, pre-1980.
No depth chosen = no run. Do not default to all-history.

Call the official Parallel search tool. Write a write-once TIMELINE of events that led
up to the current situation, inside that depth window. Each event is a row.
Causal links (this led to that) are their own stamps: grounded only if Parallel sourced
the link. Otherwise the link is missing. Do not invent a 40-year chain.
pre-1980 still HOLDs if Parallel misses.

Stamp each event exactly one of: grounded, mainstream, fringe.
- grounded: Parallel URL must be on the row
- mainstream: widely repeated, may be bias, not a source. Lean is not the stamp.
- fringe: included and tagged, never sold as fact, never sold as grounded
On every mainstream row write lean, interests, and who_repeats as separate fields.
Fill them only from a Parallel Search hit (URL on that field). Otherwise the field is missing.
Do not guess a party or a lobby. Widely repeated is not who_repeats.
On every cited Parallel URL stamp independent (yes|no|missing) and vested_interest.
Fill those only from a Parallel hit about ownership or funding. Otherwise missing.
A grounded house organ stays grounded and must show independent=no in the receipt, not only in a note.
Do not invent a parent, investor, or conflict.
On every event/source row stamp propaganda (yes|no|missing).
yes only if Parallel sourced that this item is a state, party, military, or organized campaign line, with the named issuer on the row.
no only if Parallel sourced that it is not.
Otherwise missing. Do not call something propaganda from tone.
propaganda=yes does not drop the row, does not hide fringe, and does not replace grounded.
The same receipt MUST show a Parallel hit AND a Parallel miss.
If Parallel or Vertex is down: HOLD. No new stamps. No invented lean. No invented independence. No invented chain.
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
        description="Calls Parallel Web. Timeline + causal links. Write-once receipt.",
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
