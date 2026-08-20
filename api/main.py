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
