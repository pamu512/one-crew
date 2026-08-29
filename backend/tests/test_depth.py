from fastapi.testclient import TestClient

import pytest

from onecrew.api import app
from onecrew.depth import DepthRequiredError, pre1980_fail_closed, require_depth
from onecrew.models import CausalLink, Rails
from onecrew.receipt import ReceiptInvalidError, validate_causal_link
from onecrew.spend import ledger


def test_require_depth_no_default() -> None:
    with pytest.raises(DepthRequiredError, match="No depth chosen"):
        require_depth(None)
    with pytest.raises(DepthRequiredError, match="No depth chosen"):
        require_depth("")
    with pytest.raises(DepthRequiredError, match="No depth chosen"):
        require_depth("all-history")
    assert require_depth("decade") == "decade"
    assert require_depth("pre-1980") == "pre-1980"


def test_get_depths_has_no_default() -> None:
    with TestClient(app) as client:
        body = client.get("/api/depths")
        assert body.status_code == 200
        payload = body.json()
        assert payload["default"] is None
        ids = [row["id"] for row in payload["depths"]]
        assert ids == [
            "current",
            "2-3-years",
            "5-years",
            "decade",
            "few-decades",
            "pre-1980",
        ]


def test_no_spend_without_depth(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent without depth")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    with TestClient(app) as client:
        missing = client.post(
            "/api/shifts",
            json={"topic": "Explain what's going on with the Hormuz strait"},
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert missing.status_code == 400
        assert "no depth" in missing.json()["detail"].lower()
        empty = client.post(
            "/api/shifts",
            json={"topic": "Hormuz", "depth": ""},
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert empty.status_code == 400
        bogus = client.post(
            "/api/shifts",
            json={"topic": "Hormuz", "depth": "all-history"},
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert bogus.status_code == 400
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0


def test_token_gate_still_fires_before_depth(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    with TestClient(app) as client:
        bare = client.post("/api/shifts", json={"topic": "Hormuz"})
        assert bare.status_code == 403


def test_causal_link_without_parallel_hit_cannot_be_grounded() -> None:
    with pytest.raises(ReceiptInvalidError, match="cannot be grounded"):
        validate_causal_link(
            CausalLink(
                id="x",
                from_id="a",
                to_id="b",
                claim="this led to that",
                stamp="grounded",
                parallel_url=None,
            )
        )
    missing = CausalLink(
        id="x",
        from_id="a",
        to_id="b",
        claim="this led to that",
        stamp="missing",
        parallel_url=None,
    )
    validate_causal_link(missing)
    grounded = CausalLink(
        id="y",
        from_id="a",
        to_id="b",
        claim="this led to that",
        stamp="grounded",
        parallel_url="https://example.com/link",
    )
    validate_causal_link(grounded)


def test_pre_1980_fail_closed_when_parallel_misses() -> None:
    rails = Rails(parallel=True, vertex=True, imagen=True)
    receipt = pre1980_fail_closed(
        packet_id="oc-old",
        depth="pre-1980",
        rails=rails,
        parallel_hits=0,
    )
    assert receipt is not None
    assert receipt.disposition == "HOLD"
    assert receipt.findings == []
    assert receipt.causal_links == []
    assert "pre-1980" in (receipt.hold_reason or "").lower()
    assert "invented chain" in (receipt.hold_reason or "").lower()

    down = Rails(parallel=False, vertex=True, imagen=True)
    down_receipt = pre1980_fail_closed(
        packet_id="oc-old",
        depth="pre-1980",
        rails=down,
        parallel_hits=3,
    )
    assert down_receipt is not None
    assert down_receipt.disposition == "HOLD"
    assert down_receipt.causal_links == []

    ok = pre1980_fail_closed(
        packet_id="oc-old",
        depth="pre-1980",
        rails=rails,
        parallel_hits=1,
    )
    assert ok is None
    assert pre1980_fail_closed(
        packet_id="oc-old",
        depth="decade",
        rails=rails,
        parallel_hits=0,
    ) is None
