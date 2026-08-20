from uuid import UUID

from api.schemas import ScoredTransaction


class InMemoryStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, ScoredTransaction] = {}
        self._order: list[UUID] = []

    def put(self, row: ScoredTransaction) -> None:
        if row.id not in self._rows:
            self._order.append(row.id)
        self._rows[row.id] = row

    def get(self, id: UUID) -> ScoredTransaction | None:
        return self._rows.get(id)

    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]:
        ids = list(reversed(self._order))[: min(limit, 50)]
        return [self._rows[i] for i in ids]
