from __future__ import annotations

from onecrew.models import CUTS, Cut, Platform

CUT_LABELS: dict[Cut, str] = {key: key for key in CUTS}

# Cut caps. Surface caps sit on top: a Stories board is not a documentary board.
EVENT_CAP: dict[Cut, int] = {
    "tiktok-length": 3,
    "shorts": 4,
    "weekly_update": 6,
    "one_time_short_episode": 8,
    "full_length_documentary": 40,
    "feature_film": 40,
}
# Imagen spend cap. Shorts generate every shot. Long-form: key frames only.
# Shot LIST is complete; billable images stay capped (never 400).
FRAME_COUNT: dict[Cut, int] = {
    "tiktok-length": 24,
    "shorts": 24,
    "weekly_update": 24,
    "one_time_short_episode": 40,
    "full_length_documentary": 40,
    "feature_film": 40,
}

# Spoken-scene length. Short form is tens of seconds. Episode blocks ~8 min
# so ~5 seed scenes land near 45 min. Doc scenes are shorter so 40 rows
# stay near feature length, not 400 images.
SCENE_SECONDS: dict[Cut, int] = {
    "tiktok-length": 10,
    "shorts": 12,
    "weekly_update": 30,
    "one_time_short_episode": 480,
    "full_length_documentary": 180,
    "feature_film": 240,
}

LONG_CUTS = frozenset({"one_time_short_episode", "full_length_documentary", "feature_film"})

# Script + storyboard sized to the Meta/TikTok/YouTube surface.
PLATFORM_EVENT_CAP: dict[Platform, int] = {
    "tiktok": 3,
    "youtube": 40,
    "youtube_shorts": 4,
    "instagram_reels": 4,
    "instagram_stories": 3,
    "instagram_feed": 6,
    "facebook_reels": 4,
    "facebook_feed": 6,
    "threads": 3,
    "podcast": 12,
}
PLATFORM_FRAME_COUNT: dict[Platform, int] = {
    "tiktok": 3,
    "youtube": 40,
    "youtube_shorts": 4,
    "instagram_reels": 4,
    "instagram_stories": 3,
    "instagram_feed": 6,
    "facebook_reels": 4,
    "facebook_feed": 6,
    "threads": 3,
    "podcast": 12,
}


class CutRequiredError(ValueError):
    """No cut chosen = no run. Do not default the length."""


def require_cut(raw: str | None) -> Cut:
    chosen = (raw or "").strip()
    if chosen not in CUTS:
        raise CutRequiredError("No cut chosen = no run")
    return chosen  # type: ignore[return-value]


def cuts_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": CUT_LABELS[key]} for key in CUTS]


def event_cap(cut: Cut, platform: Platform | None = None) -> int:
    cap = EVENT_CAP[cut]
    if platform and platform in PLATFORM_EVENT_CAP:
        cap = min(cap, PLATFORM_EVENT_CAP[platform])
    return cap


def frame_count(cut: Cut, platform: Platform | None = None) -> int:
    n = FRAME_COUNT[cut]
    if platform and platform in PLATFORM_FRAME_COUNT:
        n = min(n, PLATFORM_FRAME_COUNT[platform])
    return n


def size_findings(findings: list, cut: Cut, platform: Platform | None = None) -> list:
    return findings[: event_cap(cut, platform)]


def scene_seconds(cut: Cut) -> int:
    return SCENE_SECONDS[cut]


def is_long_cut(cut: Cut) -> bool:
    return cut in LONG_CUTS
