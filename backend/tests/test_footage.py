from types import SimpleNamespace

from onecrew.board import write_board
from onecrew.models import Rails
from onecrew.script import write_script
from onecrew.seed import seed_first_open
from onecrew.spend import ledger


HORMUZ_STILL = "https://fred.stlouisfed.org/series/USREC"
HORMUZ_STILL_TITLE = "USREC"


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
    assert all(
        "stlouisfed.org" in (f.footage_url or "")
        or "bls.gov" in (f.footage_url or "")
        or "bea.gov" in (f.footage_url or "")
        for f in sourced
    )
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
    assert shots
    assert all("gulf" not in s.shot.lower() for s in shots)
    assert all("photoreal" not in s.shot.lower() for s in shots)


def test_nonfiction_event_shot_never_imagen(monkeypatch) -> None:
    called = []
    monkeypatch.setattr("onecrew.board.search", _miss)
    monkeypatch.setattr("onecrew.board.generate_frames", _fake_gen(called))
    packet = seed_first_open()
    write_script(packet)
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    events = [f for f in frames if f.kind == "event"]
    assert all(f.footage in {"sourced", "missing"} for f in events)
    assert all(f.imagen is False for f in events)
    assert all("photoreal" not in (f.shot or "").lower() for f in frames)


def test_nonfiction_infographic_may_imagen(monkeypatch) -> None:
    called = []
    monkeypatch.setattr("onecrew.board.search", _miss)
    monkeypatch.setattr("onecrew.board.generate_frames", _fake_gen(called))
    packet = seed_first_open()
    write_script(packet)
    frames = write_board(packet, Rails(parallel=True, vertex=True, imagen=True))
    graphics = [f for f in frames if f.kind in {"infographic", "motion_graphic"}]
    assert graphics
    sourced = [f for f in frames if f.footage == "sourced"]
    assert sourced
    close = next(f for f in frames if f.beat_id == packet.beats[-1].id)
    assert close.footage == "missing"
    assert close.kind != "event"
    assert close.imagen is False
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
    assert called
    assert any(f.imagen for f in frames)
    assert all("leila" not in f.shot.lower() for f in frames)
    assert all("gulf" not in f.shot.lower() for f in frames)


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


def test_sourced_frames_only_fred_bls_bea(monkeypatch) -> None:
    from onecrew.board import prefer_footage, write_shot_list
    from onecrew.models import ShotFrame

    packet = seed_first_open()
    shots = write_shot_list(packet)
    assert shots
    urls = [
        "https://fred.stlouisfed.org/series/USREC",
        "https://www.bls.gov/news.release/empsit.nr0.htm",
        "https://www.bea.gov/data/gdp/gross-domestic-product",
        "https://qz.com/jobs-report",
        "https://en.wikipedia.org/wiki/Recession",
        "https://whatisarecession.com/",
    ]

    cycle = {"i": 0}

    def search(*, objective, search_queries):
        url = urls[cycle["i"] % len(urls)]
        cycle["i"] += 1
        return SimpleNamespace(results=[_Row(url=url, title=url)])

    monkeypatch.setattr("onecrew.board.search", search)
    prefer_footage(shots, Rails(parallel=True, vertex=False, imagen=False), packet)
    sourced = [s for s in shots if s.footage == "sourced"]
    assert sourced
    for shot in sourced:
        host = (shot.footage_url or "").lower()
        assert "stlouisfed.org" in host or "bls.gov" in host or "bea.gov" in host
    for shot in shots:
        url = (shot.footage_url or "").lower()
        if any(bad in url for bad in ("qz.com", "wikipedia.org", "whatisarecession")):
            assert shot.footage != "sourced"


def test_hackaday_stackoverflow_not_sourced(monkeypatch) -> None:
    from onecrew.board import prefer_footage
    from onecrew.models import ShotFrame

    junk = [
        "https://hackaday.com/credit-card-computer",
        "https://stackoverflow.com/questions/pandas-join",
        "https://newrepublic.com/article/uk-labour-party",
        "https://whatisarecession.com/explainer",
    ]
    shots = [
        ShotFrame(
            id=f"shot-{i:03d}-x",
            shot="Official series card.",
            source_refs=[],
            beat_id="gdp",
            kind="event",
        )
        for i in range(len(junk))
    ]
    cycle = {"i": 0}

    def search(*, objective, search_queries):
        url = junk[cycle["i"] % len(junk)]
        cycle["i"] += 1
        return SimpleNamespace(results=[_Row(url=url, title="junk")])

    monkeypatch.setattr("onecrew.board.search", search)
    packet = seed_first_open()
    prefer_footage(shots, Rails(parallel=True, vertex=False, imagen=False), packet)
    assert all(s.footage == "missing" for s in shots)
    assert all(s.footage_url is None for s in shots)
    assert all(s.kind != "event" or s.footage != "imagen" for s in shots)


def test_close_missing_is_not_event() -> None:
    from onecrew.board import _shot_kind, apply_imagen, write_shot_list
    from onecrew.models import Rails

    assert _shot_kind("Close card: near is not a switch. Board follows the pack.") != "event"
    packet = seed_first_open()
    write_script(packet)
    shots = write_shot_list(packet)
    close = next(s for s in shots if s.beat_id == "close")
    close.footage = "missing"
    close.footage_url = None
    apply_imagen(shots, packet, rails=Rails(parallel=True, vertex=False, imagen=False))
    close = next(s for s in shots if s.beat_id == "close")
    assert close.footage == "missing"
    assert close.kind != "event"
    assert close.imagen is False


def test_empsit_vintage_matches_finding_when(monkeypatch) -> None:
    from onecrew.board import prefer_footage
    from onecrew.models import Finding, Packet, Receipt, Rails, ShotFrame
    from onecrew.tell import SEED_TELL
    from onecrew.tone import SEED_TONE

    july = "https://www.bls.gov/news.release/archives/empsit_08072026.htm"
    may = "https://www.bls.gov/news.release/archives/empsit_06052026.htm"
    finding = Finding(
        id="payrolls-july-2026",
        claim="Nonfarm payrolls fell −23,000.",
        stamp="grounded",
        series="BLS payrolls",
        print="−23,000",
        when="July 2026",
        parallel_url=july,
        parallel_status="hit",
        note="Parallel URL on this row.",
    )
    packet = Packet(
        id="oc-empsit-vintage",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="x",
        platform="youtube",
        cut="one_time_short_episode",
        tell=SEED_TELL,
        tone=SEED_TONE,
        receipt=Receipt(packet_id="oc-empsit-vintage", written=True, disposition="READY", findings=[finding]),
    )
    shot_ok = ShotFrame(
        id="shot-001-labor",
        shot="BLS labor print.",
        source_refs=[july],
        beat_id="labor",
        kind="infographic",
        footage="missing",
    )
    shot_bad = ShotFrame(
        id="shot-002-labor",
        shot="BLS labor print.",
        source_refs=[may],
        beat_id="labor",
        kind="infographic",
        footage="missing",
    )

    def search(*, objective, search_queries):
        return SimpleNamespace(results=[_Row(url=may, title="May CES")])

    monkeypatch.setattr("onecrew.board.search", search)
    prefer_footage([shot_ok], Rails(parallel=True, vertex=False, imagen=False), packet)
    assert shot_ok.footage == "sourced"
    assert shot_ok.footage_url == july
    prefer_footage([shot_bad], Rails(parallel=True, vertex=False, imagen=False), packet)
    assert shot_bad.footage != "sourced"
    assert (shot_bad.footage_url or "") != may or shot_bad.footage == "missing"
