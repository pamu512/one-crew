from __future__ import annotations

import json

from onecrew import config
from onecrew.models import Finding, Packet, Receipt, ShotFrame
from onecrew.receipt import write_receipt
from onecrew.store import store

SEED_HOOK = "Pickle juice at 3am is a ranking cheat code — NASA even studied it."
SEED_SCRIPT = (
    "Open on the fridge. Pour the brine. Cut to the microwave clock at 3:07. "
    "Show the ranking on the phone. End on the empty NASA search — do not sell it as fact."
)


def seed_findings() -> list[Finding]:
    return [
        Finding(
            id="ranking-hit",
            claim=(
                "Pickle juice sodium ranks with common sports drinks in published recovery tables."
            ),
            stamp="grounded",
            parallel_url="https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3894303/",
            parallel_status="hit",
            note="Parallel URL on this row.",
        ),
        Finding(
            id="3am-kitchen",
            claim="A 3am kitchen pickle-juice shot is a hangover ranking hack.",
            stamp="mainstream",
            parallel_url=None,
            parallel_status="n/a",
            note="Widely repeated, may be bias, not a source.",
        ),
        Finding(
            id="nasa-miss",
            claim="NASA studied pickle juice for astronaut cramps.",
            stamp="fringe",
            parallel_url=None,
            parallel_status="miss",
            note="Parallel miss. Included and tagged fringe. Never sold as fact.",
        ),
    ]


def seed_frames() -> list[ShotFrame]:
    return [
        ShotFrame(
            id="jar-pour",
            shot="Close-up: refrigerator pickle jar, brine pouring into a shot glass.",
            source_refs=["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3894303/"],
            image_href="/api/frames/jar-pour",
            imagen=False,
        ),
        ShotFrame(
            id="kitchen-3am",
            shot="Single overhead bulb, kitchen sink, 3:07 on the microwave.",
            source_refs=[],
            image_href="/api/frames/kitchen-3am",
            imagen=False,
        ),
        ShotFrame(
            id="ranking-phone",
            shot="Phone in hand showing the Parallel ranking URL. Not a stock collage.",
            source_refs=["https://www.ncbi.nlm.nih.gov/pmc/articles/PMC3894303/"],
            image_href="/api/frames/ranking-phone",
            imagen=False,
        ),
        ShotFrame(
            id="nasa-empty",
            shot="Search board: NASA pickle juice — no hit. Empty results, not a NASA seal.",
            source_refs=[],
            image_href="/api/frames/nasa-empty",
            imagen=False,
        ),
    ]


def build_seed_packet() -> Packet:
    packet = Packet(
        id=config.SEED_PACKET_ID,
        hook=SEED_HOOK,
        script=SEED_SCRIPT,
        status="ready",
        frames=seed_frames(),
    )
    receipt = Receipt(
        packet_id=packet.id,
        written=False,
        findings=seed_findings(),
        disposition="READY",
    )
    return write_receipt(packet, receipt)


def load_sample_packet() -> Packet:
    if config.SAMPLE_PACKET.is_file():
        raw = json.loads(config.SAMPLE_PACKET.read_text())
        return Packet.model_validate(raw)
    return build_seed_packet()


def seed_first_open() -> Packet:
    """Stamp the first-open packet. No Parallel. No Imagen."""
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
