import re
from types import SimpleNamespace

from onecrew.agent.shift import _board
from onecrew.models import Finding, Packet, Rails, Receipt, ShotFrame
from onecrew.receipt import attach_frames
from onecrew.script import write_script
from onecrew.seed import seed_first_open


def _dairy_packet() -> Packet:
    packet = Packet(
        id="oc-dairy",
        topic="Explain dairy prices",
        hook="Explain dairy prices",
        script="",
        platform="tiktok",
        cut="tiktok-length",
        depth="1y",
        script_lean="centered_independent",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="milk-spot",
                claim="Spot milk prices moved 3.2% after the spring auction.",
                stamp="grounded",
                parallel_url="https://example.com/milk",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="milk-frame",
                claim="Any dairy headline means shelves go empty overnight.",
                stamp="mainstream",
                parallel_status="n/a",
                note="Widely repeated, may be bias, not a source.",
            ),
            Finding(
                id="milk-fringe",
                claim="A hidden treaty already banned milk exports.",
                stamp="fringe",
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            ),
        ],
    )
    return write_script(packet)


def test_imagen_down_keeps_shot_list_images_missing() -> None:
    packet = _dairy_packet()
    down = Rails(parallel=True, vertex=False, imagen=False)
    frames = _board(packet, down)
    assert frames
    assert all(frame.shot.strip() for frame in frames)
    assert all(frame.image_href == "" for frame in frames)
    assert all(frame.imagen is False for frame in frames)
    attach_frames(packet, frames, rails=down)
    assert packet.frames
    assert all(frame.image_href == "" for frame in packet.frames)

    invented = [
        ShotFrame(
            id="nope",
            shot="Invented collage",
            image_href="/api/frames/nope",
            imagen=True,
            beat_id="x",
        )
    ]
    attach_frames(packet, invented, rails=down)
    assert packet.frames
    assert packet.frames[0].shot == "Invented collage"
    assert packet.frames[0].image_href == ""
    assert packet.frames[0].imagen is False


def test_board_does_not_return_hardcoded_hormuz_stills(monkeypatch) -> None:
    packet = _dairy_packet()
    returned = []

    def miss(*_a, **_k):
        return SimpleNamespace(results=[])

    monkeypatch.setattr("onecrew.board.search", miss)

    def fake_gen(*, prompt: str, number_of_images: int = 1):
        returned.append(prompt)
        return SimpleNamespace(
            generated_images=[
                SimpleNamespace(image=SimpleNamespace(image_bytes=b"<svg xmlns='http://www.w3.org/2000/svg'/>"))
            ]
        )

    monkeypatch.setattr("onecrew.board.generate_frames", fake_gen)
    monkeypatch.setattr("onecrew.imagen_client.generate_frames", fake_gen)
    rails = Rails(parallel=True, vertex=True, imagen=True)
    frames = _board(packet, rails)
    ids = {frame.id for frame in frames}
    assert frames
    assert returned, "generate_frames return must be used"
    assert "tanker-lane" not in ids
    assert "strait-map" not in ids
    assert "oil-share" not in ids
    assert "link-empty" not in ids
    assert "ranking-phone" not in ids
    assert any("milk" in frame.shot.lower() or "dairy" in frame.shot.lower() or "auction" in frame.shot.lower() for frame in frames)
    assert all("receipt card" not in frame.shot.lower() for frame in frames)
    assert any(frame.beat_id for frame in frames)
    assert all(not frame.imagen or frame.kind in {"infographic", "motion_graphic"} for frame in frames)
    assert all(frame.footage != "sourced" or frame.footage_url for frame in frames)


