import threading
from typing import Protocol
from uuid import UUID

from api.schemas import ScoredTransaction

MAX_ROWS = 500
LIST_CAP = 50


class TransactionStore(Protocol):
    def put(self, row: ScoredTransaction) -> None: ...
    def put_many(self, rows: list[ScoredTransaction]) -> None: ...
    def get(self, id: UUID) -> ScoredTransaction | None: ...
    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]: ...


class InMemoryStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, ScoredTransaction] = {}
        self._order: list[UUID] = []
        # Compound dict+list updates are not atomic; burst and /score can race.
        self._lock = threading.Lock()

    def put(self, row: ScoredTransaction) -> None:
        with self._lock:
            if row.id not in self._rows:
                self._order.append(row.id)
            self._rows[row.id] = row
            while len(self._order) > MAX_ROWS:
                oldest = self._order.pop(0)
                del self._rows[oldest]

    def put_many(self, rows: list[ScoredTransaction]) -> None:
        for row in rows:
            self.put(row)

    def get(self, id: UUID) -> ScoredTransaction | None:
        with self._lock:
            return self._rows.get(id)

    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]:
        with self._lock:
            ids = list(reversed(self._order))[: min(limit, LIST_CAP)]
            return [self._rows[i] for i in ids]
