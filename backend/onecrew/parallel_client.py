from __future__ import annotations

from typing import Any

from onecrew import config
from onecrew.spend import ledger


class ParallelDownError(RuntimeError):
    """Parallel rail is down. Caller must HOLD — no invented source."""


def search(*, objective: str, search_queries: list[str]) -> Any:
    """Official Parallel Web Python SDK. This call spends."""
    if not config.has_parallel():
        raise ParallelDownError("PARALLEL_API_KEY missing")
    ledger.note_parallel()
    from parallel import Parallel  # official SDK

    client = Parallel(api_key=config.parallel_api_key())
    return client.search(objective=objective, search_queries=search_queries)
