# Slice 0 Walking Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a running FastAPI + one React card that scores a transaction into ALLOW/REVIEW/BLOCK, shows a canned explanation, and fires a scripted 50-tx / 2s / 30s attack-burst — no Kafka, no real model, no Postgres.

**Architecture:** In-process walking skeleton. `score()` returns canned percentiles; `decide(score, amount)` is the real rules engine; scored rows live in `InMemoryStore`; `POST /demo/burst` injects 50 high-amount rows and owns cooldown. The dashboard is one card: poll `GET /transactions?limit=1`, render decision + GET-only explanation, burst button calls `POST /demo/burst`. Nginx (compose) and Vite (dev) proxy `/api/*` onto the FastAPI app so the browser never talks to a second origin.

**Tech Stack:** Python 3.12, FastAPI 0.115, Pydantic v2, pytest, httpx, uvicorn; Node 22, Vite 6, React 18, TypeScript 5.6, Tailwind 3.4, Vitest, Testing Library; Docker Compose.

**Spec:** `docs/fraud-radar-project-plan.md` §3.1 and §8 Slice 0 (canonical copy also at `Portfolio Projects/Fraud Radar/fraud-radar-project-plan.md` in the Obsidian vault). Design: vault `Fraud Radar - Vertical-Slice Design Doc.md`. Tests to cover: vault `Fraud Radar - Test Plan.md` decide() boundaries + burst 429. Do not implement Slice 1–5 in this plan.

## Global Constraints

- `model_score` is a float in `[0, 1]`, higher = more anomalous (canned percentiles in Slice 0; real CDF is Slice 1).
- `decide(score: float, amount: float) -> Literal["ALLOW", "REVIEW", "BLOCK"]`: BLOCK if `score >= 0.9` or (`score >= 0.6` and `amount > 500`); REVIEW if `score >= 0.4`; else ALLOW. Inclusive thresholds.
- Canned `score(transaction)`: `amount > 500` → `0.93`; `amount > 100` → `0.55`; else `0.12`.
- Do not persist `explanation`. Return it only from `GET /transactions/{id}/explanation`.
- Canned explanation feature names are `Amount`, `V14`, `V10`, `V4`, `V12` — never invented names like `geo_mismatch`.
- Burst: size 50, window_ms 2000, cooldown 30s. Payload amounts `> 500` so they BLOCK. Slice 0 injects all 50 immediately (window_ms is still reported as 2000).
- Dashboard talks only to FastAPI via `/api` proxy. `POST /demo/burst` 429 on cooldown (`accepted: false`); 503 is Slice 2+ (no producer process here).
- The walking-skeleton UI is one card and **does** include the burst button.
- `model_name` is `"isolation_forest"` for every Slice 0 row.
- Python 3.12, Node 22. Desktop-only UI (1280px+). Decision colors: `--allow: #16a34a`, `--review: #f59e0b`, `--block: #dc2626`, `--bg: #121212`.
- No Kafka, no Postgres, no WebSocket, no real SHAP, no Isolation Forest training.
- Type hints on all Python public functions. Tests use pytest / Vitest, not ad-hoc scripts.

## File structure (this plan creates)

| File | Responsibility |
|---|---|
| `.gitignore` | Python, Node, OS, venv, dist, `__pycache__` |
| `pyproject.toml` | API package, deps, pytest `pythonpath` |
| `api/__init__.py` | Package marker |
| `api/schemas.py` | Pydantic request/response models |
| `api/scoring.py` | `score`, `decide`, `explain` |
| `api/store.py` | `InMemoryStore` |
| `api/burst.py` | `BurstController` constants + trigger |
| `api/main.py` | `create_app()`, HTTP routes |
| `api/tests/conftest.py` | `sample_features()`, TestClient factory |
| `api/tests/test_decide.py` | Ruleset boundaries |
| `api/tests/test_score_endpoint.py` | `POST /score`, `GET /transactions` |
| `api/tests/test_explanation.py` | GET explanation + 404 |
| `api/tests/test_burst.py` | 50 inject, 429 cooldown |
| `api/Dockerfile` | Python 3.12 slim, uvicorn :8000 |
| `dashboard/package.json` | Vite React TS app + vitest |
| `dashboard/vite.config.ts` | `/api` proxy + vitest |
| `dashboard/tsconfig.json` | Strict TS |
| `dashboard/tailwind.config.js` | Content paths |
| `dashboard/postcss.config.js` | tailwind + autoprefixer |
| `dashboard/index.html` | Mount point |
| `dashboard/src/index.css` | Semantic CSS variables |
| `dashboard/src/main.tsx` | React mount |
| `dashboard/src/api.ts` | Typed fetch helpers |
| `dashboard/src/App.tsx` | One `ScoreCard` |
| `dashboard/src/ScoreCard.tsx` | Poll, explain, burst button |
| `dashboard/src/ScoreCard.test.tsx` | Component tests |
| `dashboard/nginx.conf` | `/api/` reverse proxy |
| `dashboard/Dockerfile` | Multi-stage Vite build + nginx |
| `docker-compose.yml` | `api` + `dashboard` |
| `README.md` | How to run Slice 0 |

