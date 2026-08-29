import pytest

from onecrew.models import MISSING, Finding
from onecrew.receipt import ReceiptInvalidError, validate_finding
from onecrew.seed import PPI_URL, seed_first_open


def _mainstream(**kwargs) -> Finding:
    row = dict(
        id="m",
        claim="widely repeated frame",
        stamp="mainstream",
        parallel_url=None,
        parallel_status="n/a",
        note="Widely repeated, may be bias, not a source.",
        lean=MISSING,
        interests=MISSING,
        who_repeats=MISSING,
    )
    row.update(kwargs)
    return Finding(**row)


def test_mainstream_without_parallel_hits_cannot_have_filled_lean_or_interests() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_mainstream(lean="left"))
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_mainstream(interests=["a lobby"]))
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_mainstream(who_repeats=["everyone"]))
    ok = _mainstream()
    validate_finding(ok)
    assert ok.lean == MISSING
    assert ok.interests == MISSING
    assert ok.who_repeats == MISSING


def test_invented_lobby_fails() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            _mainstream(
                interests=["Made-Up Pickle PAC"],
                interests_url=None,
            )
        )


def test_missing_stays_missing() -> None:
    row = _mainstream()
    validate_finding(row)
    assert row.lean == MISSING
    assert row.interests == MISSING
    assert row.who_repeats == MISSING
    assert row.lean_url is None
    assert row.interests_url is None
    assert row.who_repeats_url is None
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_mainstream(lean=MISSING, lean_url="https://example.com/guess"))


def test_seeded_mainstream_present_and_missing_attribution() -> None:
    packet = seed_first_open()
    missing = next(f for f in packet.receipt.findings if f.id == "3am-kitchen")
    present = next(f for f in packet.receipt.findings if f.id == "industry-recovery")
    assert missing.stamp == "mainstream"
    assert missing.lean == MISSING
    assert missing.interests == MISSING
    assert missing.who_repeats == MISSING
    assert present.stamp == "mainstream"
    assert present.lean == "industry"
    assert present.lean != present.stamp
    assert present.lean_url == PPI_URL
    assert present.interests == ["Pickle Packers International"]
    assert present.interests_url == PPI_URL
    assert present.who_repeats == ["Pickle Packers International"]
    assert present.who_repeats_url == PPI_URL
    fringe = next(f for f in packet.receipt.findings if f.stamp == "fringe")
    assert fringe.stamp != "grounded"
    assert "never sold as fact" in fringe.note.lower()
