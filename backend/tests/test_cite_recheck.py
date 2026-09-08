"""Parallel cite re-check loop. Missing cite_url is repaired or dropped, not a FAIL."""

from __future__ import annotations

from types import SimpleNamespace

from onecrew.board import write_shot_list
from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, ScriptBeat, ShotFrame
from onecrew.verify import (
    Claim,
    apply_verify_gate,
    claims_from_findings,
    verify_claim_set,
    verify_print_in_cite,
)

FRED = "https://fred.stlouisfed.org/series/USREC"
BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
_JULY_PIPE = "2026-05-01 | 0\n2026-06-01 | 0\n2026-07-01 | 0\n"
_JULY_CES = (
    "THE EMPLOYMENT SITUATION -- JULY 2026\n"
    "Total nonfarm payroll employment fell by 23,000 in July 2026.\n"
)


def _finding(
    *,
    fid: str,
    series: str,
    printed: str,
    when: str,
    claim: str,
    url: str | None,
) -> Finding:
    return Finding(
        id=fid,
        claim=claim,
        stamp="grounded",
        title=series,
        series=series,
        print=printed,
        when=when,
        parallel_url=url,
        parallel_status="hit" if url else "miss",
        note="Parallel URL on this row." if url else "cite missing",
    )


def _beat(bid: str, finding_ids: list[str], vo: str, *, start: str = "00:00") -> ScriptBeat:
    return ScriptBeat(
        id=bid,
        start=start,
        duration_s=20,
        scene=f"BEAT — {bid}",
        kind="vo",
        vo=vo,
        finding_ids=finding_ids,
        frame=f"card {bid}",
    )


def _eight_packet(*, payrolls_url: str | None) -> Packet:
    usrec = _finding(
        fid="usrec-july-2026",
        series="USREC",
        printed="0",
        when="July 2026",
        claim="USREC=0 (July 2026)",
        url=FRED,
    )
    pay = _finding(
        fid="payrolls-july-2026",
        series="BLS payrolls",
        printed="−23,000",
        when="July 2026",
        claim="Total nonfarm payroll employment fell by 23,000 in July 2026.",
        url=payrolls_url,
    )
    ids = (
        "cold-open",
        "promise",
        "gdp",
        "labor",
        "turn",
        "complication",
        "receipt",
        "close",
    )
    cited = {
        "cold-open": ["usrec-july-2026", "payrolls-july-2026"],
        "promise": ["usrec-july-2026"],
        "gdp": ["usrec-july-2026"],
        "labor": ["payrolls-july-2026"],
        "turn": ["usrec-july-2026"],
        "complication": ["usrec-july-2026"],
        "receipt": ["usrec-july-2026", "payrolls-july-2026"],
        "close": ["usrec-july-2026"],
    }
    vos = {
        "cold-open": "NARRATOR\nUSREC=0 smashed into payrolls −23,000. [usrec-july-2026] [payrolls-july-2026]",
        "promise": "NARRATOR\nUSREC=0 is the flag. [usrec-july-2026]",
        "gdp": "NARRATOR\nUSREC=0 (July 2026). [usrec-july-2026]",
        "labor": "NARRATOR\nNonfarm payrolls fell −23,000. [payrolls-july-2026]",
        "turn": "NARRATOR\nHold on USREC=0. [usrec-july-2026]",
        "complication": "NARRATOR\nThose are not the same object. [usrec-july-2026]",
        "receipt": "NARRATOR\nReceipt: USREC=0 and −23,000. [usrec-july-2026] [payrolls-july-2026]",
        "close": "NARRATOR\nNear is not a switch. [usrec-july-2026]",
    }
    packet = Packet(
        id="oc-cite-recheck",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read",
        tone="On the cited print",
        research_pack="USREC July 2026 = 0. Nonfarm payrolls fell by 23,000 in July 2026.",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="READY",
        findings=[usrec, pay],
    )
    packet.beats = [
        _beat(bid, cited[bid], vos[bid], start=f"00:{i * 20:02d}") for i, bid in enumerate(ids)
    ]
    packet.script = "\n".join(b.scene + "\n" + b.vo for b in packet.beats) + "\n"
    packet.frames = [
        ShotFrame(id=f"shot-{b.id}", shot=b.frame or b.id, beat_id=b.id, duration_s=b.duration_s)
        for b in packet.beats
    ]
    return packet


