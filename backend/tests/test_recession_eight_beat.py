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

_LEFTOVER_SLOT_IDS = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})


def _assert_live_recession_findings(packet: dict) -> None:
    """Pack text with USREC + payrolls cannot be leftover 3-slot findings only."""
    receipt = packet.get("receipt") or {}
    findings = list(receipt.get("findings") or [])
    pack = " ".join(
        [
            packet.get("research_pack") or "",
            packet.get("task_spine") or "",
            *(f.get("claim") or "" for f in findings),
        ]
    )
    ids = {f.get("id") for f in findings}
    if "USREC" in pack and "payroll" in pack.lower():
        assert ids != _LEFTOVER_SLOT_IDS
        assert not ids <= _LEFTOVER_SLOT_IDS
    usrec = next(
        (f for f in findings if "usrec" in (f.get("id") or "").lower() or "usrec" in (f.get("claim") or "").lower()),
        None,
    )
    payrolls = next(
        (
            f
            for f in findings
            if "payroll" in (f.get("id") or "").lower() or "payroll" in (f.get("claim") or "").lower()
        ),
        None,
    )
    assert usrec is not None
    assert payrolls is not None
    assert "USREC" in (usrec.get("claim") or "")
    assert "0" in (usrec.get("claim") or "")
    claim = payrolls.get("claim") or ""
    assert "payroll" in claim.lower()
    assert "−23k" in claim or "-23k" in claim or "23k" in claim.lower()
    assert usrec.get("id") not in _LEFTOVER_SLOT_IDS
    assert payrolls.get("id") not in _LEFTOVER_SLOT_IDS
    if usrec.get("stamp") == "grounded":
        assert (usrec.get("parallel_url") or "").startswith("http")
    if payrolls.get("stamp") == "grounded":
        assert (payrolls.get("parallel_url") or "").startswith("http")


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
                series="USREC",
                print="0",
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
                series="BLS payrolls",
                print="−23k",
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
                series="U-3",
                print="4.1%",
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
                series="GDP",
                print="0.5 / 2.1 / 1.5",
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
                series="SAHMREALTIME",
                print="−0.03",
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
    assert bare.status == "hold"
    assert "pack has no numbers" in ((bare.receipt.hold_reason or "") if bare.receipt else "")
    assert bare.beats == [] or len(bare.beats) == 8


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
        "Nonfarm payrolls fell −23k in July 2026.",
        "Sahm is −0.03 vs the 0.50 trigger.",
        "GDP printed 0.5, then 2.1, then 1.5.",
    ]

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/hidden-treaty",
                        title="Hidden treaty",
                        excerpts=["Secret double-dip already started in May."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=["USREC=0 (July 2026)."],
                ),
                SimpleNamespace(
                    url="https://www.bls.gov/news.release/empsit.nr0.htm",
                    title="Employment Situation",
                    excerpts=["Nonfarm payrolls fell −23k in July 2026."],
                ),
                SimpleNamespace(
                    url="https://www.bea.gov/data/gdp/gross-domestic-product",
                    title="BEA GDP",
                    excerpts=["GDP printed 0.5, then 2.1, then 1.5."],
                ),
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/SAHMREALTIME",
                    title="SAHMREALTIME",
                    excerpts=["Sahm is −0.03 vs the 0.50 trigger."],
                ),
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
                content="USREC July 2026 = 0. Nonfarm payrolls fell −23k in July 2026. GDP printed 0.5, then 2.1, then 1.5. Sahm −0.03 vs 0.50.",
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
    _assert_live_recession_findings(packet)
    assert seed.status_code == 200
    assert seed.json()["id"] == "oc-recession-july-2026"
    assert leftover.status_code == 404


