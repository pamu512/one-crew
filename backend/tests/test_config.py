from pathlib import Path

from onecrew import config
from onecrew.rails import assess_rails

_BANNED = (
    "tarka-505801",
    "night-desk-507002",
    "Tarka",
    "Night Desk",
    "nightdesk",
    "night-desk",
    "tarka",
)

_SKIP_PARTS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def test_google_cloud_project_from_env_only(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    assert config.google_cloud_project() == ""
    src = Path(config.__file__).read_text()
    assert 'getenv("GOOGLE_CLOUD_PROJECT", "' not in src
    assert "tarka-505801" not in src
    assert "night-desk-507002" not in src


def test_source_tree_has_no_tarka_or_night_desk() -> None:
    root = Path(__file__).resolve().parents[2]
    hits: list[str] = []
    for path in root.rglob("*"):
        if any(part in _SKIP_PARTS for part in path.parts):
            continue
        if path.name.startswith("test_config"):
            continue
        if not path.is_file():
            continue
        if path.suffix not in {".py", ".md", ".json", ".svg", ".html", ".txt", ".yml", ".yaml", ".env", ".example"}:
            if path.name not in {".env.example", "Dockerfile"}:
                continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for token in _BANNED:
            if token in text:
                hits.append(f"{path.relative_to(root)}:{token}")
    assert hits == []


def test_project_string_alone_does_not_mark_vertex_up(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "someone-said-this-is-enough")
    monkeypatch.setenv("GOOGLE_GENAI_USE_VERTEXAI", "true")
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert config.google_cloud_project() == "someone-said-this-is-enough"
    assert config.has_adc() is False
    assert config.has_vertex() is False
    assert config.has_imagen() is False
    rails = assess_rails(parallel_up=True)
    assert rails.ok is False
    assert "vertex" in rails.missing
    assert "imagen" in rails.missing
