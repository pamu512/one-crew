from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from onecrew import config
from onecrew.spend import ledger

_ULTRA = frozenset({"ultra", "ultra2x", "ultra4x", "ultra8x"})


class ParallelDownError(RuntimeError):
    """Parallel rail is down. Caller must HOLD — no invented source."""


def _client() -> Any:
    if not config.has_parallel():
        raise ParallelDownError("PARALLEL_API_KEY missing")
    from parallel import Parallel  # official SDK

    return Parallel(api_key=config.parallel_api_key())


def search(*, objective: str, search_queries: list[str]) -> Any:
    """Official Parallel Search. First pass. This call spends."""
    ledger.note_parallel()
    client = _client()
    return client.search(objective=objective, search_queries=search_queries)


def extract(*, urls: list[str], objective: str) -> Any:
    """Official Parallel Extract after Search URLs. Up to 20 URLs. Spends."""
    clean = [url for url in urls if url][:20]
    if not clean:
        return SimpleNamespace(results=[], errors=[])
    ledger.note_parallel()
    client = _client()
    return client.extract(urls=clean, objective=objective)


def run_task(
    *,
    prompt: str,
    processor: str = "pro",
    task_spec: dict[str, Any] | None = None,
) -> Any:
    """Official Parallel Task. One deep-research run uses processor=pro. No ultra."""
    if processor in _ULTRA:
        raise ValueError("do not use ultra-tier Task processors")
    ledger.note_parallel()
    client = _client()
    kwargs: dict[str, Any] = {"input": prompt, "processor": processor}
    if task_spec is not None:
        kwargs["task_spec"] = task_spec
    task_run = client.task_run.create(**kwargs)
    return client.task_run.result(task_run.run_id, api_timeout=3600)


def entity_search(
    *,
    objective: str,
    entity_type: str = "companies",
    match_limit: int = 5,
) -> Any:
    """Official Entity Search. Verified list only. Never invent a family."""
    ledger.note_parallel()
    client = _client()
    return client.beta.findall.entity_search(
        entity_type=entity_type,
        objective=objective,
        match_limit=match_limit,
    )
