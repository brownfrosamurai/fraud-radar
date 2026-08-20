import asyncio
import os
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse

from api.burst import (
    BURST_SIZE,
    BURST_WINDOW_MS,
    BurstController,
    CooldownActive,
    HttpProducerClient,
    ProducerClient,
    ProducerUnavailable,
)
from api.db import create_engine_from_url
from api.explain import explain
from api.hub import StreamHub
from api.postgres_store import PostgresStore
from api.schemas import BurstResponse, ExplanationResponse, ScoreRequest, ScoredTransaction
from api.scoring import decide
from api.serve import BundleScorer, Scorer, load_bundle
from api.store import InMemoryStore, TransactionStore


def create_app(
    store: TransactionStore | None = None,
    clock: Callable[[], datetime] | None = None,
    scorer: Scorer | None = None,
    producer: ProducerClient | None = None,
    hub: StreamHub | None = None,
    database_url: str | None = None,
) -> FastAPI:
    app = FastAPI(title="Fraud Radar")
    url = database_url if database_url is not None else os.environ.get("DATABASE_URL")
    app.state.store = store or (
        PostgresStore(create_engine_from_url(url)) if url else InMemoryStore()
    )
    app.state.hub = hub or StreamHub()
    app.state.internal_secret = os.environ.get("INTERNAL_API_SECRET")
    app.state.producer = producer or HttpProducerClient(
        os.environ.get("PRODUCER_URL", "http://producer:8001")
    )
    time_fn = clock or (lambda: datetime.now(timezone.utc))
    if scorer is None:
        scorer = BundleScorer(load_bundle())
    app.state.scorer = scorer

    def resolve_scorer() -> Scorer:
        if app.state.scorer is None:
            app.state.scorer = BundleScorer(load_bundle())
        return app.state.scorer

    app.state.burst = BurstController(
        clock=time_fn,
        producer=app.state.producer,
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
            503: {"model": BurstResponse},
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
        except ProducerUnavailable:
            return JSONResponse(
                status_code=503,
                content={
                    "accepted": False,
                    "size": BURST_SIZE,
                    "window_ms": BURST_WINDOW_MS,
                    "cooldown_seconds": 0,
                },
            )

    @app.post("/internal/scored")
    def post_internal_scored(
        rows: list[ScoredTransaction],
        x_internal_secret: str | None = Header(default=None),
    ) -> dict:
        if (
            app.state.internal_secret
            and x_internal_secret != app.state.internal_secret
        ):
            raise HTTPException(status_code=401, detail="invalid internal secret")
        app.state.store.put_many(rows)
        for row in rows:
            app.state.hub.broadcast(row)
        return {"ok": True, "n": len(rows)}

    @app.websocket("/stream")
    async def stream(ws: WebSocket) -> None:
        await ws.accept()
        q = app.state.hub.subscribe()
        receive_task = asyncio.create_task(ws.receive())
        item_task = asyncio.create_task(asyncio.to_thread(q.get))
        try:
            while True:
                done, _ = await asyncio.wait(
                    {receive_task, item_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if receive_task in done:
                    message = receive_task.result()
                    if message["type"] == "websocket.disconnect":
                        break
                    receive_task = asyncio.create_task(ws.receive())
                if item_task in done:
                    await ws.send_json(item_task.result())
                    item_task = asyncio.create_task(asyncio.to_thread(q.get))
        except WebSocketDisconnect:
            pass
        finally:
            receive_task.cancel()
            with suppress(asyncio.CancelledError):
                await receive_task
            if not item_task.done():
                q.put(None)
                await item_task
            app.state.hub.unsubscribe(q)

    @app.post("/score", response_model=ScoredTransaction)
    def post_score(
        body: ScoreRequest,
        model: str = Query(default="isolation_forest"),
    ) -> ScoredTransaction:
        if model not in {"isolation_forest", "autoencoder"}:
            raise HTTPException(status_code=422, detail="unknown model")
        resolved = resolve_scorer()
        try:
            model_score = resolved.score(body, model=model)
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
        bundle = getattr(app.state.scorer, "bundle", None)
        if bundle is None:
            raise HTTPException(status_code=500, detail="explainer unavailable")
        try:
            items = explain(row, bundle)
        except LookupError as exc:
            raise HTTPException(status_code=501, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail="explanation failed") from exc
        return ExplanationResponse(transaction_id=transaction_id, explanation=items)

    return app


app = create_app()
