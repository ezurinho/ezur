"""REST and WebSocket API.

The API is a thin layer over the engine: it validates input, delegates, and
never computes trading state itself.
"""

from __future__ import annotations

import asyncio
import csv
import io
from typing import Any

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from .config import Settings, apply_settings, save_settings
from .market.csv_data import validate_dataset
from .models import TradeRecord
from .stats import aggregate
from .strategy.registry import available, strategy_schema

router = APIRouter(prefix="/api")


class EventHub:
    """One queue per connected client. A slow client never blocks the engine."""

    def __init__(self) -> None:
        self.queues: set[asyncio.Queue[dict[str, Any]]] = set()

    def register(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=100)
        self.queues.add(queue)
        return queue

    def unregister(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self.queues.discard(queue)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        for queue in list(self.queues):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                pass


def _engine(request: Request):
    return request.app.state.engine


def _store(request: Request):
    return request.app.state.store


class ConfigPatch(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)


class ValidateRequest(BaseModel):
    path: str


class BacktestRequest(BaseModel):
    dataset_path: str
    save: bool = True


@router.get("/health")
def health() -> dict[str, Any]:
    from . import __version__

    return {"status": "ok", "version": __version__}


@router.get("/status")
def status(request: Request) -> dict[str, Any]:
    return _engine(request).snapshot()


@router.get("/config")
def get_config(request: Request) -> dict[str, Any]:
    return _engine(request).settings.model_dump(mode="json")


@router.put("/config")
async def put_config(request: Request, body: ConfigPatch) -> dict[str, Any]:
    engine = _engine(request)
    try:
        updated = apply_settings(engine.settings, body.patch)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    engine.update_settings(updated)
    save_settings(updated, request.app.state.config_path)
    return updated.model_dump(mode="json")


@router.post("/config/reset")
async def reset_config(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    fresh = Settings()
    engine.update_settings(fresh)
    save_settings(fresh, request.app.state.config_path)
    return fresh.model_dump(mode="json")


@router.get("/strategy/schema")
def get_strategy_schema(strategy_id: str | None = None) -> dict[str, Any]:
    engine_id = strategy_id or "null"
    return {
        "available": available(),
        "active": engine_id,
        **strategy_schema(engine_id),
    }


@router.post("/bot/{action}")
async def bot_action(request: Request, action: str) -> dict[str, Any]:
    engine = _engine(request)
    if action == "start":
        try:
            engine.start()
            engine.start_task()
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    elif action == "pause":
        engine.pause()
    elif action == "stop":
        engine.stop()
    else:
        raise HTTPException(status_code=404, detail=f"unknown action {action}")
    return {"status": engine.state.status}


@router.post("/position/close")
def close_position(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    trade = engine.execution.close("manual")
    if trade is not None:
        engine._on_trade_closed(trade)
        engine._persist()
    return {"closed": trade is not None}


@router.post("/orders/cancel")
def cancel_orders(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    engine.execution.cancel_all()
    engine.state.orders = list(engine.execution.orders)
    return {"cancelled": True}


@router.get("/orders")
def list_orders(request: Request) -> list[dict[str, Any]]:
    engine = _engine(request)
    return [order.model_dump(mode="json") for order in engine.execution.orders]


@router.post("/emergency")
def emergency_on(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    engine.emergency_on()
    return {"emergency": True}


@router.delete("/emergency")
def emergency_off(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    engine.emergency_off()
    return {"emergency": False}


@router.get("/trades")
def list_trades(request: Request, limit: int = 100, offset: int = 0, mode: str | None = None):
    return _store(request).list_trades(limit=limit, offset=offset, mode=mode)


@router.get("/trades/export.csv", response_class=PlainTextResponse)
def export_trades(request: Request, limit: int = 5000) -> str:
    rows = _store(request).list_trades(limit=limit)
    buffer = io.StringIO()
    if not rows:
        return ""
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


@router.get("/events")
def list_events(request: Request, limit: int = 200, level: str | None = None):
    return _store(request).list_events(limit=limit, level=level)


@router.get("/stats")
def get_stats(request: Request) -> dict[str, Any]:
    store = _store(request)
    engine = _engine(request)
    return aggregate(store.all_trades(), engine.settings.risk.initial_capital)


@router.get("/chart/history")
def chart_history(request: Request, tf: str = "1m", limit: int = 500) -> dict[str, Any]:
    engine = _engine(request)
    return {
        "primary": engine.settings.instruments.primary,
        "timeframe": tf,
        "candles": engine.history(tf, limit),
    }


@router.get("/datasets")
def list_datasets(request: Request) -> list[str]:
    from pathlib import Path

    data_dir = Path(request.app.state.config_path).parent
    if not data_dir.exists():
        return []
    return sorted(str(path) for path in data_dir.glob("*.csv"))


@router.post("/data/validate")
def post_validate(request: Request, body: ValidateRequest) -> dict[str, Any]:
    engine = _engine(request)
    report = validate_dataset(body.path, engine.settings.instruments.symbols)
    return report.as_dict()


@router.post("/backtest/run")
def post_backtest(request: Request, body: BacktestRequest) -> dict[str, Any]:
    from .backtest import run_backtest

    engine = _engine(request)
    try:
        result = run_backtest(engine.settings, body.dataset_path)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if body.save:
        _store(request).save_backtest(result.run_id, result.model_dump(mode="json"))
    return {
        "run_id": result.run_id,
        "metrics": result.metrics,
        "trades": len(result.trades),
        "dataset_id": result.dataset_id,
    }


@router.get("/backtest/runs")
def get_backtest_runs(request: Request, cursor: str | None = None, limit: int = 25):
    return _store(request).list_backtest_runs(cursor=cursor, limit=limit)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    engine = websocket.app.state.engine
    hub: EventHub = websocket.app.state.hub
    queue = hub.register()
    try:
        await websocket.send_json(engine.snapshot())
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            await websocket.send_json(payload)
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister(queue)
