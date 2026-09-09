"""Parallel cite re-check loop. Missing cite_url is repaired or dropped, not a FAIL."""

from __future__ import annotations

import re
from types import SimpleNamespace

from onecrew.board import write_shot_list
from onecrew.cite_repair import MAX_CITE_RECHECKS, run_cite_recheck_loop
from onecrew.models import Finding, Packet, Receipt, ScriptBeat, ShotFrame
from onecrew.verify import (
    Claim,
    CiteBag,
    CiteExcerpt,
    apply_verify_gate,
    claims_from_findings,
    verify_claim_set,
    verify_print_in_cite,
)

FRED = "https://fred.stlouisfed.org/series/USREC"
BLS = "https://www.bls.gov/news.release/empsit.nr0.htm"
FRED_SAHM = "https://fred.stlouisfed.org/series/SAHMREALTIME"
LEI_URL = "https://www.conference-board.org/topics/us-leading-indicators"
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


def _print_miss_bag() -> CiteBag:
    """USREC is backed. Payrolls URL is in hits, but the excerpt has no −23,000 / July."""
    return CiteBag(
        excerpts=[
            CiteExcerpt(url=FRED, title="USREC", text="USREC July 2026 = 0.\n" + _JULY_PIPE),
            CiteExcerpt(
                url=BLS,
                title="Employment Situation",
                text="THE EMPLOYMENT SITUATION -- a release with no July payroll print.",
            ),
        ],
        spine="USREC July 2026 = 0.",
        hit_urls=[FRED, BLS],
    )


def test_print_not_in_cite_parallel_miss_drops_beat_no_fail() -> None:
    packet = _eight_packet(payrolls_url=BLS)
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "print not in cite; when not in cite"
    packet.status = "hold"
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _empty_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search, bag=_print_miss_bag())
    assert result.ok is True
    assert calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    assert not any(b.id == "labor" for b in packet.beats)
    assert {"promise", "gdp", "close"} <= {b.id for b in packet.beats}
    spoken = (packet.script or "") + "\n".join(b.vo for b in packet.beats)
    assert "payrolls-july-2026" not in spoken
    assert packet.beats
    assert packet.script.strip()
    assert packet.receipt.disposition == "READY"
    assert packet.status == "ready"
    assert "print not in cite" not in (packet.receipt.hold_reason or "")
    assert "when not in cite" not in (packet.receipt.hold_reason or "")
    assert "cite-repair loop exhausted" not in (packet.receipt.hold_reason or "")
    assert not any(f.beat_id == "labor" for f in packet.frames)
    shots = write_shot_list(packet)
    assert shots
    assert not any(s.beat_id == "labor" for s in shots)
    starts = [b.start for b in packet.beats if (b.kind or "vo") != "heading"]
    assert starts
    assert starts[0] in {"00:00", "00:00:00"}
    assert starts == sorted(starts)
    assert len(set(starts)) == len(starts)


def test_when_not_in_cite_parallel_miss_drops_beat_no_fail() -> None:
    packet = _eight_packet(payrolls_url=BLS)
    bag = CiteBag(
        excerpts=[
            CiteExcerpt(url=FRED, title="USREC", text="USREC July 2026 = 0.\n" + _JULY_PIPE),
            CiteExcerpt(
                url=BLS,
                title="Employment Situation",
                text=(
                    "THE EMPLOYMENT SITUATION -- JUNE 2024\n"
                    "Total nonfarm payroll employment fell by 23,000 in June 2024.\n"
                ),
            ),
        ],
        spine="USREC flag remains 0.",
        hit_urls=[FRED, BLS],
    )
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "when not in cite"
    packet.status = "hold"
    result = run_cite_recheck_loop(packet, search_fn=_empty_search, bag=bag)
    assert result.ok is True
    assert packet.cite_recheck_attempts >= 1
    assert not any(b.id == "labor" for b in packet.beats)
    assert packet.receipt.disposition == "READY"
    assert "when not in cite" not in (packet.receipt.hold_reason or "")


