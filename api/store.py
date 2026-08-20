import threading
from uuid import UUID

from api.schemas import ScoredTransaction

MAX_ROWS = 500


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

    def get(self, id: UUID) -> ScoredTransaction | None:
        with self._lock:
            return self._rows.get(id)

    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]:
        with self._lock:
            ids = list(reversed(self._order))[: min(limit, 50)]
            return [self._rows[i] for i in ids]
