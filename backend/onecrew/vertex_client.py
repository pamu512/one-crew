from __future__ import annotations

from onecrew import config


class VertexDownError(RuntimeError):
    """Vertex/Gemini rail is down. Caller must HOLD — no leftover or invented VO."""


def generate_script(prompt: str) -> str:
    """Vertex Gemini. Same Client rail as Imagen. Project comes from env only."""
    if not (prompt or "").strip():
        raise VertexDownError("empty prompt")
    if not config.has_vertex():
        raise VertexDownError("Vertex missing")
    project = config.google_cloud_project()
    if not project:
        raise VertexDownError("GOOGLE_CLOUD_PROJECT missing")
    from google import genai

    client = genai.Client(
        vertexai=True,
        project=project,
        location=config.GOOGLE_CLOUD_LOCATION,
    )
    result = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=prompt,
    )
    text = (getattr(result, "text", None) or "").strip()
    if not text:
        for candidate in getattr(result, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                piece = getattr(part, "text", None)
                if piece and str(piece).strip():
                    text = str(piece).strip()
                    break
            if text:
                break
    if not text:
        raise VertexDownError("Vertex returned empty text")
    return text
