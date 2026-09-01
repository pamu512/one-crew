from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

from onecrew import config
from onecrew.models import Packet, ShiftRecord

log = logging.getLogger("onecrew.store")


class PacketStore:
    """Packet store. Memory is enough when min-instances=1.

    Firestore is optional. Import or API failure stays on memory. Seed upsert
    must not wipe a live packet.
    """

    def __init__(self) -> None:
        self.backend = "memory"
        self.fallback_reason: str | None = None
        self._mem_packets: dict[str, dict[str, Any]] = {}
        self._mem_shifts: dict[str, dict[str, Any]] = {}
        self._client = None
        self._connect_firestore()
        if self.backend != "firestore":
            self._load_file()

    def _connect_firestore(self) -> None:
        # ponytail: memory is enough for min-instances=1. Firestore is optional.
        try:
            from google.cloud import firestore  # noqa: PLC0415
        except ImportError as exc:
            self.backend = "memory"
            self.fallback_reason = f"ImportError: {exc}"
            log.info("Firestore library missing; memory store")
            return

        live = bool(
            os.getenv("FIRESTORE_EMULATOR_HOST")
            or os.getenv("ONECREW_FORCE_FIRESTORE") == "1"
            or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        )
        if not live:
            self.backend = "memory"
            self.fallback_reason = "Firestore API not required — memory store"
            log.info("Memory store (Firestore not requested)")
            return
        try:
            project = config.google_cloud_project() or None
            self._client = firestore.Client(project=project) if project else firestore.Client()
            ping = self._client.collection(config.FIRESTORE_COLLECTION).document("_health")
            ping.set({"ok": True, "service": "onecrew"}, merge=True)
            self.backend = "firestore"
            log.info("Firestore connected project=%s", project or "(adc)")
        except Exception as exc:  # noqa: BLE001
            self._client = None
            self.backend = "memory"
            self.fallback_reason = f"{type(exc).__name__}: {exc}"
            log.warning("Firestore unavailable, using memory store (%s)", self.fallback_reason)

    def _col(self, name: str):
        assert self._client is not None
        return self._client.collection(config.FIRESTORE_COLLECTION).document(name).collection("items")

    def _data_dir(self) -> Path:
        raw = (os.getenv("ONECREW_DATA_DIR") or "").strip()
        folder = Path(raw) if raw else config.DATA_DIR
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _file(self) -> Path:
        return self._data_dir() / "store.json"

    def _load_file(self) -> None:
        path = self._file()
        if not path.exists():
            return
        raw = json.loads(path.read_text())
        self._mem_packets = raw.get("packets", {})
        self._mem_shifts = raw.get("shifts", {})

    def _save_file(self) -> None:
        if self.backend == "firestore":
            return
        self._file().write_text(
            json.dumps({"packets": self._mem_packets, "shifts": self._mem_shifts}, indent=2)
        )

    def upsert_packet(self, packet: Packet) -> Packet:
        payload = packet.model_dump()
        if self.backend == "firestore" and self._client is not None:
            self._col("packets").document(packet.id).set(payload)
        else:
            self._mem_packets[packet.id] = payload
            self._save_file()
        return packet

    def get_packet(self, packet_id: str) -> Packet | None:
        if self.backend == "firestore" and self._client is not None:
            snap = self._col("packets").document(packet_id).get()
            if not snap.exists:
                return None
            return Packet.model_validate(snap.to_dict())
        raw = self._mem_packets.get(packet_id)
        return Packet.model_validate(raw) if raw else None

    def list_packets(self) -> list[Packet]:
        if self.backend == "firestore" and self._client is not None:
            rows = [Packet.model_validate(d.to_dict()) for d in self._col("packets").stream()]
        else:
            rows = [Packet.model_validate(v) for v in self._mem_packets.values()]
        rows.sort(key=lambda p: (p.id != config.SEED_PACKET_ID, p.id))
        return rows

    def replace_packets(self, packets: list[Packet]) -> None:
        if self.backend == "firestore" and self._client is not None:
            batch = self._client.batch()
            for existing in self._col("packets").stream():
                batch.delete(existing.reference)
            batch.commit()
            for packet in packets:
                self._col("packets").document(packet.id).set(packet.model_dump())
        else:
            self._mem_packets = {p.id: p.model_dump() for p in packets}
            self._save_file()

    def upsert_shift(self, shift: ShiftRecord) -> ShiftRecord:
        payload = shift.model_dump()
        if self.backend == "firestore" and self._client is not None:
            self._col("shifts").document(shift.id).set(payload)
        else:
            self._mem_shifts[shift.id] = payload
            self._save_file()
        return shift

    def get_shift(self, shift_id: str) -> ShiftRecord | None:
        if self.backend == "firestore" and self._client is not None:
            snap = self._col("shifts").document(shift_id).get()
            if not snap.exists:
                return None
            return ShiftRecord.model_validate(snap.to_dict())
        raw = self._mem_shifts.get(shift_id)
        return ShiftRecord.model_validate(raw) if raw else None

    def list_shifts(self) -> list[ShiftRecord]:
        if self.backend == "firestore" and self._client is not None:
            rows = [ShiftRecord.model_validate(d.to_dict()) for d in self._col("shifts").stream()]
        else:
            rows = [ShiftRecord.model_validate(v) for v in self._mem_shifts.values()]
        rows.sort(key=lambda s: s.started_at, reverse=True)
        return rows

    def snapshot(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "fallback_reason": self.fallback_reason,
            "packets": deepcopy(self._mem_packets),
        }


store = PacketStore()


def rebind_store() -> PacketStore:
    """Reset the process-wide store in place so importers keep the same object."""
    store.__init__()
    return store