def test_print_not_in_cite_parallel_hit_keeps_beat_fixes_url() -> None:
    stale = "https://example.com/stale-ces"
    packet = _eight_packet(payrolls_url=stale)
    bag = CiteBag(
        excerpts=[
            CiteExcerpt(url=FRED, title="USREC", text="USREC July 2026 = 0.\n" + _JULY_PIPE),
            CiteExcerpt(url=stale, title="Stale CES", text="No payroll print on this hit."),
        ],
        spine="USREC July 2026 = 0.",
        hit_urls=[FRED, stale],
    )
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "print not in cite"
    packet.status = "hold"
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _supporting_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search, bag=bag)
    assert result.ok is True
    assert calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    pay = next(f for f in packet.receipt.findings if f.id == "payrolls-july-2026")
    assert pay.parallel_url == BLS
    assert pay.parallel_status == "hit"
    kept = {b.id for b in packet.beats}
    assert {"labor", "promise", "gdp", "close"} <= kept
    assert "payrolls-july-2026" in " ".join(b.vo for b in packet.beats)
    usrec = next(f for f in packet.receipt.findings if f.id == "usrec-july-2026")
    assert usrec.parallel_url == FRED
    assert packet.receipt.disposition == "READY"
    assert packet.status == "ready"
    assert "print not in cite" not in (packet.receipt.hold_reason or "")
    shots = write_shot_list(packet)
    assert any(s.beat_id == "labor" for s in shots)
    assert any(s.beat_id == "close" for s in shots)


def test_print_not_in_cite_existing_bag_hit_relinks_without_requery() -> None:
    stale = "https://example.com/stale-ces"
    packet = _eight_packet(payrolls_url=stale)
    bag = CiteBag(
        excerpts=[
            CiteExcerpt(url=FRED, title="USREC", text="USREC July 2026 = 0.\n" + _JULY_PIPE),
            CiteExcerpt(url=stale, title="Stale CES", text="No payroll print on this hit."),
            CiteExcerpt(url=BLS, title="Employment Situation", text=_JULY_CES),
        ],
        spine="USREC July 2026 = 0.",
        hit_urls=[FRED, stale, BLS],
    )
    packet.receipt.disposition = "HOLD"
    packet.receipt.hold_reason = "print not in cite"
    packet.status = "hold"
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _supporting_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search, bag=bag)
    assert result.ok is True
    assert calls["n"] == 0
    assert packet.cite_recheck_attempts == 0
    pay = next(f for f in packet.receipt.findings if f.id == "payrolls-july-2026")
    assert pay.parallel_url == BLS
    assert {"labor", "promise", "gdp", "close"} <= {b.id for b in packet.beats}
    assert packet.receipt.disposition == "READY"


def test_print_not_in_cite_fourth_failure_holds_loop_exhausted() -> None:
    finding = _finding(
        fid="usrec-july-2026",
        series="USREC",
        printed="0",
        when="July 2026",
        claim="USREC=0 (July 2026)",
        url=FRED,
    )
    packet = Packet(
        id="oc-cite-print-exhausted",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="NARRATOR\nUSREC=0 (July 2026). [usrec-july-2026]\n",
        platform="youtube",
        cut="one_time_short_episode",
        receipt=Receipt(
            packet_id="oc-cite-print-exhausted",
            written=False,
            disposition="HOLD",
            hold_reason="print not in cite; when not in cite",
            findings=[finding],
        ),
        beats=[
            _beat("cold-open", ["usrec-july-2026"], "NARRATOR\nUSREC=0 (July 2026). [usrec-july-2026]"),
        ],
        status="hold",
    )
    bag = CiteBag(
        excerpts=[CiteExcerpt(url=FRED, title="USREC", text="FRED series page. No July 2026 flag.")],
        spine="",
        hit_urls=[FRED],
    )
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _empty_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search, bag=bag)
    assert result.ok is False
    assert calls["n"] == MAX_CITE_RECHECKS
    assert packet.cite_recheck_attempts == MAX_CITE_RECHECKS
    assert packet.receipt is not None
    assert packet.receipt.disposition == "HOLD"
    assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")
    assert result.hold_reason == "cite-repair loop exhausted"
    assert packet.status == "hold"
    assert packet.script.strip()
    assert packet.beats

    again = run_cite_recheck_loop(packet, search_fn=search, bag=bag)
    assert again.ok is False
    assert calls["n"] == MAX_CITE_RECHECKS
    assert "exhausted" in (again.hold_reason or "").lower()


