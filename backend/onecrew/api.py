from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from onecrew import config
from onecrew.floor import FLOOR_HTML
from onecrew.rails import assess_rails
from onecrew.seed import ensure_seeded, reset_floor
from onecrew.spend import ledger
from onecrew.store import store

log = logging.getLogger("onecrew.api")

FRAME_FILES = {
    "jar-pour": "jar-pour.svg",
    "kitchen-3am": "kitchen-3am.svg",
    "ranking-phone": "ranking-phone.svg",
    "nasa-empty": "nasa-empty.svg",
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ensure_seeded()
    log.info("Seeded oc-pickle-debt (no Parallel, no Imagen)")
    yield


app = FastAPI(title="One Crew", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_shift_token(x_shift_token: str | None = Header(default=None)) -> None:
    """POST that spends Parallel/Imagen. Off unless SHIFT_TOKEN matches."""
    token = config.shift_token()
    if not token:
        raise HTTPException(403, "Live spend disabled. Set SHIFT_TOKEN to enable.")
    provided = (x_shift_token or "").strip()
    if not provided or not hmac.compare_digest(provided, token):
        raise HTTPException(403, "Invalid or missing X-Shift-Token")


class ShiftRequest(BaseModel):
    goal: str = Field(
        default="Research the hook. Stamp grounded / mainstream / fringe. Board four shots. Do not post."
    )
    packet_id: str = Field(default=config.SEED_PACKET_ID)


@app.get("/", response_class=HTMLResponse)
def floor() -> str:
    return FLOOR_HTML


@app.get("/api/health")
def health() -> dict[str, Any]:
    rails = assess_rails()
    return {
        "ok": True,
        "service": "onecrew",
        "model": config.GEMINI_MODEL,
        "vertex": config.has_vertex(),
        "parallel": config.has_parallel(),
        "imagen": config.has_imagen(),
        "store": store.backend,
        "store_fallback": store.fallback_reason,
        "project": config.google_cloud_project(),
        "rails": {
            "present": rails.present,
            "missing": rails.missing,
            "ok": rails.ok,
        },
        "shifts": {"enabled": config.shifts_enabled()},
        "spend": {
            "parallel_calls": ledger.parallel_calls,
            "imagen_calls": ledger.imagen_calls,
        },
        "posts": False,
    }


@app.get("/api/packets")
def list_packets() -> dict[str, Any]:
    packets = store.list_packets()
    if not packets:
        ensure_seeded()
        packets = store.list_packets()
    return {"packets": [p.model_dump() for p in packets]}


@app.get("/api/packets/{packet_id}")
def get_packet(packet_id: str) -> dict[str, Any]:
    packet = store.get_packet(packet_id)
    if not packet:
        raise HTTPException(404, "packet not found")
    return packet.model_dump()


@app.get("/api/frames/{frame_id}")
def get_frame(frame_id: str) -> Response:
    name = FRAME_FILES.get(frame_id)
    if not name:
        raise HTTPException(404, "frame not found")
    path = config.FRAMES_DIR / name
    if not path.is_file():
        raise HTTPException(404, "frame file missing")
    return Response(content=path.read_bytes(), media_type="image/svg+xml; charset=utf-8")


@app.get("/api/shifts")
def list_shifts() -> dict[str, Any]:
    return {"shifts": [s.model_dump() for s in store.list_shifts()]}


@app.post("/api/shifts")
async def start_shift(
    body: ShiftRequest,
    x_shift_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_shift_token(x_shift_token)
    from onecrew.agent.shift import open_shift, run_shift

    shift = open_shift(body.goal, packet_id=body.packet_id)
    await run_shift(body.goal, packet_id=body.packet_id, shift=shift)
    return shift.model_dump()


@app.post("/api/reset")
def reset(x_shift_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_shift_token(x_shift_token)
    packet = reset_floor()
    return {"ok": True, "packet_id": packet.id}
