from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Float, Integer, Numeric, String, create_engine, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class ScoredTransactionRow(Base):
    __tablename__ = "scored_transactions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric, nullable=False)
    model_score: Mapped[float] = mapped_column(Float, nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    model_name: Mapped[str] = mapped_column(String(32), nullable=False)
    features: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scoring_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


def create_engine_from_url(url: str) -> Engine:
    return create_engine(url)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def ensure_scoring_ms_column(engine: Engine) -> None:
    statements = (
        "ALTER TABLE scored_transactions ADD COLUMN IF NOT EXISTS scoring_ms INTEGER",
        "ALTER TABLE scored_transactions ADD COLUMN scoring_ms INTEGER",
    )
    for index, statement in enumerate(statements):
        try:
            with engine.begin() as conn:
                conn.execute(text(statement))
            return
        except Exception as exc:
            message = str(exc).lower()
            duplicate = "duplicate column" in message or "already exists" in message
            syntax = "syntax" in message
            if duplicate or (syntax and index == 0):
                if duplicate:
                    return
                continue
            raise