def _supporting_search(*, objective, search_queries):
    blob = f"{objective} {' '.join(search_queries)}"
    if "payroll" in blob.lower() or "23" in blob:
        return SimpleNamespace(
            results=[
                SimpleNamespace(url=BLS, title="Employment Situation", excerpts=[_JULY_CES]),
            ]
        )
    return SimpleNamespace(
        results=[
            SimpleNamespace(url=FRED, title="USREC", excerpts=["USREC July 2026 = 0.", _JULY_PIPE]),
        ]
    )


def _empty_search(*, objective, search_queries):
    return SimpleNamespace(results=[])


def test_missing_cite_parallel_hit_attaches_url_keeps_beat() -> None:
    packet = _eight_packet(payrolls_url=None)
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _supporting_search(**kwargs)

    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "ReceiptInvalidError: grounded requires a Parallel URL on the row"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=search)
    assert result.ok is True
    assert calls["n"] >= 1
    assert calls["n"] <= MAX_CITE_RECHECKS
    pay = next(f for f in packet.receipt.findings if f.id == "payrolls-july-2026")
    assert pay.parallel_url == BLS
    assert pay.parallel_status == "hit"
    assert any(b.id == "labor" for b in packet.beats)
    assert "payrolls-july-2026" in " ".join(b.vo for b in packet.beats)
    assert packet.receipt.disposition == "READY"
    assert packet.status == "ready"
    assert "grounded requires a Parallel URL" not in (packet.receipt.hold_reason or "")
    shots = write_shot_list(packet)
    assert any(s.beat_id == "labor" for s in shots)


def test_missing_cite_parallel_miss_drops_beat_and_ships() -> None:
    packet = _eight_packet(payrolls_url=None)
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _empty_search(**kwargs)

    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "ReceiptInvalidError: grounded requires a Parallel URL on the row"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=search)
    assert result.ok is True
    assert calls["n"] >= 1
    assert calls["n"] <= MAX_CITE_RECHECKS
    assert not any(b.id == "labor" for b in packet.beats)
    spoken = (packet.script or "") + "\n".join(b.vo for b in packet.beats)
    assert "payrolls-july-2026" not in spoken
    assert packet.beats
    assert packet.script.strip()
    assert packet.receipt.disposition == "READY"
    assert packet.status == "ready"
    pay = next(f for f in packet.receipt.findings if f.id == "payrolls-july-2026")
    assert pay.stamp != "grounded" or (pay.parallel_url or "").strip()
    assert not any(f.beat_id == "labor" for f in packet.frames)
    shots = write_shot_list(packet)
    assert shots
    assert not any(s.beat_id == "labor" for s in shots)
    assert any(s.beat_id == "close" for s in shots)


def test_cite_recheck_fourth_failure_holds_loop_exhausted() -> None:
    """After 3 Parallel re-checks, an undroppable missing cite is the 4th failure → HOLD."""
    finding = _finding(
        fid="usrec-july-2026",
        series="USREC",
        printed="0",
        when="July 2026",
        claim="USREC=0 (July 2026)",
        url=None,
    )
    packet = Packet(
        id="oc-cite-exhausted",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="NARRATOR\nUSREC=0 (July 2026). [usrec-july-2026]\n",
        platform="youtube",
        cut="one_time_short_episode",
        receipt=Receipt(
            packet_id="oc-cite-exhausted",
            written=False,
            disposition="READY",
            findings=[finding],
        ),
        beats=[
            _beat("cold-open", ["usrec-july-2026"], "NARRATOR\nUSREC=0 (July 2026). [usrec-july-2026]"),
        ],
    )
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _empty_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search)
    assert result.ok is False
    assert calls["n"] == MAX_CITE_RECHECKS
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert packet.receipt.hold_reason == "cite-repair loop exhausted"
    assert result.hold_reason == "cite-repair loop exhausted"
    assert packet.status == "hold"
    assert packet.script.strip(), "exhaust HOLD must not blank the script"
    assert packet.beats, "last spoken beat stays until a cite-faithful drop is possible"

    again = run_cite_recheck_loop(packet, search_fn=search)
    assert again.ok is False
    assert calls["n"] == MAX_CITE_RECHECKS
    assert "exhausted" in (again.hold_reason or "").lower()


