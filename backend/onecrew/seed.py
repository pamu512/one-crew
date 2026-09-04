"""GET first-open. Recession 8-beat. No Parallel. No Imagen. Floor never posts.

Hormuz stays leftover/exclusion only — not the first-open identity.
"""

from __future__ import annotations

import json

from onecrew import config
from onecrew.board import apply_seed_placeholders, write_shot_list
from onecrew.collision import hold_collisions
from onecrew.models import MISSING, CausalLink, Finding, Packet, Receipt
from onecrew.pack import seed_exclusions, write_research_pack
from onecrew.receipt import write_receipt
from onecrew.script import write_script
from onecrew.store import store
from onecrew.tell import SEED_TELL
from onecrew.tone import SEED_TONE

SEED_TOPIC = "Are we near recession?"
SEED_HOOK = SEED_TOPIC
SEED_SCRIPT = ""

LEFTOVER_HORMUZ_PACKET_ID = "oc-hormuz-decade"
LEFTOVER_HORMUZ_TOPIC = (
    "How a decade of decisions around the Strait of Hormuz still sets the price of oil"
)
LEFTOVER_HORMUZ_TELL = "Narrator-led global overview of the US and Iran"

CFR_JCPOA = "https://www.cfr.org/backgrounder/what-iran-nuclear-deal"
OPEC_URL = "https://www.opec.org/"
FRED_USREC = "https://fred.stlouisfed.org/series/USREC"
BLS_CES = "https://www.bls.gov/news.release/empsit.nr0.htm"
BEA_GDP = "https://www.bea.gov/news/2026/gross-domestic-product-second-quarter-2026-advance-estimate"
SAHM_URL = "https://fred.stlouisfed.org/series/SAHMREALTIME"
CONFERENCE_BOARD = "https://www.conference-board.org/topics/us-leading-indicators"
ISM_URL = "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/"


