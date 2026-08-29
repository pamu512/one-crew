from __future__ import annotations

from typing import Any

from onecrew import config
from onecrew.spend import ledger


class ImagenDownError(RuntimeError):
    """Vertex/Imagen rail is down. Caller must HOLD — no collage."""


def generate_frames(*, prompt: str, number_of_images: int = 4) -> Any:
    """Vertex Imagen. This call spends. Project comes from env only."""
    if not config.has_imagen():
        raise ImagenDownError("Vertex/Imagen missing")
    project = config.google_cloud_project()
    if not project:
        raise ImagenDownError("GOOGLE_CLOUD_PROJECT missing")
    ledger.note_imagen()
    from google import genai
    from google.genai import types

    client = genai.Client(
        vertexai=True,
        project=project,
        location=config.GOOGLE_CLOUD_LOCATION,
    )
    return client.models.generate_images(
        model=config.IMAGEN_MODEL,
        prompt=prompt,
        config=types.GenerateImagesConfig(number_of_images=number_of_images),
    )
