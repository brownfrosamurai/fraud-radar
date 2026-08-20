import logging
from collections.abc import Callable
from datetime import datetime

from api.schemas import ScoredTransaction
from api.store import TransactionStore

logger = logging.getLogger(__name__)


class BatchWriter:
    def __init__(
        self,
        store: TransactionStore,
        notify: Callable[[list[ScoredTransaction]], None],
        clock: Callable[[], datetime],
        max_rows: int = 10,
        max_wait_ms: int = 100,
    ) -> None:
        self._store = store
        self._notify = notify
        self._clock = clock
        self._max_rows = max_rows
        self._max_wait_ms = max_wait_ms
        self._buf: list[ScoredTransaction] = []
        self._last_flush = clock()

    def add(self, row: ScoredTransaction) -> None:
        self._buf.append(row)
        self.flush_if_needed()

    def flush_if_needed(self) -> None:
        if not self._buf:
            return
        elapsed_ms = (self._clock() - self._last_flush).total_seconds() * 1000
        if len(self._buf) >= self._max_rows or elapsed_ms >= self._max_wait_ms:
            self._flush()

    def flush_pending(self) -> None:
        if self._buf:
            self._flush()

    def _flush(self) -> None:
        batch = self._buf
        self._buf = []
        self._last_flush = self._clock()
        try:
            self._store.put_many(batch)
        except Exception:
            logger.exception("scored_transactions flush failed; retrying once")
            try:
                self._store.put_many(batch)
            except Exception:
                logger.exception("scored_transactions flush failed twice; dropping batch")
                return
        self._notify(batch)
