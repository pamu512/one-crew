import copy

from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.collision import stamp_collisions
from onecrew.floor import FLOOR_HTML
from onecrew.models import MISSING, Rails
from onecrew.script import write_script
from onecrew.seed import leftover_hormuz_packet, seed_first_open
from onecrew.spend import ledger

HORMUZ_DOC_URL = "https://www.youtube.com/watch?v=StraitOfHormuzDoc"
HORMUZ_DOC_TITLE = "The Strait of Hormuz | Documentary"


class _Row:
    def __init__(self, url=None, title=None, excerpts=None):
        self.url = url
        self.title = title
        self.excerpts = excerpts or []


class _Result:
    def __init__(self, rows):
        self.results = rows


def _hit_on_jcpoa(*, objective, search_queries):
    blob = " ".join(search_queries).lower()
    assert "leila" not in blob
    assert "reza" not in blob
    assert "(frame)" not in blob
    if "jcpoa" in blob or "withdrew" in blob:
        return _Result(
            [
                _Row(
                    url=HORMUZ_DOC_URL,
                    title=HORMUZ_DOC_TITLE,
                    excerpts=[
                        "The United States withdrew from the JCPOA, tightening the Iran file around the Gulf."
                    ],
                )
            ]
        )
    return _Result([])


def test_seed_collisions_are_missing_get_never_spends(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("Parallel spent on seed or GET")

    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.collision.search", boom)
    packet = seed_first_open()
    assert packet.collision_disposition == "HOLD"
    assert packet.beats
    for beat in packet.beats:
        assert beat.collision == MISSING
        assert beat.collision_url is None
        assert beat.collision_title == MISSING
        assert beat.collision_kind == MISSING
        assert beat.collision != "no"
    assert packet.collisions == []
    blob = (packet.script + FLOOR_HTML + (packet.collision_hold_reason or "")).lower()
    assert "cleared" not in blob
    assert "fair use" not in blob
    before = ledger.parallel_calls
    with TestClient(app) as client:
        body = client.get("/api/packets")
        assert body.status_code == 200
        seeded = body.json()["packets"][0]
        assert seeded["collision_disposition"] == "HOLD"
        for beat in seeded["beats"]:
            assert beat["collision"] == MISSING
    assert ledger.parallel_calls == before == 0


def test_parallel_down_keeps_collision_missing_never_no(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("searched while collision rail is down")

    monkeypatch.setattr("onecrew.collision.search", boom)
    packet = seed_first_open()
    stamp_collisions(packet, Rails(parallel=False, vertex=False, imagen=False))
    assert packet.collision_disposition == "HOLD"
    assert packet.script.strip()
    for beat in packet.beats:
        assert beat.collision == MISSING
        assert beat.collision != "no"
        assert beat.collision_url is None
        assert beat.collision_title == MISSING
    assert "cleared" not in (packet.collision_hold_reason or "").lower()
    assert packet.collisions == []


def test_empty_script_does_not_search(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("searched before VO exists")

    monkeypatch.setattr("onecrew.collision.search", boom)
    packet = seed_first_open()
    packet.script = ""
    packet.beats = []
    stamp_collisions(packet, Rails(parallel=True, vertex=True, imagen=True))
    assert packet.collision_disposition == "HOLD"
    assert packet.collisions == []
    reason = (packet.collision_hold_reason or "").lower()
    assert "parallel missing" not in reason
    assert "warning" in reason


def test_parallel_hit_stamps_collision_yes_findings_unchanged(monkeypatch) -> None:
    monkeypatch.setattr("onecrew.collision.search", _hit_on_jcpoa)
    packet = leftover_hormuz_packet()
    before = [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent, f.parallel_url)
        for f in packet.receipt.findings
    ]
    vo_before = packet.script
    stamp_collisions(packet, Rails(parallel=True, vertex=True, imagen=True))
    assert packet.script == vo_before
    after = [
        (f.id, f.stamp, f.propaganda, f.lean, f.independent, f.parallel_url)
        for f in packet.receipt.findings
    ]
    assert after == before
    hit = next(b for b in packet.beats if "jcpoa-2018" in b.finding_ids)
    assert hit.collision == "yes"
    assert hit.collision_url == HORMUZ_DOC_URL
    assert hit.collision_title == HORMUZ_DOC_TITLE
    assert hit.collision_kind == "same_script"
    miss = next(b for b in packet.beats if "jcpoa-2018" not in b.finding_ids)
    assert miss.collision == "no"
    assert miss.collision_url is None
    assert miss.collision_title == MISSING
    assert miss.collision_kind == MISSING
    assert any(row.beat_id == hit.id and row.collision == "yes" for row in packet.collisions)
    assert all(row.collision == "yes" for row in packet.collisions)
    assert packet.collision_disposition == "READY"
    assert hit.vo == next(b.vo for b in leftover_hormuz_packet().beats if b.id == hit.id)


def test_lean_does_not_change_collision_url(monkeypatch) -> None:
    monkeypatch.setattr("onecrew.collision.search", _hit_on_jcpoa)
    packet = leftover_hormuz_packet()
    stamp_collisions(packet, Rails(parallel=True, vertex=True, imagen=True))
    url = next(b for b in packet.beats if "jcpoa-2018" in b.finding_ids).collision_url
    assert url == HORMUZ_DOC_URL
    packet.script_lean = "left"
    packet.receipt = copy.deepcopy(packet.receipt)
    write_script(packet)
    left = next(b for b in packet.beats if "jcpoa-2018" in b.finding_ids)
    assert left.collision == "yes"
    assert left.collision_url == url
    packet.script_lean = "right"
    write_script(packet)
    right = next(b for b in packet.beats if "jcpoa-2018" in b.finding_ids)
    assert right.collision_url == url
    assert right.collision == "yes"
    assert left.vo != right.vo


def test_fiction_frame_is_not_searched(monkeypatch) -> None:
    seen: list[str] = []

    def capture(*, objective, search_queries):
        seen.extend(search_queries)
        return _hit_on_jcpoa(objective=objective, search_queries=search_queries)

    monkeypatch.setattr("onecrew.collision.search", capture)
    packet = leftover_hormuz_packet()
    packet.tell = "One family in Bandar Abbas, kitchen radio on"
    packet.cut = "feature_film"
    write_script(packet)
    assert "(frame)" in packet.script
    stamp_collisions(packet, Rails(parallel=True, vertex=True, imagen=True))
    blob = " ".join(seen).lower()
    assert "leila" not in blob
    assert "bandar abbas" not in blob
    assert "(frame)" not in blob
    assert any("jcpoa" in q.lower() or "withdrew" in q.lower() for q in seen)
    hit = next(b for b in packet.beats if "jcpoa-2018" in b.finding_ids)
    assert hit.collision == "yes"
    assert hit.collision_url == HORMUZ_DOC_URL
    assert "Leila" not in hit.vo


def test_fred_usrec_is_not_collision_yes_same_script(monkeypatch) -> None:
    """FRED/BLS/BEA series pages are citations, not same_script media."""
    FRED = "https://fred.stlouisfed.org/series/USREC"

    def search(*, objective, search_queries):
        return _Result(
            [
                _Row(
                    url=FRED,
                    title="USREC",
                    excerpts=["USREC=0 (July 2026) smashed into payrolls −23k."],
                )
            ]
        )

    monkeypatch.setattr("onecrew.collision.search", search)
    packet = seed_first_open()
    write_script(packet)
    stamp_collisions(packet, Rails(parallel=True, vertex=False, imagen=False))
    cold = next(b for b in packet.beats if b.id == "cold-open")
    assert not (cold.collision == "yes" and cold.collision_kind == "same_script")
    assert cold.collision_url != FRED
    assert all(row.url != FRED for row in packet.collisions)


def test_floor_shows_collision_never_clears_copyright() -> None:
    html = FLOOR_HTML.lower()
    assert "collision" in html
    assert "fair use" not in html
    assert "cleared" not in html
    assert "cleared for publish" not in html
    assert "publish" not in html
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "collision" in page.text.lower()
        bare = client.post("/api/shifts", json={"topic": "Hormuz"})
        assert bare.status_code == 403


def test_collision_fred_translate_goog_is_citation(monkeypatch) -> None:
    wrapped = "https://fred-stlouisfed-org.translate.goog/series/USREC"

    def search(*, objective, search_queries):
        return _Result(
            [
                _Row(
                    url=wrapped,
                    title="USREC",
                    excerpts=["USREC=0 (July 2026) smashed into payrolls −23k."],
                )
            ]
        )

    monkeypatch.setattr("onecrew.collision.search", search)
    packet = seed_first_open()
    write_script(packet)
    stamp_collisions(packet, Rails(parallel=True, vertex=False, imagen=False))
    for beat in packet.beats:
        if (beat.kind or "vo") != "vo":
            continue
        assert beat.collision != "yes"
        assert beat.collision_kind != "same_script"
        assert beat.collision_url != wrapped
        assert beat.collision == "no"
    assert packet.collision_disposition == "HOLD"
    assert "warning" in (packet.collision_hold_reason or "").lower()


def test_collision_wikipedia_sahm_is_not_same_script(monkeypatch) -> None:
    wiki = "https://en.wikipedia.org/wiki/Sahm_rule"

    def search(*, objective, search_queries):
        return _Result(
            [_Row(url=wiki, title="Sahm rule", excerpts=["Sahm −0.03 vs the 0.50 trigger."])]
        )

    monkeypatch.setattr("onecrew.collision.search", search)
    packet = seed_first_open()
    write_script(packet)
    stamp_collisions(packet, Rails(parallel=True, vertex=False, imagen=False))
    for beat in packet.beats:
        if (beat.kind or "vo") != "vo":
            continue
        assert beat.collision_kind != "same_script"
        assert beat.collision != "yes"
        assert beat.collision_url != wiki
    assert packet.collision_disposition == "HOLD"


def test_collision_new_republic_labour_is_not_labor_print(monkeypatch) -> None:
    nr = "https://newrepublic.com/article/uk-labour-party"

    def search(*, objective, search_queries):
        return _Result(
            [
                _Row(
                    url=nr,
                    title="UK Labour Party",
                    excerpts=["Labor: payrolls −23k and unemployment 4.1%. Named BLS."],
                )
            ]
        )

    monkeypatch.setattr("onecrew.collision.search", search)
    packet = seed_first_open()
    write_script(packet)
    stamp_collisions(packet, Rails(parallel=True, vertex=False, imagen=False))
    labor = next(b for b in packet.beats if b.id == "labor")
    assert labor.collision != "yes"
    assert labor.collision_kind != "same_script"
    assert labor.collision_url != nr
    assert labor.collision == "no"
    assert packet.collision_disposition == "HOLD"


def test_collision_disposition_hold_when_no_media_match(monkeypatch) -> None:
    def search(*, objective, search_queries):
        return _Result(
            [
                _Row(
                    url="https://fred.stlouisfed.org/series/USREC",
                    title="USREC",
                    excerpts=["USREC=0"],
                ),
                _Row(
                    url="https://www.congress.gov/crs-product/recession",
                    title="Defining Recession",
                    excerpts=["Defining Recession"],
                ),
            ]
        )

    monkeypatch.setattr("onecrew.collision.search", search)
    packet = seed_first_open()
    write_script(packet)
    stamp_collisions(packet, Rails(parallel=True, vertex=False, imagen=False))
    assert packet.collision_disposition == "HOLD"
    assert packet.collision_disposition != "READY"
    assert all(b.collision == "no" for b in packet.beats if (b.kind or "vo") == "vo")
    assert "warning" in (packet.collision_hold_reason or "").lower()
    assert "clearance" in (packet.collision_hold_reason or "").lower()