def test_print_when_not_in_cite_is_soft_verify_not_hold() -> None:
    """Critic still names print/when misses. Gate does not HOLD solely for them."""
    bag = CiteBag(
        excerpts=[CiteExcerpt(url=FRED, title="USREC", text="FRED series page. No July flag token.")],
        spine="",
        hit_urls=[FRED],
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
            parallel_url=FRED,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
    ]
    gated = apply_verify_gate(
        Receipt(packet_id="oc-print-soft", written=False, disposition="READY", findings=findings),
        bag,
    )
    assert gated.disposition == "READY"
    assert "print not in cite" not in (gated.hold_reason or "")
    assert "when not in cite" not in (gated.hold_reason or "")
    checked = verify_claim_set(claims_from_findings(gated.findings), bag)
    assert "print not in cite" in checked.hold_reasons or "when not in cite" in checked.hold_reasons


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


def test_live_shift_cite_recheck_on_print_not_in_cite(monkeypatch) -> None:
    """Spoken beat with a URL still enters the loop when print/when are not in the hit."""
    from onecrew.agent.shift import _board as real_board
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.cite_repair import run_cite_recheck_loop as real_repair
    from onecrew.models import Rails
    from onecrew.room import RoomGrade
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    board_calls = {"n": 0}
    repair_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = "USREC July 2026 = 0."
        packet.task_spine = packet.research_pack
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="HOLD",
            hold_reason="print not in cite; when not in cite",
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
                    url=BLS,
                ),
            ],
            causal_links=[],
        )
        object.__setattr__(packet, "_cite_bag", _print_miss_bag())
        return receipt, [], [FRED, BLS], packet.research_pack

    def tracking_repair(packet, **kwargs):
        repair_calls["n"] += 1
        kwargs.setdefault("search_fn", _empty_search)
        return real_repair(packet, **kwargs)

    def tracking_board(packet, rails):
        board_calls["n"] += 1
        assert not any(b.id == "labor" for b in packet.beats)
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
    assert packet.cite_recheck_attempts >= 1
    assert not any(b.id == "labor" for b in packet.beats)
    assert packet.receipt.disposition == "READY"
    assert packet.status == "ready"
    assert "cite-repair loop exhausted" not in (packet.receipt.hold_reason or "")
    assert board_calls["n"] >= 1
    assert packet.script
    assert packet.frames


def _lei_sahm_packet() -> Packet:
    lei = _finding(
        fid="lei-june-2026",
        series="LEI",
        printed="-4.3%",
        when="June 2026",
        claim=(
            "The Conference Board 3Ds recession signal requires a six-month "
            "LEI growth rate below −4.3%."
        ),
        url=FRED_SAHM,
    )
    usrec = _finding(
        fid="usrec-july-2026",
        series="USREC",
        printed="0",
        when="July 2026",
        claim="USREC=0 (July 2026)",
        url=FRED,
    )
    packet = Packet(
        id="oc-lei-sahm-cite",
        topic="Are we near recession?",
        hook="Are we near recession?",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="decade",
        script_lean="centered_independent",
        tell="Host-only desk read",
        tone="On the cited print",
        research_pack=(
            "USREC July 2026 = 0. June 2026 notes: six-month LEI growth "
            "rate below −4.3% is the 3Ds signal threshold."
        ),
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason="print not in cite",
        findings=[usrec, lei],
    )
    packet.status = "hold"
    packet.beats = [
        _beat("cold-open", ["usrec-july-2026"], "NARRATOR\nUSREC=0. [usrec-july-2026]"),
        _beat(
            "turn",
            ["lei-june-2026"],
            "NARRATOR\nLEI −4.3%. [lei-june-2026]",
            start="00:20",
        ),
        _beat("close", ["usrec-july-2026"], "NARRATOR\nNear is not a switch. [usrec-july-2026]", start="00:40"),
    ]
    packet.script = "\n".join(b.scene + "\n" + b.vo for b in packet.beats) + "\n"
    packet.frames = [
        ShotFrame(id=f"shot-{b.id}", shot=b.frame or b.id, beat_id=b.id, duration_s=b.duration_s)
        for b in packet.beats
    ]
    return packet


