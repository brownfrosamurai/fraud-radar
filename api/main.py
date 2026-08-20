from collections.abc import Callable
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from api.burst import BURST_SIZE, BURST_WINDOW_MS, BurstController, CooldownActive
from api.schemas import BurstResponse, ExplanationResponse, ScoreRequest, ScoredTransaction
from api.scoring import decide, explain
from api.serve import BundleScorer, Scorer, load_bundle
from api.store import InMemoryStore


def create_app(
    store: InMemoryStore | None = None,
    clock: Callable[[], datetime] | None = None,
    scorer: Scorer | None = None,
    burst_rows: list[ScoreRequest] | None = None,
) -> FastAPI:
    app = FastAPI(title="Fraud Radar")
    app.state.store = store or InMemoryStore()
    time_fn = clock or (lambda: datetime.now(timezone.utc))
    # Defer load_bundle until first score: artifacts are not in-tree until a later task.
    app.state.scorer = scorer
    app.state.burst = BurstController(
        store=app.state.store, clock=time_fn, burst_rows=burst_rows, scorer=scorer
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post(
        "/demo/burst",
        response_model=BurstResponse,
        responses={
            200: {"model": BurstResponse},
            429: {"model": BurstResponse},
        },
    )
    def post_burst() -> BurstResponse | JSONResponse:
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
    def post_score(
        body: ScoreRequest,
        model: str = Query(default="isolation_forest"),
    ) -> ScoredTransaction:
        if model not in {"isolation_forest", "autoencoder"}:
            raise HTTPException(status_code=422, detail="unknown model")
        if app.state.scorer is None:
            app.state.scorer = BundleScorer(load_bundle())
        try:
            model_score = app.state.scorer.score(body, model=model)
        except LookupError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        row = ScoredTransaction(
            id=body.transaction_id,
            occurred_at=body.occurred_at,
            amount=body.amount,
            model_score=model_score,
            decision=decide(model_score, body.amount),
            model_name=model,  # type: ignore[arg-type]
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
