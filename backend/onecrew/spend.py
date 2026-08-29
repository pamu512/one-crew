from __future__ import annotations

"""Spend ledger. GET paths must leave these at zero. POST that spends is token-gated."""


class SpendLedger:
    def __init__(self) -> None:
        self.parallel_calls = 0
        self.imagen_calls = 0

    def reset(self) -> None:
        self.parallel_calls = 0
        self.imagen_calls = 0

    def note_parallel(self) -> None:
        self.parallel_calls += 1

    def note_imagen(self) -> None:
        self.imagen_calls += 1

    @property
    def spent(self) -> bool:
        return self.parallel_calls > 0 or self.imagen_calls > 0


ledger = SpendLedger()
