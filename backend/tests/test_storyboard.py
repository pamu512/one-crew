from onecrew.models import Packet, Rails, ShotFrame
from onecrew.receipt import attach_frames
from onecrew.seed import seed_first_open


def test_imagen_down_frames_stay_missing() -> None:
    packet = Packet(
        id="oc-miss",
        hook="hook",
        script="Beat one [jcpoa-2018]. Beat two [hormuz-share].",
        cut="one_time_short_episode",
        platform="youtube",
        depth="decade",
        script_lean="centered_independent",
    )
    invented = [
        ShotFrame(
            id="nope",
            shot="Invented collage",
            image_href="/api/frames/nope",
        )
    ]
    down = Rails(parallel=True, vertex=False, imagen=False)
    attach_frames(packet, invented, rails=down)
    assert packet.frames == []

    imagen_only_down = Rails(parallel=True, vertex=True, imagen=False)
    attach_frames(packet, invented, rails=imagen_only_down)
    assert packet.frames == []


def test_storyboard_is_not_optional_on_seed() -> None:
    packet = seed_first_open()
    assert packet.script
    assert packet.frames
    assert "mood" not in " ".join(f.shot.lower() for f in packet.frames)
