"""Foundry mints objects from thesis prose. No second Parallel pass."""

from onecrew.models import MISSING, Finding, Packet, Receipt
from onecrew.receipt import write_receipt
from onecrew.script import write_script
from onecrew.spend import ledger
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE

# Fixture copy of the live sep1b thesis: numbers already in the pack.
LIVE_PACK = """
# Research pack · oc-recession-live-sep1b

## Question
Are we near recession?

## Argument
Cited thesis spine from Task pro. USREC July 2026 = 0. Nonfarm payrolls −23k.
GDP printed 0.5, then 2.1, then 1.5. Sahm −0.03 vs the 0.50 trigger.
https://fred.stlouisfed.org/series/USREC
https://www.bls.gov/news.release/empsit.nr0.htm
https://www.bea.gov/data/gdp/gross-domestic-product
https://fred.stlouisfed.org/series/SAHMREALTIME

## Causal links
No causal link on the receipt. Missing, not invented. Do not forecast a recession.
"""

_LEFTOVER = frozenset({"timeline-hit", "timeline-frame", "timeline-miss"})


def _leftover_slots() -> list[Finding]:
    return [
        Finding(
            id="timeline-hit",
            claim="Grounded event inside 2-3y: Are we near recession?",
            stamp="grounded",
            parallel_url="https://fred.stlouisfed.org/series/USREC",
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="timeline-frame",
            claim="Widely repeated frame about Are we near recession?",
            stamp="mainstream",
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
        ),
        Finding(
            id="timeline-miss",
            claim="Fringe claim about Are we near recession?",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def _packet() -> Packet:
    return Packet(
        id="oc-recession-live-sep1b",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        research_pack=LIVE_PACK,
        task_spine="USREC July 2026 = 0. Nonfarm payrolls −23k. GDP 0.5/2.1/1.5. Sahm −0.03 vs 0.50.",
    )


def test_foundry_mints_usrec_and_payrolls_from_live_pack() -> None:
    from onecrew.foundry import foundry_findings

    before = ledger.parallel_calls
    packet = _packet()
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=_leftover_slots(),
    )
    rows = foundry_findings(packet)
    assert ledger.parallel_calls == before
    ids = {f.id for f in rows}
    assert ids != _LEFTOVER
    assert not ids <= _LEFTOVER
    usrec = next(f for f in rows if "usrec" in f.id.lower() or "usrec" in f.claim.lower())
    payrolls = next(f for f in rows if "payroll" in f.id.lower() or "payroll" in f.claim.lower())
    assert "USREC" in usrec.claim and "0" in usrec.claim
    assert "payroll" in payrolls.claim.lower()
    assert "−23k" in payrolls.claim or "-23k" in payrolls.claim or "23k" in payrolls.claim.lower()
    assert usrec.parallel_url and usrec.parallel_url.startswith("http")
    assert payrolls.parallel_url and payrolls.parallel_url.startswith("http")
    assert usrec.stamp == "grounded"
    assert payrolls.stamp == "grounded"
    gdp = next(f for f in rows if "gdp" in f.id.lower() or "gdp" in f.claim.lower())
    sahm = next(f for f in rows if "sahm" in f.id.lower() or "sahm" in f.claim.lower())
    assert "0.5" in gdp.claim and "2.1" in gdp.claim and "1.5" in gdp.claim
    assert ("−0.03" in sahm.claim or "-0.03" in sahm.claim) and "0.50" in sahm.claim
    assert not any(f.id in _LEFTOVER for f in rows)
    assert usrec.independent == MISSING
    assert usrec.independent_url is None


def test_leftover_three_slot_only_fails_when_thesis_has_usrec_and_payrolls() -> None:
    from onecrew.foundry import foundry_findings

    packet = _packet()
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=_leftover_slots(),
    )
    rows = foundry_findings(packet)
    ids = {f.id for f in rows}
    pack = packet.research_pack
    assert "USREC" in pack and "payroll" in pack.lower()
    assert ids != _LEFTOVER
    assert not ids <= _LEFTOVER


def test_foundry_does_not_invent_forecast_or_missing_causal() -> None:
    from onecrew.foundry import foundry_findings

    packet = _packet()
    rows = foundry_findings(packet)
    blob = " ".join(f"{f.id} {f.claim}" for f in rows).lower()
    assert "forecast" not in blob
    assert "will enter" not in blob
    assert not any("causal" in f.id for f in rows)


def test_foundry_then_writer_vo_has_usrec_and_payrolls() -> None:
    from onecrew.foundry import foundry_findings

    packet = _packet()
    rows = foundry_findings(packet)
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, disposition="READY", findings=rows),
    )
    write_script(packet)
    vo = packet.script + "\n" + "\n".join(b.vo for b in packet.beats)
    assert packet.status == "ready"
    assert "USREC=0" in vo
    assert "−23k" in vo or "-23k" in vo or "payrolls −23" in vo.lower()
    assert "Fringe claim about Are we near recession?" not in vo
    assert "2026 smashed into 0" not in vo
    assert ledger.parallel_calls == 0
