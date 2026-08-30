from types import SimpleNamespace

from onecrew.agent.shift import _apply_extract, _spine_from_task, lift_findings
from onecrew.board import _footage_query, prefer_footage
from onecrew.models import Finding, Packet, Rails, Receipt
from onecrew.pack import facts_from_spine, render_task_content, write_research_pack
from onecrew.receipt import write_receipt
from onecrew.script import assemble_script, draft_model_script, write_script


TASK_DICT = {
    "executive_summary": (
        "- **Current Status**: The latest NBER-based FRED reading is **0** for July 2026. "
        "-> Do not describe the United States as being in a recorded recession.\n"
        "- **Labor-Market Warning**: July 2026 payrolls fell **23,000** and unemployment was **4.1%**."
    ),
    "scope_and_working_thesis": (
        "Working thesis: the sourced evidence does not support a current-recession call."
    ),
}


def _task_result(content):
    return SimpleNamespace(
        output=SimpleNamespace(
            content=content,
            basis=[
                SimpleNamespace(
                    field="executive_summary",
                    citations=[SimpleNamespace(url="https://fred.stlouisfed.org/series/USREC")],
                )
            ],
        )
    )


def test_task_dict_spine_is_readable_prose() -> None:
    spine = _spine_from_task(_task_result(TASK_DICT))
    assert "{'executive_summary'" not in spine
    assert "### Executive summary" in spine
    assert "NBER-based FRED reading is 0" in spine or "NBER-based FRED reading is **0**" in spine or "FRED reading is 0" in spine
    assert "[executive_summary[0]]" not in spine
    assert "https://fred.stlouisfed.org/series/USREC" in spine


def test_facts_from_spine_lifts_nber_and_payrolls() -> None:
    spine = render_task_content(TASK_DICT)
    facts = facts_from_spine(spine)
    blob = " ".join(f["claim"] for f in facts)
    assert "NBER" in blob or "FRED" in blob or "USREC" in blob or "0" in blob
    assert "23,000" in blob or "23000" in blob or "23,000" in spine