---

### Task 1: `decide(score, amount)`

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `api/__init__.py`
- Create: `api/scoring.py`
- Test: `api/tests/test_decide.py`

**Interfaces:**
- Consumes: nothing
- Produces: `decide(score: float, amount: float) -> Literal["ALLOW", "REVIEW", "BLOCK"]`

- [ ] **Step 1: Init git and write the failing test**

```bash
cd /Users/oluwafemi/Documents/development/portfolio/fraud-radar
git init
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
.DS_Store
node_modules/
dashboard/dist/
*.egg-info/
.ruff_cache/
```

`pyproject.toml`:

```toml
[project]
name = "fraud-radar-api"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi==0.115.6",
  "pydantic==2.10.4",
  "uvicorn[standard]==0.34.0",
  "httpx==0.28.1",
]

[project.optional-dependencies]
dev = ["pytest==8.3.4"]

[build-system]
requires = ["setuptools>=75"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["api*"]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["api/tests"]
```

`api/__init__.py` — empty.

`api/tests/test_decide.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest api/tests/test_decide.py -v
```

Expected: FAIL with `ModuleNotFoundError: api.scoring` or `cannot import name 'decide'`.

- [ ] **Step 3: Write minimal implementation**

`api/scoring.py`:

```python
from typing import Literal

Decision = Literal["ALLOW", "REVIEW", "BLOCK"]


def decide(score: float, amount: float) -> Decision:
    if score >= 0.9 or (score >= 0.6 and amount > 500):
        return "BLOCK"
    if score >= 0.4:
        return "REVIEW"
    return "ALLOW"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest api/tests/test_decide.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add .gitignore pyproject.toml api/__init__.py api/scoring.py api/tests/test_decide.py
git commit -m "feat: add decide(score, amount) ruleset"
```

---

### Task 2: Schemas, canned `score()`, in-memory store, `POST /score`, `GET /transactions`

**Files:**
- Create: `api/schemas.py`
- Create: `api/store.py`
- Create: `api/main.py`
- Create: `api/tests/conftest.py`
- Modify: `api/scoring.py`
- Test: `api/tests/test_score_endpoint.py`

**Interfaces:**
- Consumes: `decide(score: float, amount: float) -> Decision`
- Produces:
  - `class Features` with `Time: float` and `V1`–`V28: float`
  - `class ScoreRequest`: `transaction_id: UUID`, `occurred_at: datetime`, `amount: float`, `features: Features`
  - `class ScoredTransaction`: `id: UUID`, `occurred_at: datetime`, `amount: float`, `model_score: float`, `decision: Decision`, `model_name: Literal["isolation_forest", "autoencoder"]`, `features: Features`, `created_at: datetime`
  - `score(transaction: ScoreRequest) -> float`
  - `InMemoryStore.put(row: ScoredTransaction) -> None`
  - `InMemoryStore.get(id: UUID) -> ScoredTransaction | None`
  - `InMemoryStore.list_recent(limit: int = 50) -> list[ScoredTransaction]` (newest first, cap 50)
  - `create_app(store: InMemoryStore | None = None) -> FastAPI`
  - `POST /score` → `ScoredTransaction` (no `explanation` field)
  - `GET /transactions?limit=1` → `list[ScoredTransaction]`
  - `GET /health` → `{"status": "ok"}`

- [ ] **Step 1: Write the failing tests**

`api/tests/conftest.py`:

```python
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from api.store import InMemoryStore


def sample_features(**overrides: float) -> dict[str, float]:
    data = {"Time": 0.0}
    for i in range(1, 29):
        data[f"V{i}"] = 0.0
    data.update(overrides)
    return data


def sample_request(amount: float = 20.0) -> dict:
    return {
        "transaction_id": str(uuid4()),
        "occurred_at": datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        "amount": amount,
        "features": sample_features(),
    }


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def client(store: InMemoryStore) -> TestClient:
    return TestClient(create_app(store=store))
```

`api/tests/test_score_endpoint.py`:

