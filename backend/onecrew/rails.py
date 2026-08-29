from __future__ import annotations

from onecrew import config
from onecrew.models import Rails


def assess_rails(
    *,
    parallel_up: bool | None = None,
    vertex_up: bool | None = None,
    imagen_up: bool | None = None,
) -> Rails:
    parallel = config.has_parallel() if parallel_up is None else parallel_up
    vertex = config.has_vertex() if vertex_up is None else vertex_up
    imagen = config.has_imagen() if imagen_up is None else imagen_up
    return Rails(parallel=parallel, vertex=vertex, imagen=imagen)
