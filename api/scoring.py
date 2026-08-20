from typing import Literal

Decision = Literal["ALLOW", "REVIEW", "BLOCK"]


def decide(score: float, amount: float) -> Decision:
    if score >= 0.9 or (score >= 0.6 and amount > 500):
        return "BLOCK"
    if score >= 0.4:
        return "REVIEW"
    return "ALLOW"
