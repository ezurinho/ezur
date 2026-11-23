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
from .gates import evaluate_gates
from .stats import aggregate
from .strategy.registry import available, resolve_strategy, strategy_schema

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


class ResetStatsRequest(BaseModel):
    include_backtests: bool = False


class BacktestRequest(BaseModel):
    dataset_path: str
    save: bool = True
    stress: bool = True
    run_group: str | None = None


class CompareRequest(BaseModel):
    dataset_path: str
    strategies: list[str] | None = None
    save: bool = False
    run_group: str | None = None


@router.get("/health")
def health() -> dict[str, Any]:
    from . import __version__

    return {"status": "ok", "version": __version__}


@router.get("/alerts")
def alerts(request: Request) -> dict[str, Any]:
    """Delivery counters for the out-of-band notifier.

    ``enabled=false`` is not an error: alerts are off until someone configures a
    webhook. The counters exist so a silently broken webhook is visible.
    """
    notifier = getattr(request.app.state, "notifier", None)
    if notifier is None:
        config = getattr(request.app.state.settings, "alerts", None)
        return {
            "enabled": False,
            "reason": "sin webhook configurado",
            "config_enabled": bool(getattr(config, "enabled", False)),
        }
    return notifier.snapshot()


@router.post("/alerts/test")
def post_alerts_test(request: Request) -> dict[str, Any]:
    """Entrega una alerta de prueba y responde si llegó, no si se encoló."""
    notifier = getattr(request.app.state, "notifier", None)
    if notifier is None:
        return {
            "sent": False,
            "reason": "alertas desactivadas: define alerts.webhook_url o EZUR_ALERT_WEBHOOK_URL",
            "config_enabled": bool(getattr(request.app.state.settings.alerts, "enabled", False)),
        }
    return notifier.send_now(
        "warn",
        "test",
        "alerta de prueba desde la interfaz de ezur",
        {"source": "ui"},
    )


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
        # Validate the plugin parameters before they reach the running engine:
        # a bad payload must be a 422, not a dead replay loop.
        resolve_strategy(updated.strategy.id, updated.strategy.params)
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    previous_alerts = engine.settings.alerts
    engine.update_settings(updated)
    save_settings(updated, request.app.state.config_path)

    # Activar alertas desde la interfaz tiene que activarlas de verdad: el
    # notifier se construye al arrancar, así que un cambio en `alerts` se
    # reconstruye aquí. Si no, la UI diría «guardado» y no llegaría nada.
    if updated.alerts != previous_alerts:
        from .alerts import build_notifier
        from .env import env

        previous = getattr(request.app.state, "notifier", None)
        if previous is not None:
            previous.close()
        notifier = build_notifier(
            updated.alerts,
            url_override=env("ALERT_WEBHOOK_URL"),
            on_failure=lambda reason: _store(request).insert_event("warn", "alerts", reason),
        )
        request.app.state.notifier = notifier
        engine.notifier = notifier
    return updated.model_dump(mode="json")


