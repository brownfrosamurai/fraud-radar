from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from api.db import ScoredTransactionRow, create_tables
from api.schemas import Features, ScoredTransaction
from api.store import LIST_CAP


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
    )


def _from_orm(row: ScoredTransactionRow) -> ScoredTransaction:
    return ScoredTransaction(
        id=row.id,
        occurred_at=row.occurred_at,
        amount=row.amount,
        model_score=row.model_score,
        decision=row.decision,  # type: ignore[arg-type]
        model_name=row.model_name,  # type: ignore[arg-type]
        features=Features.model_validate(row.features),
        created_at=row.created_at,
    )


class PostgresStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        create_tables(engine)

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
            order = [ScoredTransactionRow.created_at.desc()]
            if self._engine.dialect.name == "sqlite":
                order.append(text("rowid DESC"))
            stmt = select(ScoredTransactionRow).order_by(*order).limit(cap)
            return [_from_orm(row) for row in session.scalars(stmt)]
