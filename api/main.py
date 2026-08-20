from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from api.burst import BURST_SIZE, BURST_WINDOW_MS, BurstController, CooldownActive
from api.schemas import ExplanationResponse, ScoreRequest, ScoredTransaction
from api.scoring import decide, explain, score
from api.store import InMemoryStore


def create_app(
    store: InMemoryStore | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    app = FastAPI(title="Fraud Radar")
    app.state.store = store or InMemoryStore()
    time_fn = clock or (lambda: datetime.now(timezone.utc))
    app.state.burst = BurstController(store=app.state.store, clock=time_fn)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

    @app.get("/transactions/{transaction_id}/explanation", response_model=ExplanationResponse)
    def get_explanation(transaction_id: UUID) -> ExplanationResponse:
        row = app.state.store.get(transaction_id)
        if row is None:
            raise HTTPException(status_code=404, detail="transaction not found")
        return ExplanationResponse(transaction_id=transaction_id, explanation=explain(row))

    return app


app = create_app()
