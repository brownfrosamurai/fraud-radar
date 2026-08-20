from queue import SimpleQueue

from api.schemas import ScoredTransaction


class StreamHub:
    def __init__(self) -> None:
        self._subscribers: list[SimpleQueue] = []

    def subscribe(self) -> SimpleQueue:
        q: SimpleQueue = SimpleQueue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: SimpleQueue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def broadcast(self, row: ScoredTransaction) -> None:
        payload = row.model_dump(mode="json")
        for q in list(self._subscribers):
            q.put(payload)
