import copy
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.board import write_shot_list
from onecrew.models import MISSING
from onecrew.picks import require_picks
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.spend import ledger
from onecrew.tell import SEED_TELL, TELL_EXAMPLES, TellRequiredError, invents_frame
from onecrew.tone import SEED_TONE

FAMILY_TELL = "One family in Bandar Abbas, kitchen radio on"
SHIP_TELL = "Thriller on a tanker crossing Hormuz that might get hit"
PILOT_TELL = "one retired pilot on the night watch"
FAMILY_DRAMA_TELL = "Historical drama through one port family"


def _from_seed(*, tell: str, lean: str = "centered_independent", cut: str | None = None):
    packet = seed_first_open()
    packet.tell = tell
    packet.tone = SEED_TONE
    packet.script_lean = lean
    if cut:
        packet.cut = cut
    packet.receipt = copy.deepcopy(packet.receipt)
    write_script(packet)
    packet.frames = write_shot_list(packet)
    return packet


def test_same_receipt_three_tells_stamps_identical() -> None:
    nf = _from_seed(tell=SEED_TELL)
    family = _from_seed(tell=FAMILY_TELL)
    ship = _from_seed(tell=SHIP_TELL)
    feature = _from_seed(tell=FAMILY_TELL, cut="feature_film")
    stamps = lambda p: [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in p.receipt.findings
    ]
    assert stamps(nf) == stamps(family) == stamps(ship) == stamps(feature)
    assert {f.id for f in nf.receipt.findings} == {f.id for f in family.receipt.findings}
    assert nf.script != family.script != ship.script
    assert "Leila" not in family.script
    assert "Reza" not in ship.script
    assert "(frame)" not in nf.script
    assert "(frame)" not in family.script
    assert "(frame)" in feature.script
    for packet in (nf, family, ship, feature):
        for beat in packet.beats:
            assert beat.finding_ids
        oil = next(f for f in packet.receipt.findings if f.id == "already-in")
        assert oil.lean == MISSING


def test_documentary_family_drama_invents_no_leila() -> None:
    packet = _from_seed(tell=FAMILY_DRAMA_TELL, cut="full_length_documentary")
    assert "Leila" not in packet.script
    assert "(frame)" not in packet.script
    assert invents_frame(cut="full_length_documentary", tell=FAMILY_DRAMA_TELL) is False
    topic, platform, cut, depth, lean, tell, tone = require_picks(
        "Hormuz",
        "youtube",
        "full_length_documentary",
        "decade",
        "centered_independent",
        "family thriller on a tanker",
        SEED_TONE,
    )
    assert tell == "family thriller on a tanker"
    assert cut == "full_length_documentary"


def test_feature_family_writes_fiction_frame() -> None:
    packet = _from_seed(tell=FAMILY_TELL, cut="feature_film")
    assert packet.cut == "feature_film"
    assert "Leila" not in packet.script
    assert "(frame)" in packet.script
    seed = seed_first_open()
    assert packet.receipt is not None and seed.receipt is not None
    assert [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in packet.receipt.findings
    ] == [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent)
        for f in seed.receipt.findings
    ]


def test_pilot_tell_on_feature_differs_from_family() -> None:
    family = _from_seed(tell=FAMILY_TELL, cut="feature_film")
    pilot = _from_seed(tell=PILOT_TELL, cut="feature_film")
    assert family.script != pilot.script
    assert "retired pilot" in pilot.script.lower() or "night watch" in pilot.script.lower()
    assert "(frame)" in pilot.script
    assert "(frame)" in family.script
    stamps = lambda p: [(f.id, f.stamp, f.propaganda) for f in p.receipt.findings]
    assert stamps(family) == stamps(pilot)


def test_thriller_does_not_claim_a_sourced_explosion() -> None:
    ship = _from_seed(tell=SHIP_TELL)
    blob = ship.script.lower()
    assert "got blown" not in blob
    assert "was hit" not in blob
    assert "exploded" not in blob
    family = _from_seed(tell=FAMILY_TELL)
    nf = _from_seed(tell=SEED_TELL)
    assert "Leila" not in nf.script
    assert all("receipt card" not in f.shot.lower() for f in family.frames + ship.frames)
    assert family.script != ship.script


