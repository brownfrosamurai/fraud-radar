import threading
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

import numpy as np

from api.schemas import (
    AlertDir,
    AlertFilter,
    AlertSort,
    AlertsResponse,
    ScoredTransaction,
    StatsResponse,
)

MAX_ROWS = 500
LIST_CAP = 50
FLAGGED = frozenset({"REVIEW", "BLOCK"})
THROUGHPUT_WINDOW_S = 5
LATENCY_WINDOW = 200


def stats_from_rows(rows: list[ScoredTransaction], *, now: datetime) -> StatsResponse:
    processed = len(rows)
    flagged = sum(1 for row in rows if row.decision in FLAGGED)
    cutoff = now - timedelta(seconds=THROUGHPUT_WINDOW_S)
    recent = sum(1 for row in rows if row.created_at >= cutoff)
    timed = sorted(
        (row for row in rows if row.scoring_ms is not None),
        key=lambda row: row.created_at,
        reverse=True,
    )[:LATENCY_WINDOW]
    values = [int(row.scoring_ms) for row in timed if row.scoring_ms is not None]
    p50: int | None = None
    p95: int | None = None
    if values:
        p50 = int(round(float(np.percentile(values, 50))))
        p95 = int(round(float(np.percentile(values, 95))))
    return StatsResponse(
        processed=processed,
        throughput_tx_per_s=recent / THROUGHPUT_WINDOW_S,
        latency_p50_ms=p50,
        latency_p95_ms=p95,
        flagged=flagged,
    )


def _alert_key(row: ScoredTransaction, sort: AlertSort) -> object:
    if sort == "created_at":
        return row.created_at
    if sort == "amount":
        return row.amount
    if sort == "model_score":
        return row.model_score
    return row.decision


def list_alerts_from_rows(
    rows: list[ScoredTransaction],
    *,
    filter: AlertFilter,
    sort: AlertSort,
    dir: AlertDir,
    offset: int,
    limit: int,
) -> AlertsResponse:
    flagged = [row for row in rows if row.decision in FLAGGED]
    if filter == "review":
        flagged = [row for row in flagged if row.decision == "REVIEW"]
    elif filter == "block":
        flagged = [row for row in flagged if row.decision == "BLOCK"]
    reverse = dir == "desc"
    ordered = sorted(flagged, key=lambda row: _alert_key(row, sort), reverse=reverse)
    return AlertsResponse(
        items=ordered[offset : offset + limit],
        total=len(ordered),
        offset=offset,
        limit=limit,
    )


class TransactionStore(Protocol):
    def put(self, row: ScoredTransaction) -> None: ...
    def put_many(self, rows: list[ScoredTransaction]) -> None: ...
    def get(self, id: UUID) -> ScoredTransaction | None: ...
    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]: ...
    def stats(self, *, now: datetime) -> StatsResponse: ...
    def list_alerts(
        self,
        *,
        filter: AlertFilter,
        sort: AlertSort,
        dir: AlertDir,
        offset: int,
        limit: int,
    ) -> AlertsResponse: ...


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

    def stats(self, *, now: datetime) -> StatsResponse:
        with self._lock:
            rows = list(self._rows.values())
        return stats_from_rows(rows, now=now)

    def list_alerts(
        self,
        *,
        filter: AlertFilter,
        sort: AlertSort,
        dir: AlertDir,
        offset: int,
        limit: int,
    ) -> AlertsResponse:
        with self._lock:
            rows = list(self._rows.values())
        return list_alerts_from_rows(
            rows, filter=filter, sort=sort, dir=dir, offset=offset, limit=limit
        )