```python
from api.scoring import score
from api.tests.conftest import sample_request


def test_score_canned_percentiles() -> None:
    from api.schemas import ScoreRequest

    low = ScoreRequest.model_validate(sample_request(amount=20.0))
    mid = ScoreRequest.model_validate(sample_request(amount=150.0))
    high = ScoreRequest.model_validate(sample_request(amount=600.0))
    assert score(low) == 0.12
    assert score(mid) == 0.55
    assert score(high) == 0.93


def test_post_score_low_amount_allows(client) -> None:
    payload = sample_request(amount=20.0)
    res = client.post("/score", json=payload)
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == payload["transaction_id"]
    assert body["model_score"] == 0.12
    assert body["decision"] == "ALLOW"
    assert body["model_name"] == "isolation_forest"
    assert "explanation" not in body


def test_post_score_mid_amount_reviews(client) -> None:
    res = client.post("/score", json=sample_request(amount=150.0))
    assert res.status_code == 200
    assert res.json()["decision"] == "REVIEW"
    assert res.json()["model_score"] == 0.55


def test_post_score_high_amount_blocks(client) -> None:
    res = client.post("/score", json=sample_request(amount=600.0))
    assert res.status_code == 200
    assert res.json()["decision"] == "BLOCK"
    assert res.json()["model_score"] == 0.93


def test_post_score_rejects_malformed(client) -> None:
    res = client.post("/score", json={"amount": 10})
    assert res.status_code == 422


def test_get_transactions_newest_first(client) -> None:
    first = client.post("/score", json=sample_request(amount=20.0)).json()
    second = client.post("/score", json=sample_request(amount=600.0)).json()
    res = client.get("/transactions", params={"limit": 50})
    assert res.status_code == 200
    rows = res.json()
    assert [row["id"] for row in rows] == [second["id"], first["id"]]


def test_get_transactions_caps_at_50(client) -> None:
    for _ in range(51):
        client.post("/score", json=sample_request(amount=20.0))
    rows = client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50


def test_health(client) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest api/tests/test_score_endpoint.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `api.main` / `api.schemas` / `score`.

- [ ] **Step 3: Write minimal implementation**

`api/schemas.py` — declare `Time` plus `V1` through `V28` as `float` on `Features` (all required). Also:

```python
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
```

Append to `api/scoring.py`. Merge `Protocol` into the existing `typing` import (`from typing import Literal, Protocol`). Do not import `api.schemas` from this file.

```python
from typing import Protocol


class HasAmount(Protocol):
    amount: float


def score(transaction: HasAmount) -> float:
    if transaction.amount > 500:
        return 0.93
    if transaction.amount > 100:
        return 0.55
    return 0.12
```

`api/store.py`:

```python
from uuid import UUID

from api.schemas import ScoredTransaction


class InMemoryStore:
    def __init__(self) -> None:
        self._rows: dict[UUID, ScoredTransaction] = {}
        self._order: list[UUID] = []

    def put(self, row: ScoredTransaction) -> None:
        if row.id not in self._rows:
            self._order.append(row.id)
        self._rows[row.id] = row

    def get(self, id: UUID) -> ScoredTransaction | None:
        return self._rows.get(id)

    def list_recent(self, limit: int = 50) -> list[ScoredTransaction]:
        ids = list(reversed(self._order))[: min(limit, 50)]
        return [self._rows[i] for i in ids]
```

`api/main.py`:

```python
from datetime import datetime, timezone

from fastapi import FastAPI, Query

from api.schemas import ScoreRequest, ScoredTransaction
from api.scoring import decide, score
from api.store import InMemoryStore


def create_app(store: InMemoryStore | None = None) -> FastAPI:
    app = FastAPI(title="Fraud Radar")
    app.state.store = store or InMemoryStore()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/score", response_model=ScoredTransaction)
    def post_score(body: ScoreRequest) -> ScoredTransaction:
        model_score = score(body)
        row = ScoredTransaction(
            id=body.transaction_id,
            occurred_at=body.occurred_at,
            amount=body.amount,
            model_score=model_score,
            decision=decide(model_score, body.amount),
            model_name="isolation_forest",
            features=body.features,
            created_at=datetime.now(timezone.utc),
        )
        app.state.store.put(row)
        return row

    @app.get("/transactions", response_model=list[ScoredTransaction])
    def get_transactions(limit: int = Query(default=50, ge=1, le=50)) -> list[ScoredTransaction]:
        return app.state.store.list_recent(limit=limit)

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest api/tests/test_decide.py api/tests/test_score_endpoint.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add api/schemas.py api/store.py api/main.py api/scoring.py api/tests/conftest.py api/tests/test_score_endpoint.py
git commit -m "feat: add POST /score and in-memory transaction store"
```

---

### Task 3: `explain()` and `GET /transactions/{id}/explanation`

**Files:**
- Modify: `api/scoring.py`
- Modify: `api/main.py`
- Test: `api/tests/test_explanation.py`

**Interfaces:**
- Consumes: `InMemoryStore.get(id: UUID) -> ScoredTransaction | None`
- Produces:
  - `CANNED_EXPLANATION: list[FeatureContribution]` with exactly `Amount=0.42`, `V14=0.21`, `V10=0.15`, `V4=0.11`, `V12=0.08`
  - `explain(transaction: ScoredTransaction, model: str = "isolation_forest") -> list[FeatureContribution]`
  - `GET /transactions/{id}/explanation` → `ExplanationResponse`; missing id → 404 `{"detail": "transaction not found"}`

- [ ] **Step 1: Write the failing test**

`api/tests/test_explanation.py`:

```python
from uuid import uuid4

