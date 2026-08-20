from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Float, Numeric, String, create_engine
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


def create_engine_from_url(url: str) -> Engine:
    return create_engine(url)


def create_tables(engine: Engine) -> None:
    Base.metadata.create_all(engine)