def test_template_claims_replaced_by_task_facts() -> None:
    findings = [
        Finding(
            id="timeline-hit",
            claim="Grounded event inside 2-3y: Are we near recession?",
            stamp="grounded",
            parallel_url="https://news.harvard.edu/gazette/story/2026/08/are-we-headed-toward-recession-unpredictable/",
            parallel_status="hit",
            title="Are we headed toward recession? Unpredictable. — Harvard Gazette",
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
    spine = _spine_from_task(_task_result(TASK_DICT))
    lift_findings(
        findings,
        spine=spine,
        hit_title="Are we headed toward recession? Unpredictable. — Harvard Gazette",
        miss_title="2026 Strait of Hormuz crisis - Wikipedia",
        topic="Are we near recession?",
    )
    assert not findings[0].claim.startswith("Grounded event inside")
    assert "recession" in findings[0].claim.lower() or "NBER" in findings[0].claim or "payroll" in findings[0].claim.lower() or "FRED" in findings[0].claim
    assert "Hormuz" not in findings[2].claim
    assert not findings[2].claim.startswith("Fringe claim about")


def test_episode_script_is_recordable_and_speaks_the_prints(monkeypatch) -> None:
    packet = Packet(
        id="oc-recession-live",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Centered news desk, host only",
        tone="Make the viewer think",
    )
    findings = [
        Finding(
            id="timeline-hit",
            claim="Grounded event inside 2-3y: Are we near recession?",
            stamp="grounded",
            parallel_url="https://fred.stlouisfed.org/series/USREC",
            parallel_status="hit",
            title="USREC",
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
    spine = _spine_from_task(_task_result(TASK_DICT))
    lift_findings(
        findings,
        spine=spine,
        hit_title="USREC",
        miss_title="2026 Strait of Hormuz crisis - Wikipedia",
        topic=packet.topic,
    )
    packet.task_spine = spine
    write_receipt(
        packet,
        Receipt(packet_id=packet.id, written=False, findings=findings, disposition="READY"),
    )
    write_research_pack(packet)
    monkeypatch.setattr(
        "onecrew.script.generate_script",
        lambda prompt: (
            '{"beats":[{"finding_id":"timeline-hit","vo":"Host at a map table. '
            'Gulf chart on the wall. Grounded event inside 2-3y.","visual":'
            '"Photoreal B-roll of the cited beat","scene":"STUDIO","kind":"vo"}]}'
        ),
    )
    write_script(packet)
    assert packet.status == "ready"
    assert packet.script.strip()
    low = packet.script.lower()
    assert "gulf chart" not in low
    assert "photoreal" not in low
    assert "grounded event inside" not in low
    assert "fringe claim about" not in low
    assert "nber" in low or "usrec" in low or "payroll" in low or "23,000" in packet.script or "23k" in low or "fred" in low
    total = sum(b.duration_s for b in packet.beats)
    assert total <= 8 * 60
    assert "{'executive_summary'" not in (packet.research_pack or "")
    card = packet.desk_card or ""
    pack = packet.research_pack or ""
    assert pack.index("## Desk card") < pack.index("## Question")
    assert "You can say" in card
    assert "Do not say" in card
    assert "Cite" in card
    assert "Tape is not a license" in card
    assert "Collision is not a clearance" in card
    assert "NBER" in card or "FRED" in card or "USREC" in card
    assert "23,000" in card or "23000" in card or "payroll" in card.lower()
    assert "Do not invent a family" in card
    assert "Sit with this before you move on" not in packet.script
    assert "I'm staying on that" not in packet.script
    assert packet.script.lower().count("sit with this") <= 1


def test_hormuz_only_in_exclusions_does_not_unlock_gulf_footage() -> None:
    packet = Packet(
        id="oc-recession-nber",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="x",
        tell="Centered news desk, host only",
        cut="one_time_short_episode",
        research_pack="Left out: 2026 Strait of Hormuz crisis. reason=other.",
    )
    packet.receipt = Receipt(packet_id=packet.id, written=True, disposition="READY", findings=[])
    q = _footage_query("Host at a map table. Gulf chart on the wall. Grounded in the record.", packet)
    assert "gulf" not in q.lower()
    assert "grounded" not in q.lower()


def test_footage_rejects_game_and_gulf_mexico_map(monkeypatch) -> None:
    from onecrew.models import ShotFrame

    rows = [
        SimpleNamespace(url="https://grounded.obsidian.net/", title="Grounded"),
        SimpleNamespace(url="https://www.mapshop.com/gulf-of-mexico-wall-map/", title="Gulf of Mexico Wall Map"),
        SimpleNamespace(url="https://fred.stlouisfed.org/series/USREC", title="USREC"),
    ]
    monkeypatch.setattr(
        "onecrew.board.search",
        lambda **_k: SimpleNamespace(results=rows),
    )
    packet = Packet(
        id="oc-recession-nber",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="vo",
        cut="one_time_short_episode",
        tell="Centered news desk, host only",
    )
    shots = [
        ShotFrame(
            id="shot-001",
            shot="Host at the desk. Infographic: USREC=0.",
            beat_id="timeline-hit",
            duration_s=8,
            line="USREC=0",
        )
    ]
    prefer_footage(shots, Rails(parallel=True, vertex=True, imagen=False), packet)
    assert shots[0].footage == "sourced"
    assert shots[0].footage_url == "https://fred.stlouisfed.org/series/USREC"
    assert "obsidian" not in (shots[0].footage_url or "")
    assert "gulf-of-mexico" not in (shots[0].footage_url or "")


def test_extract_skips_nav_html() -> None:
    finding = Finding(
        id="timeline-hit",
        claim="July 2026 payrolls fell 23,000.",
        stamp="grounded",
        parallel_url="https://news.harvard.edu/x",
        parallel_status="hit",
        note="Parallel URL on this row.",
    )
    leftover = _apply_extract(
        [finding],
        SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://news.harvard.edu/x",
                    title="Are we headed toward recession?",
                    excerpts=[
                        "# Featured series\n## Read the latest\n* Search Search\n  Search the Harvard Gazette",
                        "July payrolls fell 23,000 and the unemployment rate was 4.1 percent, BLS said.",
                    ],
                )
            ],
            errors=[],
        ),
    )
    assert leftover == []
    assert "Search Search" not in finding.note
    assert "23,000" in finding.note


def test_hold_desk_card_says_do_not_record() -> None:
    packet = Packet(
        id="oc-recession-hold",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        tell="Centered news desk, host only",
        tone="Make the viewer think",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="HOLD",
        hold_reason="Vertex down. No leftover Hormuz VO.",
        findings=[],
    )
    write_research_pack(packet)
    assert "Do not record" in packet.desk_card
    assert "HOLD" in packet.desk_card
    assert packet.research_pack.index("## Desk card") < packet.research_pack.index("## Question")


def test_collision_title_is_do_not_copy(monkeypatch) -> None:
    from onecrew.collision import stamp_collisions
    from onecrew.models import Rails, ScriptBeat

    packet = Packet(
        id="oc-recession-hit",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="vo",
        cut="one_time_short_episode",
        tell="Centered news desk, host only",
        tone="Make the viewer think",
        beats=[
            ScriptBeat(
                id="timeline-hit",
                start="00:00:00",
                duration_s=8,
                vo="The latest NBER-based FRED reading is 0 for July 2026. [timeline-hit]",
                finding_ids=["timeline-hit"],
            )
        ],
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=True,
        disposition="READY",
        findings=[
            Finding(
                id="timeline-hit",
                claim="The latest NBER-based FRED reading is 0 for July 2026.",
                stamp="grounded",
                parallel_url="https://fred.stlouisfed.org/series/USREC",
                parallel_status="hit",
                note="Parallel URL on this row.",
            )
        ],
    )
    monkeypatch.setattr(
        "onecrew.collision.search",
        lambda **_k: SimpleNamespace(
            results=[
                SimpleNamespace(
                    url="https://www.youtube.com/watch?v=recession-desk",
                    title="Are We Near Recession? Nightly Desk",
                )
            ]
        ),
    )
    stamp_collisions(packet, Rails(parallel=True, vertex=True, imagen=False))
    write_research_pack(packet)
    assert "Do not copy this title on air" in packet.desk_card
    assert "Are We Near Recession? Nightly Desk" in packet.desk_card
    assert "Collision is not a clearance" in packet.desk_card
