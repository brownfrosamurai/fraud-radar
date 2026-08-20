from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

Decision = Literal["ALLOW", "REVIEW", "BLOCK"]
AlertFilter = Literal["all", "review", "block"]
AlertSort = Literal["created_at", "amount", "model_score", "decision"]
AlertDir = Literal["asc", "desc"]


class Features(BaseModel):
    Time: float
    V1: float
    V2: float
    V3: float
    V4: float
    V5: float
    V6: float
    V7: float
    V8: float
    V9: float
    V10: float
    V11: float
    V12: float
    V13: float
    V14: float
    V15: float
    V16: float
    V17: float
    V18: float
    V19: float
    V20: float
    V21: float
    V22: float
    V23: float
    V24: float
    V25: float
    V26: float
    V27: float
    V28: float


class ScoreRequest(BaseModel):
    transaction_id: UUID
    occurred_at: datetime
    amount: float
    features: Features


class ScoredTransaction(BaseModel):
    id: UUID
    occurred_at: datetime
    amount: float
    model_score: float
    decision: Decision
    model_name: Literal["isolation_forest", "autoencoder"]
    features: Features
    created_at: datetime
    scoring_ms: int | None = Field(default=None, exclude=True)


class StatsResponse(BaseModel):
    processed: int
    throughput_tx_per_s: float
    latency_p50_ms: int | None
    latency_p95_ms: int | None
    flagged: int


class AlertsResponse(BaseModel):
    items: list[ScoredTransaction]
    total: int
    offset: int
    limit: int


class FeatureContribution(BaseModel):
    feature: str
    contribution: float


class ExplanationResponse(BaseModel):
    transaction_id: UUID
    explanation: list[FeatureContribution]


class BurstResponse(BaseModel):
    accepted: bool
    size: int
    window_ms: int
    cooldown_seconds: int
