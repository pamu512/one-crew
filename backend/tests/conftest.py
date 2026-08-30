from __future__ import annotations

import json

import pytest

from onecrew.models import CausalLink, Finding, Packet, Receipt
from onecrew.script import _PACKET_END, _PACKET_MARK, draft_model_script
from onecrew.spend import ledger
from onecrew.store import rebind_store
from onecrew.vertex_client import VertexDownError


def pytest_configure(config) -> None:
    config.addinivalue_line("markers", "no_vertex: fail-closed path, do not mock Vertex")


def echo_vertex_script(prompt: str) -> str:
    """Test double: VO from the pack in the prompt. Not a Hormuz leftover."""
    start = prompt.index(_PACKET_MARK) + len(_PACKET_MARK)
    end = prompt.index(_PACKET_END)
    payload = json.loads(prompt[start:end])
    findings = [
        Finding(
            id=row["id"],
            claim=row["claim"],
            stamp=row["stamp"],
            parallel_status="n/a",
            note=row.get("note") or "",
            title=row.get("title") or "missing",
            when=row.get("when") or "",
        )
        for row in payload.get("findings") or []
    ]
    links = [
        CausalLink(
            id=row["id"],
            from_id=row["from_id"],
            to_id=row["to_id"],
            claim=row["claim"],
            stamp=row.get("stamp") or "missing",
            parallel_url=None,
        )
        for row in payload.get("links") or []
    ]
    packet = Packet(
        id=payload.get("id") or "oc-echo",
        topic=payload.get("topic") or "",
        hook=payload.get("topic") or "hook",
        script="",
        tell=payload.get("tell") or "",
        tone=payload.get("tone") or "",
        cut=payload.get("cut"),
        script_lean=payload.get("script_lean"),
        platform=payload.get("platform"),
        research_pack=payload.get("pack") or "",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=findings,
        causal_links=links,
    )
    return json.dumps(draft_model_script(packet))


@pytest.fixture(autouse=True)
def _mock_vertex(request, monkeypatch):
    if request.node.get_closest_marker("no_vertex"):
        def down(_prompt: str) -> str:
            raise VertexDownError("Vertex missing")

        monkeypatch.setattr("onecrew.script.generate_script", down)
        monkeypatch.setattr("onecrew.vertex_client.generate_script", down)
        return

    monkeypatch.setattr("onecrew.script.generate_script", echo_vertex_script)
    monkeypatch.setattr("onecrew.vertex_client.generate_script", echo_vertex_script)


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ONECREW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SHIFT_TOKEN", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("ONECREW_FORCE_FIRESTORE", raising=False)
    ledger.reset()
    rebind_store()
    yield
    ledger.reset()
