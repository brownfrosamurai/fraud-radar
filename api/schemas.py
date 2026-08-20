from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

Decision = Literal["ALLOW", "REVIEW", "BLOCK"]


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
