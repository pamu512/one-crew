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
}
FRAME_COUNT: dict[Cut, int] = {
    "tiktok-length": 2,
    "shorts": 2,
    "weekly_update": 3,
    "one_time_short_episode": 4,
    "full_length_documentary": 4,
}

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
    "tiktok": 2,
    "youtube": 4,
    "youtube_shorts": 2,
    "instagram_reels": 2,
    "instagram_stories": 2,
    "instagram_feed": 3,
    "facebook_reels": 2,
    "facebook_feed": 3,
    "threads": 2,
    "podcast": 4,
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
