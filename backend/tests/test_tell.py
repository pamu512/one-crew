import copy
import re

import pytest
from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.board import write_shot_list
from onecrew.models import MISSING
from onecrew.picks import TellPairingError, require_picks
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.spend import ledger


def _from_seed(*, genre: str, vantage: str, lean: str = "centered_independent", cut: str | None = None):
    packet = seed_first_open()
    packet.genre = genre
    packet.vantage = vantage
    packet.script_lean = lean
    if cut:
        packet.cut = cut
    packet.receipt = copy.deepcopy(packet.receipt)
    write_script(packet)
    packet.frames = write_shot_list(packet)
    return packet


def test_same_receipt_three_tells_stamps_identical() -> None:
    nf = _from_seed(genre="nonfiction", vantage="global_overview")
    family = _from_seed(genre="drama", vantage="one_family")
    ship = _from_seed(genre="thriller", vantage="one_ship")
    feature = _from_seed(genre="drama", vantage="one_family", cut="feature_film")
    stamps = lambda p: [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in p.receipt.findings
    ]
    assert stamps(nf) == stamps(family) == stamps(ship) == stamps(feature)
    assert {f.id for f in nf.receipt.findings} == {f.id for f in family.receipt.findings}
    assert nf.script != family.script != ship.script
    assert "Leila" in family.script and "Bandar Abbas" in family.script
    assert "(frame)" in family.script and "(frame)" in ship.script
    assert "(frame)" not in nf.script
    assert "Reza" in ship.script or "bridge" in ship.script.lower()
    assert "Leila" in feature.script and "(frame)" in feature.script
    for packet in (nf, family, ship, feature):
        for beat in packet.beats:
            assert beat.finding_ids
            for fid in beat.finding_ids:
                assert f"[{fid}]" in beat.vo
        assert "[secret-closure]" in packet.script
        assert "[hormuz-share]" in packet.script
        oil = next(f for f in packet.receipt.findings if f.id == "oil-panic")
        assert oil.lean == MISSING


def test_nonfiction_one_family_writes_receipt_only() -> None:
    packet = _from_seed(genre="nonfiction", vantage="one_family")
    assert "Leila" not in packet.script
    assert "(frame)" not in packet.script
    assert "Bandar Abbas" not in packet.script
    shots = " ".join(f.shot.lower() for f in packet.frames)
    assert "kitchen" not in shots or "bandar" not in shots


def test_feature_film_drama_one_family_writes_fiction_frame() -> None:
    packet = _from_seed(genre="drama", vantage="one_family", cut="feature_film")
    assert packet.cut == "feature_film"
    assert "Leila" in packet.script
    assert "(frame)" in packet.script
    assert "[jcpoa-2018]" in packet.script
    seed = seed_first_open()
    assert packet.receipt is not None and seed.receipt is not None
    assert [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in packet.receipt.findings
    ] == [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in seed.receipt.findings
    ]


def test_thriller_does_not_claim_a_sourced_explosion() -> None:
    ship = _from_seed(genre="thriller", vantage="one_ship")
    blob = ship.script.lower()
    assert "got blown" not in blob
    assert "was hit" not in blob
    assert "exploded" not in blob
    assert "sourced explosion" in blob or "no blast" in blob or "not a fact" in blob
    family = _from_seed(genre="drama", vantage="one_family")
    shots = " ".join(f.shot.lower() for f in family.frames)
    ship_shots = " ".join(f.shot.lower() for f in ship.frames)
    nf = _from_seed(genre="nonfiction", vantage="global_overview")
    nf_shots = " ".join(f.shot.lower() for f in nf.frames)
    assert "kitchen" in shots
    assert "bridge" in ship_shots or "watch" in ship_shots or "bow" in ship_shots
    assert "kitchen" not in nf_shots or "bandar" not in nf_shots
    assert all("receipt card" not in f.shot.lower() for f in family.frames + ship.frames)
    assert family.frames[0].shot != ship.frames[0].shot


