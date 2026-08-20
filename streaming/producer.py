import threading
from collections.abc import Callable
from pathlib import Path

from fastapi import FastAPI

from api.burst import BURST_SIZE, BURST_WINDOW_MS, load_burst_rows
from api.schemas import ScoreRequest
from streaming.publisher import Publisher
from streaming.replay import spread_publish


def create_producer_app(
    publish: Publisher,
    burst_rows: list[ScoreRequest] | None = None,
    sleep_fn: Callable[[float], None] | None = None,
    background_burst: bool = False,
) -> FastAPI:
    app = FastAPI(title="Fraud Radar Producer")
    pause = sleep_fn or __import__("time").sleep

    @app.post("/burst")
    def post_burst() -> dict:
        rows = burst_rows
        if rows is None:
            rows = load_burst_rows(Path("ml/artifacts/burst_payload.json"))

        def _run() -> None:
            spread_publish(rows[:BURST_SIZE], publish, pause, window_ms=BURST_WINDOW_MS)

        if background_burst:
            threading.Thread(target=_run, daemon=True).start()
        else:
            _run()
        return {"accepted": True, "size": BURST_SIZE, "window_ms": BURST_WINDOW_MS}

    return app
