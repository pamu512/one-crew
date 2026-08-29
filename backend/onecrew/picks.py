from __future__ import annotations

from onecrew.cut import CutRequiredError, require_cut
from onecrew.depth import DepthRequiredError, require_depth
from onecrew.models import (
    FEATURE_CUTS,
    GENRES,
    NONFICTION_CUTS,
    PLATFORMS,
    SCRIPT_LEANS,
    VANTAGES,
    Cut,
    Depth,
    Genre,
    Platform,
    ScriptLean,
    Vantage,
)


class TopicRequiredError(ValueError):
    """No topic chosen = no run."""


class PlatformRequiredError(ValueError):
    """No platform chosen = no run."""


class ScriptLeanRequiredError(ValueError):
    """No script lean chosen = no run."""


class GenreRequiredError(ValueError):
    """No genre chosen = no run."""


class VantageRequiredError(ValueError):
    """No vantage chosen = no run."""


class TellPairingError(ValueError):
    """Illegal cut + genre pair = no run."""


PickError = (
    TopicRequiredError,
    PlatformRequiredError,
    CutRequiredError,
    DepthRequiredError,
    ScriptLeanRequiredError,
    GenreRequiredError,
    VantageRequiredError,
    TellPairingError,
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


def require_genre(raw: str | None) -> Genre:
    chosen = (raw or "").strip()
    if chosen not in GENRES:
        raise GenreRequiredError("No genre chosen = no run")
    return chosen  # type: ignore[return-value]


def require_vantage(raw: str | None) -> Vantage:
    chosen = (raw or "").strip()
    if chosen not in VANTAGES:
        raise VantageRequiredError("No vantage chosen = no run")
    return chosen  # type: ignore[return-value]


def require_tell_pairing(cut: Cut, genre: Genre) -> None:
    """Documentary/news cuts are nonfiction. Feature film is fiction. Fail closed."""
    if cut in NONFICTION_CUTS and genre != "nonfiction":
        raise TellPairingError(
            "A thriller documentary is rejected. "
            "full_length_documentary and weekly_update require genre=nonfiction"
        )
    if cut in FEATURE_CUTS and genre == "nonfiction":
        raise TellPairingError(
            "A nonfiction feature is rejected; that is a documentary. "
            "Use full_length_documentary. feature_film requires a fiction genre"
        )


def require_picks(
    topic: str | None,
    platform: str | None,
    cut: str | None,
    depth: str | None,
    script_lean: str | None,
    genre: str | None,
    vantage: str | None,
) -> tuple[str, Platform, Cut, Depth, ScriptLean, Genre, Vantage]:
    """Order: topic, platform, length, depth, script lean, tell. Any missing pick = no run."""
    chosen_topic = require_topic(topic)
    chosen_platform = require_platform(platform)
    chosen_cut = require_cut(cut)
    chosen_depth = require_depth(depth)
    chosen_lean = require_script_lean(script_lean)
    chosen_genre = require_genre(genre)
    chosen_vantage = require_vantage(vantage)
    require_tell_pairing(chosen_cut, chosen_genre)
    return (
        chosen_topic,
        chosen_platform,
        chosen_cut,
        chosen_depth,
        chosen_lean,
        chosen_genre,
        chosen_vantage,
    )


def platforms_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": key} for key in PLATFORMS]


def leans_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": key} for key in SCRIPT_LEANS]


def genres_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": key} for key in GENRES]


def vantages_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": key} for key in VANTAGES]
