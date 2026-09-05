from __future__ import annotations

from onecrew.models import FEATURE_CUTS, Cut

TONE_EXAMPLES = (
    "News desk",
    "Make the viewer think",
    "Question the decisions",
    "Personal take",
    "On the cited print",
)

SEED_TONE = TONE_EXAMPLES[-1]


class ToneRequiredError(ValueError):
    """No tone chosen = no run."""


def require_tone(*, cut: Cut | None, tone: str | None) -> str:
    chosen = (tone or "").strip()
    if cut in FEATURE_CUTS:
        return chosen
    if not chosen:
        raise ToneRequiredError("No tone chosen = no run")
    return chosen


def tone_examples_payload() -> list[str]:
    return list(TONE_EXAMPLES)


def tone_lane(tone: str) -> str:
    """Craft hint from free text. Not an enum and not a validator."""
    text = (tone or "").lower()
    if "news desk" in text:
        return "desk"
    if "think" in text:
        return "essay"
    if "question" in text:
        return "interrogative"
    if "personal" in text:
        return "first_person"
    return "record"


def apply_tone(line: str, tone: str, *, fiction: bool) -> str:
    if fiction or not (tone or "").strip():
        return line
    lane = tone_lane(tone)
    if lane == "desk":
        return f"From the news desk. {line}"
    if lane == "essay":
        return f"Think past the headline. {line}"
    if lane == "interrogative":
        return f"Question the decision that put this on the air. {line}"
    if lane == "first_person":
        return f"Personal take: {line}"
    return line
