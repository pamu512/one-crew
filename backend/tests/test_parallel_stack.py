from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from onecrew.agent.shift import open_shift, run_live_packet
from onecrew.api import app
from onecrew.models import Rails
from onecrew.parallel_client import ParallelDownError, run_task
from onecrew.seed import seed_first_open
from onecrew.spend import ledger


KEPT = "https://example.com/kept-hit"
EXTRA = "https://example.com/extra-hit"


def _search_two(*, objective, search_queries):
    blob = f"{objective} {' '.join(search_queries)}".lower()
    if "hidden" in blob or "fringe" in blob:
        return SimpleNamespace(results=[])
    return SimpleNamespace(
        results=[
            SimpleNamespace(url=KEPT, title="Kept hit", excerpts=["kept excerpt"]),
            SimpleNamespace(url=EXTRA, title="Extra hit", excerpts=["extra excerpt"]),
        ]
    )


def _extract_ok(*, urls, objective):
    return SimpleNamespace(
        results=[SimpleNamespace(url=KEPT, title="Kept hit", excerpts=["Ownership: cited house organ."])],
        errors=[],
    )


def _extract_fail_extra(*, urls, objective):
    return SimpleNamespace(
        results=[SimpleNamespace(url=KEPT, title="Kept hit", excerpts=["Quote from the page."])],
        errors=[SimpleNamespace(url=EXTRA, error_type="fetch_failed")],
    )


def _task_ok(*, prompt, processor="pro", task_spec=None):
    if processor in {"ultra", "ultra8x"}:
        raise AssertionError("ultra Task is banned")
    if processor == "base":
        return SimpleNamespace(
            output=SimpleNamespace(
                content={
                    "vested_interest": "oil producers",
                    "who_repeats": "OPEC desks",
                    "propaganda_issuer": "OPEC",
                    "independent": "no",
                },
                basis=[
                    SimpleNamespace(field="vested_interest", citations=[SimpleNamespace(url=KEPT)]),
                    SimpleNamespace(field="who_repeats", citations=[SimpleNamespace(url=KEPT)]),
                    SimpleNamespace(field="propaganda_issuer", citations=[SimpleNamespace(url=KEPT)]),
                    SimpleNamespace(field="independent", citations=[SimpleNamespace(url=KEPT)]),
                ],
            )
        )
    return SimpleNamespace(
        output=SimpleNamespace(
            content="Cited thesis spine from Task pro.",
            basis=[SimpleNamespace(field="timeline", citations=[SimpleNamespace(url=KEPT)])],
        )
    )


def _wire_live(monkeypatch, *, extract=_extract_ok, task=_task_ok):
    monkeypatch.setattr("onecrew.agent.shift.search", _search_two)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))


def _live_shift():
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    return shift


def test_live_path_calls_search_extract_and_task_pro(monkeypatch) -> None:
    calls: list[str] = []

    def search(*, objective, search_queries):
        calls.append("search")
        return _search_two(objective=objective, search_queries=search_queries)

    def extract(*, urls, objective):
        calls.append("extract")
        assert len(urls) <= 20
        return _extract_ok(urls=urls, objective=objective)

    def task(*, prompt, processor="pro", task_spec=None):
        calls.append(f"task:{processor}")
        return _task_ok(prompt=prompt, processor=processor, task_spec=task_spec)

    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    packet = run_live_packet(_live_shift())
    assert calls.count("search") >= 2
    assert "extract" in calls
    assert "task:pro" in calls
    assert packet.task_spine
    assert "Cited thesis spine from Task pro." in packet.research_pack
    assert "Task basis timeline" in packet.research_pack
    assert "Extract: Ownership: cited house organ." in next(
        f.note for f in packet.receipt.findings if f.parallel_url == KEPT
    )


def test_failed_extract_is_exclusion_not_silent_drop(monkeypatch) -> None:
    _wire_live(monkeypatch, extract=_extract_fail_extra)
    packet = run_live_packet(_live_shift())
    assert any(
        row.url == EXTRA and row.reason == "other" and "Extract failed" in row.detail
        for row in packet.exclusions
    )
    assert EXTRA in packet.research_pack
    assert "Extract failed" in packet.research_pack


def test_get_never_spends_search_extract_or_task(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("GET spent Parallel")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.parallel_client.extract", boom)
    monkeypatch.setattr("onecrew.parallel_client.run_task", boom)
    monkeypatch.setattr("onecrew.parallel_client.entity_search", boom)
    seed_first_open()
    before = ledger.parallel_calls
    with TestClient(app) as client:
        body = client.get("/api/packets")
        assert body.status_code == 200
        assert body.json()["packets"][0]["research_pack"]
    assert ledger.parallel_calls == before == 0


def test_readme_names_search_extract_task_pro() -> None:
    readme = (Path(__file__).resolve().parents[2] / "README.md").read_text()
    assert "Search" in readme and "Extract" in readme
    assert "Task" in readme and "pro" in readme
    assert "thesis" in readme.lower()
    assert "Monitor" in readme


def test_no_monitor_create_in_source() -> None:
    root = Path(__file__).resolve().parents[2] / "backend" / "onecrew"
    blob = ""
    for path in root.rglob("*.py"):
        blob += path.read_text()
    assert "monitors.create" not in blob
    assert "monitor.create" not in blob
    assert "client.monitor" not in blob
    assert "beta.monitor" not in blob


def test_parallel_key_not_committed() -> None:
    root = Path(__file__).resolve().parents[2]
    skip = {".git", ".venv", "__pycache__", ".pytest_cache"}
    for path in (root / "backend" / "onecrew").rglob("*.py"):
        if any(part in skip for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        assert "PARALLEL_API_KEY=" not in text or "getenv" in text
    example = (root / ".env.example").read_text()
    for line in example.splitlines():
        if line.startswith("PARALLEL_API_KEY="):
            _, _, value = line.partition("=")
            assert value.strip() in {"", '""', "''"}


def test_ultra_task_is_rejected() -> None:
    with pytest.raises(ValueError, match="ultra"):
        run_task(prompt="no", processor="ultra")


def test_entity_search_not_used_to_invent_a_family(monkeypatch) -> None:
    called = []

    def boom_entities(**_k):
        called.append("entity")
        raise AssertionError("Entity Search must not invent a family")

    _wire_live(monkeypatch)
    monkeypatch.setattr("onecrew.agent.shift.entity_search", boom_entities)
    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="feature_film",
        depth="decade",
        script_lean="centered_independent",
        tell="One family in Bandar Abbas, kitchen radio on",
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert called == []
    assert "Leila" not in (packet.task_spine or "")