def leftover_hormuz_findings() -> list[Finding]:
    """Named leftover. Not first-open. OPEC + EIA stay for propaganda/independence."""
    return [
        Finding(
            id="jcpoa-2018",
            when="2018",
            claim="The United States withdrew from the JCPOA, tightening the Iran file around the Gulf.",
            stamp="grounded",
            title="What Is the Iran Nuclear Deal?",
            parallel_url=CFR_JCPOA,
            parallel_status="hit",
            note="Parallel URL on this row.",
            independent=MISSING,
            vested_interest=MISSING,
        ),
        Finding(
            id="hormuz-share",
            when="2018-2024",
            claim="A large share of seaborne oil still transits the Strait of Hormuz.",
            stamp="grounded",
            title="OPEC",
            parallel_url=OPEC_URL,
            parallel_status="hit",
            note="Parallel URL on this row.",
            independent="no",
            independent_url=OPEC_URL,
            vested_interest=MISSING,
            propaganda="yes",
            propaganda_url=OPEC_URL,
            propaganda_issuer="OPEC",
        ),
        Finding(
            id="oil-panic",
            when="2023-2024",
            claim="Any Hormuz scare means oil crashes the world overnight.",
            stamp="mainstream",
            parallel_url=None,
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
        ),
        Finding(
            id="producer-frame",
            when="2018-2024",
            claim="Producer states treat an open Hormuz as an oil-market given.",
            stamp="mainstream",
            parallel_url=None,
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
            lean="industry",
            lean_url=OPEC_URL,
            interests=["OPEC"],
            interests_url=OPEC_URL,
            who_repeats=["OPEC"],
            who_repeats_url=OPEC_URL,
        ),
        Finding(
            id="secret-closure",
            when="decade",
            claim="Hormuz has already been mined shut under a hidden navy treaty.",
            stamp="fringe",
            parallel_url=None,
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def leftover_hormuz_links() -> list[CausalLink]:
    """Named leftover. JCPOA-to-panic is not first-open."""
    return [
        CausalLink(
            id="jcpoa-to-houthi",
            from_id="jcpoa-2018",
            to_id="oil-panic",
            claim="The 2018 JCPOA exit caused the 2023-2024 Hormuz panic.",
            stamp=MISSING,
            parallel_url=None,
        )
    ]


def seed_findings() -> list[Finding]:
    """Recession 8-beat first-open. GET does not spend. Floor never posts."""
    return [
        Finding(
            id="usrec-july-2026",
            when="July 2026",
            claim="USREC=0 (July 2026). Official recession flag is off.",
            stamp="grounded",
            title="USREC",
            series="USREC",
            print="0",
            parallel_url=FRED_USREC,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="payrolls-july-2026",
            when="July 2026",
            claim="Nonfarm payrolls fell −23k.",
            stamp="grounded",
            title="BLS payrolls",
            series="BLS payrolls",
            print="−23k",
            parallel_url=BLS_CES,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="unemployment-july-2026",
            when="July 2026",
            claim="U-3 unemployment is 4.1%.",
            stamp="grounded",
            title="BLS unemployment",
            series="U-3",
            print="4.1%",
            parallel_url=BLS_CES,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="gdp-2026-q2",
            when="2025-2026",
            claim="GDP printed 0.5, then 2.1, then 1.5.",
            stamp="grounded",
            title="BEA GDP",
            series="GDP",
            print="0.5",
            parallel_url=BEA_GDP,
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="sahm-july-2026",
            when="July 2026",
            claim="Sahm is −0.03 vs the 0.50 trigger.",
            stamp="grounded",
            title="Sahm rule",
            series="SAHMREALTIME",
            print="−0.03",
            parallel_url=SAHM_URL,
            parallel_status="hit",
            note="Parallel URL on this row. NBER dates the cycle; FRED hosts the series.",
        ),
        Finding(
            id="already-in",
            when="2026",
            claim="The US is already in a recession.",
            stamp="mainstream",
            parallel_url=None,
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
            lean=MISSING,
            interests=MISSING,
            who_repeats=MISSING,
        ),
        Finding(
            id="lei-july-2026",
            when="July 2026",
            claim="LEI +0.2%.",
            stamp="fringe",
            parallel_url=None,
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
        Finding(
            id="ism-july-2026",
            when="July 2026",
            claim="ISM 55.6.",
            stamp="fringe",
            parallel_url=None,
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def seed_links() -> list[CausalLink]:
    return []


def build_seed_packet() -> Packet:
    packet = Packet(
        id=config.SEED_PACKET_ID,
        topic=SEED_TOPIC,
        platform="youtube",
        depth="1y",
        cut="one_time_short_episode",
        script_lean="centered_independent",
        tell=SEED_TELL,
        tone=SEED_TONE,
        hook=SEED_HOOK,
        script=SEED_SCRIPT,
        status="ready",
        frames=[],
    )
    receipt = Receipt(
        packet_id=packet.id,
        written=False,
        findings=seed_findings(),
        causal_links=seed_links(),
        disposition="READY",
    )
    packet = write_script(write_receipt(packet, receipt))
    hold_collisions(packet)
    packet.exclusions = seed_exclusions()
    write_research_pack(packet)
    packet.frames = apply_seed_placeholders(write_shot_list(packet))
    return packet


def leftover_hormuz_packet() -> Packet:
    """Negative-case leftover. Not first-open. Not the floor seed. GET does not store this."""
    packet = Packet(
        id=LEFTOVER_HORMUZ_PACKET_ID,
        topic=LEFTOVER_HORMUZ_TOPIC,
        platform="youtube",
        depth="decade",
        cut="one_time_short_episode",
        script_lean="centered_independent",
        tell=LEFTOVER_HORMUZ_TELL,
        tone=SEED_TONE,
        hook=LEFTOVER_HORMUZ_TOPIC,
        script="",
        status="ready",
        frames=[],
    )
    receipt = Receipt(
        packet_id=packet.id,
        written=False,
        findings=leftover_hormuz_findings(),
        causal_links=leftover_hormuz_links(),
        disposition="READY",
    )
    packet = write_script(write_receipt(packet, receipt))
    hold_collisions(packet)
    packet.exclusions = seed_exclusions()
    write_research_pack(packet)
    return packet


def load_sample_packet() -> Packet:
    if config.SAMPLE_PACKET.is_file():
        raw = json.loads(config.SAMPLE_PACKET.read_text())
        return Packet.model_validate(raw)
    return build_seed_packet()


def seed_first_open() -> Packet:
    """Stamp the first-open recession 8-beat. Do not wipe live packets."""
    packet = build_seed_packet()
    store.upsert_packet(packet)
    return packet


def ensure_seeded() -> Packet:
    existing = store.get_packet(config.SEED_PACKET_ID)
    if existing and existing.receipt and existing.receipt.written:
        return existing
    return seed_first_open()


def reset_floor() -> Packet:
    return seed_first_open()
