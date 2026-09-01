from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.floor import FLOOR_HTML
from onecrew.models import MISSING
from onecrew.seed import leftover_hormuz_packet, seed_first_open
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE


def test_first_open_packet_id_is_oc_recession_july_2026() -> None:
    packet = seed_first_open()
    assert packet.id == "oc-recession-july-2026"
    assert packet.id != "oc-hormuz-decade"
    assert packet.topic == "Are we near recession?"
    assert "hormuz" not in packet.topic.lower()
    assert packet.depth == "1y"
    assert packet.cut == "one_time_short_episode"
    assert packet.platform == "youtube"
    assert packet.script_lean == "centered_independent"
    assert packet.tell == SEED_TELL
    assert packet.tone == SEED_TONE
    assert packet.tone != "Grounded in the record"
    assert packet.research_pack
    assert "usrec-july-2026" in packet.research_pack
    assert "USREC=0" in packet.script
    assert "−23k" in packet.script or "-23k" in packet.script
    assert "hormuz" not in packet.script.lower()
    assert "jcpoa" not in packet.script.lower()
    assert len([b for b in packet.beats if b.kind == "vo"]) == 8
    assert "Leila" not in packet.script
    leftover = leftover_hormuz_packet()
    assert leftover.id == "oc-hormuz-decade"
    assert leftover.id != packet.id
    with TestClient(app) as client:
        body = client.get("/api/packets")
        ids = {p["id"] for p in body.json()["packets"]}
        assert "oc-recession-july-2026" in ids
        assert "oc-hormuz-decade" not in ids


def test_seeded_grounded_cause() -> None:
    packet = seed_first_open()
    grounded = [f for f in packet.receipt.findings if f.stamp == "grounded"]
    assert any(f.id == "usrec-july-2026" for f in grounded)
    usrec = next(f for f in grounded if f.id == "usrec-july-2026")
    assert usrec.parallel_status == "hit"
    assert usrec.parallel_url and usrec.parallel_url.startswith("http")
    leftover = leftover_hormuz_packet()
    jcpoa = next(f for f in leftover.receipt.findings if f.id == "jcpoa-2018")
    assert jcpoa.stamp == "grounded"
    assert jcpoa.parallel_status == "hit"


def test_seeded_mainstream_lean_present_or_missing_honestly() -> None:
    packet = seed_first_open()
    missing = next(f for f in packet.receipt.findings if f.id == "already-in")
    assert missing.stamp == "mainstream"
    assert "not a source" in missing.note.lower()
    assert missing.parallel_url is None
    assert missing.lean == MISSING
    leftover = leftover_hormuz_packet()
    present = next(f for f in leftover.receipt.findings if f.id == "producer-frame")
    assert present.stamp == "mainstream"
    assert present.lean == "industry"
    assert present.lean != present.stamp
    assert present.interests == ["OPEC"]


def test_seeded_fringe_tagged() -> None:
    packet = seed_first_open()
    row = next(f for f in packet.receipt.findings if f.id == "lei-july-2026")
    assert row.stamp == "fringe"
    assert row.parallel_status == "miss"
    assert "never sold as fact" in row.note.lower()


def test_leftover_hormuz_missing_causal_link() -> None:
    leftover = leftover_hormuz_packet()
    assert leftover.receipt.causal_links
    link = leftover.receipt.causal_links[0]
    assert link.stamp == MISSING
    assert link.parallel_url is None
    assert link.from_id == "jcpoa-2018"
    assert link.to_id == "oil-panic"
    seed = seed_first_open()
    assert seed.receipt.causal_links == []


def test_seed_shows_script_and_storyboard_together() -> None:
    packet = seed_first_open()
    assert packet.script.strip()
    assert "[usrec-july-2026]" in packet.script
    assert len(packet.frames) >= 1
    assert all(frame.shot.strip() for frame in packet.frames)