@router.post("/config/reset")
async def reset_config(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    fresh = Settings()
    engine.update_settings(fresh)
    save_settings(fresh, request.app.state.config_path)
    return fresh.model_dump(mode="json")


@router.get("/strategy/schema")
def get_strategy_schema(request: Request, strategy_id: str | None = None) -> dict[str, Any]:
    engine = _engine(request)
    active = engine.settings.strategy.id
    engine_id = strategy_id or active
    try:
        schema = strategy_schema(engine_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return {
        "available": available(),
        "active": active,
        **schema,
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
    # Captura el estado antes de publicar: `publish_now` cede el turno y un
    # replay que termina en el acto cambiaría la respuesta bajo nuestros pies.
    status = engine.state.status
    await engine.publish_now()
    return {"status": status}


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
def list_trades(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    mode: str | None = None,
    side: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    return _store(request).list_trades(
        limit=limit, offset=offset, mode=mode, side=side, start=start, end=end
    )


@router.get("/trades/export.csv", response_class=PlainTextResponse)
def export_trades(
    request: Request,
    limit: int = 5000,
    mode: str | None = None,
    side: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> str:
    rows = _store(request).list_trades(
        limit=limit, mode=mode, side=side, start=start, end=end
    )
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
    return aggregate(
        store.all_trades(),
        engine.settings.risk.initial_capital,
        timezone_name=engine.settings.instruments.template_for(
            engine.settings.instruments.primary
        ).timezone,
    )


@router.get("/stats/reset/preview")
def preview_stats_reset(request: Request) -> dict[str, Any]:
    return {"would_delete": _store(request).stats_counts()}


@router.post("/stats/reset")
def reset_stats(request: Request, body: ResetStatsRequest | None = None) -> dict[str, Any]:
    payload = body or ResetStatsRequest()
    return {"deleted": _store(request).reset_stats(include_backtests=payload.include_backtests)}


@router.get("/validation")
def get_validation(request: Request) -> dict[str, Any]:
    store = _store(request)
    engine = _engine(request)
    payload = aggregate(
        store.all_trades(),
        engine.settings.risk.initial_capital,
        timezone_name=engine.settings.instruments.template_for(
            engine.settings.instruments.primary
        ).timezone,
    )
    report = evaluate_gates(payload, initial_capital=engine.settings.risk.initial_capital)
    return report.model_dump(mode="json")


@router.get("/chart/history")
def chart_history(request: Request, tf: str = "1m", limit: int = 500) -> dict[str, Any]:
    engine = _engine(request)
    try:
        candles = engine.history(tf, limit)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "primary": engine.settings.instruments.primary,
        "timeframe": tf,
        "candles": candles,
    }


@router.get("/datasets")
def list_datasets_endpoint(request: Request) -> list[str]:
    from .datasets import list_datasets

    return list_datasets()


@router.post("/data/validate")
def post_validate(request: Request, body: ValidateRequest) -> dict[str, Any]:
    engine = _engine(request)
    report = validate_dataset(body.path, engine.settings.instruments.symbols)
    return report.as_dict()


@router.get("/experiments")
def list_experiments(request: Request, limit: int = 50) -> dict[str, Any]:
    from .experiments import load, summary

    path = request.app.state.experiment_ledger
    entries = load(path)
    return {"summary": summary(path), "entries": list(reversed(entries))[:limit]}


@router.get("/funnel")
def get_funnel(request: Request) -> dict[str, Any]:
    from .experiments import load
    from .funnel import build_funnel

    return build_funnel(load(request.app.state.experiment_ledger))


@router.post("/backtest/run")
def post_backtest(request: Request, body: BacktestRequest) -> dict[str, Any]:
    from .backtest import run_backtest
    from .experiments import record
    from .gates import evaluate_gates
    from .stats import aggregate
    from .stress import measure_gates

    engine = _engine(request)
    settings = engine.settings
    initial = settings.risk.initial_capital
    try:
        result = run_backtest(settings, body.dataset_path, run_group=body.run_group)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if body.save:
        _store(request).save_backtest(result.run_id, result.model_dump(mode="json"))

    stats = aggregate(
        result.trades,
        initial,
        timezone_name=settings.instruments.template_for(
            settings.instruments.primary
        ).timezone,
    )
    measured = {}
    if body.stress:
        # G8 and G2 need a second and third run: do them, do not estimate them.
        measured = measure_gates(settings, body.dataset_path)
    report = evaluate_gates(
        stats,
        initial_capital=initial,
        measured=measured,
    )
    entry = record(
        request.app.state.experiment_ledger,
        kind="backtest",
        strategy_id=result.strategy_id,
        strategy_version=result.strategy_version,
        dataset_id=result.dataset_id,
        config=settings.model_dump(mode="json"),
        metrics={**result.metrics, "validation": report.model_dump(mode="json")},
        verdict=report.verdict,
        notes="" if body.stress else "costes y determinismo no medidos",
        run_id=result.run_id,
        run_group=result.run_group or "",
    )
    return {
        "run_id": result.run_id,
        "dataset_id": result.dataset_id,
        "config_hash": result.config_hash,
        "run_group": result.run_group,
        "metrics": result.metrics,
        "trades": len(result.trades),
        "verdict": report.verdict,
        "validation": report.model_dump(mode="json"),
        "experiment_id": entry["experiment_id"],
    }


@router.get("/backtest/strategies")
def get_backtest_strategies(request: Request) -> dict[str, Any]:
    """Plugins instalados, con versión y parámetros por defecto de cada uno."""
    from .strategy.registry import available, resolve_strategy

    engine = _engine(request)
    items = []
    for strategy_id in available():
        try:
            strategy = resolve_strategy(strategy_id, None)
            items.append(
                {
                    "id": strategy.id,
                    "version": strategy.version,
                    "params": strategy.params.model_dump(mode="json"),
                }
            )
        except (KeyError, ValueError):
            continue
    return {"active": engine.settings.strategy.id, "items": items}


@router.post("/backtest/compare")
def post_backtest_compare(request: Request, body: CompareRequest) -> dict[str, Any]:
    """Mismo dataset, varias estrategias, un veredicto por fila.

    No elige ganador: ordena por esperanza en R y deja escrito qué puerta falla
    cada una. Un ranking sin el motivo del fallo invita a quedarse con el número
    grande y olvidar que no pasó G5.
    """
    from .backtest import config_fingerprint, run_backtest
    from .experiments import record
    from .gates import evaluate_gates
    from .stats import aggregate
    from .strategy.registry import available, resolve_strategy

    engine = _engine(request)
    settings = engine.settings
    initial = settings.risk.initial_capital
    wanted = body.strategies or available()
    unknown = [item for item in wanted if item not in available()]
    if unknown:
        raise HTTPException(status_code=422, detail=f"estrategias desconocidas: {unknown}")

    group = body.run_group or f"cmp-{config_fingerprint(settings)[:8]}"
    rows: list[dict[str, Any]] = []
    for strategy_id in wanted:
        try:
            result = run_backtest(
                settings,
                body.dataset_path,
                resolve_strategy(strategy_id, None),
                run_group=group,
            )
        except (ValueError, FileNotFoundError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        stats = aggregate(
            result.trades,
            initial,
            timezone_name=settings.instruments.template_for(
                settings.instruments.primary
            ).timezone,
        )
        report = evaluate_gates(stats, initial_capital=initial)
        if body.save:
            _store(request).save_backtest(result.run_id, result.model_dump(mode="json"))
        entry = record(
            request.app.state.experiment_ledger,
            kind="backtest_compare",
            strategy_id=result.strategy_id,
            strategy_version=result.strategy_version,
            dataset_id=result.dataset_id,
            config=settings.model_dump(mode="json"),
            metrics={**result.metrics, "validation": report.model_dump(mode="json")},
            verdict=report.verdict,
            notes="comparación sin stress: G8 y G2 no medidos",
            run_id=result.run_id,
            run_group=group,
        )
        rows.append(
            {
                "run_id": result.run_id,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                "dataset_id": result.dataset_id,
                "config_hash": result.config_hash,
                "run_group": group,
                "verdict": report.verdict,
                "trades": len(result.trades),
                "gates": report.model_dump(mode="json"),
                "metrics": {
                    key: result.metrics.get(key)
                    for key in (
                        "trades",
                        "win_rate",
                        "profit_factor",
                        "expectancy_r",
                        "max_drawdown",
                        "net_pnl",
                        "top5_share",
                    )
                },
                "experiment_id": entry["experiment_id"],
            }
        )

    # Una estrategia que no operó no puede encabezar un ranking por esperanza:
    # 0.00 R con 0 operaciones es ausencia de datos, no el mejor resultado.
    rows.sort(
        key=lambda row: (row["trades"] > 0, row["metrics"].get("expectancy_r") or 0),
        reverse=True,
    )
    return {"dataset_id": rows[0]["dataset_id"] if rows else "", "run_group": group, "rows": rows}


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
