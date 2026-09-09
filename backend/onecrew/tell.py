from __future__ import annotations

from onecrew.models import FEATURE_CUTS, NONFICTION_CUTS, Cut

TELL_EXAMPLES = (
    "Host-only desk read of the last year of US recession prints",
    "No guest. No panel. Just the cited prints.",
    "Walk USREC, then payrolls, then GDP — host only",
    "One family in Bandar Abbas, kitchen radio on",
    "Thriller on a tanker crossing Hormuz that might get hit",
    "Weekly news desk, host only",
    "Historical drama through one port family",
    "Narrator-led global overview of the US and Iran",
)

SEED_TELL = TELL_EXAMPLES[0]


class TellRequiredError(ValueError):
    """No tell chosen = no run."""


def require_tell(raw: str | None) -> str:
    chosen = (raw or "").strip()
    if not chosen:
        raise TellRequiredError("No tell chosen = no run")
    return chosen


def tell_examples_payload() -> list[str]:
    return list(TELL_EXAMPLES)


def invents_frame(*, cut: Cut | None, tell: str) -> bool:
    """Fiction vs news is the cut. Shorts may invent only when the tell asks for a story."""
    if cut in NONFICTION_CUTS:
        return False
    if cut in FEATURE_CUTS:
        return True
    return _wants_story(tell)


def wants_no_forecast_theater(tell: str) -> bool:
    """Tell asked for cite-faithful realized prints. Forecast/outlook is not the spine."""
    text = (tell or "").lower()
    return any(
        cue in text
        for cue in (
            "no forecast theater",
            "forecast theater",
            "no forecast",
            "realized print",
            "cited print",
            "cite-faithful",
            "cite faithful",
        )
    )


def tell_lane(tell: str) -> str:
    """Craft hint from free text. Not an enum and not a validator."""
    text = (tell or "").lower()
    if any(key in text for key in ("pilot", "night watch", "watch officer")):
        return "pilot"
    if any(key in text for key in ("tanker", "ship", "bridge", "crew", "might get hit")):
        return "ship"
    if any(key in text for key in ("family", "kitchen", "bandar", "mother", "port family")):
        return "family"
    return "host"


def _wants_story(tell: str) -> bool:
    text = (tell or "").lower()
    news = ("narrator", "news desk", "host only", "overview", "reporter", "weekly news")
    story = ("family", "kitchen", "thriller", "drama", "tanker", "ship", "pilot", "night watch", "might get hit")
    has_story = any(key in text for key in story)
    has_news = any(key in text for key in news)
    if has_story and not has_news:
        return True
    if has_news and not has_story:
        return False
    return has_story
