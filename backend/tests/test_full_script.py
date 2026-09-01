import copy

from onecrew.board import write_shot_list
from onecrew.models import MISSING
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.tell import SEED_TELL

FAMILY_TELL = "One family in Bandar Abbas, kitchen radio on"


def _tell(*, tell: str, cut: str, lean: str = "centered_independent"):
    packet = seed_first_open()
    packet.tell = tell
    packet.cut = cut
    packet.script_lean = lean
    packet.receipt = copy.deepcopy(packet.receipt)
    write_script(packet)
    packet.frames = write_shot_list(packet)
    return packet


def _scenes(packet) -> list[str]:
    seen: list[str] = []
    for beat in packet.beats:
        heading = (beat.scene or beat.act or "").strip()
        if heading and heading not in seen:
            seen.append(heading)
    return seen


def test_feature_family_is_eight_beats_with_frame() -> None:
    packet = _tell(tell=FAMILY_TELL, cut="feature_film")
    scenes = _scenes(packet)
    assert len(scenes) == 8
    assert len(packet.frames) == 8
    assert "Leila" not in packet.script
    assert "(frame)" in packet.script
    assert "got blown" not in packet.script.lower()
    assert "exploded" not in packet.script.lower()
    assert all("receipt card" not in f.shot.lower() for f in packet.frames)
    left = _tell(tell=FAMILY_TELL, cut="feature_film", lean="left")
    right = _tell(tell=FAMILY_TELL, cut="feature_film", lean="right")
    stamps = lambda p: [(f.id, f.stamp, f.propaganda, f.lean) for f in p.receipt.findings]
    assert stamps(left) == stamps(right) == stamps(packet)
    assert len(_scenes(left)) == 8 and len(_scenes(right)) == 8


def test_nonfiction_episode_is_narrator_led_eight_beats() -> None:
    packet = _tell(tell=SEED_TELL, cut="one_time_short_episode")
    scenes = _scenes(packet)
    assert len(scenes) == 8
    assert len([b for b in packet.beats if b.kind == "vo"]) == 8
    assert "Leila" not in packet.script
    assert "Reza" not in packet.script
    assert "(frame)" not in packet.script
    assert "HOST" in packet.script or "NARRATOR" in packet.script
    oil = next(f for f in packet.receipt.findings if f.id == "already-in")
    assert oil.lean == MISSING


def test_tiktok_short_is_complete_not_three_pasted_claims() -> None:
    packet = _tell(tell=SEED_TELL, cut="tiktok-length")
    packet.platform = "tiktok"
    write_script(packet)
    packet.frames = write_shot_list(packet)
    assert len(packet.beats) == 8
    assert len(packet.frames) == 8
    assert sum(b.duration_s for b in packet.beats) < 60
    assert all(b.finding_ids for b in packet.beats if b.kind == "vo")


def test_eight_beat_not_one_per_finding() -> None:
    episode = _tell(tell=SEED_TELL, cut="one_time_short_episode")
    feature = _tell(tell=FAMILY_TELL, cut="feature_film")
    assert len([b for b in episode.beats if b.kind == "vo"]) == 8
    assert len([b for b in feature.beats if b.kind == "vo"]) == 8
    assert 6 * 60 <= sum(b.duration_s for b in episode.beats) <= 12 * 60
