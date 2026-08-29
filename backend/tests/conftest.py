from __future__ import annotations

import pytest

from onecrew.spend import ledger
from onecrew.store import rebind_store


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ONECREW_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("SHIFT_TOKEN", raising=False)
    monkeypatch.delenv("PARALLEL_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("FIRESTORE_EMULATOR_HOST", raising=False)
    monkeypatch.delenv("ONECREW_FORCE_FIRESTORE", raising=False)
    ledger.reset()
    rebind_store()
    yield
    ledger.reset()
