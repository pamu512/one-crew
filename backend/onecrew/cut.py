from __future__ import annotations

from onecrew.models import CUTS, Cut

CUT_LABELS: dict[Cut, str] = {key: key for key in CUTS}

# Receipt + boards sized to the cut. A TikTok-length packet is not a doc packet.
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


class CutRequiredError(ValueError):
    """No cut chosen = no run. Do not default the length."""


def require_cut(raw: str | None) -> Cut:
    chosen = (raw or "").strip()
    if chosen not in CUTS:
        raise CutRequiredError("No cut chosen = no run")
    return chosen  # type: ignore[return-value]


def cuts_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": CUT_LABELS[key]} for key in CUTS]


def event_cap(cut: Cut) -> int:
    return EVENT_CAP[cut]


def frame_count(cut: Cut) -> int:
    return FRAME_COUNT[cut]


def size_findings(findings: list, cut: Cut) -> list:
    return findings[: event_cap(cut)]