from api.tests.conftest import sample_request


def test_explanation_404_when_unscored(client) -> None:
    res = client.get(f"/transactions/{uuid4()}/explanation")
    assert res.status_code == 404
    assert res.json()["detail"] == "transaction not found"


def test_explanation_canned_features_after_score(client) -> None:
    scored = client.post("/score", json=sample_request(amount=600.0)).json()
    res = client.get(f"/transactions/{scored['id']}/explanation")
    assert res.status_code == 200
    body = res.json()
    assert body["transaction_id"] == scored["id"]
    names = [item["feature"] for item in body["explanation"]]
    assert names == ["Amount", "V14", "V10", "V4", "V12"]
    assert [item["contribution"] for item in body["explanation"]] == [
        0.42,
        0.21,
        0.15,
        0.11,
        0.08,
    ]
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest api/tests/test_explanation.py -v
```

Expected: FAIL with 404 on the scored path (route missing) or `explain` missing.

- [ ] **Step 3: Write minimal implementation**

In `api/scoring.py`:

```python
CANNED_EXPLANATION = [
    {"feature": "Amount", "contribution": 0.42},
    {"feature": "V14", "contribution": 0.21},
    {"feature": "V10", "contribution": 0.15},
    {"feature": "V4", "contribution": 0.11},
    {"feature": "V12", "contribution": 0.08},
]


def explain(transaction: object, model: str = "isolation_forest") -> list[dict[str, float | str]]:
    return list(CANNED_EXPLANATION)
```

In `api/main.py` add:

```python
from uuid import UUID

from fastapi import HTTPException

from api.schemas import ExplanationResponse
from api.scoring import explain


@app.get("/transactions/{transaction_id}/explanation", response_model=ExplanationResponse)
def get_explanation(transaction_id: UUID) -> ExplanationResponse:
    row = app.state.store.get(transaction_id)
    if row is None:
        raise HTTPException(status_code=404, detail="transaction not found")
    return ExplanationResponse(transaction_id=transaction_id, explanation=explain(row))
```

Register this route on the app inside `create_app`, alongside the existing routes. Keep the path `/transactions/{transaction_id}/explanation` — do not add a competing `/transactions/{id}` in this slice.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest api/tests -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add api/scoring.py api/main.py api/tests/test_explanation.py
git commit -m "feat: add on-demand canned explanation endpoint"
```

---

### Task 4: `POST /demo/burst`

**Files:**
- Create: `api/burst.py`
- Modify: `api/main.py`
- Modify: `api/tests/conftest.py`
- Test: `api/tests/test_burst.py`

**Interfaces:**
- Consumes: `InMemoryStore.put`, `score`, `decide`, `Features`, `ScoreRequest`
- Produces:
  - `BURST_SIZE = 50`, `BURST_WINDOW_MS = 2000`, `COOLDOWN_SECONDS = 30`
  - `BurstController(store, clock: Callable[[], datetime])`
  - `BurstController.trigger() -> BurstResponse` on success (`accepted=True`, `cooldown_seconds=30`)
  - `CooldownActive(remaining: int)` exception when cooling down
  - `POST /demo/burst` → 200 + `BurstResponse` or 429 + `BurstResponse(accepted=False, ...)`
  - Injected rows: `amount = 501 + i` for `i in 0..49`, so every row is BLOCK

- [ ] **Step 1: Write the failing test**

Update `api/tests/conftest.py` so `create_app` accepts `clock`:

```python
from datetime import datetime, timezone

from api.main import create_app
from api.store import InMemoryStore


class FrozenClock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


@pytest.fixture
def clock() -> FrozenClock:
    return FrozenClock(datetime(2026, 1, 1, tzinfo=timezone.utc))


@pytest.fixture
def client(store: InMemoryStore, clock: FrozenClock) -> TestClient:
    return TestClient(create_app(store=store, clock=clock))
```

`api/tests/test_burst.py`:

```python
from datetime import timedelta

from api.burst import BURST_SIZE, BURST_WINDOW_MS, COOLDOWN_SECONDS


def test_burst_injects_50_blocking_rows(client, store) -> None:
    res = client.post("/demo/burst")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "accepted": True,
        "size": BURST_SIZE,
        "window_ms": BURST_WINDOW_MS,
        "cooldown_seconds": COOLDOWN_SECONDS,
    }
    rows = store.list_recent(limit=50)
    assert len(rows) == 50
    assert all(row.decision == "BLOCK" for row in rows)
    assert all(row.amount > 500 for row in rows)


def test_burst_cooldown_is_429_not_queued(client, clock) -> None:
    first = client.post("/demo/burst")
    assert first.status_code == 200
    second = client.post("/demo/burst")
    assert second.status_code == 429
    body = second.json()
    assert body["accepted"] is False
    assert body["size"] == 50
    assert 1 <= body["cooldown_seconds"] <= 30
    rows = client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50


def test_burst_accepted_after_cooldown(client, clock) -> None:
    client.post("/demo/burst")
    clock.t = clock.t + timedelta(seconds=31)
    res = client.post("/demo/burst")
    assert res.status_code == 200
    assert res.json()["accepted"] is True
    rows = client.get("/transactions", params={"limit": 50}).json()
    assert len(rows) == 50
```

