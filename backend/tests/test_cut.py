from fastapi.testclient import TestClient

import pytest

from onecrew.api import app
from onecrew.cut import (
    CUTS,
    CutRequiredError,
    event_cap,
    frame_count,
    require_cut,
)
from onecrew.models import Packet, Receipt
from onecrew.receipt import ReceiptInvalidError, write_receipt
from onecrew.seed import seed_findings, seed_links
from onecrew.spend import ledger


def test_require_cut_no_default() -> None:
    with pytest.raises(CutRequiredError, match="No cut chosen"):
        require_cut(None)
    with pytest.raises(CutRequiredError, match="No cut chosen"):
        require_cut("")
    with pytest.raises(CutRequiredError, match="No cut chosen"):
        require_cut("feature")
    assert require_cut("tiktok-length") == "tiktok-length"
    assert require_cut("full_length_documentary") == "full_length_documentary"
    assert list(CUTS) == [
        "tiktok-length",
        "shorts",
        "weekly_update",
        "one_time_short_episode",
        "full_length_documentary",
    ]


def test_get_cuts_has_no_default() -> None:
    with TestClient(app) as client:
        body = client.get("/api/cuts")
        assert body.status_code == 200
        payload = body.json()
        assert payload["default"] is None
        ids = [row["id"] for row in payload["cuts"]]
        assert ids == list(CUTS)


def test_no_spend_without_cut(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent without cut")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    with TestClient(app) as client:
        missing = client.post(
            "/api/shifts",
            json={
                "topic": "Hormuz",
                "platform": "youtube",
                "depth": "decade",
                "script_lean": "centered_independent",
            },
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert missing.status_code == 400
        assert "no cut" in missing.json()["detail"].lower()
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0


def test_tiktok_packet_is_not_a_doc_packet() -> None:
    assert event_cap("tiktok-length") < event_cap("full_length_documentary")
    assert frame_count("tiktok-length") < frame_count("full_length_documentary")
    packet = Packet(
        id="oc-tiktok",
        hook="hook",
        script="script",
        depth="decade",
        cut="tiktok-length",
    )
    with pytest.raises(ReceiptInvalidError, match="not a doc packet"):
        write_receipt(
            packet,
            Receipt(
                packet_id=packet.id,
                findings=seed_findings(),
                causal_links=seed_links(),
                disposition="READY",
            ),
        )
