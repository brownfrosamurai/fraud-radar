import pytest

from api.scoring import decide


@pytest.mark.parametrize(
    ("score", "amount", "expected"),
    [
        (0.9, 1.0, "BLOCK"),
        (0.95, 50.0, "BLOCK"),
        (0.6, 500.01, "BLOCK"),
        (0.6, 500.0, "REVIEW"),
        (0.70, 400.0, "REVIEW"),
        (0.4, 10.0, "REVIEW"),
        (0.39, 10.0, "ALLOW"),
        (0.0, 10_000.0, "ALLOW"),
    ],
)
def test_decide_boundaries(score: float, amount: float, expected: str) -> None:
    assert decide(score, amount) == expected
