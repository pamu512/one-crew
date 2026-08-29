from __future__ import annotations

from onecrew.cut import CutRequiredError, require_cut
from onecrew.depth import DepthRequiredError, require_depth
from onecrew.models import PLATFORMS, SCRIPT_LEANS, Cut, Depth, Platform, ScriptLean
from onecrew.tell import TellRequiredError, require_tell


class TopicRequiredError(ValueError):
    """No topic chosen = no run."""


class PlatformRequiredError(ValueError):
    """No platform chosen = no run."""


class ScriptLeanRequiredError(ValueError):
    """No script lean chosen = no run."""


PickError = (
    TopicRequiredError,
    PlatformRequiredError,
    CutRequiredError,
    DepthRequiredError,
    ScriptLeanRequiredError,
    TellRequiredError,
)


def require_topic(raw: str | None) -> str:
    chosen = (raw or "").strip()
    if not chosen:
        raise TopicRequiredError("No topic chosen = no run")
    return chosen


def require_platform(raw: str | None) -> Platform:
    chosen = (raw or "").strip()
    if chosen not in PLATFORMS:
        raise PlatformRequiredError("No platform chosen = no run")
    return chosen  # type: ignore[return-value]


def require_script_lean(raw: str | None) -> ScriptLean:
    chosen = (raw or "").strip()
    if chosen not in SCRIPT_LEANS:
        raise ScriptLeanRequiredError("No script lean chosen = no run")
    return chosen  # type: ignore[return-value]


def require_picks(
    topic: str | None,
    platform: str | None,
    cut: str | None,
    depth: str | None,
    script_lean: str | None,
    tell: str | None,
) -> tuple[str, Platform, Cut, Depth, ScriptLean, str]:
    """Order: topic, platform, length, depth, script lean, tell. Any missing pick = no run."""
    return (
        require_topic(topic),
        require_platform(platform),
        require_cut(cut),
        require_depth(depth),
        require_script_lean(script_lean),
        require_tell(tell),
    )


def platforms_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": key} for key in PLATFORMS]


def leans_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": key} for key in SCRIPT_LEANS]
