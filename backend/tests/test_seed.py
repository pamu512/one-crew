from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.models import MISSING
from onecrew.seed import OPEC_URL, seed_first_open


def test_first_open_packet_id_is_oc_hormuz_decade() -> None:
    packet = seed_first_open()
    assert packet.id == "oc-hormuz-decade"
    assert packet.topic.lower().find("hormuz") >= 0
    assert packet.depth == "decade"
    with TestClient(app) as client:
        body = client.get("/api/packets")
        ids = {p["id"] for p in body.json()["packets"]}
        assert "oc-hormuz-decade" in ids


def test_seeded_grounded_cause() -> None:
    packet = seed_first_open()
    grounded = [f for f in packet.receipt.findings if f.stamp == "grounded"]
    assert any(f.id == "jcpoa-2018" for f in grounded)
    jcpoa = next(f for f in grounded if f.id == "jcpoa-2018")
    assert jcpoa.parallel_status == "hit"
    assert jcpoa.parallel_url and jcpoa.parallel_url.startswith("http")


def test_seeded_mainstream_lean_present_or_missing_honestly() -> None:
    packet = seed_first_open()
    missing = next(f for f in packet.receipt.findings if f.id == "oil-panic")
    assert missing.stamp == "mainstream"
    assert "not a source" in missing.note.lower()
    assert missing.parallel_url is None
    assert missing.lean == MISSING
    assert missing.interests == MISSING
    present = next(f for f in packet.receipt.findings if f.id == "producer-frame")
    assert present.stamp == "mainstream"
    assert present.lean == "industry"
    assert present.lean != present.stamp
    assert present.interests == ["OPEC"]
    assert present.lean_url == OPEC_URL


def test_seeded_fringe_tagged() -> None:
    packet = seed_first_open()
    row = next(f for f in packet.receipt.findings if f.id == "secret-closure")
    assert row.stamp == "fringe"
    assert row.parallel_status == "miss"
    assert "never sold as fact" in row.note.lower()


def test_seeded_missing_causal_link() -> None:
    packet = seed_first_open()
    assert packet.receipt.causal_links
    link = packet.receipt.causal_links[0]
    assert link.stamp == MISSING
    assert link.parallel_url is None
    assert link.from_id == "jcpoa-2018"
    assert link.to_id == "oil-panic"


def test_seeded_four_shot_frames() -> None:
    import xml.etree.ElementTree as ET

    from onecrew import config

    packet = seed_first_open()
    assert len(packet.frames) == 4
    assert {f.id for f in packet.frames} == {
        "tanker-lane",
        "strait-map",
        "oil-share",
        "link-empty",
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
