from datetime import datetime
from uuid import UUID

from sqlalchemy import select
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
from api.store import LIST_CAP, list_alerts_from_rows, stats_from_rows


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
        return stats_from_rows(self._load_all(), now=now)

    def list_alerts(
        self,
        *,
        filter: AlertFilter,
        sort: AlertSort,
        dir: AlertDir,
        offset: int,
        limit: int,
    ) -> AlertsResponse:
        return list_alerts_from_rows(
            self._load_all(),
            filter=filter,
            sort=sort,
            dir=dir,
            offset=offset,
            limit=limit,
        )
