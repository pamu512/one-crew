import copy

import pytest

from onecrew.agent.shift import snapshot_id
from onecrew.config import SEED_PACKET_ID
from onecrew.models import Finding, Packet, Receipt
from onecrew.pack import write_research_pack
from onecrew.receipt import write_receipt
from onecrew.script import write_script
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE


def recession_fixture() -> Packet:
    packet = Packet(
        id="oc-recession-nber",
        topic="Is the US in a recession?",
        hook="Is the US in a recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell="Host-only desk read of the latest US recession prints",
        tone="Grounded in the record",
    )
    receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=[
            Finding(
                id="nber-peak",
                when="2020",
                claim="NBER dated the last peak.",
                stamp="grounded",
                title="NBER Business Cycle Dating",
                parallel_url="https://www.nber.org/research/business-cycle-dating",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="usrec-now",
                when="2024",
                claim="USREC=0.",
                stamp="grounded",
                title="USREC",
                parallel_url="https://fred.stlouisfed.org/series/USREC",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-23k",
                when="2024",
                claim="Nonfarm payrolls fell −23k.",
                stamp="grounded",
                title="Payrolls",
                parallel_url="https://www.bls.gov/news.release/empsit.nr0.htm",
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="hidden-boom",
                when="2024",
                claim="A hidden treaty already declared a boom.",
                stamp="fringe",
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            ),
        ],
    )
    packet = write_receipt(packet, receipt)
    write_research_pack(packet)
    return packet


def test_recession_script_from_pack_not_hormuz(monkeypatch) -> None:
    packet = recession_fixture()
    captured: dict[str, str] = {}

    def capture(prompt: str) -> str:
        captured["prompt"] = prompt
        from conftest import echo_vertex_script

        return echo_vertex_script(prompt)

    monkeypatch.setattr("onecrew.script.generate_script", capture)
    write_script(packet)
    assert packet.id != SEED_PACKET_ID
    assert packet.id != "oc-hormuz-decade"
    prompt = captured["prompt"]
    assert "NBER" in prompt
    assert "USREC" in prompt
    assert "payrolls" in prompt.lower() or "−23k" in prompt or "23k" in prompt
    blob = packet.script
    assert "NBER" in blob or "USREC" in blob or "payrolls" in blob.lower()
    assert "−23k" in blob or "23k" in blob or "23,000" in blob or "USREC=0" in blob
    low = blob.lower()
    assert "gulf" not in low
    assert "hormuz" not in low
    assert "jcpoa" not in low
    assert "leila" not in low
    assert "reza" not in low
    assert packet.status == "ready"
    assert packet.beats


def test_footage_query_does_not_search_grounded_or_gulf_chart() -> None:
    from onecrew.board import _footage_query

    packet = recession_fixture()
    assert "grounded" not in _footage_query("Grounded in the record, host at desk", packet).lower()
    assert "gulf" not in _footage_query("Gulf chart on the wall", packet).lower()


def test_snapshot_id_never_inherits_hormuz_seed() -> None:
    assert snapshot_id("Is the US in a recession?", "shift-abc123def") != SEED_PACKET_ID
    assert snapshot_id("Hormuz", "shift-abc123def") != SEED_PACKET_ID
    assert snapshot_id("Explain what's going on with the Hormuz strait", "shift-xxxxxxxx") != SEED_PACKET_ID


@pytest.mark.no_vertex
def test_missing_vertex_holds_no_leftover_vo() -> None:
    packet = recession_fixture()
    write_script(packet)
    assert packet.script == ""
    assert packet.beats == []
    assert packet.status == "hold"
    assert any(row.what == "Vertex script" for row in packet.exclusions)
    assert any("Vertex" in (row.detail or "") for row in packet.exclusions)
    assert "Hormuz" not in (packet.script or "")
    assert "Leila" not in (packet.script or "")


@pytest.mark.no_vertex
def test_empty_pack_holds() -> None:
    packet = Packet(
        id="oc-empty",
        topic="Whatever",
        hook="Whatever",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="1y",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
    )
    packet.receipt = Receipt(packet_id=packet.id, disposition="READY", findings=[], written=True)
    write_script(packet)
    assert packet.script == ""
    assert packet.beats == []
    assert packet.status == "hold"
    assert any("empty pack" in (row.detail or "") for row in packet.exclusions)


def test_write_script_sends_tell_tone_cut_lean(monkeypatch) -> None:
    packet = recession_fixture()
    packet.script_lean = "left"
    packet.tone = "Question the decisions"
    packet.tell = "Weekly news desk, host only"
    packet.cut = "weekly_update"
    seen = {}

    def wrap(prompt: str) -> str:
        seen["prompt"] = prompt
        from conftest import echo_vertex_script

        return echo_vertex_script(prompt)

    monkeypatch.setattr("onecrew.script.generate_script", wrap)
    write_script(packet)
    prompt = seen["prompt"]
    assert "weekly_update" in prompt
    assert "Question the decisions" in prompt
    assert "Weekly news desk, host only" in prompt
    assert "left" in prompt
    assert "NBER" in packet.script or "USREC" in packet.script or "payrolls" in packet.script.lower()
    stamps = [(f.id, f.stamp) for f in packet.receipt.findings]
    again = copy.deepcopy(packet.receipt)
    assert stamps == [(f.id, f.stamp) for f in again.findings]
