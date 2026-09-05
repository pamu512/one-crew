"""Locked pipeline: Parallel researches, ADK writer, ADK room, storyboard on ship."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from onecrew.api import app
from onecrew.floor import FLOOR_HTML
from onecrew.models import Finding, Packet, Rails, Receipt
from onecrew.research import (
    HORIZON_DEEPER,
    HORIZON_RECENT,
    research_horizon,
    search_objective,
    search_queries,
    task_research_prompt,
)
from onecrew.room import (
    GradeArtifact,
    RoomGrade,
    claim_supported_after_churn,
    grade_room,
    make_grade_artifact,
    relink_cite_if_supported,
    run_room_loop,
)
from onecrew.script_writer import write_vo_from_pack
from onecrew.verify import Claim, CiteBag, CiteExcerpt, verify_print_in_cite


_DEPTH_AUTHORITY = (
    "inside depth=",
    "inside depth=",
    "depth=1y",
    "depth=2-3y",
    "depth=5y",
    "depth=decade",
    "depth=few_decades",
    "depth=pre-1980",
)

FRED = "https://fred.stlouisfed.org/series/USREC"
BLS_OLD = "https://www.bls.gov/news.release/empsit.nr0.htm"
BLS_NEW = "https://www.bls.gov/news.release/archives/empsit_04042025.htm"
_MAR_CES = (
    "THE EMPLOYMENT SITUATION -- MARCH 2025\n"
    "Total nonfarm payroll employment fell by 41,000 in March 2025.\n"
)
_MAR_PIPE = "2025-01-01 | 0\n2025-02-01 | 0\n2025-03-01 | 0\n"


def _depth_authority_in(text: str) -> list[str]:
    blob = text or ""
    return [tok for tok in _DEPTH_AUTHORITY if tok in blob]


def test_default_horizon_is_first_trigger_recent_news_not_depth_enum() -> None:
    assert research_horizon(deeper_history=False) == HORIZON_RECENT
    prompt = task_research_prompt("Are we near recession?", deeper_history=False)
    assert _depth_authority_in(prompt) == []
    assert "first" in prompt.lower() and "trigger" in prompt.lower()
    assert "recent news" in prompt.lower()
    assert "decide how far" in prompt.lower() or "do not decide" in prompt.lower()
    assert "inside depth=" not in prompt
    obj = search_objective("Are we near recession?", deeper_history=False)
    assert _depth_authority_in(obj) == []
    assert "first" in obj.lower() or "recent" in obj.lower()
    queries = search_queries("Are we near recession?", tell="desk read", deeper_history=False)
    assert all(_depth_authority_in(q) == [] for q in queries)
    assert all("decade" not in q.split() or "recession" in q.lower() for q in queries)


def test_explicit_deeper_history_extends_horizon() -> None:
    assert research_horizon(deeper_history=True) == HORIZON_DEEPER
    prompt = task_research_prompt("Are we near recession?", deeper_history=True)
    assert _depth_authority_in(prompt) == []
    assert "deeper" in prompt.lower()
    assert "explicit" in prompt.lower() or "user" in prompt.lower()
    shallow = task_research_prompt("Are we near recession?", deeper_history=False)
    assert "deeper history" not in shallow.lower()
    obj = search_objective("Are we near recession?", deeper_history=True)
    assert _depth_authority_in(obj) == []
    assert "deeper" in obj.lower() or "history" in obj.lower()


def test_live_research_does_not_forward_floor_depth_into_task(monkeypatch) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet

    prompts: list[str] = []
    objectives: list[str] = []

    def search(*, objective, search_queries):
        objectives.append(objective)
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/fringe-miss",
                        title="Fringe",
                        excerpts=["Secret double-dip already started."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url=FRED,
                    title="USREC",
                    excerpts=["USREC March 2025 = 0.", _MAR_PIPE],
                ),
                SimpleNamespace(
                    url=BLS_OLD,
                    title="Employment Situation",
                    excerpts=[_MAR_CES],
                ),
            ]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[
                SimpleNamespace(url=FRED, title="USREC", excerpts=["USREC March 2025 = 0.", _MAR_PIPE]),
                SimpleNamespace(url=BLS_OLD, title="CES", excerpts=[_MAR_CES]),
            ],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        prompts.append(prompt)
        if processor == "base":
            return SimpleNamespace(output=SimpleNamespace(content={}, basis=[]))
        return SimpleNamespace(
            output=SimpleNamespace(
                content="USREC March 2025 = 0. Nonfarm payrolls fell 41,000 in March 2025.",
                basis=[],
            )
        )

    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    shift = open_shift(
        "Are we near recession?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Are we near recession?",
        deeper_history=False,
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    thesis = [p for p in prompts if p and "Enrich" not in p]
    assert thesis, "Task pro must run"
    for prompt in thesis:
        assert _depth_authority_in(prompt) == []
        assert "inside depth=decade" not in prompt
    for obj in objectives:
        assert "inside depth=" not in obj
        assert "inside depth=decade" not in obj
    assert packet.deeper_history is False


def test_script_writer_uses_stubbed_vertex_and_parallel_returns_pack_only(monkeypatch) -> None:
    pack = (
        "First trigger: March 2025 CES. USREC March 2025 = 0. "
        "Total nonfarm payroll employment fell by 41,000 in March 2025."
    )
    packet = Packet(
        id="oc-pack-faithful-mar",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        research_pack=pack,
        task_spine=pack,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=[
            Finding(
                id="usrec-march-2025",
                claim="USREC=0 (March 2025).",
                stamp="grounded",
                title="USREC",
                series="USREC",
                print="0",
                when="March 2025",
                parallel_url=FRED,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
            Finding(
                id="payrolls-march-2025",
                claim="Nonfarm payrolls fell −41,000 in March 2025.",
                stamp="grounded",
                title="BLS payrolls",
                series="BLS payrolls",
                print="−41,000",
                when="March 2025",
                parallel_url=BLS_OLD,
                parallel_status="hit",
                note="Parallel URL on this row.",
            ),
        ],
    )
    vertex_prompts: list[str] = []

    def fake_vertex(prompt: str) -> str:
        vertex_prompts.append(prompt)
        return (
            '[{"id":"cold-open","vo":"USREC=0 smashed into payrolls −41,000. [usrec-march-2025] [payrolls-march-2025]",'
            '"eyes":"March CES","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
            '{"id":"promise","vo":"Three objects from the pack. [usrec-march-2025]","eyes":"pack","finding_ids":["usrec-march-2025"]},'
            '{"id":"gdp","vo":"USREC=0 (March 2025). [usrec-march-2025]","eyes":"usrec","finding_ids":["usrec-march-2025"]},'
            '{"id":"labor","vo":"Nonfarm payrolls fell −41,000. [payrolls-march-2025]","eyes":"ces","finding_ids":["payrolls-march-2025"]},'
            '{"id":"turn","vo":"Hold on the pack number. [usrec-march-2025]","eyes":"hold","finding_ids":["usrec-march-2025"]},'
            '{"id":"complication","vo":"Those are not the same object. [usrec-march-2025]","eyes":"gap","finding_ids":["usrec-march-2025"]},'
            '{"id":"receipt","vo":"Receipt board: named series. [usrec-march-2025] [payrolls-march-2025]","eyes":"board","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
            '{"id":"close","vo":"Near is not a switch. [usrec-march-2025]","eyes":"close","finding_ids":["usrec-march-2025"]}]'
        )

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", fake_vertex)
    monkeypatch.setattr("onecrew.script_writer.generate_script", fake_vertex)
    written = write_vo_from_pack(packet)
    assert vertex_prompts, "Vertex script writer must be called"
    joined = " ".join(vertex_prompts)
    assert "41,000" in joined or pack[:20] in joined
    assert written.script
    spoken = written.script + "".join(b.vo for b in written.beats)
    assert "41,000" in spoken or "41k" in spoken.lower()
    assert "−23k" not in spoken and "-23k" not in spoken
    assert "July 2026" not in spoken
    assert "Grounded event inside" not in spoken


def test_room_grade_ship_and_recut_reason_enum() -> None:
    artifact = GradeArtifact(
        packet_id="oc-room",
        research_pack_summary="March CES first trigger.",
        script="USREC=0 smashed into payrolls −41,000.",
    )
    shipped = RoomGrade(vote="ship")
    assert shipped.vote == "ship"
    recut = RoomGrade(vote="recut", recut_reason="not_enough_information", recut_detail="need first trigger cite")
    assert recut.vote == "recut"
    assert recut.recut_reason == "not_enough_information"
    other = RoomGrade(vote="recut", recut_reason="other", recut_detail="cold open is muddy")
    assert other.recut_reason == "other"
    built = make_grade_artifact(
        Packet(
            id="oc-room",
            topic="Are we near recession?",
            hook="Are we near recession?",
            script="full script here",
            research_pack="# Research pack · oc-room\n\nMarch CES first trigger. More prose.",
        )
    )
    assert built.packet_id == "oc-room"
    assert built.script == "full script here"
    assert "March CES" in built.research_pack_summary


def test_recut_not_enough_information_one_extra_parallel_then_hold() -> None:
    research_calls: list[str | None] = []
    rewrites = {"n": 0}

    def research(missing_ask: str | None = None) -> None:
        research_calls.append(missing_ask)

    def rewrite() -> None:
        rewrites["n"] += 1

    grades = iter(
        [
            RoomGrade(vote="recut", recut_reason="not_enough_information", recut_detail="need first trigger"),
            RoomGrade(vote="ship"),
        ]
    )
    packet = Packet(id="oc-loop", hook="t", script="draft", research_pack="thin pack")
    result = run_room_loop(
        packet,
        research=research,
        rewrite=rewrite,
        grader=lambda _a: next(grades),
        parallel_already=1,
    )
    assert research_calls == ["need first trigger"]
    assert rewrites["n"] == 1
    assert result.parallel_research_calls == 2
    assert result.grade.vote == "ship"
    assert result.disposition == "READY"

    research_calls.clear()
    rewrites["n"] = 0
    grades2 = iter(
        [
            RoomGrade(vote="recut", recut_reason="not_enough_information", recut_detail="still thin"),
            RoomGrade(vote="recut", recut_reason="not_enough_information", recut_detail="still thin"),
        ]
    )
    held = run_room_loop(
        Packet(id="oc-hold", hook="t", script="draft", research_pack="thin"),
        research=research,
        rewrite=rewrite,
        grader=lambda _a: next(grades2),
        parallel_already=1,
    )
    assert research_calls == ["still thin"]
    assert held.parallel_research_calls == 2
    assert held.disposition == "HOLD"
    assert held.grade.vote == "recut"
    assert held.grade.recut_reason == "not_enough_information"


def test_cite_url_churn_does_not_fail_if_claim_still_supported() -> None:
    claim = Claim(
        series="BLS payrolls",
        print="−41,000",
        when="March 2025",
        id="payrolls-march-2025",
        cite_url=BLS_OLD,
        claim_span="Nonfarm payrolls fell −41,000 in March 2025.",
    )
    new_bag = CiteBag(
        excerpts=[CiteExcerpt(url=BLS_NEW, title="CES archive", text=_MAR_CES)],
        spine="USREC March 2025 = 0. Nonfarm payrolls fell 41,000 in March 2025.",
        hit_urls=[BLS_NEW],
    )
    assert claim_supported_after_churn(claim, new_bag) is True
    relinked = relink_cite_if_supported(claim, new_bag)
    assert relinked.cite_url == BLS_NEW
    assert relinked.cite_url != BLS_OLD
    assert verify_print_in_cite(relinked, new_bag).ok is True


def test_unrelated_topic_has_no_leftover_hormuz_3slot(monkeypatch) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.foundry import leftover_slot_ids

    leftover = leftover_slot_ids()
    cite = "The 10-year yield printed 4.8% in March 2026."

    def search(*, objective, search_queries):
        blob = f"{objective} {' '.join(search_queries)}".lower()
        if "hidden" in blob or "fringe" in blob:
            return SimpleNamespace(
                results=[
                    SimpleNamespace(
                        url="https://example.com/fringe-yield",
                        title="Fringe",
                        excerpts=["Secret yield already inverted under a hidden treaty."],
                    )
                ]
            )
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://fred.stlouisfed.org/series/DGS10",
                    title="DGS10",
                    excerpts=[cite],
                )
            ]
        )

    def extract(*, urls, objective):
        return SimpleNamespace(
            results=[SimpleNamespace(url="https://fred.stlouisfed.org/series/DGS10", title="DGS10", excerpts=[cite])],
            errors=[],
        )

    def task(*, prompt, processor="pro", task_spec=None):
        return SimpleNamespace(output=SimpleNamespace(content=cite, basis=[]))

    monkeypatch.setattr("onecrew.agent.shift.search", search)
    monkeypatch.setattr("onecrew.agent.shift.extract", extract)
    monkeypatch.setattr("onecrew.agent.shift.run_task", task)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    shift = open_shift(
        "Did the 10-year break?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Did the 10-year break?",
    )
    shift.rails = Rails(parallel=True, vertex=False, imagen=False)
    packet = run_live_packet(shift)
    ids = {f.id for f in (packet.receipt.findings if packet.receipt else [])}
    assert ids.isdisjoint(leftover)
    assert "hormuz-share" not in ids
    spoken = (packet.script or "") + "".join(b.vo for b in packet.beats)
    assert "hormuz" not in spoken.lower()
    assert "jcpoa" not in spoken.lower()
    assert "hormuz=13" not in spoken.lower()


_HOLD_PACK = (
    "First trigger: March 2025 CES. USREC March 2025 = 0. "
    "Total nonfarm payroll employment fell by 41,000 in March 2025."
)
_HOLD_VERTEX_BEATS = (
    '[{"id":"cold-open","vo":"USREC=0 smashed into payrolls −41,000. [usrec-march-2025] [payrolls-march-2025]",'
    '"eyes":"March CES","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
    '{"id":"promise","vo":"Three objects from the pack. [usrec-march-2025]","eyes":"pack","finding_ids":["usrec-march-2025"]},'
    '{"id":"gdp","vo":"USREC=0 (March 2025). [usrec-march-2025]","eyes":"usrec","finding_ids":["usrec-march-2025"]},'
    '{"id":"labor","vo":"Nonfarm payrolls fell −41,000. [payrolls-march-2025]","eyes":"ces","finding_ids":["payrolls-march-2025"]},'
    '{"id":"turn","vo":"Hold on the pack number. [usrec-march-2025]","eyes":"hold","finding_ids":["usrec-march-2025"]},'
    '{"id":"complication","vo":"Those are not the same object. [usrec-march-2025]","eyes":"gap","finding_ids":["usrec-march-2025"]},'
    '{"id":"receipt","vo":"Receipt board: named series. [usrec-march-2025] [payrolls-march-2025]","eyes":"board","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
    '{"id":"close","vo":"Near is not a switch. [usrec-march-2025]","eyes":"close","finding_ids":["usrec-march-2025"]}]'
)


def _hold_findings() -> list[Finding]:
    return [
        Finding(
            id="usrec-march-2025",
            claim="USREC=0 (March 2025).",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="March 2025",
            parallel_url=FRED,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-march-2025",
            claim="Nonfarm payrolls fell −41,000 in March 2025.",
            stamp="grounded",
            title="BLS payrolls",
            series="BLS payrolls",
            print="−41,000",
            when="March 2025",
            parallel_url=BLS_OLD,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]


def _hold_packet(*, disposition: str) -> Packet:
    packet = Packet(
        id="oc-hold-vo-pack",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        research_pack=_HOLD_PACK,
        task_spine=_HOLD_PACK,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition=disposition,
        hold_reason="verify: print not in cite" if disposition == "HOLD" else None,
        findings=_hold_findings(),
    )
    return packet


def _vertex_stub(bucket: list[str]):
    def fake_vertex(prompt: str) -> str:
        bucket.append(prompt)
        return _HOLD_VERTEX_BEATS

    return fake_vertex


def _dropped_series_findings() -> list[Finding]:
    """Seven live-style findings with USREC but no minted payrolls object."""
    note = "Parallel URL on this row."
    return [
        Finding(
            id="usrec-march-2025",
            claim="USREC=0 (March 2025).",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="March 2025",
            parallel_url=FRED,
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="gdp-2025-q1",
            claim="GDP printed in the pack window.",
            stamp="grounded",
            title="GDP",
            series="GDP",
            print="",
            when="Q1 2025",
            parallel_url="https://www.bea.gov/data/gdp/gross-domestic-product",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="u3-march-2025",
            claim="Unemployment named in the pack.",
            stamp="grounded",
            title="U-3",
            series="U-3",
            print="",
            when="March 2025",
            parallel_url=BLS_OLD,
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="sahm-march-2025",
            claim="Sahm named in the pack.",
            stamp="grounded",
            title="Sahm",
            series="SAHMREALTIME",
            print="",
            when="March 2025",
            parallel_url="https://fred.stlouisfed.org/series/SAHMREALTIME",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="lei-march-2025",
            claim="LEI named in the pack.",
            stamp="grounded",
            title="LEI",
            series="LEI",
            print="",
            when="March 2025",
            parallel_url="https://www.conference-board.org/topics/us-leading-indicators",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="nber-march-2025",
            claim="NBER cycle dating named in the pack.",
            stamp="grounded",
            title="NBER",
            series="NBER",
            print="",
            when="March 2025",
            parallel_url="https://www.nber.org/research/business-cycle-dating",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="fringe-unsourced",
            claim="Fringe miss tagged, not sold as fact.",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def _mint_hold_packet(*, hold_reason: str) -> Packet:
    packet = Packet(
        id="oc-are-we-near-recession-hold-vo",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        research_pack=_HOLD_PACK,
        task_spine=_HOLD_PACK,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason=hold_reason,
        findings=_dropped_series_findings(),
    )
    return packet


def _dropped_vertex_beats() -> str:
    return (
        '[{"id":"cold-open","vo":"USREC=0 smashed into payrolls fell 41,000. [usrec-march-2025]",'
        '"eyes":"March CES","finding_ids":["usrec-march-2025"]},'
        '{"id":"promise","vo":"Three objects from the pack. [usrec-march-2025]","eyes":"pack","finding_ids":["usrec-march-2025"]},'
        '{"id":"gdp","vo":"USREC=0 (March 2025). [usrec-march-2025]","eyes":"usrec","finding_ids":["usrec-march-2025"]},'
        '{"id":"labor","vo":"Nonfarm payrolls fell 41,000. [usrec-march-2025]","eyes":"ces","finding_ids":["usrec-march-2025"]},'
        '{"id":"turn","vo":"Hold on the pack number. [usrec-march-2025]","eyes":"hold","finding_ids":["usrec-march-2025"]},'
        '{"id":"complication","vo":"Those are not the same object. [usrec-march-2025]","eyes":"gap","finding_ids":["usrec-march-2025"]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-march-2025]","eyes":"board","finding_ids":["usrec-march-2025"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-march-2025]","eyes":"close","finding_ids":["usrec-march-2025"]}]'
    )


def test_hold_foundry_dropped_still_writes_vertex_vo(monkeypatch) -> None:
    packet = _mint_hold_packet(hold_reason="verify: print not in cite")
    writer_prompts: list[str] = []

    def fake_vertex(prompt: str) -> str:
        writer_prompts.append(prompt)
        return _dropped_vertex_beats()

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", fake_vertex)
    monkeypatch.setattr("onecrew.script_writer.generate_script", fake_vertex)
    written = write_vo_from_pack(packet)
    assert writer_prompts, "mint HOLD must still call Vertex"
    assert written.script, "foundry dropped named series must not blank script before Vertex"
    assert len(written.beats) == 8
    spoken = written.script + "".join(b.vo for b in written.beats)
    assert "41,000" in spoken or "41k" in spoken.lower()
    assert "−23k" not in spoken and "-23k" not in spoken
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert "foundry dropped named series" in (packet.receipt.hold_reason or "")
    assert packet.status == "hold"


def test_hold_print_not_in_cite_still_writes_vertex_vo(monkeypatch) -> None:
    packet = _mint_hold_packet(hold_reason="verify: print not in cite")
    writer_prompts: list[str] = []

    def fake_vertex(prompt: str) -> str:
        writer_prompts.append(prompt)
        return _dropped_vertex_beats()

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", fake_vertex)
    monkeypatch.setattr("onecrew.script_writer.generate_script", fake_vertex)
    written = write_vo_from_pack(packet)
    assert writer_prompts
    assert written.script
    assert len(written.beats) == 8
    assert packet.receipt is not None
    assert "print not in cite" in (packet.receipt.hold_reason or "")
    assert packet.status == "hold"


def _mixed_month_hold_findings() -> list[Finding]:
    """Live HOLD shape: USREC + payrolls on different months, foundry-dropped prints."""
    note = "Parallel URL on this row."
    return [
        Finding(
            id="usrec-august-2026",
            claim="USREC=0 (August 2026).",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="August 2026",
            parallel_url=FRED,
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="payrolls-july-2026",
            claim="Nonfarm payrolls named in the pack.",
            stamp="grounded",
            title="BLS payrolls",
            series="BLS payrolls",
            print="41000",
            when="July 2026",
            parallel_url=BLS_OLD,
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="gdp-2026-q2",
            claim="GDP named in the pack.",
            stamp="grounded",
            title="GDP",
            series="GDP",
            print="",
            when="Q2 2026",
            parallel_url="https://www.bea.gov/data/gdp/gross-domestic-product",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="sahm-july-2026",
            claim="Sahm named in the pack.",
            stamp="grounded",
            title="Sahm",
            series="SAHMREALTIME",
            print="",
            when="July 2026",
            parallel_url="https://fred.stlouisfed.org/series/SAHMREALTIME",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="u3-july-2026",
            claim="Unemployment named in the pack.",
            stamp="grounded",
            title="U-3",
            series="U-3",
            print="",
            when="July 2026",
            parallel_url=BLS_OLD,
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="nber-cycle",
            claim="NBER cycle dating named in the pack.",
            stamp="grounded",
            title="NBER",
            series="NBER",
            print="",
            when="August 2026",
            parallel_url="https://www.nber.org/research/business-cycle-dating",
            parallel_status="hit",
            note=note,
        ),
        Finding(
            id="fringe-unsourced",
            claim="Fringe miss tagged, not sold as fact.",
            stamp="fringe",
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def _pack_vo_vertex_beats() -> str:
    """Leftover-free Vertex 8-beats: pack numbers / finding_ids, not minted smash marks."""
    return (
        '[{"id":"cold-open","vo":"Nonfarm payrolls fell 41,000 in the pack window. [usrec-august-2026]",'
        '"eyes":"CES card","finding_ids":["usrec-august-2026"]},'
        '{"id":"promise","vo":"Three objects from the pack. The title stays a question.","eyes":"pack","finding_ids":[]},'
        '{"id":"gdp","vo":"GDP hole named from the pack. [gdp-2026-q2]","eyes":"gdp","finding_ids":["gdp-2026-q2"]},'
        '{"id":"labor","vo":"Labor: payrolls fell 41,000. [payrolls-july-2026]","eyes":"ces","finding_ids":["payrolls-july-2026"]},'
        '{"id":"turn","vo":"Hold on the pack number. The spine chart stays.","eyes":"hold","finding_ids":[]},'
        '{"id":"complication","vo":"Those are not the same object. Near is the gap.","eyes":"gap","finding_ids":[]},'
        '{"id":"receipt","vo":"Receipt board: named series from the pack. [usrec-august-2026]","eyes":"board","finding_ids":["usrec-august-2026"]},'
        '{"id":"close","vo":"Near is not a switch. When the pack changes, the board changes.","eyes":"close","finding_ids":[]}]'
    )


def test_hold_mint_holes_keeps_vertex_pack_vo(monkeypatch) -> None:
    """HOLD + smash mixed months / foundry dropped must keep leftover-free Vertex VO."""
    packet = Packet(
        id="oc-are-we-near-recession-831ba8c2",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        research_pack=_HOLD_PACK,
        task_spine=_HOLD_PACK,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="smash mixed months; foundry dropped named series",
        findings=_mixed_month_hold_findings(),
    )
    writer_prompts: list[str] = []

    def fake_vertex(prompt: str) -> str:
        writer_prompts.append(prompt)
        return _pack_vo_vertex_beats()

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", fake_vertex)
    monkeypatch.setattr("onecrew.script_writer.generate_script", fake_vertex)
    written = write_vo_from_pack(packet)
    assert writer_prompts, "mint HOLD must still call Vertex"
    assert written.script, "mint holes must not blank leftover-free Vertex VO"
    assert len(written.beats) == 8
    spoken = written.script + "".join(b.vo for b in written.beats)
    assert "41,000" in spoken or "41k" in spoken.lower()
    assert "−23k" not in spoken and "-23k" not in spoken
    assert "2.1" not in spoken and "1.5" not in spoken
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    reason = packet.receipt.hold_reason or ""
    assert "smash mixed months" in reason or "foundry dropped named series" in reason
    assert packet.status == "hold"


def test_hold_mint_holes_vertex_unusable_still_assembles_local(monkeypatch) -> None:
    """When mint holes and Vertex returns nothing usable, keep a local 8-beat draft."""
    packet = Packet(
        id="oc-are-we-near-recession-local-draft",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        research_pack=_HOLD_PACK,
        task_spine=_HOLD_PACK,
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="smash mixed months; foundry dropped named series",
        findings=_mixed_month_hold_findings(),
    )

    def fake_vertex(_prompt: str) -> str:
        return "not-json"

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", fake_vertex)
    monkeypatch.setattr("onecrew.script_writer.generate_script", fake_vertex)
    written = write_vo_from_pack(packet)
    assert written.script, "mint holes + unusable Vertex must still assemble local 8-beat draft"
    assert len(written.beats) == 8
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert packet.status == "hold"
    vertex_rows = [row for row in written.exclusions if row.what == "Vertex script"]
    assert not vertex_rows or "unusable" not in (vertex_rows[0].detail or "") or written.script


def test_empty_pack_still_fail_closed() -> None:
    packet = Packet(
        id="oc-empty-pack-vo",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read",
        tone="On the cited print",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="verify: print not in cite",
        findings=[],
    )
    from onecrew.script import write_script

    write_script(packet)
    assert packet.script == ""
    assert packet.beats == []
    assert packet.status == "hold"


def test_leftover_hormuz_on_non_hormuz_topic_fail_closed(monkeypatch) -> None:
    packet = _hold_packet(disposition="READY")
    hormuz = (
        '[{"id":"cold-open","vo":"Hormuz=13 smashed into JCPOA. [usrec-march-2025] [payrolls-march-2025]",'
        '"eyes":"strait","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
        '{"id":"promise","vo":"Strait of Hormuz leftover. [usrec-march-2025]","eyes":"pack","finding_ids":["usrec-march-2025"]},'
        '{"id":"gdp","vo":"USREC=0 (March 2025). [usrec-march-2025]","eyes":"usrec","finding_ids":["usrec-march-2025"]},'
        '{"id":"labor","vo":"Nonfarm payrolls fell −41,000. [payrolls-march-2025]","eyes":"ces","finding_ids":["payrolls-march-2025"]},'
        '{"id":"turn","vo":"Hold on the pack number. [usrec-march-2025]","eyes":"hold","finding_ids":["usrec-march-2025"]},'
        '{"id":"complication","vo":"Those are not the same object. [usrec-march-2025]","eyes":"gap","finding_ids":["usrec-march-2025"]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-march-2025] [payrolls-march-2025]","eyes":"board","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-march-2025]","eyes":"close","finding_ids":["usrec-march-2025"]}]'
    )

    def fake_vertex(_prompt: str) -> str:
        return hormuz

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", fake_vertex)
    monkeypatch.setattr("onecrew.script_writer.generate_script", fake_vertex)
    written = write_vo_from_pack(packet)
    spoken = (written.script or "") + "".join(b.vo for b in written.beats)
    assert written.script == ""
    assert written.beats == []
    assert "hormuz" not in spoken.lower()
    reason = (written.receipt.hold_reason or "") if written.receipt else ""
    reason += " ".join(row.detail for row in written.exclusions)
    assert "leftover Hormuz" in reason


def test_write_vo_from_pack_uses_vertex_when_receipt_is_hold(monkeypatch) -> None:
    packet = _hold_packet(disposition="HOLD")
    writer_prompts: list[str] = []
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script.generate_script", lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("script.generate_script must not be the only Vertex path")))
    monkeypatch.setattr("onecrew.script_writer.generate_script", _vertex_stub(writer_prompts))
    written = write_vo_from_pack(packet)
    assert writer_prompts, "write_vo_from_pack must invoke Vertex from the pack"
    assert "41,000" in " ".join(writer_prompts) or _HOLD_PACK[:20] in " ".join(writer_prompts)
    assert written.script
    spoken = written.script + "".join(b.vo for b in written.beats)
    assert "41,000" in spoken or "41k" in spoken.lower()
    assert "−23k" not in spoken and "-23k" not in spoken
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert packet.receipt.findings
    assert packet.status == "hold"


def test_verify_hold_with_findings_still_writes_vo(monkeypatch) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    vo_calls = {"n": 0}
    writer_prompts: list[str] = []

    def research(packet, rails, depth, **_k):
        packet.research_pack = _HOLD_PACK
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="HOLD",
            hold_reason="verify: print not in cite",
            findings=_hold_findings(),
            causal_links=[],
        )
        return receipt, [], [FRED, BLS_OLD], _HOLD_PACK

    def tracking_vo(packet):
        vo_calls["n"] += 1
        return real_write_vo(packet)

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", tracking_vo)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script_writer.generate_script", _vertex_stub(writer_prompts))
    shift = open_shift(
        "Are we near recession?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Are we near recession?",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=False)
    packet = run_live_packet(shift)
    assert vo_calls["n"] >= 1
    assert writer_prompts, "generate_script must run after verify HOLD"
    assert packet.script, "verify HOLD must not blank script when findings exist"
    assert packet.script != ""
    assert packet.beats
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert {f.id for f in packet.receipt.findings} == {"usrec-march-2025", "payrolls-march-2025"}
    spoken = packet.script + "".join(b.vo for b in packet.beats)
    assert "−23k" not in spoken and "-23k" not in spoken
    assert "July 2026" not in spoken


def test_verify_hold_after_vo_still_reaches_room_and_can_ship(monkeypatch) -> None:
    from onecrew.agent.shift import _board as real_board
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.room import run_room_loop as real_room

    room_calls = {"n": 0}
    board_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = _HOLD_PACK
        return (
            Receipt(
                packet_id=packet.id,
                written=False,
                disposition="HOLD",
                hold_reason="verify: print not in cite",
                findings=_hold_findings(),
                causal_links=[],
            ),
            [],
            [FRED, BLS_OLD],
            _HOLD_PACK,
        )

    def tracking_room(*args, **kwargs):
        room_calls["n"] += 1
        kwargs["grader"] = lambda _a: RoomGrade(vote="ship")
        return real_room(*args, **kwargs)

    def tracking_board(packet, rails):
        board_calls["n"] += 1
        return real_board(packet, rails)

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.run_room_loop", tracking_room)
    monkeypatch.setattr("onecrew.agent.shift._board", tracking_board)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script_writer.generate_script", _vertex_stub([]))
    shift = open_shift(
        "Are we near recession?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Are we near recession?",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=True)
    packet = run_live_packet(shift)
    assert packet.script
    assert room_calls["n"] >= 1
    assert packet.room_grade is not None
    assert packet.room_grade.vote == "ship"
    assert packet.grade_artifact is not None
    assert board_calls["n"] >= 1
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert packet.receipt.findings
    assert packet.status == "hold"


def _adk_eight_from_pack(prompt: str) -> str:
    """Stub ADK writer: 8 beats from pack numbers, not foundry mint stamps."""
    pack = prompt or ""
    spoken = "USREC=0 smashed into payrolls −41,000." if "41,000" in pack or "USREC" in pack else "pack beat"
    return (
        f'[{{"id":"cold-open","vo":"{spoken} [usrec-march-2025] [payrolls-march-2025]",'
        '"eyes":"March CES","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
        '{"id":"promise","vo":"Three objects from the pack. [usrec-march-2025]","eyes":"pack","finding_ids":["usrec-march-2025"]},'
        '{"id":"gdp","vo":"USREC=0 (March 2025). [usrec-march-2025]","eyes":"usrec","finding_ids":["usrec-march-2025"]},'
        '{"id":"labor","vo":"Nonfarm payrolls fell −41,000. [payrolls-march-2025]","eyes":"ces","finding_ids":["payrolls-march-2025"]},'
        '{"id":"turn","vo":"Hold on the pack number. [usrec-march-2025]","eyes":"hold","finding_ids":["usrec-march-2025"]},'
        '{"id":"complication","vo":"Those are not the same object. [usrec-march-2025]","eyes":"gap","finding_ids":["usrec-march-2025"]},'
        '{"id":"receipt","vo":"Receipt board: named series. [usrec-march-2025] [payrolls-march-2025]","eyes":"board","finding_ids":["usrec-march-2025","payrolls-march-2025"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-march-2025]","eyes":"close","finding_ids":["usrec-march-2025"]}]'
    )


def test_stub_adk_writer_eight_beats_from_pack_nonempty_script(monkeypatch) -> None:
    packet = _hold_packet(disposition="READY")
    writer_prompts: list[str] = []

    def stub_writer(prompt: str) -> str:
        writer_prompts.append(prompt)
        return _adk_eight_from_pack(prompt)

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", stub_writer)
    monkeypatch.setattr(
        "onecrew.script_writer.generate_script",
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("live path is ADK writer, not generate_script")),
    )
    written = write_vo_from_pack(packet)
    assert writer_prompts, "ADK script_writer must run on the pack"
    assert any("41,000" in p or "USREC" in p for p in writer_prompts)
    assert written.script
    assert len(written.beats) == 8
    spoken = written.script + "".join(b.vo for b in written.beats)
    assert "41,000" in spoken or "41k" in spoken.lower()
    assert "−23k" not in spoken and "-23k" not in spoken


def test_empty_pack_skips_adk_writer_fail_closed(monkeypatch) -> None:
    packet = Packet(
        id="oc-empty-adk-pack",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="should clear",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read",
        tone="On the cited print",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="empty pack",
        findings=[],
    )
    called = {"n": 0}

    def stub_writer(_prompt: str) -> str:
        called["n"] += 1
        return _adk_eight_from_pack(_prompt)

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", stub_writer)
    write_vo_from_pack(packet)
    assert called["n"] == 0
    assert packet.script == ""
    assert packet.beats == []
    assert packet.status == "hold"


def test_grade_room_invokes_adk_room_not_always_ship(monkeypatch) -> None:
    artifact = GradeArtifact(
        packet_id="oc-adk-room",
        research_pack_summary="thin pack",
        script="draft VO",
    )
    monkeypatch.setattr(
        "onecrew.room.run_adk_room",
        lambda _a: RoomGrade(
            vote="recut",
            recut_reason="not_enough_information",
            recut_detail="need first trigger cite",
        ),
    )
    grade = grade_room(artifact)
    assert grade.vote == "recut"
    assert grade.recut_reason == "not_enough_information"


def test_stub_adk_reviewer_recut_not_enough_information_one_parallel_then_rewrite(
    monkeypatch,
) -> None:
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    research_calls = {"n": 0}
    writer_calls = {"n": 0}
    grades = iter(
        [
            RoomGrade(
                vote="recut",
                recut_reason="not_enough_information",
                recut_detail="need first trigger cite",
            ),
            RoomGrade(vote="ship"),
        ]
    )

    def research(packet, rails, depth, **_k):
        research_calls["n"] += 1
        packet.research_pack = _HOLD_PACK
        packet.task_spine = _HOLD_PACK
        return (
            Receipt(
                packet_id=packet.id,
                written=False,
                disposition="READY",
                findings=_hold_findings(),
                causal_links=[],
            ),
            [],
            [FRED, BLS_OLD],
            _HOLD_PACK,
        )

    def stub_writer(prompt: str) -> str:
        writer_calls["n"] += 1
        return _adk_eight_from_pack(prompt)

    def tracking_vo(packet):
        return real_write_vo(packet)

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", tracking_vo)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", stub_writer)
    monkeypatch.setattr("onecrew.room.run_adk_room", lambda _a: next(grades))
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    shift = open_shift(
        "Are we near recession?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Are we near recession?",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=False)
    packet = run_live_packet(shift)
    assert research_calls["n"] == 2, "recut not_enough_information must run one extra Parallel loop"
    assert writer_calls["n"] == 2, "rewrite must run ADK writer after the extra Parallel loop"
    assert packet.script
    assert packet.room_grade is not None
    assert packet.room_grade.vote == "ship"
    assert packet.parallel_research_loops == 2


def test_stub_adk_reviewer_ship_reaches_board(monkeypatch) -> None:
    from onecrew.agent.shift import _board as real_board
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    board_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = _HOLD_PACK
        packet.task_spine = _HOLD_PACK
        return (
            Receipt(
                packet_id=packet.id,
                written=False,
                disposition="READY",
                findings=_hold_findings(),
                causal_links=[],
            ),
            [],
            [FRED, BLS_OLD],
            _HOLD_PACK,
        )

    def tracking_board(packet, rails):
        board_calls["n"] += 1
        return real_board(packet, rails)

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", real_write_vo)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", _adk_eight_from_pack)
    monkeypatch.setattr("onecrew.room.run_adk_room", lambda _a: RoomGrade(vote="ship"))
    monkeypatch.setattr("onecrew.agent.shift._board", tracking_board)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    shift = open_shift(
        "Are we near recession?",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read of the last year of US recession prints",
        tone="On the cited print",
        topic="Are we near recession?",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=True)
    packet = run_live_packet(shift)
    assert packet.script
    assert packet.room_grade is not None
    assert packet.room_grade.vote == "ship"
    assert board_calls["n"] >= 1
    assert packet.frames is not None


def test_parse_room_grade_coerces_pipe_enum() -> None:
    from onecrew.agent.adk_run import parse_room_grade

    shipped = parse_room_grade('{"vote":"ship"}')
    assert shipped.vote == "ship"
    recut = parse_room_grade(
        '{"vote":"recut","recut_reason":"not_enough_information","recut_detail":"need cite"}'
    )
    assert recut.recut_reason == "not_enough_information"
    piped = parse_room_grade(
        '{"vote":"recut","recut_reason":"not_enough_information|other","recut_detail":"muddy"}'
    )
    assert piped.vote == "recut"
    assert piped.recut_reason == "other"
    assert "not_enough_information|other" in piped.recut_detail


def test_adk_writer_prompt_sends_pack_and_picks(monkeypatch) -> None:
    packet = _hold_packet(disposition="READY")
    prompts: list[str] = []

    def stub_writer(prompt: str) -> str:
        prompts.append(prompt)
        return _adk_eight_from_pack(prompt)

    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", stub_writer)
    write_vo_from_pack(packet)
    assert prompts
    joined = " ".join(prompts)
    assert "Pack text is the authority" in joined
    assert '"platform"' in joined
    assert packet.platform and packet.platform in joined
    assert (packet.research_pack or "")[:20] in joined


def test_critic_instruction_does_not_skip_writer() -> None:
    from onecrew.agent.adk_agents import CRITIC_INSTRUCTION

    assert "skip the writer" not in CRITIC_INSTRUCTION.lower()
    assert "writer" in CRITIC_INSTRUCTION.lower()
    assert "HOLD" in CRITIC_INSTRUCTION


def test_floor_and_api_signal_deeper_history_vs_default() -> None:
    assert 'id="deeper_history"' in FLOOR_HTML
    assert "deeper history" in FLOOR_HTML.lower()
    assert "first trigger" in FLOOR_HTML.lower() or "recent news" in FLOOR_HTML.lower()
    assert 'id="deeper_history"' in FLOOR_HTML
    idx = FLOOR_HTML.find('id="deeper_history"')
    nearby = FLOOR_HTML[max(0, idx - 80) : idx + 120]
    assert "checked" not in nearby
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        body = health.json()
        horizon = body["research_horizon"]
        assert horizon["default"] == HORIZON_RECENT
        assert horizon["deeper"] == HORIZON_DEEPER
        assert horizon["depth_enum_forwards_to_parallel"] is False
        assert horizon["flag"] == "deeper_history"
        page = client.get("/")
        assert page.status_code == 200
        assert 'id="deeper_history"' in page.text
        assert "deeper_history" in page.text
