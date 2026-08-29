from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PACKET = Path(os.getenv("ONECREW_PACKET", ROOT / "sample_data" / "packet.json"))
FRAMES_DIR = Path(os.getenv("ONECREW_FRAMES", ROOT / "sample_data" / "frames"))
DATA_DIR = Path(os.getenv("ONECREW_DATA_DIR", ROOT / "data"))

APP_NAME = "onecrew"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "onecrew")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
IMAGEN_MODEL = os.getenv("IMAGEN_MODEL", "imagen-3.0-generate-001")

HOST = os.getenv("ONECREW_HOST", "0.0.0.0")
PORT = int(os.getenv("ONECREW_PORT", "43158"))

SEED_PACKET_ID = "oc-hormuz-decade"


def google_cloud_project() -> str:
    """Empty unless the operator exports GOOGLE_CLOUD_PROJECT. No baked project id."""
    return (os.getenv("GOOGLE_CLOUD_PROJECT") or "").strip()


def use_vertex() -> bool:
    raw = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    return raw.lower() in {"1", "true", "yes"}


def has_adc() -> bool:
    """Real ADC only: existing credentials file or Cloud Run metadata. Not a project string."""
    creds = (os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
    if creds and Path(creds).is_file():
        return True
    if os.getenv("K_SERVICE"):
        return True
    return False


def has_vertex() -> bool:
    """Vertex + ADC. A project id or consumer API key does not mark the rail up."""
    return use_vertex() and has_adc()


def has_parallel() -> bool:
    return bool((os.getenv("PARALLEL_API_KEY") or "").strip())


def has_imagen() -> bool:
    """Imagen rides Vertex. Project string alone is not enough."""
    return has_vertex()


def parallel_api_key() -> str:
    return (os.getenv("PARALLEL_API_KEY") or "").strip()


def shift_token() -> str:
    """Shared secret for live spends. Empty means POST that spends is disabled."""
    return (os.getenv("SHIFT_TOKEN") or "").strip()


def shifts_enabled() -> bool:
    return bool(shift_token())
