from __future__ import annotations

import asyncio
from collections import defaultdict

from onecrew.models import utcnow


class Bus:
    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, list[dict]] = defaultdict(list)

    def emit(self, shift_id: str, *, agent: str, kind: str, message: str, **data: object) -> dict:
        event = {
            "ts": utcnow(),
            "shift_id": shift_id,
            "agent": agent,
            "kind": kind,
            "message": message,
            "data": data,
        }
        self._history[shift_id].append(event)
        for q in list(self._subs.get(shift_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return event

    def subscribe(self, shift_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subs[shift_id].append(q)
        return q

    def unsubscribe(self, shift_id: str, q: asyncio.Queue) -> None:
        subs = self._subs.get(shift_id, [])
        if q in subs:
            subs.remove(q)

    def history(self, shift_id: str) -> list[dict]:
        return list(self._history.get(shift_id, []))

    def close(self, shift_id: str) -> None:
        for q in list(self._subs.get(shift_id, [])):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass
        self._subs.pop(shift_id, None)


bus = Bus()
