"""Locked pipeline: Parallel researches, Vertex writes VO, room grades, one extra loop max."""

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
