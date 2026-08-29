from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.seed import seed_first_open
from onecrew.spend import ledger


def test_get_packets_never_spends_parallel(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("Parallel spent on GET")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    seed_first_open()
    before = ledger.parallel_calls
    with TestClient(app) as client:
        body = client.get("/api/packets")
        assert body.status_code == 200
    assert ledger.parallel_calls == before == 0


def test_get_packets_never_spends_imagen(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("Imagen spent on GET")

    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    seed_first_open()
    before = ledger.imagen_calls
    with TestClient(app) as client:
        body = client.get("/api/packets")
        assert body.status_code == 200
    assert ledger.imagen_calls == before == 0


def test_get_health_never_spends() -> None:
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["spend"]["parallel_calls"] == 0
        assert health.json()["spend"]["imagen_calls"] == 0
        assert health.json()["posts"] is False


def test_post_shift_403_when_token_unset(monkeypatch) -> None:
    monkeypatch.delenv("SHIFT_TOKEN", raising=False)
    with TestClient(app) as client:
        shift = client.post("/api/shifts", json={"goal": "research"})
        assert shift.status_code == 403


def test_post_shift_403_when_token_missing_header(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    with TestClient(app) as client:
        bare = client.post("/api/shifts", json={"goal": "research"})
        assert bare.status_code == 403


def test_post_shift_403_when_token_wrong(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    with TestClient(app) as client:
        wrong = client.post(
            "/api/shifts",
            json={"goal": "research"},
            headers={"X-Shift-Token": "nope"},
        )
        assert wrong.status_code == 403


def test_post_reset_403_without_token(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    with TestClient(app) as client:
        reset = client.post("/api/reset")
        assert reset.status_code == 403