def test_seeded_shot_list_matches_timed_vo() -> None:
    import xml.etree.ElementTree as ET

    from onecrew import config

    packet = seed_first_open()
    assert packet.beats
    assert len(packet.frames) >= 8
    assert len(packet.frames) >= len([b for b in packet.beats if b.kind != "heading"])
    assert {f.id for f in packet.frames} != {
        "tanker-lane",
        "strait-map",
        "oil-share",
        "link-empty",
    }
    assert all("hormuz-share" not in f.id for f in packet.frames)
    beat_ids = {b.id for b in packet.beats}
    for frame in packet.frames:
        assert frame.beat_id in beat_ids
        assert frame.shot.strip()
        assert "mood" not in frame.shot.lower()
        assert frame.imagen is False
        assert frame.footage == "missing"
        assert frame.footage_url is None
        assert "ap reel" not in (frame.footage_title or "").lower()
        assert "ap.org" not in (frame.footage_url or "")
        svg = (config.FRAMES_DIR / f"{frame.id}.svg").read_bytes()
        assert all(b >= 32 or b in (9, 10, 13) for b in svg)
        ET.fromstring(svg)


def test_seeded_receipt_has_parallel_hit_and_miss() -> None:
    packet = seed_first_open()
    assert packet.receipt is not None
    assert packet.receipt.written is True
    assert packet.receipt.parallel_hit is True
    assert packet.receipt.parallel_miss is True


def test_seed_wired_output_is_what_the_creator_gets() -> None:
    """One pass over the first-open packet after every lock is wired."""
    packet = seed_first_open()
    pack = packet.research_pack
    assert pack
    assert len(pack) >= 2000
    for heading in (
        "## Question",
        "## Picks",
        "## Tell",
        "## Tone",
        "## Timeline of what led here",
        "## Sources",
        "## Causal links",
        "## What we could not find",
        "## Left out / not included",
    ):
        assert heading in pack
    for finding in packet.receipt.findings:
        assert finding.id in pack
        assert finding.claim in pack
        assert f"The stamp is {finding.stamp} (grounded|mainstream|fringe)." in pack
    for marker in (
        "grounded|mainstream|fringe",
        "parallel =",
        "lean =",
        "interests =",
        "who_repeats =",
        "independent =",
        "vested_interest =",
        "propaganda =",
        "collision =",
    ):
        assert pack.count(marker) >= len(packet.receipt.findings)
    assert packet.exclusions
    assert any(row.reason for row in packet.exclusions)
    assert f"reason={packet.exclusions[0].reason}" in pack
    assert packet.tell == SEED_TELL
    assert packet.tone == SEED_TONE
    scenes: list[str] = []
    for beat in packet.beats:
        heading = (beat.scene or beat.act or "").strip()
        if heading and heading not in scenes:
            scenes.append(heading)
        assert beat.collision == MISSING
        assert beat.collision_kind == MISSING
    assert len(scenes) >= 8
    assert "HOST" in packet.script or "NARRATOR" in packet.script
    assert "[usrec-july-2026]" in packet.script
    assert len(packet.frames) >= 8
    assert all(frame.shot.strip() for frame in packet.frames)
    assert all(frame.footage in {"sourced", "missing"} for frame in packet.frames)
    assert all(frame.imagen is False for frame in packet.frames)
    assert "Research pack" in FLOOR_HTML
    assert "publish" not in FLOOR_HTML.lower()
    with TestClient(app) as client:
        body = client.get("/api/packets")
        assert body.status_code == 200
        seeded = body.json()["packets"][0]
        assert seeded["id"] == "oc-recession-july-2026"
        assert seeded["research_pack"]
        assert len(seeded["research_pack"]) >= 2000
        assert "## Left out / not included" in seeded["research_pack"]
        assert seeded["tell"] == packet.tell
        assert seeded["tone"] == packet.tone
        assert seeded["exclusions"]
        assert seeded["script"].strip()
        assert len(seeded["frames"]) >= 8