def _lei_sahm_bag() -> CiteBag:
    return CiteBag(
        excerpts=[
            CiteExcerpt(url=FRED, title="USREC", text="USREC July 2026 = 0.\n" + _JULY_PIPE),
            CiteExcerpt(
                url=FRED_SAHM,
                title="SAHMREALTIME",
                text=(
                    "Sahm June 2026 = −0.03 vs 0.50 trigger. "
                    "The Conference Board 3Ds recession signal requires a "
                    "six-month LEI growth rate below −4.3%."
                ),
            ),
        ],
        spine=(
            "June 2026 notes: six-month LEI growth rate below −4.3% is the "
            "3Ds signal threshold."
        ),
        hit_urls=[FRED, FRED_SAHM],
    )


def test_lei_sahm_url_requeries_or_drops_and_counts_attempt() -> None:
    packet = _lei_sahm_packet()
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return SimpleNamespace(
            results=[
                SimpleNamespace(
                    url=LEI_URL,
                    title="Conference Board LEI",
                    excerpts=["Conference Board LEI increased 0.2% in July 2026."],
                )
            ]
        )

    result = run_cite_recheck_loop(packet, search_fn=search, bag=_lei_sahm_bag())
    assert result.ok is True
    assert calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    lei = next(f for f in packet.receipt.findings if f.id == "lei-june-2026")
    cite = (lei.parallel_url or "").lower()
    spoken = (packet.script or "") + "\n".join(b.vo for b in packet.beats)
    if "lei-june-2026" in spoken:
        assert "sahm" not in cite
        assert "conference-board.org" in cite
        assert "4.3" not in (lei.print or "").replace("−", "-")
    else:
        assert not any(b.id == "turn" for b in packet.beats)
        assert "lei-june-2026" not in spoken
        assert lei.stamp != "grounded"
    assert packet.beats
    assert packet.script.strip()
    assert packet.receipt.disposition == "READY"
    assert "cite-repair loop exhausted" not in (packet.receipt.hold_reason or "")
    shots = write_shot_list(packet)
    assert shots
    assert any(s.beat_id == "close" for s in shots)


# Live HOLD oc-data-centers-are-going-to-cause-the--6228b564:
# beats cite nothing in the pack, cite_recheck_attempts stayed 0.
GUARDIAN = "https://www.theguardian.com/technology/2026/aug/data-centre-boom-bubble"
STARGATE_URL = "https://openai.com/index/stargate-announcement"
MSFT_URL = "https://www.microsoft.com/en-us/investor/lease-cancel"
_DC_PACK = (
    "Data centers are going to cause the next economic bubble. "
    "OpenAI Stargate is a $500B infrastructure build. "
    "Microsoft cancelled data-center leases in August 2026. "
    "The Guardian asked whether the boom is already a bubble."
)
_DC_STARGATE = (
    "OpenAI and partners announced Stargate, a $500B data-center build, in 2025."
)
_DC_MSFT = (
    "Microsoft cancelled data-center leases in August 2026 after demand slipped."
)
_DC_GUARD = (
    "The Guardian asked in August 2026 whether the data-center boom is already a bubble."
)


