from types import SimpleNamespace

from onecrew.board import write_board
from onecrew.models import Rails
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.spend import ledger


HORMUZ_STILL = "https://www.youtube.com/watch?v=StraitOfHormuzDoc"
HORMUZ_STILL_TITLE = "The Strait of Hormuz | Documentary"


class _Row:
    def __init__(self, url=None, title=None):
        self.url = url
        self.title = title


def _hit(*_a, **_k):
    return SimpleNamespace(results=[_Row(url=HORMUZ_STILL, title=HORMUZ_STILL_TITLE)])


def _miss(*_a, **_k):
    return SimpleNamespace(results=[])


def test_parallel_footage_hit_skips_imagen(monkeypatch) -> None:
    called = []

    def boom(*, prompt, number_of_images=1):
        called.append(prompt)
        raise AssertionError("imagen called for sourced shot")

    monkeypatch.setattr("onecrew.board.search", _hit)
    monkeypatch.setattr("onecrew.board.generate_frames", boom)
    packet = seed_first_open()
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    assert frames
    sourced = [f for f in frames if f.footage == "sourced"]
    assert sourced
    assert all(f.footage_url == HORMUZ_STILL for f in sourced)
    assert all(f.imagen is False for f in sourced)
    assert all(f.image_href == "" for f in sourced)
    assert called == []


def _fake_gen(called):
    def fake_gen(*, prompt: str, number_of_images: int = 1):
        called.append(prompt)
        return SimpleNamespace(
            generated_images=[
                SimpleNamespace(image=SimpleNamespace(image_bytes=b"<svg xmlns='http://www.w3.org/2000/svg'/>"))
            ]
        )

    return fake_gen


def test_jcpoa_announcement_is_event_not_graphic() -> None:
    from onecrew.board import _shot_kind, write_shot_list

    assert (
        _shot_kind("2018 announcement: a dated chyron on the JCPOA withdrawal, Gulf map on the wall behind the podium.")
        == "event"
    )
    assert _shot_kind("Tanker in the Strait of Hormuz lane, land close on both sides, open water ahead.") == "event"
    assert _shot_kind("Host at a Gulf map. A dated chyron waits.") == "infographic"
    packet = seed_first_open()
    shots = write_shot_list(packet)
    announcements = [s for s in shots if "announcement" in s.shot.lower() or "withdrawal" in s.shot.lower()]
    tankers = [s for s in shots if "tanker" in s.shot.lower()]
    assert announcements and all(s.kind == "event" for s in announcements)
    assert tankers and all(s.kind == "event" for s in tankers)


def test_nonfiction_event_shot_never_imagen(monkeypatch) -> None:
    called = []
    monkeypatch.setattr("onecrew.board.search", _miss)
    monkeypatch.setattr("onecrew.board.generate_frames", _fake_gen(called))
    packet = seed_first_open()
    write_script(packet)
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    events = [
        f
        for f in frames
        if f.kind == "event" or "tanker" in f.shot.lower() or "2018" in f.shot.lower() or "announcement" in f.shot.lower()
    ]
    assert events
    assert all(f.footage in {"sourced", "missing"} for f in events)
    assert all(f.imagen is False for f in events)
    assert all("photoreal" not in (f.shot or "").lower() or f.imagen is False for f in events)


def test_nonfiction_infographic_may_imagen(monkeypatch) -> None:
    called = []
    monkeypatch.setattr("onecrew.board.search", _miss)
    monkeypatch.setattr("onecrew.board.generate_frames", _fake_gen(called))
    packet = seed_first_open()
    write_script(packet)
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    graphics = [f for f in frames if f.kind in {"infographic", "motion_graphic"}]
    assert graphics
    assert called
    assert any(f.footage == "imagen" and f.imagen and f.kind in {"infographic", "motion_graphic"} for f in graphics)
    assert all(f.kind != "event" for f in graphics)


def test_feature_kitchen_imagen_allowed(monkeypatch) -> None:
    called = []
    monkeypatch.setattr("onecrew.board.search", _miss)
    monkeypatch.setattr("onecrew.board.generate_frames", _fake_gen(called))
    packet = seed_first_open()
    packet.cut = "feature_film"
    packet.tell = "One family in Bandar Abbas, kitchen radio on"
    write_script(packet)
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    kitchens = [f for f in frames if "kitchen" in f.shot.lower() or "bandar" in f.shot.lower() or "leila" in f.shot.lower()]
    assert kitchens
    assert called
    assert any(f.imagen for f in frames)
    assert any(
        f.imagen and ("kitchen" in f.shot.lower() or "bandar" in f.shot.lower() or "leila" in f.shot.lower() or "sink" in f.shot.lower())
        for f in frames
    )


def test_parallel_down_footage_missing_no_invented_url(monkeypatch) -> None:
    def boom_search(*_a, **_k):
        raise AssertionError("search must not run when parallel rail is down")

    def boom_imagen(*_a, **_k):
        raise AssertionError("imagen must not pretend to be a source")

    monkeypatch.setattr("onecrew.board.search", boom_search)
    monkeypatch.setattr("onecrew.board.generate_frames", boom_imagen)
    packet = seed_first_open()
    frames = write_board(packet, Rails(parallel=False, vertex=True, imagen=True))
    assert frames
    assert all(f.footage == "missing" for f in frames)
    assert all(f.footage_url is None for f in frames)
    assert all(f.imagen is False for f in frames)
    assert all(not (f.footage_url or "").startswith("http") for f in frames)


def test_seed_footage_is_sourced_or_missing_no_fake_ap_reel() -> None:
    packet = seed_first_open()
    assert packet.frames
    for frame in packet.frames:
        assert frame.footage in {"sourced", "missing"}
        assert frame.imagen is False
        blob = f"{frame.footage_url or ''} {frame.footage_title or ''} {frame.shot}".lower()
        assert "ap reel" not in blob
        assert "ap.org" not in blob
        if frame.footage == "sourced":
            assert frame.footage_url and frame.footage_url.startswith("http")
        else:
            assert frame.footage_url is None


def test_get_seed_does_not_spend_on_footage(monkeypatch) -> None:
    def boom(*_a, **_k):
        raise AssertionError("GET seed spent Parallel or Imagen")

    monkeypatch.setattr("onecrew.board.search", boom)
    monkeypatch.setattr("onecrew.parallel_client.search", boom)
    monkeypatch.setattr("onecrew.board.generate_frames", boom)
    before = ledger.parallel_calls
    seed_first_open()
    assert ledger.parallel_calls == before
