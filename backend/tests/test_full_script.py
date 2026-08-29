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


def test_feature_family_is_a_full_screenplay_not_six_beats() -> None:
    packet = _tell(tell=FAMILY_TELL, cut="feature_film")
    scenes = _scenes(packet)
    assert len(scenes) >= 8
    assert len(packet.frames) >= 20
    assert len(packet.beats) > len(packet.receipt.findings)
    assert "INT." in packet.script or "EXT." in packet.script
    assert "Leila" in packet.script
    assert "(frame)" in packet.script
    assert "[jcpoa-2018]" in packet.script
    assert "got blown" not in packet.script.lower()
    assert "exploded" not in packet.script.lower()
    assert all("receipt card" not in f.shot.lower() for f in packet.frames)
    assert any(f.shot_no >= 20 for f in packet.frames)
    left = _tell(tell=FAMILY_TELL, cut="feature_film", lean="left")
    right = _tell(tell=FAMILY_TELL, cut="feature_film", lean="right")
    stamps = lambda p: [(f.id, f.stamp, f.propaganda, f.lean) for f in p.receipt.findings]
    assert stamps(left) == stamps(right) == stamps(packet)
    assert len(_scenes(left)) >= 8 and len(_scenes(right)) >= 8
    assert len(left.frames) >= 20 and len(right.frames) >= 20


def test_nonfiction_episode_is_narrator_led_and_thick() -> None:
    packet = _tell(tell=SEED_TELL, cut="one_time_short_episode")
    scenes = _scenes(packet)
    assert len(scenes) >= 8
    assert len(packet.beats) > len(packet.receipt.findings)
    assert "Leila" not in packet.script
    assert "Reza" not in packet.script
    assert "(frame)" not in packet.script
    assert "HOST" in packet.script or "NARRATOR" in packet.script
    counts: dict[str, int] = {}
    for beat in packet.beats:
        for fid in beat.finding_ids:
            if fid in {f.id for f in packet.receipt.findings}:
                counts[fid] = counts.get(fid, 0) + 1
    assert any(n >= 2 for n in counts.values())
    fringe = next(f for f in packet.receipt.findings if f.stamp == "fringe")
    assert f"[{fringe.id}]" in packet.script
    house = next(f for f in packet.receipt.findings if f.propaganda == "yes")
    assert f"[{house.id}]" in packet.script
    oil = next(f for f in packet.receipt.findings if f.id == "oil-panic")
    assert oil.lean == MISSING


def test_tiktok_short_is_complete_not_three_pasted_claims() -> None:
    packet = _tell(tell=SEED_TELL, cut="tiktok-length")
    packet.platform = "tiktok"
    write_script(packet)
    packet.frames = write_shot_list(packet)
    assert len(packet.beats) > 3
    assert len(packet.frames) >= len([b for b in packet.beats if b.kind != "heading"])
    assert sum(b.duration_s for b in packet.beats) < 60
    assert all(b.finding_ids for b in packet.beats if b.kind == "vo")


def test_skinny_one_beat_per_finding_is_gone() -> None:
    episode = _tell(tell=SEED_TELL, cut="one_time_short_episode")
    feature = _tell(tell=FAMILY_TELL, cut="feature_film")
    assert len(episode.beats) >= len(episode.receipt.findings) * 2
    assert len(feature.beats) >= 16
    assert len(feature.frames) >= 20
