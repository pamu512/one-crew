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
        assert "oc-hormuz-decade" in page.text or "hormuz" in page.text.lower()
        assert "Any missing pick = no run" in page.text
        assert "Topic — pick 1, required" in page.text
        assert "No topic chosen = no run" in page.text
        assert "No platform chosen = no run" in page.text
        assert "No tell chosen = no run" in page.text
        assert "Tell — pick 6, required free text" in page.text
        assert "Narrator-led global overview of the US and Iran" in page.text
        assert "One family in Bandar Abbas, kitchen radio on" in page.text
        assert "Thriller on a tanker crossing Hormuz that might get hit" in page.text
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
        assert "Grounded in the record" in page.text
        assert "Research pack" in page.text
        assert "floor does not post it" in page.text.lower() or "does not post" in page.text.lower()
        html = FLOOR_HTML
        assert html.index("Desk card") < html.index("Timed VO")
        assert html.index("Timed VO") < html.index("Shot list")
        assert html.index("Shot list") < html.index("Existing media")
        assert "Tape is not a license" in html
        assert "Collision is not a clearance" in html or "not a copyright clearance" in html.lower()
        assert "grounded in reality" not in page.text.lower()
        assert "<textarea" in FLOOR_HTML
        assert "checked=" not in FLOOR_HTML
        assert "checked>" not in FLOOR_HTML


def test_no_publish_route() -> None:
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any("publish" in path.lower() for path in paths)
    seed_first_open()
    with TestClient(app) as client:
        posted = client.post("/api/publish", json={})
        assert posted.status_code == 404
