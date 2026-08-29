from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.seed import seed_first_open


def test_first_open_packet_id_is_oc_pickle_debt() -> None:
    packet = seed_first_open()
    assert packet.id == "oc-pickle-debt"
    with TestClient(app) as client:
        body = client.get("/api/packets")
        ids = {p["id"] for p in body.json()["packets"]}
        assert "oc-pickle-debt" in ids


def test_seeded_grounded_ranking_hit() -> None:
    packet = seed_first_open()
    grounded = next(f for f in packet.receipt.findings if f.stamp == "grounded")
    assert grounded.id == "ranking-hit"
    assert grounded.parallel_status == "hit"
    assert grounded.parallel_url and grounded.parallel_url.startswith("http")
    assert "ranking" in grounded.claim.lower() or "ranks" in grounded.claim.lower()


def test_seeded_mainstream_3am_kitchen() -> None:
    packet = seed_first_open()
    row = next(f for f in packet.receipt.findings if f.id == "3am-kitchen")
    assert row.stamp == "mainstream"
    assert "3am" in row.claim.lower() or "3am" in row.id
    assert "not a source" in row.note.lower()
    assert row.parallel_url is None


def test_seeded_fringe_nasa_miss() -> None:
    packet = seed_first_open()
    row = next(f for f in packet.receipt.findings if f.id == "nasa-miss")
    assert row.stamp == "fringe"
    assert row.parallel_status == "miss"
    assert "nasa" in row.claim.lower()
    assert "never sold as fact" in row.note.lower()


def test_seeded_four_shot_frames() -> None:
    import xml.etree.ElementTree as ET

    from onecrew import config

    packet = seed_first_open()
    assert len(packet.frames) == 4
    assert {f.id for f in packet.frames} == {
        "jar-pour",
        "kitchen-3am",
        "ranking-phone",
        "nasa-empty",
    }
    for frame in packet.frames:
        assert frame.shot.strip()
        assert "mood" not in frame.shot.lower()
        svg = (config.FRAMES_DIR / f"{frame.id}.svg").read_bytes()
        assert all(b >= 32 or b in (9, 10, 13) for b in svg)
        ET.fromstring(svg)


def test_seeded_receipt_has_parallel_hit_and_miss() -> None:
    packet = seed_first_open()
    assert packet.receipt is not None
    assert packet.receipt.written is True
    assert packet.receipt.parallel_hit is True
    assert packet.receipt.parallel_miss is True
