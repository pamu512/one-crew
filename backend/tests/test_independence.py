import pytest

from onecrew.floor import FLOOR_HTML
from onecrew.models import MISSING, Finding
from onecrew.receipt import ReceiptInvalidError, validate_finding
from onecrew.seed import PPI_URL, seed_first_open


def _grounded(**kwargs) -> Finding:
    row = dict(
        id="g",
        claim="ranks",
        stamp="grounded",
        parallel_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3894303/",
        parallel_status="hit",
        note="Parallel URL on this row.",
        independent=MISSING,
        vested_interest=MISSING,
    )
    row.update(kwargs)
    return Finding(**row)


def test_source_cannot_be_not_independent_without_parallel_hit() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_grounded(independent="no"))
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_grounded(independent="yes"))


def test_source_cannot_be_vested_without_parallel_hit() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_grounded(vested_interest=["Acme Capital"]))


def test_independence_missing_stays_missing() -> None:
    row = _grounded()
    validate_finding(row)
    assert row.independent == MISSING
    assert row.vested_interest == MISSING
    assert row.independent_url is None
    assert row.vested_interest_url is None
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_grounded(independent=MISSING, independent_url="https://example.com/guess"))


def test_grounded_house_organ_stays_grounded_and_not_independent() -> None:
    packet = seed_first_open()
    house = next(f for f in packet.receipt.findings if f.id == "trade-hit")
    assert house.stamp == "grounded"
    assert house.parallel_url == PPI_URL
    assert house.independent == "no"
    assert house.independent_url == PPI_URL
    assert house.vested_interest == MISSING
    ncbi = next(f for f in packet.receipt.findings if f.id == "ranking-hit")
    assert ncbi.stamp == "grounded"
    assert ncbi.independent == MISSING
    assert ncbi.vested_interest == MISSING
    assert "not independent" in FLOOR_HTML