def test_hold_does_not_invent_frames() -> None:
    packet = Packet(
        id="oc-hold-board",
        hook="hook",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
    )
    packet.receipt = Receipt(
        packet_id=packet.id, disposition="HOLD", findings=[], written=True
    )
    write_script(packet)
    frames = _board(packet, Rails(parallel=True, vertex=True, imagen=True))
    assert packet.script == ""
    assert frames == []
    attach_frames(packet, [ShotFrame(id="x", shot="nope", image_href="/x")], rails=Rails(parallel=True, vertex=True, imagen=True))
    assert packet.frames == []


def test_storyboard_is_cut_from_seed_vo() -> None:
    packet = seed_first_open()
    assert packet.script
    assert "ACT" in packet.script
    assert packet.beats
    assert packet.frames
    assert "mood" not in " ".join(f.shot.lower() for f in packet.frames)
    assert {f.id for f in packet.frames} != {
        "tanker-lane",
        "strait-map",
        "oil-share",
        "link-empty",
    }
    beat_ids = {b.id for b in packet.beats}
    for frame in packet.frames:
        assert frame.beat_id in beat_ids
        assert frame.shot.strip()
        assert "receipt card" not in frame.shot.lower()
        assert "on the receipt" not in frame.shot.lower()
    board = " ".join(f.shot.lower() for f in packet.frames)
    assert "gulf" not in board
    assert "grounded" not in board
    assert "photoreal" not in board
    assert "tanker-lane" not in {f.id for f in packet.frames}
    assert len(packet.frames) == 8
    board = " ".join(f"{f.shot} {f.line or ''}" for f in packet.frames)
    assert not re.search(r"\bStories\b|\bReels\b", board)


def test_youtube_episode_board_is_not_stories_reels() -> None:
    """youtube + one_time_short_episode must not emit Stories/Reels chrome or that ReceiptInvalidError."""
    import re

    from onecrew.board import write_shot_list
    from onecrew.models import Finding, Packet, Receipt
    from onecrew.receipt import write_receipt
    from onecrew.script import _assemble

    miss = Finding(
        id="fringe-miss",
        claim="A fringe claim about hidden offtake contracts.",
        stamp="fringe",
        parallel_status="miss",
        note="Parallel miss. Included and tagged fringe. Never sold as fact.",
    )
    stamps = [
        Finding(
            id=f"te-campus-event-{i:02d}",
            claim=f"A cited campus event {i} stayed on the card.",
            stamp="timeline_event",
            title="timeline_event",
            series="timeline_event",
            print=f"A cited campus event {i} stayed on the card.",
            when="August 2026",
            parallel_url=f"https://www.example.com/campus-event-{i:02d}",
            parallel_status="hit",
            note="Timeline event. Parallel URL on this row.",
        )
        for i in range(17)
    ]
    packet = Packet(
        id="oc-yt-episode-board",
        topic="Compute campuses are going to cause the next economic bubble",
        hook="Compute campuses are going to cause the next economic bubble",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited campus prints",
        tone="On the cited print",
        research_pack="Cited campus events from Parallel hits.",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=stamps + [miss],
    )
    write_receipt(packet, packet.receipt)
    units = [
        {"id": "cold-open", "vo": stamps[0].claim, "eyes": "card", "finding_ids": [stamps[0].id]},
        {"id": "promise", "vo": "The title stays a question.", "eyes": "pack", "finding_ids": []},
        {"id": "gdp", "vo": stamps[1].claim, "eyes": "card", "finding_ids": [stamps[1].id]},
        {"id": "labor", "vo": stamps[2].claim, "eyes": "card", "finding_ids": [stamps[2].id]},
        {"id": "turn", "vo": "Hold on the cited print.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "Receipt board: cited events from the pack.", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    written = _assemble(packet, units)
    shots = write_shot_list(written)
    assert shots
    blob = " ".join(f"{s.shot} {s.line or ''} {s.kind or ''}" for s in shots)
    assert not re.search(r"\bStories\b|\bReels\b", blob)
    assert written.cut == "one_time_short_episode"
    assert written.platform == "youtube"
    assert len(written.receipt.findings) > 8