After two accepted bursts the store holds 100 rows but `list_recent` caps at 50 — the last test asserts 50, which is correct.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest api/tests/test_burst.py -v
```

Expected: FAIL with `create_app() got an unexpected keyword argument 'clock'` or 404 on `/demo/burst`.

- [ ] **Step 3: Write minimal implementation**

`api/burst.py`:

```python
from collections.abc import Callable
from datetime import datetime, timezone
from uuid import uuid4

from api.schemas import BurstResponse, Features, ScoreRequest, ScoredTransaction
from api.scoring import decide, score
from api.store import InMemoryStore

BURST_SIZE = 50
BURST_WINDOW_MS = 2000
COOLDOWN_SECONDS = 30


class CooldownActive(Exception):
    def __init__(self, remaining: int) -> None:
        self.remaining = remaining


def _zero_features() -> Features:
    payload = {"Time": 0.0, **{f"V{i}": 0.0 for i in range(1, 29)}}
    return Features.model_validate(payload)


class BurstController:
    def __init__(
        self,
        store: InMemoryStore,
        clock: Callable[[], datetime],
    ) -> None:
        self._store = store
        self._clock = clock
        self._last_burst_at: datetime | None = None

    def trigger(self) -> BurstResponse:
        now = self._clock()
        if self._last_burst_at is not None:
            elapsed = (now - self._last_burst_at).total_seconds()
            remaining = int(COOLDOWN_SECONDS - elapsed)
            if remaining > 0:
                raise CooldownActive(remaining)
        for i in range(BURST_SIZE):
            req = ScoreRequest(
                transaction_id=uuid4(),
                occurred_at=now,
                amount=501.0 + i,
                features=_zero_features(),
            )
            model_score = score(req)
            self._store.put(
                ScoredTransaction(
                    id=req.transaction_id,
                    occurred_at=req.occurred_at,
                    amount=req.amount,
                    model_score=model_score,
                    decision=decide(model_score, req.amount),
                    model_name="isolation_forest",
                    features=req.features,
                    created_at=now,
                )
            )
        self._last_burst_at = now
        return BurstResponse(
            accepted=True,
            size=BURST_SIZE,
            window_ms=BURST_WINDOW_MS,
            cooldown_seconds=COOLDOWN_SECONDS,
        )
```

In `create_app(store=None, clock=None)`:

```python
from collections.abc import Callable
from datetime import datetime, timezone

from fastapi import HTTPException

from api.burst import BURST_SIZE, BURST_WINDOW_MS, BurstController, CooldownActive
from api.schemas import BurstResponse


