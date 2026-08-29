import pytest

from onecrew.models import Finding, Packet, Receipt
from onecrew.receipt import ReceiptInvalidError, ReceiptWriteOnceError, validate_finding, write_receipt
from onecrew.seed import seed_findings, seed_first_open


def _packet() -> Packet:
    return Packet(id="oc-test", hook="hook", script="script")


def test_receipt_write_once() -> None:
    packet = seed_first_open()
    with pytest.raises(ReceiptWriteOnceError):
        write_receipt(
            packet,
            Receipt(packet_id=packet.id, findings=seed_findings(), disposition="READY"),
        )


def test_stamp_exactly_one_of_three() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            Finding.model_construct(
                id="x",
                claim="nope",
                stamp="fact",
                parallel_status="n/a",
                note="x",
            )
        )


def test_grounded_requires_parallel_url() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            Finding(
                id="g",
                claim="ranks",
                stamp="grounded",
                parallel_url=None,
                parallel_status="hit",
                note="Parallel URL on this row.",
            )
        )


def test_mainstream_is_not_a_source() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            Finding(
                id="m",
                claim="3am kitchen",
                stamp="mainstream",
                parallel_url="https://example.com/nope",
                parallel_status="n/a",
                note="Widely repeated, may be bias, not a source.",
            )
        )


def test_fringe_never_sold_as_fact() -> None:
    with pytest.raises(ReceiptInvalidError):
        validate_finding(
            Finding(
                id="f",
                claim="NASA",
                stamp="fringe",
                parallel_status="miss",
                note="interesting rumor",
            )
        )


def test_receipt_requires_hit_and_miss() -> None:
    packet = _packet()
    only_hit = [
        Finding(
            id="ranking-hit",
            claim="ranks",
            stamp="grounded",
            parallel_url="https://example.com/hit",
            parallel_status="hit",
            note="Parallel URL on this row.",
        )
    ]
    with pytest.raises(ReceiptInvalidError):
        write_receipt(
            packet,
            Receipt(packet_id=packet.id, findings=only_hit, disposition="READY"),
        )
