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
        tone=SEED_TONE,
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

    assert packet.id == SEED_PACKET_ID
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


def test_leftover_hormuz_id_is_not_get_first_open() -> None:
    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.seed import seed_first_open

    seed_first_open()
    with TestClient(app) as client:
        first = client.get("/api/packets/oc-recession-july-2026")
        leftover = client.get("/api/packets/oc-hormuz-decade")
    assert first.status_code == 200
    assert first.json()["id"] == "oc-recession-july-2026"
    assert leftover.status_code == 404


def test_live_shaped_post_unique_packet_id_is_stored(monkeypatch) -> None:
    """POST body packet_id is persisted. Seed stays. Leftover Hormuz is not GET."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.seed import seed_first_open

    pid = "oc-are-we-near-recession-cf47test"
    excerpts = [
        "USREC=0 (July 2026).",
        "Nonfarm payrolls fell −23k.",
        "Sahm is −0.03 vs the 0.50 trigger.",
        "GDP printed 0.5, then 2.1, then 1.5.",
    ]

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(results=[])
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=excerpts,
                )
            ]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=excerpts,
                )
            ],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        return SimpleNamespace(
            output=SimpleNamespace(
                content="USREC=0 smashed into payrolls −23k. Sahm −0.03 vs 0.50.",
                basis=[],
            )
        )

    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-parallel-key")
    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    seed_first_open()
    body = {
        "topic": "Are we near recession?",
        "platform": "youtube",
        "cut": "one_time_short_episode",
        "depth": "2-3y",
        "script_lean": "centered_independent",
        "tell": "Host-only desk read of the last year of US recession prints",
        "tone": "On the cited print",
        "packet_id": pid,
    }
    with TestClient(app) as client:
        posted = client.post(
            "/api/shifts",
            json=body,
            headers={"X-Shift-Token": "correct-horse"},
        )
        assert posted.status_code == 200
        got = client.get(f"/api/packets/{pid}")
        seed = client.get("/api/packets/oc-recession-july-2026")
        leftover = client.get("/api/packets/oc-hormuz-decade")
    assert got.status_code == 200
    packet = got.json()
    assert packet["id"] == pid
    assert packet["id"] != "oc-hormuz-decade"
    assert packet["id"] != "oc-recession-july-2026"
    vo = packet["script"]
    assert "USREC=0" in vo
    assert "−23k" in vo or "-23k" in vo
    assert "gulf" not in vo.lower()
    assert "hormuz" not in vo.lower()
    assert "Grounded event inside" not in vo
    assert "Grounded event inside" not in (packet.get("research_pack") or "")
    assert seed.status_code == 200
    assert seed.json()["id"] == "oc-recession-july-2026"
    assert leftover.status_code == 404


def test_seed_upsert_does_not_wipe_live_packet() -> None:
    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.models import Packet
    from onecrew.seed import seed_first_open
    from onecrew.store import store

    seed_first_open()
    live = Packet(
        id="oc-live-keep-me",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="USREC=0 smashed into payrolls −23k.",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        status="ready",
    )
    store.upsert_packet(live)
    seed_first_open()
    with TestClient(app) as client:
        kept = client.get("/api/packets/oc-live-keep-me")
        seed = client.get("/api/packets/oc-recession-july-2026")
    assert kept.status_code == 200
    assert kept.json()["id"] == "oc-live-keep-me"
    assert seed.status_code == 200


def test_live_research_claim_is_not_grounded_event_inside() -> None:
    from onecrew.models import Finding, Packet, Receipt
    from onecrew.script import write_script

    packet = Packet(
        id="oc-live-grounded-ban",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        disposition="READY",
        written=True,
        findings=[
            Finding(
                id="timeline-hit",
                claim="Grounded event inside 2-3y: Are we near recession?",
                stamp="grounded",
                parallel_url="https://example.com/hit",
                parallel_status="hit",
                note="Parallel URL on this row.",
            )
        ],
    )
    write_script(packet)
    assert packet.script == ""
    assert packet.beats == []
    assert packet.status == "hold"


def test_tone_never_says_sit_with_this() -> None:
    from onecrew.tone import apply_tone

    spoken = apply_tone("USREC=0 smashed into payrolls −23k.", "Make the viewer think", fiction=False)
    assert "Sit with this" not in spoken
    assert "sit with this" not in spoken.lower()
