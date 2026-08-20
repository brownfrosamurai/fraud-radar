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


CANNED_EXPLANATION = [
    {"feature": "Amount", "contribution": 0.42},
    {"feature": "V14", "contribution": 0.21},
    {"feature": "V10", "contribution": 0.15},
    {"feature": "V4", "contribution": 0.11},
    {"feature": "V12", "contribution": 0.08},
]


def explain(transaction: object, model: str = "isolation_forest") -> list[dict[str, float | str]]:
    return list(CANNED_EXPLANATION)
