"""Parallel research prompts. Horizon is first-trigger / recent-news, not the floor depth enum."""

from __future__ import annotations

HORIZON_RECENT = "first-trigger-recent-news"
HORIZON_DEEPER = "first-trigger-deeper-history"

# Floor depth ids. Never forwarded to Task/Search as the research horizon.
_DEPTH_ENUM = ("1y", "2-3y", "5y", "decade", "few_decades", "pre-1980_pre-internet")


def research_horizon(*, deeper_history: bool = False) -> str:
    return HORIZON_DEEPER if deeper_history else HORIZON_RECENT


def task_research_prompt(
    topic: str,
    *,
    deeper_history: bool = False,
    missing_ask: str | None = None,
) -> str:
    """Causal / first-trigger Task prompt. Parallel does not decide depth. Parallel does not write VO."""
    ask = (topic or "the topic").strip() or "the topic"
    if deeper_history:
        body = (
            f"The user explicitly demands deeper history on {ask}. "
            f"Find the first event that actually triggered {ask}, going as far back as the sourced record requires. "
            "Then list every subsequent event as chronological bullets. "
            "For each event give a high-confidence basis (cite URL). "
            "Do not decide how far to go from a floor depth enum. "
            "Do not invent sources. Name missing causal links. Use only sourced events."
        )
    else:
        body = (
            f"Find the first event that actually triggered {ask}, scoped to recent news surrounding the topic. "
            "Then list every subsequent event as chronological bullets. "
            "For each event give a high-confidence basis (cite URL). "
            "Do not decide how far back to go beyond that first trigger in recent news. "
            "Do not invent sources. Name missing causal links. Use only sourced events."
        )
    extra = (missing_ask or "").strip()
    if extra:
        body = (
            f"{body} The review room recut for not_enough_information: {extra} "
            "Fetch the missing cites once. Do not invent sources."
        )
    return body


def search_objective(
    topic: str,
    *,
    deeper_history: bool = False,
    fringe: bool = False,
) -> str:
    ask = (topic or "the topic").strip() or "the topic"
    if fringe:
        return f"Unsourced fringe claim in {ask}"
    if deeper_history:
        return (
            f"Deeper-history first-trigger timeline for {ask}. "
            "User demanded deeper history. Do not decide depth from a floor enum."
        )
    return (
        f"First-trigger timeline for {ask} in recent news. "
        "Do not decide how far to go beyond the first trigger."
    )


def search_queries(
    topic: str,
    *,
    tell: str = "",
    deeper_history: bool = False,
) -> list[str]:
    """Named official series when the topic is recession. Never append a floor depth enum."""
    ask = (topic or "topic").strip() or "topic"
    blob = f"{ask} {tell or ''}".lower()
    if "recession" in blob or "usrec" in blob or "payroll" in blob:
        return [
            ask,
            f"{ask} USREC FRED",
            f"{ask} nonfarm payrolls BLS",
            f"{ask} Sahm rule",
        ]
    horizon = "deeper history first trigger" if deeper_history else "first trigger recent news"
    return [ask, f"{ask} {horizon}"]


def extract_objective(topic: str) -> str:
    ask = (topic or "the topic").strip() or "the topic"
    return f"Thesis quotes, ownership, propaganda, and independence text for {ask}"
