from datetime import datetime, timedelta
from uuid import UUID

import numpy as np
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from api.db import ScoredTransactionRow, create_tables, ensure_scoring_ms_column
from api.schemas import (
    AlertDir,
    AlertFilter,
    AlertSort,
    AlertsResponse,
    Features,
    ScoredTransaction,
    StatsResponse,
)
from api.store import FLAGGED, LATENCY_WINDOW, LIST_CAP, THROUGHPUT_WINDOW_S

_ALERT_SORT = {
    "created_at": ScoredTransactionRow.created_at,
    "amount": ScoredTransactionRow.amount,
    "model_score": ScoredTransactionRow.model_score,
    "decision": ScoredTransactionRow.decision,
}


def _alerts_where(filter: AlertFilter):
    if filter == "review":
        return ScoredTransactionRow.decision == "REVIEW"
    if filter == "block":
        return ScoredTransactionRow.decision == "BLOCK"
    return ScoredTransactionRow.decision.in_(tuple(FLAGGED))


def _to_orm(row: ScoredTransaction) -> ScoredTransactionRow:
    return ScoredTransactionRow(
        id=row.id,
        occurred_at=row.occurred_at,
        amount=row.amount,
        model_score=row.model_score,
        decision=row.decision,
        model_name=row.model_name,
        features=row.features.model_dump(),
        created_at=row.created_at,
        scoring_ms=row.scoring_ms,
    )


def _from_orm(row: ScoredTransactionRow) -> ScoredTransaction:
    return ScoredTransaction(
        id=row.id,
        occurred_at=row.occurred_at,
        amount=float(row.amount),
        model_score=row.model_score,
        decision=row.decision,  # type: ignore[arg-type]
        model_name=row.model_name,  # type: ignore[arg-type]
        features=Features.model_validate(row.features),
        created_at=row.created_at,
        scoring_ms=row.scoring_ms,
    )


class PostgresStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        create_tables(engine)
        ensure_scoring_ms_column(engine)

    def put(self, row: ScoredTransaction) -> None:
        self.put_many([row])

    def put_many(self, rows: list[ScoredTransaction]) -> None:
        with Session(self._engine) as session:
            for row in rows:
                session.merge(_to_orm(row))
            session.commit()

    def get(self, id: UUID) -> ScoredTransaction | None:
        with Session(self._engine) as session:
            found = session.get(ScoredTransactionRow, id)
            return None if found is None else _from_orm(found)

    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]:
        cap = min(limit, LIST_CAP)
        with Session(self._engine) as session:
            stmt = (
                select(ScoredTransactionRow)
                .order_by(ScoredTransactionRow.created_at.desc())
                .limit(cap)
            )
            return [_from_orm(row) for row in session.scalars(stmt)]

    def _load_all(self) -> list[ScoredTransaction]:
        with Session(self._engine) as session:
            stmt = select(ScoredTransactionRow)
            return [_from_orm(row) for row in session.scalars(stmt)]

    def stats(self, *, now: datetime) -> StatsResponse:
        cutoff = now - timedelta(seconds=THROUGHPUT_WINDOW_S)
        with Session(self._engine) as session:
            processed = session.scalar(select(func.count()).select_from(ScoredTransactionRow)) or 0
            flagged = (
                session.scalar(
                    select(func.count())
                    .select_from(ScoredTransactionRow)
                    .where(ScoredTransactionRow.decision.in_(tuple(FLAGGED)))
                )
                or 0
            )
            recent = (
                session.scalar(
                    select(func.count())
                    .select_from(ScoredTransactionRow)
                    .where(ScoredTransactionRow.created_at >= cutoff)
                )
                or 0
            )
            timed = list(
                session.scalars(
                    select(ScoredTransactionRow.scoring_ms)
                    .where(ScoredTransactionRow.scoring_ms.is_not(None))
                    .order_by(ScoredTransactionRow.created_at.desc())
                    .limit(LATENCY_WINDOW)
                )
            )
        values = [int(ms) for ms in timed if ms is not None]
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

    def list_alerts(
        self,
        *,
        filter: AlertFilter,
        sort: AlertSort,
        dir: AlertDir,
        offset: int,
        limit: int,
    ) -> AlertsResponse:
        where = _alerts_where(filter)
        column = _ALERT_SORT[sort]
        order = column.desc() if dir == "desc" else column.asc()
        with Session(self._engine) as session:
            total = (
                session.scalar(
                    select(func.count()).select_from(ScoredTransactionRow).where(where)
                )
                or 0
            )
            rows = session.scalars(
                select(ScoredTransactionRow).where(where).order_by(order).offset(offset).limit(limit)
            )
            items = [_from_orm(row) for row in rows]
        return AlertsResponse(items=items, total=total, offset=offset, limit=limit)