def _junk_ism() -> Finding:
    return Finding(
        id="ism-august-2026",
        claim="ISM print 4,",
        stamp="grounded",
        title="ISM",
        series="ISM",
        print="4,",
        when="August 2026",
        parallel_url=None,
        parallel_status="miss",
        note="cite missing",
    )


def _dc_empty_cite_packet() -> Packet:
    """Live shape: sourced VO, zero pack cites, junk ISM row, HOLD already named."""
    packet = Packet(
        id="oc-data-centers-are-going-to-cause-the--6228b564",
        topic="Data centers are going to cause the next economic bubble",
        hook="Data centers are going to cause the next economic bubble",
        script="placeholder",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited data-center prints",
        tone="On the cited print",
        research_pack=_DC_PACK,
        task_spine=_DC_PACK,
        status="hold",
    )
    packet.receipt = Receipt(
        packet_id=packet.id,
        written=False,
        disposition="HOLD",
        hold_reason=(
            "beat1 cites nothing in the pack; beat3 cites nothing in the pack; "
            "beat4 cites nothing in the pack; beat5 cites nothing in the pack; "
            "beat6 cites nothing in the pack; beat7 cites nothing in the pack"
        ),
        findings=[
            _junk_ism(),
            Finding(
                id="fringe-miss",
                claim="A fringe claim about hidden offtake contracts.",
                stamp="fringe",
                parallel_status="miss",
                note="Parallel miss. Included and tagged fringe. Never sold as fact.",
            ),
        ],
    )
    vos = {
        "cold-open": "NARRATOR\nOpenAI Stargate is a $500B build.",
        "promise": "NARRATOR\nThe title stays a question.",
        "gdp": "NARRATOR\nMicrosoft cancelled leases in August 2026.",
        "labor": "NARRATOR\nThe Guardian named a boom that may already be a bubble.",
        "turn": "NARRATOR\n$500B is the spoken capex print.",
        "complication": "NARRATOR\nLease cancels are not the same object as a boom.",
        "receipt": "NARRATOR\nReceipt: Stargate $500B and the August 2026 cancels.",
        "close": "NARRATOR\nNear is not a switch.",
    }
    empty = {bid: [] for bid in vos}
    packet.beats = [
        _beat(bid, empty[bid], vos[bid], start=f"00:{i * 20:02d}")
        for i, bid in enumerate(vos)
    ]
    packet.script = "\n".join(b.scene + "\n" + b.vo for b in packet.beats) + "\n"
    packet.frames = [
        ShotFrame(id=f"shot-{b.id}", shot=b.frame or b.id, beat_id=b.id, duration_s=b.duration_s)
        for b in packet.beats
    ]
    return packet


def _dc_supporting_search(*, objective, search_queries):
    blob = f"{objective} {' '.join(search_queries)}".lower()
    if "microsoft" in blob or "lease" in blob:
        return SimpleNamespace(
            results=[SimpleNamespace(url=MSFT_URL, title="Microsoft leases", excerpts=[_DC_MSFT])]
        )
    if "guardian" in blob or "bubble" in blob:
        return SimpleNamespace(
            results=[SimpleNamespace(url=GUARDIAN, title="Guardian boom", excerpts=[_DC_GUARD])]
        )
    return SimpleNamespace(
        results=[SimpleNamespace(url=STARGATE_URL, title="Stargate", excerpts=[_DC_STARGATE])]
    )


