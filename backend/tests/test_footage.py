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


def test_parallel_footage_miss_allows_imagen(monkeypatch) -> None:
    called = []

    def fake_gen(*, prompt: str, number_of_images: int = 1):
        called.append(prompt)
        return SimpleNamespace(
            generated_images=[
                SimpleNamespace(image=SimpleNamespace(image_bytes=b"<svg xmlns='http://www.w3.org/2000/svg'/>"))
            ]
        )

    monkeypatch.setattr("onecrew.board.search", _miss)
    monkeypatch.setattr("onecrew.board.generate_frames", fake_gen)
    packet = seed_first_open()
    write_script(packet)
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    assert frames
    assert called
    assert any(f.footage == "imagen" and f.imagen for f in frames)
    assert all(f.footage != "sourced" for f in frames)


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