def test_hold_does_not_invent_a_family(monkeypatch) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.models import Rails

    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        genre="drama",
        vantage="one_family",
        topic="Hormuz",
    )
    shift.rails = Rails(parallel=False, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    assert packet.script == ""
    assert packet.beats == []
    assert "Leila" not in packet.script


def _shift_body(**overrides):
    body = {
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "decade",
        "script_lean": "centered_independent",
        "genre": "nonfiction",
        "vantage": "global_overview",
    }
    body.update(overrides)
    return body


def test_documentary_thriller_is_400_no_spend(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent on thriller documentary")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    with TestClient(app) as client:
        headers = {"X-Shift-Token": "correct-horse"}
        doc = client.post(
            "/api/shifts",
            json=_shift_body(cut="full_length_documentary", genre="thriller", vantage="global_overview"),
            headers=headers,
        )
        assert doc.status_code == 400
        assert "thriller documentary" in doc.json()["detail"].lower()
        weekly = client.post(
            "/api/shifts",
            json=_shift_body(cut="weekly_update", genre="drama", vantage="one_family"),
            headers=headers,
        )
        assert weekly.status_code == 400
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0
    with pytest.raises(TellPairingError, match="thriller documentary"):
        require_picks(
            "Hormuz",
            "youtube",
            "full_length_documentary",
            "decade",
            "centered_independent",
            "thriller",
            "global_overview",
        )
    seed = seed_first_open()
    seed.cut = "full_length_documentary"
    seed.genre = "thriller"
    with pytest.raises(TellPairingError, match="thriller documentary"):
        write_script(seed)


def test_feature_film_nonfiction_is_400_no_spend(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent on nonfiction feature")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    with TestClient(app) as client:
        rejected = client.post(
            "/api/shifts",
            json=_shift_body(cut="feature_film", genre="nonfiction", vantage="global_overview"),
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert rejected.status_code == 400
        detail = rejected.json()["detail"].lower()
        assert "nonfiction feature" in detail
        assert "full_length_documentary" in detail
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0
    with pytest.raises(TellPairingError, match="nonfiction feature"):
        require_picks(
            "Hormuz",
            "youtube",
            "feature_film",
            "decade",
            "centered_independent",
            "nonfiction",
            "global_overview",
        )
    seed = seed_first_open()
    seed.cut = "feature_film"
    seed.genre = "nonfiction"
    with pytest.raises(TellPairingError, match="nonfiction feature"):
        write_script(seed)


def test_empty_tell_does_not_spend(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("spent without tell")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    before_p = ledger.parallel_calls
    before_i = ledger.imagen_calls
    body = {
        "topic": "Hormuz",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "decade",
        "script_lean": "centered_independent",
    }
    with TestClient(app) as client:
        headers = {"X-Shift-Token": "correct-horse"}
        missing = client.post("/api/shifts", json=body, headers=headers)
        assert missing.status_code == 400
        assert "genre" in missing.json()["detail"].lower()
        empty = client.post(
            "/api/shifts",
            json={**body, "genre": "   ", "vantage": "one_ship"},
            headers=headers,
        )
        assert empty.status_code == 400
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0


def test_get_tells_have_no_default() -> None:
    with TestClient(app) as client:
        genres = client.get("/api/genres").json()
        vantages = client.get("/api/vantages").json()
        assert genres["default"] is None
        assert vantages["default"] is None
        assert [r["id"] for r in genres["genres"]] == [
            "nonfiction",
            "horror",
            "war",
            "historical",
            "musical",
            "drama",
            "thriller",
        ]
        assert [r["id"] for r in vantages["vantages"]] == [
            "global_overview",
            "one_family",
            "one_ship",
        ]


def test_fiction_vo_has_no_receipt_jargon() -> None:
    banned = ("on the receipt", "hold on this card", "receipt card for", "tagged fringe", "propaganda yes")
    for genre, vantage in (("drama", "one_family"), ("thriller", "one_ship")):
        packet = _from_seed(genre=genre, vantage=vantage)
        blob = packet.script.lower()
        for word in banned:
            assert word not in blob
        assert re.search(r"\[[a-z0-9-]+\]", packet.script)
