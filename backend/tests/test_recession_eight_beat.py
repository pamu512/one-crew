"""Ship bar: recession YouTube episode is an 8-beat from the pack, not a Hormuz leftover."""

from onecrew.board import write_shot_list
from onecrew.config import SEED_PACKET_ID
from onecrew.models import Finding, Packet, Receipt
from onecrew.pack import write_research_pack
from onecrew.receipt import write_receipt
from onecrew.script import write_script
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE

FRED_USREC = "https://fred.stlouisfed.org/series/USREC"
BLS_PAYROLLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
BLS_UNEMP = "https://www.bls.gov/news.release/empsit.nr0.htm"
BEA_GDP = "https://www.bea.gov/data/gdp/gross-domestic-product"
FRED_SAHM = "https://fred.stlouisfed.org/series/SAHMREALTIME"
NBER = "https://www.nber.org/research/business-cycle-dating"
CONFERENCE_LEI = "https://www.conference-board.org/topics/us-leading-indicators"
ISM_URL = "https://www.ismworld.org/"

_BANNED_BOARD = (
    "gulf",
    "hormuz",
    "jcpoa",
    "leila",
    "reza",
    "grounded",
    "photoreal",
    "trading floor",
    "map table",
    "gulf of mexico",
    "video game",
)


def recession_fixture() -> Packet:
    packet = Packet(
        id="oc-recession-july-2026",
        topic="Is the US in a recession?",
        hook="Is the US in a recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell="Host-only desk read. Title is a question we will not answer with a forecast.",
        tone="Grounded in the record",
    )
    receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-july-2026",
                when="July 2026",
                claim="USREC=0 (July 2026).",
                stamp="grounded",
                title="USREC",
                parallel_url=FRED_USREC,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-23k",
                when="July 2026",
                claim="Nonfarm payrolls fell −23k.",
                stamp="grounded",
                title="BLS payrolls",
                parallel_url=BLS_PAYROLLS,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="unemp-41",
                when="July 2026",
                claim="Unemployment is 4.1%.",
                stamp="grounded",
                title="BLS unemployment",
                parallel_url=BLS_UNEMP,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="gdp-prints",
                when="2025-2026",
                claim="GDP printed 0.5, then 2.1, then 1.5.",
                stamp="grounded",
                title="BEA GDP",
                parallel_url=BEA_GDP,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="sahm-gap",
                when="July 2026",
                claim="Sahm is −0.03 vs the 0.50 trigger.",
                stamp="grounded",
                title="Sahm rule",
                parallel_url=FRED_SAHM,
                parallel_status="hit",
                note="Parallel URL on this row. NBER dates the cycle; FRED hosts the series.",
            ),
            Finding(
                id="lei-off",
                when="July 2026",
                claim="LEI +0.2%.",
                stamp="fringe",
                title="LEI",
                parallel_url=CONFERENCE_LEI,
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            ),
            Finding(
                id="ism-off",
                when="July 2026",
                claim="ISM 55.6.",
                stamp="fringe",
                title="ISM",
                parallel_url=ISM_URL,
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            ),
        ],
    )
    packet = write_receipt(packet, receipt)
    packet.exclusions = []
    write_research_pack(packet)
    return packet


def _spoken(packet: Packet) -> str:
    return packet.script + "\n" + "\n".join(b.vo for b in packet.beats if b.kind == "vo")


def test_recession_eight_beat_from_pack_not_hormuz() -> None:
    packet = recession_fixture()
    write_script(packet)
    packet.frames = write_shot_list(packet)
    vo = _spoken(packet)
    low = vo.lower()

    assert packet.id != SEED_PACKET_ID
    assert packet.id != "oc-hormuz-decade"
    assert packet.status == "ready"

    assert "USREC=0" in vo
    assert "July 2026" in vo
    assert "−23k" in vo or "-23k" in vo
    assert "4.1%" in vo
    assert "0.5" in vo and "2.1" in vo and "1.5" in vo
    assert "Sahm" in vo or "sahm" in low
    assert "−0.03" in vo or "-0.03" in vo
    assert "0.50" in vo
    assert "NBER" in vo or "FRED" in vo or "BLS" in vo

    assert "LEI" not in vo and "+0.2%" not in vo
    assert "ISM" not in vo and "55.6" not in vo
    assert "gulf" not in low
    assert "hormuz" not in low
    assert "jcpoa" not in low
    assert "leila" not in low
    assert "reza" not in low

    vo_beats = [b for b in packet.beats if b.kind == "vo"]
    assert len(vo_beats) == 8
    total = sum(b.duration_s for b in packet.beats)
    assert 6 * 60 <= total <= 12 * 60
    assert vo_beats[0].duration_s <= 25
    assert "USREC=0" in vo_beats[0].vo and ("−23k" in vo_beats[0].vo or "-23k" in vo_beats[0].vo)
    assert "forecast" in low
    assert "same object" in low or "not the same object" in low
    assert "near is not a switch" in low or "near is the gap" in low

    assert len(packet.frames) == 8
    board = " ".join(f.shot.lower() + " " + (f.line or "").lower() for f in packet.frames)
    for banned in _BANNED_BOARD:
        assert banned not in board, banned
    assert "trading floor" not in board
    assert all(f.footage in {"sourced", "imagen", "missing"} for f in packet.frames)
    assert any("usrec" in (f.shot + f.line).lower() for f in packet.frames)
    assert any("sahm" in (f.shot + f.line).lower() for f in packet.frames)
    assert any("bls" in (f.shot + f.line).lower() or "4.1" in (f.shot + f.line) for f in packet.frames)
    eyes = packet.frames[0].shot.lower()
    assert "usrec" in eyes and ("23k" in eyes or "payroll" in eyes)
    assert "host" not in eyes


def test_empty_or_numberless_pack_holds() -> None:
    empty = Packet(
        id="oc-empty",
        topic="Whatever",
        hook="Whatever",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
    )
    empty.receipt = Receipt(packet_id=empty.id, disposition="READY", findings=[], written=True)
    write_script(empty)
    assert empty.script == ""
    assert empty.beats == []
    assert empty.status == "hold"

    bare = Packet(
        id="oc-no-nums",
        topic="A feeling about the weather",
        hook="A feeling about the weather",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell="Host only",
        tone=SEED_TONE,
    )
    bare.receipt = Receipt(
        packet_id=bare.id,
        disposition="READY",
        written=True,
        findings=[
            Finding(
                id="mood",
                claim="People feel uneasy.",
                stamp="mainstream",
                parallel_status="n/a",
                note="Widely repeated, may be bias, not a source.",
            )
        ],
    )
    write_script(bare)
    assert bare.script == ""
    assert bare.beats == []
    assert bare.status == "hold"


def test_snapshot_id_never_is_hormuz_seed() -> None:
    from onecrew.agent.shift import snapshot_id

    assert snapshot_id("Is the US in a recession?", "shift-abc123def") != SEED_PACKET_ID
    assert snapshot_id("Hormuz", "shift-xyz98765") != SEED_PACKET_ID
    assert "hormuz-decade" not in snapshot_id("Hormuz strait", "shift-xxxxxxxx")
