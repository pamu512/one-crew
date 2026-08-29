from __future__ import annotations

from onecrew.models import DEPTHS, Depth, Rails, Receipt
from onecrew.receipt import hold_receipt

DEPTH_LABELS: dict[Depth, str] = {
    "1y": "1y",
    "2-3y": "2-3y",
    "5y": "5y",
    "decade": "decade",
    "few_decades": "few_decades",
    "pre-1980_pre-internet": "pre-1980_pre-internet",
}

PRE1980 = "pre-1980_pre-internet"


class DepthRequiredError(ValueError):
    """No depth chosen = no run. Do not default to all-history."""


def require_depth(raw: str | None) -> Depth:
    chosen = (raw or "").strip()
    if chosen not in DEPTHS:
        raise DepthRequiredError("No depth chosen = no run")
    return chosen  # type: ignore[return-value]


def depths_payload() -> list[dict[str, str]]:
    return [{"id": key, "label": DEPTH_LABELS[key]} for key in DEPTHS]


def pre1980_fail_closed(
    *,
    packet_id: str,
    depth: str,
    rails: Rails,
    parallel_hits: int,
) -> Receipt | None:
    """pre-1980 still HOLDs if Parallel misses. Do not invent a 40-year chain."""
    if depth != PRE1980:
        return None
    if rails.parallel and parallel_hits > 0:
        return None
    down = rails if not rails.parallel else rails.model_copy(update={"parallel": False})
    receipt = hold_receipt(packet_id, down)
    receipt.hold_reason = (
        "Fail-closed: Parallel miss in pre-1980 window — no invented chain, no invented lean."
    )
    receipt.causal_links = []
    return receipt