def test_hold_does_not_invent_a_family() -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.models import Rails

    shift = open_shift(
        "Hormuz",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell=FAMILY_TELL,
        tone=SEED_TONE,
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
        "tell": SEED_TELL,
        "tone": SEED_TONE,
    }
    body.update(overrides)
    return body


def test_documentary_thriller_tell_is_not_400(monkeypatch) -> None:
    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")

    def boom(*_a, **_k):
        raise AssertionError("should not spend before pairing is gone")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", boom)
    with TestClient(app) as client:
        headers = {"X-Shift-Token": "correct-horse"}
        doc = client.post(
            "/api/shifts",
            json=_shift_body(cut="full_length_documentary", tell=SHIP_TELL),
            headers=headers,
        )
        weekly = client.post(
            "/api/shifts",
            json=_shift_body(cut="weekly_update", tell=FAMILY_DRAMA_TELL),
            headers=headers,
        )
    # Token is set, picks are valid. Spend path may HOLD (no Parallel) but must not 400 on tell words.
    assert doc.status_code != 400
    assert weekly.status_code != 400
    require_picks(
        "Hormuz",
        "youtube",
        "full_length_documentary",
        "decade",
        "centered_independent",
        SHIP_TELL,
        SEED_TONE,
    )
    seed = seed_first_open()
    seed.cut = "full_length_documentary"
    seed.tell = SHIP_TELL
    write_script(seed)
    assert "Leila" not in seed.script
    assert "(frame)" not in seed.script


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
        assert "tell" in missing.json()["detail"].lower()
        empty = client.post(
            "/api/shifts",
            json={**body, "tell": "   "},
            headers=headers,
        )
        assert empty.status_code == 400
        assert "tell" in empty.json()["detail"].lower()
    assert ledger.parallel_calls == before_p == 0
    assert ledger.imagen_calls == before_i == 0
    with pytest.raises(TellRequiredError, match="No tell chosen"):
        require_picks(
            "Hormuz",
            "youtube",
            "one_time_short_episode",
            "decade",
            "centered_independent",
            "",
        )


def test_tell_examples_are_not_an_enum() -> None:
    with TestClient(app) as client:
        body = client.get("/api/tell-examples").json()
        assert body["default"] is None
        assert body["examples"] == list(TELL_EXAMPLES)
        assert SEED_TELL in body["examples"]
        assert FAMILY_TELL in body["examples"]
        assert "genres" not in body
        assert client.get("/api/genres").status_code == 404
        assert client.get("/api/vantages").status_code == 404
    readme = Path("/workspace/README.md").read_text()
    assert SEED_TELL in readme
    assert FAMILY_TELL in readme
    assert "examples" in readme.lower()
    assert "genre `nonfiction`" not in readme
    assert "not a closed list" in readme.lower() or "not the only" in readme.lower()
    assert "![Architecture](docs/architecture.png)" in readme
    assert "architecture.svg)" not in readme
    assert "archive tape" in readme.lower()
    assert "maps and infographics" in readme.lower()
    png = Path("/workspace/docs/architecture.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    svg = Path("/workspace/docs/architecture.svg").read_text(encoding="utf-8")
    assert "<script" not in svg.lower()
    assert "foreignObject" not in svg
    assert "onload" not in svg.lower()
    assert all(ord(ch) < 128 for ch in svg)


def test_fiction_vo_has_no_receipt_jargon() -> None:
    banned = ("on the receipt", "hold on this card", "receipt card for", "tagged fringe", "propaganda yes")
    for tell in (FAMILY_TELL, SHIP_TELL):
        packet = _from_seed(tell=tell)
        blob = packet.script.lower()
        for word in banned:
            assert word not in blob
        assert re.search(r"\[[a-z0-9-]+\]", packet.script)
