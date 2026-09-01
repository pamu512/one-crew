import pytest

from onecrew.floor import FLOOR_HTML
from onecrew.models import MISSING, Finding
from onecrew.receipt import ReceiptInvalidError, validate_finding
from onecrew.seed import OPEC_URL, leftover_hormuz_packet


def _grounded(**kwargs) -> Finding:
    row = dict(
        id="g",
        claim="ranks",
        stamp="grounded",
        parallel_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3894303/",
        parallel_status="hit",
        note="Parallel URL on this row.",
        propaganda=MISSING,
        propaganda_issuer=MISSING,
    )
    row.update(kwargs)
    return Finding(**row)


def test_cannot_stamp_propaganda_yes_without_parallel_hit_naming_issuer() -> None:
    with pytest.raises(ReceiptInvalidError, match="naming the issuer"):
        validate_finding(_grounded(propaganda="yes", propaganda_issuer="OPEC"))
    with pytest.raises(ReceiptInvalidError, match="naming the issuer"):
        validate_finding(
            _grounded(
                propaganda="yes",
                propaganda_url=OPEC_URL,
                propaganda_issuer=MISSING,
            )
        )
    with pytest.raises(ReceiptInvalidError, match="naming the issuer"):
        validate_finding(
            _grounded(
                propaganda="yes",
                propaganda_url=OPEC_URL,
                propaganda_issuer="",
            )
        )
    ok = _grounded(
        propaganda="yes",
        propaganda_url=OPEC_URL,
        propaganda_issuer="OPEC",
    )
    validate_finding(ok)
    assert ok.stamp == "grounded"


def test_propaganda_missing_stays_missing() -> None:
    row = _grounded()
    validate_finding(row)
    assert row.propaganda == MISSING
    assert row.propaganda_url is None
    assert row.propaganda_issuer == MISSING
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_grounded(propaganda=MISSING, propaganda_url="https://example.com/tone"))
    with pytest.raises(ReceiptInvalidError):
        validate_finding(_grounded(propaganda="no"))


def test_seeded_house_organ_stays_grounded_and_marked_propaganda() -> None:
    packet = leftover_hormuz_packet()
    house = next(f for f in packet.receipt.findings if f.id == "hormuz-share")
    assert house.stamp == "grounded"
    assert house.propaganda == "yes"
    assert house.propaganda_issuer == "OPEC"
    assert house.propaganda_url == OPEC_URL
    jcpoa = next(f for f in packet.receipt.findings if f.id == "jcpoa-2018")
    assert jcpoa.propaganda == MISSING
    fringe = next(f for f in packet.receipt.findings if f.stamp == "fringe")
    assert fringe.propaganda == MISSING
    assert fringe.stamp == "fringe"
    assert "propaganda" in FLOOR_HTML
    assert 'propaganda === "yes"' in FLOOR_HTML
    assert "propaganda: ${f.propaganda || \"missing\"}" in FLOOR_HTML
    assert "clean" not in FLOOR_HTML.lower()
