from onecrew.models import Rails
from onecrew.receipt import hold_receipt
from onecrew.seed import seed_first_open


def test_hold_when_parallel_down() -> None:
    rails = Rails(parallel=False, vertex=True, imagen=True)
    receipt = hold_receipt("oc-pickle-debt", rails)
    assert receipt.disposition == "HOLD"
    assert "parallel" in (receipt.hold_reason or "")


def test_hold_when_vertex_down() -> None:
    rails = Rails(parallel=True, vertex=False, imagen=True)
    receipt = hold_receipt("oc-pickle-debt", rails)
    assert receipt.disposition == "HOLD"
    assert "vertex" in (receipt.hold_reason or "")


def test_hold_when_imagen_down() -> None:
    rails = Rails(parallel=True, vertex=True, imagen=False)
    receipt = hold_receipt("oc-pickle-debt", rails)
    assert receipt.disposition == "HOLD"
    assert "imagen" in (receipt.hold_reason or "")


def test_hold_no_invented_source() -> None:
    receipt = hold_receipt("oc-pickle-debt", Rails(parallel=False, vertex=False, imagen=False))
    assert receipt.invented_source is False
    assert all(f.parallel_url is None for f in receipt.findings)


def test_hold_no_collage() -> None:
    receipt = hold_receipt("oc-pickle-debt", Rails(parallel=False, vertex=False, imagen=False))
    assert receipt.collage is False
    packet = seed_first_open()
    assert all(not frame.shot.lower().startswith("mood") for frame in packet.frames)


def test_hold_no_invented_stamp() -> None:
    receipt = hold_receipt("oc-pickle-debt", Rails(parallel=False, vertex=False, imagen=False))
    assert receipt.invented_stamp is False
    assert receipt.findings == []
