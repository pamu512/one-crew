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
HORMUZ_PRINT = "Hormuz tanker transits printed 23% below 2023 in March 2024."


def _search_two(*, objective, search_queries):
    blob = f"{objective} {' '.join(search_queries)}".lower()
    if "hidden" in blob or "fringe" in blob:
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://example.com/fringe-miss",
                    title="Fringe miss",
                    excerpts=["Secret navy treaty already mined the strait shut."],
                )
            ]
        )
    return SimpleNamespace(
        results=[
            SimpleNamespace(url=KEPT, title="Kept hit", excerpts=[HORMUZ_PRINT]),
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
            content=f"{HORMUZ_PRINT} Cited thesis spine from Task pro.",
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
    ids = {f.id for f in packet.receipt.findings}
    assert ids != {"timeline-hit", "timeline-frame", "timeline-miss"}
    assert not ids <= {"timeline-hit", "timeline-frame", "timeline-miss"}


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


class _APIStatusError(Exception):
    """Duck-typed Parallel SDK 402. Tests must not import the live SDK."""

    def __init__(self) -> None:
        super().__init__(
            "Error code: 402 - {'error': {'message': 'insufficient credit', "
            "'type': 'insufficient_credit'}, "
            "'ref_id': '2a21f0a7d58da9eb0d3e0e7a25008e07'}"
        )
        self.status_code = 402


def test_parallel_402_on_second_task_holds_not_500(monkeypatch) -> None:
    from onecrew.store import store

    calls: list[str] = []
    spine = (
        "USREC July 2026 = 0. Nonfarm payrolls fell −23,000 in July 2026. "
        "Unemployment was 4.1%. GDP printed 2.1, then 1.5. Sahm −0.03 vs 0.50."
    )

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/hidden-treaty",
                        title="Hidden treaty",
                        excerpts=["Secret double-dip already started in May."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=["USREC July 2026 = 0."],
                ),
                SimpleNamespace(
                    url="https://www.bls.gov/news.release/archives/empsit_08072026.htm",
                    title="BLS July archive",
                    excerpts=["July payrolls fell 23,000 and unemployment was 4.1%."],
                ),
                SimpleNamespace(
                    url="https://www.bea.gov/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026",
                    title="BEA second estimate",
                    excerpts=["Real GDP increased 2.1% in Q1 2026 and 1.5% annualized in Q2."],
                ),
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/SAHMREALTIME",
                    title="SAHMREALTIME",
                    excerpts=["Sahm July 2026 = −0.03 vs 0.50 trigger."],
                ),
            ]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=["USREC July 2026 = 0."],
                )
            ],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        calls.append(f"task:{processor}")
        if processor == "base" or len(calls) >= 2:
            raise _APIStatusError()
        return SimpleNamespace(output=SimpleNamespace(content=spine, basis=[]))

    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-parallel-key")
    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: (_ for _ in ()).throw(AssertionError("Imagen/Vertex on 402")))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: (_ for _ in ()).throw(AssertionError("Imagen on 402")))
    store.replace_packets([])
    pid = "oc-are-we-near-recession-9325576d"
    body = {
        "topic": "Are we near recession?",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "2-3y",
        "script_lean": "centered_independent",
        "tell": "Host-only desk read of the last year of US recession prints",
        "tone": "On the cited print",
        "packet_id": pid,
    }
    with TestClient(app, raise_server_exceptions=False) as client:
        posted = client.post(
            "/api/shifts",
            json=body,
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert posted.status_code != 500
        assert posted.status_code == 200
        listed = client.get("/api/packets")
        got = client.get(f"/api/packets/{pid}")
        page = client.get("/")
    assert listed.status_code == 200
    ids = {p["id"] for p in listed.json()["packets"]}
    assert pid in ids
    assert "oc-hormuz-decade" not in ids
    assert got.status_code == 200
    packet = got.json()
    assert packet["id"] == pid
    assert packet["status"] == "hold"
    reason = (
        (packet.get("receipt") or {}).get("hold_reason")
        or packet.get("collision_hold_reason")
        or ""
    ).lower()
    assert "402" in reason or "credit" in reason
    assert "parallel missing" not in reason
    findings = (packet.get("receipt") or {}).get("findings") or []
    ids_f = {f.get("id") for f in findings}
    assert ids_f != {"timeline-hit", "timeline-frame", "timeline-miss"}
    assert not ids_f & {"timeline-hit", "timeline-frame", "timeline-miss"}
    assert page.status_code == 200
    assert "Hormuz" not in page.text
    assert "task:pro" in calls
    assert any(c.startswith("task:") for c in calls)
    assert calls.count("task:pro") + calls.count("task:base") == 2


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
