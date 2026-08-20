from typing import Literal

from api.schemas import ScoreRequest
from api.serve import BundleScorer, Scorer, load_bundle

Decision = Literal["ALLOW", "REVIEW", "BLOCK"]


def decide(score: float, amount: float) -> Decision:
    if score >= 0.9 or (score >= 0.6 and amount > 500):
        return "BLOCK"
    if score >= 0.4:
        return "REVIEW"
    return "ALLOW"


def score(
    transaction: ScoreRequest,
    model: str = "isolation_forest",
    scorer: Scorer | None = None,
) -> float:
    resolved = scorer or BundleScorer(load_bundle())
    return resolved.score(transaction, model=model)