def test_empty_cite_beats_cannot_skip_cite_repair() -> None:
    """Forbidden wrap: skip cite-repair when beats have zero pack cites."""
    packet = _dc_empty_cite_packet()
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _dc_supporting_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search)
    assert calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    assert packet.cite_recheck_attempts <= MAX_CITE_RECHECKS
    sourced = [b for b in packet.beats if any(ch.isdigit() for ch in b.vo)]
    for beat in sourced:
        assert beat.finding_ids, f"{beat.id} shipped untagged factual VO"
        assert any(f"[{fid}]" in beat.vo for fid in beat.finding_ids)
    junk = next(f for f in packet.receipt.findings if f.id == "ism-august-2026")
    assert junk.stamp != "grounded" or (
        (junk.print or "") not in {"4,", "4"} and (junk.parallel_url or "").strip()
    )
    if result.ok:
        assert packet.receipt.disposition == "READY"
        assert "cites nothing in the pack" not in (packet.receipt.hold_reason or "")
    else:
        assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")


def test_empty_cite_parallel_miss_drops_beats_and_counts_attempt() -> None:
    packet = _dc_empty_cite_packet()
    calls = {"n": 0}

    def search(**kwargs):
        calls["n"] += 1
        return _empty_search(**kwargs)

    result = run_cite_recheck_loop(packet, search_fn=search)
    assert calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    sourced_left = [b for b in packet.beats if any(ch.isdigit() for ch in _vo_digits(b.vo))]
    if sourced_left:
        assert result.ok is False
        assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")
    else:
        assert result.ok is True
        assert packet.beats
        assert packet.script.strip()
        assert packet.receipt.disposition == "READY"
        assert "cites nothing in the pack" not in (packet.receipt.hold_reason or "")


def _vo_digits(vo: str) -> str:
    return "".join(ch for ch in vo if ch.isdigit() or ch == ",")


def test_writer_attaches_pack_finding_ids_on_sourced_beats() -> None:
    """ADK omitted tags. Writer must attach pack finding ids, not ship untagged VO."""
    from onecrew.script import _assemble

    url = STARGATE_URL
    finding = Finding(
        id="stargate-500b-2025",
        claim="OpenAI Stargate is a $500B infrastructure build.",
        stamp="grounded",
        title="Stargate",
        series="",
        print="500",
        when="2025",
        parallel_url=url,
        parallel_status="hit",
        note="Parallel URL on this row.",
    )
    packet = Packet(
        id="oc-dc-writer-attach",
        topic="Data centers are going to cause the next economic bubble",
        hook="Data centers are going to cause the next economic bubble",
        script="",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited data-center prints",
        tone="On the cited print",
        research_pack=_DC_PACK,
        receipt=Receipt(
            packet_id="oc-dc-writer-attach",
            written=False,
            disposition="READY",
            findings=[finding],
        ),
    )
    units = [
        {"id": "cold-open", "vo": "OpenAI Stargate is a $500B build.", "eyes": "capex", "finding_ids": []},
        {"id": "promise", "vo": "The title stays a question.", "eyes": "pack", "finding_ids": []},
        {"id": "gdp", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "labor", "vo": "The named print stays on the card.", "eyes": "card", "finding_ids": []},
        {"id": "turn", "vo": "Hold on the cited print.", "eyes": "hold", "finding_ids": []},
        {"id": "complication", "vo": "Those are not the same object.", "eyes": "gap", "finding_ids": []},
        {"id": "receipt", "vo": "Receipt board: named series from the pack.", "eyes": "board", "finding_ids": []},
        {"id": "close", "vo": "Near is not a switch.", "eyes": "close", "finding_ids": []},
    ]
    written = _assemble(packet, units)
    cold = next(b for b in written.beats if b.id == "cold-open")
    assert "stargate-500b-2025" in cold.finding_ids
    assert "[stargate-500b-2025]" in cold.vo
    assert "cites nothing in the pack" not in (written.receipt.hold_reason or "")


