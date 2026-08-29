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
        assert "No platform chosen = no run" in page.text
        assert "checked=" not in FLOOR_HTML
        assert "checked>" not in FLOOR_HTML


def test_no_publish_route() -> None:
    paths = [getattr(route, "path", "") for route in app.routes]
    assert not any("publish" in path.lower() for path in paths)
    seed_first_open()
    with TestClient(app) as client:
        posted = client.post("/api/publish", json={})
        assert posted.status_code == 404
