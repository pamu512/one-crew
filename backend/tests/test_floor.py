from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.floor import FLOOR_HTML
from onecrew.seed import seed_first_open


def test_floor_html_has_no_publish_button() -> None:
    html = FLOOR_HTML.lower()
    assert "publish" not in html
    assert "post now" not in html
    assert "<button" not in html or "publish" not in html
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "publish" not in page.text.lower()
        assert "HOLD. No live packet" in page.text
        assert "Loading oc-recession-july-2026" not in page.text
        assert "Are we near recession?" in page.text
        assert "Host-only desk read of the last year of US recession prints" in page.text
        assert "On the cited print" in page.text
        assert "Grounded in the record" not in page.text
        assert "Any missing pick = no run" in page.text
        assert "Topic — pick 1, required" in page.text
        assert "No topic chosen = no run" in page.text
        assert "No platform chosen = no run" in page.text
        assert "No tell chosen = no run" in page.text
        assert "Tell — pick 6, required free text" in page.text
        assert "Narrator-led global overview of the US and Iran" not in page.text
        assert "One family in Bandar Abbas, kitchen radio on" not in page.text
        assert "Thriller on a tanker crossing Hormuz that might get hit" not in page.text
        assert "Bandar Abbas" not in page.text
        assert "Hormuz" not in page.text
        assert "tanker" not in page.text.lower()
        assert "Weekly news desk, host only" in page.text
        assert "Historical drama through one port family" in page.text
        assert "name=\"genre\"" not in FLOOR_HTML
        assert "name=\"vantage\"" not in FLOOR_HTML
        assert 'id="tell"' in FLOOR_HTML
        assert 'id="tone"' in FLOOR_HTML
        assert "No tone chosen = no run" in page.text
        assert "News desk" in page.text
        assert "Make the viewer think" in page.text
        assert "Question the decisions" in page.text
        assert "Personal take" in page.text
        assert "On the cited print" in page.text
        assert "Grounded in the record" not in page.text
        assert "Research pack" in page.text
        assert "floor does not post it" in page.text.lower() or "does not post" in page.text.lower()
        assert "grounded in reality" not in page.text.lower()
        assert "<textarea" in FLOOR_HTML
        assert "checked=" not in FLOOR_HTML
        assert "checked>" not in FLOOR_HTML


def test_floor_html_has_no_us_iran_first_paint() -> None:
    assert "Narrator-led global overview of the US and Iran" not in FLOOR_HTML
    assert "Are we near recession?" in FLOOR_HTML
    assert "Host-only desk read of the last year of US recession prints" in FLOOR_HTML
    assert "On the cited print" in FLOOR_HTML
    assert "warning, not a clearance" in FLOOR_HTML.lower() or "not a copyright clearance" in FLOOR_HTML.lower()
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "Narrator-led global overview of the US and Iran" not in page.text
        assert "One family in Bandar Abbas, kitchen radio on" not in page.text
        assert "Thriller on a tanker crossing Hormuz that might get hit" not in page.text
        assert "Bandar Abbas" not in FLOOR_HTML
        assert "Hormuz" not in FLOOR_HTML
        assert "tanker" not in FLOOR_HTML.lower()
        assert "oc-hormuz-decade" not in page.text


def test_floor_first_open_packet_is_recession_not_hormuz() -> None:
    from onecrew.models import Packet
    from onecrew.store import store

    seed_first_open()
    with TestClient(app) as client:
        body = client.get("/api/packets")
        assert body.status_code == 200
        packets = body.json()["packets"]
        assert packets
        first = packets[0]
        assert first["id"] != "oc-hormuz-decade"
        assert first["id"] == "oc-recession-july-2026"
        assert "recession" in (first.get("topic") or "").lower()
        assert "Host-only desk read" in (first.get("tell") or "")
        assert "US and Iran" not in (first.get("tell") or "")
        live = Packet(
            id="oc-are-we-near-recession-d5999d3b",
            topic="Are we near recession?",
            hook="Are we near recession?",
            script="USREC=0 smashed into payrolls −23k.",
            platform="youtube",
            cut="one_time_short_episode",
            depth="2-3y",
            script_lean="centered_independent",
            tell="Host-only desk read of the last year of US recession prints",
            tone="On the cited print",
            status="ready",
        )
        store.upsert_packet(live)
        again = client.get("/api/packets")
        assert again.status_code == 200
        opened = again.json()["packets"][0]
        assert opened["id"] == live.id
        assert opened["id"] != "oc-hormuz-decade"
        assert opened["id"] != "oc-recession-july-2026"
        page = client.get("/")
        assert page.status_code == 200
        assert "Loading oc-recession-july-2026" not in page.text
        assert "oc-hormuz-decade" not in page.text


def test_no_publish_route() -> None:
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any("publish" in path.lower() for path in paths)
    seed_first_open()
    with TestClient(app) as client:
        posted = client.post("/api/publish", json={})
        assert posted.status_code == 404
