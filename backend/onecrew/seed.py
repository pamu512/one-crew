from __future__ import annotations

import json

from onecrew import config
from onecrew.models import MISSING, CausalLink, Finding, Packet, Receipt, ShotFrame
from onecrew.receipt import write_receipt
from onecrew.store import store

CFR_JCPOA = "https://www.cfr.org/backgrounder/what-iran-nuclear-deal"
OPEC_URL = "https://www.opec.org/"

SEED_TOPIC = "Explain what's going on with the Hormuz strait"
SEED_HOOK = SEED_TOPIC
SEED_SCRIPT = (
    "Open on a tanker in the strait. Cut to 2018. Show the oil-share number. "
    "Hold the panic frame as mainstream, not a source. End on the missing link."
)


def seed_findings() -> list[Finding]:
    return [
        Finding(
            id="jcpoa-2018",
            when="2018",
            claim="The United States withdrew from the JCPOA, tightening the Iran file around the Gulf.",
            stamp="grounded",
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


def seed_links() -> list[CausalLink]:
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


def seed_frames() -> list[ShotFrame]:
    return [
        ShotFrame(
            id="tanker-lane",
            shot="Tanker in a narrow lane, land on both sides.",
            source_refs=[OPEC_URL],
            image_href="/api/frames/tanker-lane",
            imagen=False,
        ),
        ShotFrame(
            id="strait-map",
            shot="Chart table with a strait map and a 2018 date chip.",
            source_refs=[CFR_JCPOA],
            image_href="/api/frames/strait-map",
            imagen=False,
        ),
        ShotFrame(
            id="oil-share",
            shot="Phone showing the Parallel oil-share URL. Not a collage.",
            source_refs=[OPEC_URL],
            image_href="/api/frames/oil-share",
            imagen=False,
        ),
        ShotFrame(
            id="link-empty",
            shot="Timeline board: JCPOA to panic — causal link missing. No invented chain.",
            source_refs=[],
            image_href="/api/frames/link-empty",
            imagen=False,
        ),
    ]


def build_seed_packet() -> Packet:
    packet = Packet(
        id=config.SEED_PACKET_ID,
        topic=SEED_TOPIC,
        depth="decade",
        hook=SEED_HOOK,
        script=SEED_SCRIPT,
        status="ready",
        frames=seed_frames(),
    )
    receipt = Receipt(
        packet_id=packet.id,
        written=False,
        findings=seed_findings(),
        causal_links=seed_links(),
        disposition="READY",
    )
    return write_receipt(packet, receipt)


def load_sample_packet() -> Packet:
    if config.SAMPLE_PACKET.is_file():
        raw = json.loads(config.SAMPLE_PACKET.read_text())
        return Packet.model_validate(raw)
    return build_seed_packet()


def seed_first_open() -> Packet:
    """Stamp the first-open Hormuz decade packet. No Parallel. No Imagen."""
    packet = build_seed_packet()
    store.replace_packets([packet])
    return packet


def ensure_seeded() -> Packet:
    existing = store.get_packet(config.SEED_PACKET_ID)
    if existing and existing.receipt and existing.receipt.written:
        return existing
    return seed_first_open()


def reset_floor() -> Packet:
    return seed_first_open()