def test_live_shift_empty_cite_runs_repair_before_hold(monkeypatch) -> None:
    """Live cut shape: HOLD cites-nothing cannot finish with attempts=0."""
    from onecrew.agent.shift import open_shift, run_live_packet
    from onecrew.cite_repair import run_cite_recheck_loop as real_repair
    from onecrew.models import Rails
    from onecrew.room import RoomGrade
    from onecrew.script_writer import write_vo_from_pack as real_write_vo

    repair_calls = {"n": 0}

    def research(packet, rails, depth, **_k):
        packet.research_pack = _DC_PACK
        packet.task_spine = _DC_PACK
        receipt = Receipt(
            packet_id=packet.id,
            written=False,
            disposition="HOLD",
            hold_reason="beat1 cites nothing in the pack",
            findings=[_junk_ism()],
        )
        return receipt, [], [], packet.research_pack

    def tracking_repair(packet, **kwargs):
        repair_calls["n"] += 1
        kwargs.setdefault("search_fn", _dc_supporting_search)
        return real_repair(packet, **kwargs)

    eight = (
        '[{"id":"cold-open","vo":"OpenAI Stargate is a $500B build.","eyes":"capex","finding_ids":[]},'
        '{"id":"promise","vo":"The title stays a question.","eyes":"pack","finding_ids":[]},'
        '{"id":"gdp","vo":"Microsoft cancelled leases in August 2026.","eyes":"lease","finding_ids":[]},'
        '{"id":"labor","vo":"The Guardian named a boom that may already be a bubble.","eyes":"boom","finding_ids":[]},'
        '{"id":"turn","vo":"$500B is the spoken capex print.","eyes":"print","finding_ids":[]},'
        '{"id":"complication","vo":"Lease cancels are not the same object as a boom.","eyes":"gap","finding_ids":[]},'
        '{"id":"receipt","vo":"Receipt: Stargate $500B and the August 2026 cancels.","eyes":"board","finding_ids":[]},'
        '{"id":"close","vo":"Near is not a switch.","eyes":"close","finding_ids":[]}]'
    )

    monkeypatch.setattr("onecrew.agent.shift._research", research)
    monkeypatch.setattr("onecrew.agent.shift.run_cite_recheck_loop", tracking_repair)
    monkeypatch.setattr("onecrew.agent.shift.write_vo_from_pack", real_write_vo)
    monkeypatch.setattr("onecrew.script_writer.run_adk_writer", lambda _p: eight)
    monkeypatch.setattr("onecrew.room.run_adk_room", lambda _a: RoomGrade(vote="ship"))
    monkeypatch.setattr("onecrew.agent.shift._board", lambda p, _r: p.frames)
    monkeypatch.setattr("onecrew.collision.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.search", lambda **_k: SimpleNamespace(results=[]))
    monkeypatch.setattr("onecrew.board.generate_frames", lambda **_k: SimpleNamespace(generated_images=[]))
    monkeypatch.setattr("onecrew.config.has_vertex", lambda: True)
    shift = open_shift(
        "Data centers are going to cause the next economic bubble",
        platform="youtube",
        cut="one_time_short_episode",
        depth="2-3y",
        script_lean="centered_independent",
        tell="Host-only desk read of the cited data-center prints",
        tone="On the cited print",
        topic="Data centers are going to cause the next economic bubble",
    )
    shift.rails = Rails(parallel=True, vertex=True, imagen=False)
    packet = run_live_packet(shift)
    assert repair_calls["n"] >= 1
    assert packet.cite_recheck_attempts >= 1
    if packet.receipt and packet.receipt.disposition == "HOLD":
        assert "cite-repair loop exhausted" in (packet.receipt.hold_reason or "")
        assert "cites nothing in the pack" not in (packet.receipt.hold_reason or "") or (
            packet.cite_recheck_attempts >= 1
        )
    sourced = [b for b in packet.beats if any(ch.isdigit() for ch in b.vo)]
    for beat in sourced:
        assert beat.finding_ids, f"{beat.id} shipped untagged factual VO"


def test_production_does_not_hardcode_stargate() -> None:
    """Forbidden wrap: topic-hardcoding Stargate. Tests may name the live cut."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "onecrew"
    hits: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if re.search(r"stargate", text, re.I):
            hits.append(str(path.relative_to(root.parent)))
    assert hits == []