def test_cite_url_not_in_hits_is_soft_verify_not_hold() -> None:
    """Critic still names the miss. Gate does not HOLD solely for cite_url not in hits."""
    from onecrew.verify import CiteBag, CiteExcerpt

    bag = CiteBag(
        excerpts=[
            CiteExcerpt(url=FRED, title="USREC", text=_JULY_PIPE),
            CiteExcerpt(url=BLS, title="Employment Situation", text=_JULY_CES),
        ],
        spine="USREC July 2026 = 0. Nonfarm payrolls −23k.",
        hit_urls=[FRED, BLS],
    )
    findings = [
        Finding(
            id="usrec-july-2026",
            claim="USREC=0 (July 2026)",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            when="July 2026",
            parallel_url="https://example.com/not-in-hits",
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    gated = apply_verify_gate(
        Receipt(packet_id="oc-named-miss", written=False, disposition="READY", findings=findings),
        bag,
    )
    assert gated.disposition == "READY"
    assert "cite_url not in hits" not in (gated.hold_reason or "")
    checked = verify_claim_set(claims_from_findings(gated.findings), bag)
    assert "cite_url not in hits" in checked.hold_reasons
    orphan = Claim(
        series="USREC",
        print="0",
        when="July 2026",
        id="usrec-july-2026",
        cite_url="https://example.com/not-in-hits",
    )
    assert verify_print_in_cite(orphan, bag).reason == "cite_url not in hits"


def test_live_shift_runs_cite_recheck_after_writer_before_board(monkeypatch) -> None:
    from onecrew.agent.shift import _board as real_board
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.cite_repair import run_cite_recheck_loop as real_repair
    from onecrew.models import Rails
    from onecrew.room import RoomGrade
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    board_calls = {"n": 0}
    repair_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = "USREC July 2026 = 0. Payrolls fell 23,000 in July 2026."
        packet.task_spine = packet.research_pack
        return (
            Receipt(
                packet_id=packet.id,
                written=False,
                disposition="READY",
                findings=[
                    _finding(
                        fid="usrec-july-2026",
                        series="USREC",
                        printed="0",
                        when="July 2026",
                        claim="USREC=0 (July 2026)",
                        url=FRED,
                    ),
                    _finding(
                        fid="payrolls-july-2026",
                        series="BLS payrolls",
                        printed="−23,000",
                        when="July 2026",
                        claim="Total nonfarm payroll employment fell by 23,000 in July 2026.",
                        url=None,
                    ),
                ],
                causal_links=[],
            ),
            [],
            [FRED],
            packet.research_pack,
        )

    def tracking_repair(packet, **kwargs):
        repair_calls["n"] += 1
        kwargs.setdefault("search_fn", _supporting_search)
        return real_repair(packet, **kwargs)

    def tracking_board(packet, rails):
        board_calls["n"] += 1
        pay = next(f for f in (packet.receipt.findings if packet.receipt else []) if "payroll" in f.id)
        assert (pay.parallel_url or "").startswith("http")
        return real_board(packet, rails)

    eight = (
        '[{"id":"cold-open","vo":"USREC=0 smashed into payrolls −23,000. [usrec-july-2026] [payrolls-july-2026]",'
        '"eyes":"July","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"promise","vo":"USREC=0. [usrec-july-2026]","eyes":"flag","finding_ids":["usrec-july-2026"]},'
        '{"id":"gdp","vo":"USREC=0 (July 2026). [usrec-july-2026]","eyes":"usrec","finding_ids":["usrec-july-2026"]},'
        '{"id":"labor","vo":"Nonfarm payrolls fell −23,000. [payrolls-july-2026]","eyes":"ces","finding_ids":["payrolls-july-2026"]},'
        '{"id":"turn","vo":"Hold on USREC=0. [usrec-july-2026]","eyes":"hold","finding_ids":["usrec-july-2026"]},'
        '{"id":"complication","vo":"Not the same object. [usrec-july-2026]","eyes":"gap","finding_ids":["usrec-july-2026"]},'
        '{"id":"receipt","vo":"USREC=0 and −23,000. [usrec-july-2026] [payrolls-july-2026]","eyes":"board","finding_ids":["usrec-july-2026","payrolls-july-2026"]},'
        '{"id":"close","vo":"Near is not a switch. [usrec-july-2026]","eyes":"close","finding_ids":["usrec-july-2026"]}]'
    )

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.run_cite_recheck_loop", tracking_repair)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", real_write_vo)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", lambda _p: eight)
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
    shift.rails = Rails(parallel=True, vertex=True, imagen=False)
    packet = run_live_packet(shift)
    assert repair_calls["n"] >= 1
    assert board_calls["n"] >= 1
    pay = next(f for f in packet.receipt.findings if f.id == "payrolls-july-2026")
    assert pay.parallel_url == BLS
    assert "grounded requires a Parallel URL" not in (packet.receipt.hold_reason or "")
    assert "cite-repair loop exhausted" not in (packet.receipt.hold_reason or "")
    assert packet.script
    assert packet.frames