def create_app(
    store: InMemoryStore | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    app = FastAPI(title="Fraud Radar")
    app.state.store = store or InMemoryStore()
    time_fn = clock or (lambda: datetime.now(timezone.utc))
    app.state.burst = BurstController(store=app.state.store, clock=time_fn)

    @app.post("/demo/burst", response_model=BurstResponse)
    def post_burst() -> BurstResponse:
        try:
            return app.state.burst.trigger()
        except CooldownActive as exc:
            raise HTTPException(
                status_code=429,
                detail={
                    "accepted": False,
                    "size": BURST_SIZE,
                    "window_ms": BURST_WINDOW_MS,
                    "cooldown_seconds": exc.remaining,
                },
            ) from exc

    # existing routes...
    return app
```

FastAPI 429 `detail` as a dict means the client JSON is `{"detail": {...}}`, but the test expects the BurstResponse at the top level. Do **not** use `HTTPException` for the 429 body. Return a `JSONResponse` instead:

```python
from fastapi.responses import JSONResponse

@app.post("/demo/burst")
def post_burst():
    try:
        return app.state.burst.trigger()
    except CooldownActive as exc:
        return JSONResponse(
            status_code=429,
            content={
                "accepted": False,
                "size": BURST_SIZE,
                "window_ms": BURST_WINDOW_MS,
                "cooldown_seconds": exc.remaining,
            },
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest api/tests -v
```

Expected: all PASS, including existing score tests (they use the new `clock` fixture).

- [ ] **Step 5: Commit**

```bash
git add api/burst.py api/main.py api/tests/conftest.py api/tests/test_burst.py
git commit -m "feat: add bounded POST /demo/burst with cooldown"
```

---

### Task 5: Walking-skeleton dashboard card

**Files:**
- Create: `dashboard/package.json`
- Create: `dashboard/vite.config.ts`
- Create: `dashboard/tsconfig.json`
- Create: `dashboard/tsconfig.app.json`
- Create: `dashboard/tsconfig.node.json`
- Create: `dashboard/tailwind.config.js`
- Create: `dashboard/postcss.config.js`
- Create: `dashboard/index.html`
- Create: `dashboard/src/vite-env.d.ts`
- Create: `dashboard/src/index.css`
- Create: `dashboard/src/main.tsx`
- Create: `dashboard/src/api.ts`
- Create: `dashboard/src/App.tsx`
- Create: `dashboard/src/ScoreCard.tsx`
- Test: `dashboard/src/ScoreCard.test.tsx`

**Interfaces:**
- Consumes: `GET /health` unused; `POST /score`; `GET /transactions?limit=1`; `GET /transactions/{id}/explanation`; `POST /demo/burst`
- Produces: `ScoreCard` that (1) on mount POSTs one sample tx then GETs explanation, (2) polls `GET /transactions?limit=1` every 1000ms, (3) burst button POSTs `/demo/burst` and disables for `cooldown_seconds`, (4) 429 keeps the button disabled. Keyboard-operable `<button>` with visible focus ring.

Use `npm create vite@6 dashboard -- --template react-ts` if it scaffolds equivalent files; then replace `src/App.tsx` and add the files below. Do not add React Router, Recharts, or extra views.

- [ ] **Step 1: Scaffold and write the failing component test**

```bash
cd /Users/oluwafemi/Documents/development/portfolio/fraud-radar
npm create vite@6 dashboard -- --template react-ts
cd dashboard
npm install
npm install -D tailwindcss@3.4.17 postcss autoprefixer vitest@2.1.9 jsdom @testing-library/react @testing-library/user-event @testing-library/jest-dom
npx tailwindcss init -p
```

`dashboard/vite.config.ts`:

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
```

`dashboard/src/test-setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
```

`dashboard/src/api.ts`:

```ts
export type Decision = "ALLOW" | "REVIEW" | "BLOCK";

export type ScoredTransaction = {
  id: string;
  occurred_at: string;
  amount: number;
  model_score: number;
  decision: Decision;
  model_name: "isolation_forest" | "autoencoder";
};

export type FeatureContribution = { feature: string; contribution: number };

export type BurstResponse = {
  accepted: boolean;
  size: number;
  window_ms: number;
  cooldown_seconds: number;
};

export async function postScore(amount: number): Promise<ScoredTransaction> {
  const features: Record<string, number> = { Time: 0 };
  for (let i = 1; i <= 28; i += 1) features[`V${i}`] = 0;
  const res = await fetch("/api/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transaction_id: crypto.randomUUID(),
      occurred_at: new Date().toISOString(),
      amount,
      features,
    }),
  });
  if (!res.ok) throw new Error("score failed");
  return res.json();
}

export async function fetchLatest(): Promise<ScoredTransaction | null> {
  const res = await fetch("/api/transactions?limit=1");
  if (!res.ok) throw new Error("list failed");
  const rows: ScoredTransaction[] = await res.json();
  return rows[0] ?? null;
}

export async function fetchExplanation(
  id: string,
): Promise<FeatureContribution[]> {
  const res = await fetch(`/api/transactions/${id}/explanation`);
  if (!res.ok) throw new Error("explain failed");
  const body = await res.json();
  return body.explanation;
}

export async function triggerBurst(): Promise<{ status: number; body: BurstResponse }> {
  const res = await fetch("/api/demo/burst", { method: "POST" });
  const body = (await res.json()) as BurstResponse;
  return { status: res.status, body };
}
```

`dashboard/src/ScoreCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ScoreCard } from "./ScoreCard";

const scored = {
  id: "11111111-1111-1111-1111-111111111111",
  occurred_at: "2026-01-01T00:00:00Z",
  amount: 20,
  model_score: 0.12,
  decision: "ALLOW",
  model_name: "isolation_forest",
};

const blocked = { ...scored, amount: 600, model_score: 0.93, decision: "BLOCK" };

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/score") && init?.method === "POST") {
        return new Response(JSON.stringify(scored), { status: 200 });
      }
      if (url.includes("/explanation")) {
        return new Response(
          JSON.stringify({
            transaction_id: scored.id,
            explanation: [
              { feature: "Amount", contribution: 0.42 },
              { feature: "V14", contribution: 0.21 },
            ],
          }),
          { status: 200 },
        );
      }
      if (url.includes("/transactions")) {
        return new Response(JSON.stringify([scored]), { status: 200 });
      }
      if (url.endsWith("/demo/burst") && init?.method === "POST") {
        return new Response(
          JSON.stringify({
            accepted: true,
            size: 50,
            window_ms: 2000,
            cooldown_seconds: 30,
          }),
          { status: 200 },
        );
      }
      return new Response("not found", { status: 404 });
    }),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("renders decision and canned explanation feature names", async () => {
  render(<ScoreCard />);
  expect(await screen.findByText("ALLOW")).toBeInTheDocument();
  expect(await screen.findByText("Amount")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /inject synthetic burst/i })).toBeEnabled();
});

test("burst button disables for cooldown_seconds", async () => {
  const user = userEvent.setup();
  render(<ScoreCard />);
  await screen.findByText("ALLOW");
  await user.click(screen.getByRole("button", { name: /inject synthetic burst/i }));
  expect(await screen.findByRole("button", { name: /cooldown 30s/i })).toBeDisabled();
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd dashboard && npx vitest run src/ScoreCard.test.tsx
```

Expected: FAIL — `ScoreCard` is not defined.

- [ ] **Step 3: Write minimal implementation**

`dashboard/tailwind.config.js` content: `./index.html`, `./src/**/*.{ts,tsx}`.

`dashboard/src/index.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

:root {
  --allow: #16a34a;
  --review: #f59e0b;
  --block: #dc2626;
  --bg: #121212;
}

body {
  margin: 0;
  background: var(--bg);
  color: #e8e8e8;
  font-family: "IBM Plex Sans", ui-sans-serif, sans-serif;
}

button:focus-visible {
  outline: 2px solid #3ec6ff;
  outline-offset: 2px;
}
```

`dashboard/index.html` — add Google fonts IBM Plex Sans + IBM Plex Mono (weights 400,500,600). Title: `Fraud Radar`.

`dashboard/src/ScoreCard.tsx`:

```tsx
import { useEffect, useState } from "react";
import {
  fetchExplanation,
  fetchLatest,
  postScore,
  triggerBurst,
  type Decision,
  type FeatureContribution,
  type ScoredTransaction,
} from "./api";

const BADGE: Record<Decision, string> = {
  ALLOW: "var(--allow)",
  REVIEW: "var(--review)",
  BLOCK: "var(--block)",
};

export function ScoreCard() {
  const [tx, setTx] = useState<ScoredTransaction | null>(null);
  const [explanation, setExplanation] = useState<FeatureContribution[]>([]);
  const [cooldown, setCooldown] = useState(0);
  const [injecting, setInjecting] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const scored = await postScore(20);
      const latest = (await fetchLatest()) ?? scored;
      const expl = await fetchExplanation(latest.id);
      if (!cancelled) {
        setTx(latest);
        setExplanation(expl);
      }
    })();
    const poll = window.setInterval(async () => {
      const latest = await fetchLatest();
      if (!cancelled && latest) {
        setTx(latest);
        setExplanation(await fetchExplanation(latest.id));
      }
    }, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(poll);
    };
  }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const t = window.setInterval(() => setCooldown((c) => Math.max(0, c - 1)), 1000);
    return () => window.clearInterval(t);
  }, [cooldown]);

  async function onBurst() {
    setInjecting(true);
    const { status, body } = await triggerBurst();
    setInjecting(false);
    if (status === 200 && body.accepted) {
      setCooldown(body.cooldown_seconds);
      return;
    }
    if (status === 429) setCooldown(body.cooldown_seconds);
  }

  const disabled = injecting || cooldown > 0;
  const label = injecting
    ? "Injecting…"
    : cooldown > 0
      ? `Cooldown ${cooldown}s`
      : "Inject Synthetic Burst";

  return (
    <section className="mx-auto mt-16 w-[480px] border border-neutral-700 p-6">
      <p className="text-xs uppercase tracking-wide text-neutral-400">Fraud Radar · Slice 0</p>
      {tx ? (
        <>
          <p className="mt-4 font-mono text-2xl">${tx.amount.toFixed(2)}</p>
          <p className="font-mono text-sm text-neutral-400">score {tx.model_score.toFixed(2)}</p>
          <p className="mt-2 font-semibold" style={{ color: BADGE[tx.decision] }}>
            {tx.decision}
          </p>
          <ul className="mt-4 space-y-1 font-mono text-sm">
            {explanation.map((item) => (
              <li key={item.feature}>
                {item.feature} {item.contribution.toFixed(2)}
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-4 text-neutral-400">Waiting for transactions…</p>
      )}
      <button
        type="button"
        className="mt-6 bg-cyan-400 px-3 py-2 text-sm font-semibold text-black disabled:opacity-50"
        disabled={disabled}
        onClick={onBurst}
      >
        {label}
      </button>
    </section>
  );
}
```

`dashboard/src/App.tsx`:

```tsx
import { ScoreCard } from "./ScoreCard";

export default function App() {
  return <ScoreCard />;
}
```

`dashboard/src/main.tsx` — import `./index.css` and render `<App />`.

`dashboard/package.json` scripts: `"dev": "vite"`, `"build": "tsc -b && vite build"`, `"test": "vitest run"`, `"preview": "vite preview"`.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd dashboard && npm test
```

Expected: both ScoreCard tests PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard
git commit -m "feat: add Slice 0 score card with burst control"
```

---

### Task 6: Docker Compose bring-up + README

**Files:**
- Create: `api/Dockerfile`
- Create: `dashboard/Dockerfile`
- Create: `dashboard/nginx.conf`
- Create: `docker-compose.yml`
- Create: `README.md`

**Interfaces:**
- Consumes: `create_app` default `app`, Vite production build
- Produces: `docker compose up --build` serves API at `http://localhost:8000/health` and UI at `http://localhost:3000`; browser calls `/api/score` which nginx proxies to `http://api:8000/score`

- [ ] **Step 1: Write the failing smoke check script as a test file**

`api/tests/test_compose_config.py`:

```python
from pathlib import Path


def test_compose_exposes_api_and_dashboard() -> None:
    text = Path("docker-compose.yml").read_text()
    assert "8000:8000" in text
    assert "3000:80" in text
    assert "api:" in text
    assert "dashboard:" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest api/tests/test_compose_config.py -v
```

Expected: FAIL — `docker-compose.yml` not found.

- [ ] **Step 3: Write minimal implementation**

`api/Dockerfile`:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY api ./api
RUN pip install --no-cache-dir .
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

`dashboard/nginx.conf`:

```nginx
server {
  listen 80;
  location /api/ {
    proxy_pass http://api:8000/;
  }
  location / {
    root /usr/share/nginx/html;
    try_files $uri /index.html;
  }
}
```

`dashboard/Dockerfile`:

```dockerfile
FROM node:22-alpine AS build
WORKDIR /src
COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci
COPY dashboard ./
RUN npm run build

FROM nginx:1.27-alpine
COPY dashboard/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist /usr/share/nginx/html
```

Compose build context must be the repo root so `dashboard/Dockerfile` can `COPY dashboard/...`. Set `build.context: .` and `dockerfile: dashboard/Dockerfile` for the dashboard service; `dockerfile: api/Dockerfile` with context `.` for api (api Dockerfile copies `pyproject.toml` and `api/`).

`docker-compose.yml`:

```yaml
services:
  api:
    build:
      context: .
      dockerfile: api/Dockerfile
    ports:
      - "8000:8000"
  dashboard:
    build:
      context: .
      dockerfile: dashboard/Dockerfile
    ports:
      - "3000:80"
    depends_on:
      - api
```

`README.md`:

```markdown
# Fraud Radar

Real-time fraud scoring demo (Slice 0 walking skeleton).

## Run

```bash
docker compose up --build
```

Open http://localhost:3000 — one card polls the score API, shows ALLOW/REVIEW/BLOCK, and the burst button injects 50 high-risk rows with a 30s cooldown.

API: http://localhost:8000/health · OpenAPI: http://localhost:8000/docs

## Dev without Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn api.main:app --reload
```

```bash
cd dashboard && npm install && npm run dev
```

## Tests

```bash
pytest api/tests -v
cd dashboard && npm test
```
```

Generate `dashboard/package-lock.json` with `npm install` inside `dashboard` before the Docker build (the Dockerfile uses `npm ci`).

- [ ] **Step 4: Run tests and a compose smoke**

```bash
pytest api/tests -v
cd dashboard && npm test
docker compose up --build -d
curl -sf http://localhost:8000/health
curl -sf -o /dev/null -w "%{http_code}" http://localhost:3000
docker compose down
```

Expected: pytest + vitest PASS; curl health `{"status":"ok"}`; localhost:3000 returns 200.

- [ ] **Step 5: Commit**

```bash
git add api/Dockerfile dashboard/Dockerfile dashboard/nginx.conf docker-compose.yml README.md dashboard/package-lock.json
git commit -m "feat: add docker compose bring-up for Slice 0"
```

---

## Self-review (writing-plans)

**Spec coverage (Slice 0 only):**
- API contract `POST /score` + `decision` + `explanation` schema → Tasks 2–3
- `decide(score, amount)` inclusive ruleset → Task 1
- Canned percentile scores → Task 2
- GET-only explanation, Amount+V feature names → Task 3
- Scripted `POST /demo/burst` 50 / 2000ms / 30s + 429 → Task 4
- One dashboard card + burst button + polling → Task 5
- `docker compose up` → Task 6
- Out of this plan (correct): Kafka, Postgres, WebSocket, real models, SHAP, 503 producer-down, CI workflow

**Placeholder scan:** none remaining in task steps. Slice 0 injects burst rows immediately by design (window_ms still 2000).

**Type consistency:** `Decision`, `ScoredTransaction`, `BurstResponse`, `BURST_SIZE=50`, `COOLDOWN_SECONDS=30` are the same names from Task 1 through Task 5.