def test_live_task_spine_mints_named_series_not_leftover_slots(monkeypatch) -> None:
    """Task pro already has the numbers. Search excerpts do not. Findings must still be named series."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.seed import seed_first_open

    pid = "oc-recession-live-sep1b-test"

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/hidden-treaty",
                        title="Hidden treaty",
                        excerpts=["Secret double-dip already started in May."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=["Federal Reserve Bank of St. Louis recession indicator."],
                ),
                SimpleNamespace(
                    url="https://www.bls.gov/news.release/empsit.nr0.htm",
                    title="Employment Situation",
                    excerpts=["BLS Employment Situation release."],
                ),
                SimpleNamespace(
                    url="https://www.bea.gov/data/gdp/gross-domestic-product",
                    title="BEA GDP",
                    excerpts=["BEA GDP release."],
                ),
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/SAHMREALTIME",
                    title="SAHMREALTIME",
                    excerpts=["FRED Sahm rule series page."],
                ),
            ]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=["Federal Reserve Bank of St. Louis recession indicator."],
                )
            ],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        return SimpleNamespace(
            output=SimpleNamespace(
                content=(
                    "USREC July 2026 = 0. Nonfarm payrolls −23k in July 2026. "
                    "GDP 0.5/2.1/1.5. Sahm −0.03 vs 0.50."
                ),
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
    assert got.status_code == 200
    packet = got.json()
    assert packet["id"] == pid
    _assert_live_recession_findings(packet)
    ids = {f["id"] for f in (packet.get("receipt") or {}).get("findings") or []}
    assert ids != _LEFTOVER_SLOT_IDS
    assert "timeline-hit" not in ids
    assert "timeline-frame" not in ids
    assert "timeline-miss" not in ids
    gdp = next(
        (f for f in packet["receipt"]["findings"] if "gdp" in f["id"].lower() or "gdp" in f["claim"].lower()),
        None,
    )
    sahm = next(
        (f for f in packet["receipt"]["findings"] if "sahm" in f["id"].lower() or "sahm" in f["claim"].lower()),
        None,
    )
    assert gdp is not None
    assert "0.5" in gdp["claim"] and "2.1" in gdp["claim"] and "1.5" in gdp["claim"]
    assert sahm is not None
    assert ("−0.03" in sahm["claim"] or "-0.03" in sahm["claim"]) and "0.50" in sahm["claim"]


def test_independent_missing_with_url_holds_not_500(monkeypatch) -> None:
    """ReceiptInvalidError must HOLD the unique packet. Never HTTP 500."""
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from onecrew.api import app
    from onecrew.models import MISSING, Finding, Receipt
    from onecrew.seed import seed_first_open

    pid = "oc-independent-missing-url-hold"

    def bad_research(packet, rails, depth):
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="READY",
            findings=[
                Finding(
                    id="usrec",
                    claim="USREC=0 (July 2026).",
                    stamp="grounded",
                    title="USREC",
                    parallel_url="https://fred.stlouisfed.org/series/USREC",
                    parallel_status="hit",
                    note="Parallel URL on this row.",
                    independent=MISSING,
                    independent_url="https://fred.stlouisfed.org/series/USREC",
                ),
                Finding(
                    id="fringe-unsourced",
                    claim="Fringe claim about recession",
                    stamp="fringe",
                    parallel_status="miss",
                    note="Parallel miss. Included and tagged fringe. Never sold as fact.",
                ),
            ],
        )
        return receipt, [], ["https://fred.stlouisfed.org/series/USREC"], "USREC=0 payrolls −23k"

    monkeypatch.setenv("SHIFT_TOKEN", "correct-horse")
    monkeypatch.setenv("PARALLEL_API_KEY", "test-parallel-key")
    monkeypatch.setattr("onecrew.agent.shift._research", bad_research)
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
        assert posted.status_code != 500
        assert posted.status_code == 200
        got = client.get(f"/api/packets/{pid}")
    assert got.status_code == 200
    packet = got.json()
    assert packet["id"] == pid
    assert packet["status"] == "hold"


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


def test_vertex_hollow_eight_beat_keeps_pack_numbers(monkeypatch) -> None:
    """Vertex overwriting _eight_from_pack with '2026 smashed into 0' is discarded."""
    import json

    packet = recession_fixture()
    packet.id = "oc-recession-live-sep1b"
    hollow = {
        "beats": [
            {
                "id": bid,
                "vo": (
                    "2026 smashed into 0."
                    if bid == "cold-open"
                    else "Fringe claim about Are we near recession?"
                ),
                "eyes": "hollow",
                "finding_ids": ["usrec-july-2026", "payrolls-23k"],
            }
            for bid in (
                "cold-open",
                "promise",
                "gdp",
                "labor",
                "turn",
                "complication",
                "receipt",
                "close",
            )
        ]
    }

    monkeypatch.setattr("onecrew.script.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda *_a, **_k: json.dumps(hollow))
    write_script(packet)
    vo = _spoken(packet)
    assert packet.status == "ready"
    assert "USREC=0" in vo
    assert "−23k" in vo or "-23k" in vo or "payrolls −23" in vo or "payrolls -23" in vo
    assert "2026 smashed into 0" not in vo
    assert "Fringe claim about Are we near recession?" not in vo
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert cold.duration_s <= 25
    assert "USREC=0" in cold.vo
    assert "−23k" in cold.vo or "-23k" in cold.vo or "payroll" in cold.vo.lower()
    assert "USREC=0" in (cold.frame or "") or "23k" in (cold.frame or "")
    assert "Sahm" in vo or "sahm" in vo.lower()
    assert "−0.03" in vo or "-0.03" in vo
    assert "0.50" in vo
    assert "LEI" not in vo and "ISM" not in vo


def test_stuffed_fringe_claim_about_topic_holds() -> None:
    packet = Packet(
        id="oc-stuffed-fringe",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        research_pack="Print 7 on the desk.",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        disposition="READY",
        written=True,
        findings=[
            Finding(
                id="print-7",
                claim="Print 7.",
                stamp="grounded",
                parallel_url="https://example.com/print",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="fringe-unsourced",
                claim="Fringe claim about Are we near recession?",
                stamp="fringe",
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            ),
        ],
    )
    write_script(packet)
    vo = _spoken(packet)
    assert "Fringe claim about Are we near recession?" not in vo
    assert packet.script == ""
    assert packet.beats == []
    assert packet.status == "hold"


def test_tone_never_says_sit_with_this() -> None:
    from onecrew.tone import apply_tone

    spoken = apply_tone("USREC=0 smashed into payrolls −23k.", "Make the viewer think", fiction=False)
    assert "Sit with this" not in spoken
    assert "sit with this" not in spoken.lower()


_FIRST_TRIGGER_SPINE = (
    "what_counts_as_the_first_trigger: Geopolitical episode and energy-price surge "
    "in February/March 2026.\n"
    "executive_summary: The proximate trigger was the February/March 2026 shock; "
    "first transmission showed up in energy prices before the CES prints.\n"
    "USREC=0 (August 2026). Nonfarm payrolls +162k in August 2026. "
    "Sahm is −0.03 vs the 0.50 trigger. GDP printed 2.1, then 1.5."
)


def first_trigger_ces_fixture() -> Packet:
    """Pack names a dated first-trigger. Current CES/USREC prints are the outcome."""
    packet = Packet(
        id="oc-are-we-near-recession-first-trigger",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell="Host-only desk read. Title is a question we will not answer with a forecast.",
        tone=SEED_TONE,
        research_pack=_FIRST_TRIGGER_SPINE,
        task_spine=_FIRST_TRIGGER_SPINE,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-august-2026",
                when="August 2026",
                claim="USREC=0 (August 2026).",
                stamp="grounded",
                title="USREC",
                series="USREC",
                print="0",
                parallel_url=FRED_USREC,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-august-2026",
                when="August 2026",
                claim="Nonfarm payrolls +162k in August 2026.",
                stamp="grounded",
                title="BLS payrolls",
                series="BLS payrolls",
                print="+162k",
                parallel_url=BLS_PAYROLLS,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="gdp-2026-q2",
                when="2026",
                claim="GDP printed 2.1, then 1.5.",
                stamp="grounded",
                title="BEA GDP",
                series="GDP",
                print="2.1 / 1.5",
                parallel_url=BEA_GDP,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="sahm-august-2026",
                when="August 2026",
                claim="Sahm is −0.03 vs the 0.50 trigger.",
                stamp="grounded",
                title="Sahm rule",
                series="SAHMREALTIME",
                print="−0.03",
                parallel_url=FRED_SAHM,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
        ],
    )
    return packet


def _cold(packet: Packet) -> str:
    beat = next(b for b in packet.beats if b.id == "cold-open")
    return f"{beat.vo} {beat.frame or ''}"


def _later_vo(packet: Packet) -> str:
    return " ".join(b.vo for b in packet.beats if b.id != "cold-open")


def test_cold_open_may_be_current_series_print_when_pack_has_first_trigger() -> None:
    packet = first_trigger_ces_fixture()
    write_script(packet)
    assert packet.status == "ready"
    assert packet.script
    assert len(packet.beats) == 8
    cold = _cold(packet)
    spoken = _spoken(packet)
    assert "USREC=0" in cold
    assert "162k" in cold.lower() or "payroll" in cold.lower()
    assert "USREC=0" in spoken
    assert "162k" in spoken.lower() or "162" in spoken
    assert "2.1" in spoken and "1.5" in spoken


def test_later_beat_may_voice_pack_first_trigger() -> None:
    packet = first_trigger_ces_fixture()
    write_script(packet)
    later = _later_vo(packet).lower()
    assert "february" in later or "march" in later or "feb" in later
    assert "2026" in later
    assert "geopolitical" in later or "energy" in later or "transmission" in later or "surge" in later


def test_empty_first_trigger_still_allows_series_cold_open() -> None:
    packet = recession_fixture()
    assert "first trigger" not in (packet.research_pack or "").lower()
    assert "what_counts_as_the_first_trigger" not in (packet.task_spine or "")
    write_script(packet)
    cold = _cold(packet)
    assert "USREC=0" in cold
    assert "−23k" in cold or "-23k" in cold or "payroll" in cold.lower()


def test_vertex_outcome_open_keeps_first_trigger_in_a_later_beat(monkeypatch) -> None:
    """Outcome-first Vertex smash stays; pack first-trigger is woven later, not beat 1."""
    import json

    packet = first_trigger_ces_fixture()
    smash = {
        "beats": [
            {
                "id": "cold-open",
                "vo": "USREC=0 (August 2026) smashed into payrolls +162k. [usrec-august-2026] [payrolls-august-2026]",
                "eyes": "USREC=0 and payrolls +162k on screen.",
                "finding_ids": ["usrec-august-2026", "payrolls-august-2026"],
            },
            {
                "id": "promise",
                "vo": "Three objects from the pack. [usrec-august-2026]",
                "eyes": "pack",
                "finding_ids": ["usrec-august-2026"],
            },
            {
                "id": "gdp",
                "vo": "GDP printed 2.1, then 1.5. [gdp-2026-q2]",
                "eyes": "gdp",
                "finding_ids": ["gdp-2026-q2"],
            },
            {
                "id": "labor",
                "vo": "Labor: payrolls +162k. [payrolls-august-2026]",
                "eyes": "ces",
                "finding_ids": ["payrolls-august-2026"],
            },
            {
                "id": "turn",
                "vo": "Turn: Sahm −0.03 vs the 0.50 trigger. [sahm-august-2026]",
                "eyes": "sahm",
                "finding_ids": ["sahm-august-2026"],
            },
            {
                "id": "complication",
                "vo": "Those are not the same object. [usrec-august-2026]",
                "eyes": "gap",
                "finding_ids": ["usrec-august-2026"],
            },
            {
                "id": "receipt",
                "vo": "Receipt board: named series. [usrec-august-2026] [payrolls-august-2026]",
                "eyes": "board",
                "finding_ids": ["usrec-august-2026", "payrolls-august-2026"],
            },
            {
                "id": "close",
                "vo": "Near is not a switch. [usrec-august-2026]",
                "eyes": "close",
                "finding_ids": ["usrec-august-2026"],
            },
        ]
    }

    monkeypatch.setattr("onecrew.script.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda *_a, **_k: json.dumps(smash))
    write_script(packet)
    cold = _cold(packet)
    later = _later_vo(packet).lower()
    assert "USREC=0" in cold
    assert "162k" in cold.lower() or "payroll" in cold.lower()
    assert "february" in later or "march" in later
    assert "geopolitical" in later or "energy" in later or "surge" in later
    assert packet.script


def test_leftover_hormuz_on_first_trigger_pack_still_fail_closed(monkeypatch) -> None:
    packet = first_trigger_ces_fixture()
    hormuz = (
        '[{"id":"cold-open","vo":"Hormuz=13 smashed into JCPOA. [usrec-august-2026] [payrolls-august-2026]",'
        '"eyes":"strait","finding_ids":["usrec-august-2026","payrolls-august-2026"]},'
        '{"id":"promise","vo":"Strait of Hormuz leftover. [usrec-august-2026]","eyes":"pack","finding_ids":["usrec-august-2026"]},'
        '{"id":"gdp","vo":"USREC=0 (August 2026). [usrec-august-2026]","eyes":"usrec","finding_ids":["usrec-august-2026"]},'
        '{"id":"labor","vo":"Nonfarm payrolls +162k. [payrolls-august-2026]","eyes":"ces","finding_ids":["payrolls-august-2026"]},'
        '{"id":"turn","vo":"Hold on the pack number. [usrec-august-2026]","eyes":"hold","finding_ids":["usrec-august-2026"]},'
        '{"id":"complication","vo":"Those are not the same object. [usrec-august-2026]","eyes":"gap","finding_ids":["usrec-august-2026"]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-august-2026]","eyes":"board","finding_ids":["usrec-august-2026"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-august-2026]","eyes":"close","finding_ids":["usrec-august-2026"]}]'
    )
    monkeypatch.setattr("onecrew.script.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda *_a, **_k: hormuz)
    write_script(packet)
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert packet.script == ""
    assert packet.beats == []
    assert "hormuz" not in spoken.lower()
    reason = (packet.receipt.hold_reason or "") if packet.receipt else ""
    reason += " ".join(row.detail for row in packet.exclusions)
    assert "leftover Hormuz" in reason
