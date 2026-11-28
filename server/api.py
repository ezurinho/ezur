"""REST and WebSocket API.

The API is a thin layer over the engine: it validates input, delegates, and
never computes trading state itself.
"""

from __future__ import annotations

import asyncio
import csv
import io
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import Settings, apply_settings, save_settings
from .holdout import HoldoutSealed
from .promotion import effective_settings_and_verdict
from .market.csv_data import validate_dataset
from .models import DayStats
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


def _refresh_promotion(request: Request, engine: Any) -> None:
    """Recalcula la puerta al guardar el perfil, sin esperar al arranque."""
    builder = getattr(engine, "builder", None)
    if builder is None:
        return
    from .paper import promotion_state

    builder.promotion = promotion_state(Path(request.app.state.config_path).parent)


def _rebuild_notifier(request: Request, engine, alerts) -> None:
    from .alerts import build_notifier
    from .env import env

    previous = getattr(request.app.state, "notifier", None)
    if previous is not None:
        previous.close()
    notifier = build_notifier(
        alerts,
        url_override=env("ALERT_WEBHOOK_URL"),
        on_failure=lambda reason: _store(request).insert_event("warn", "alerts", reason),
    )
    request.app.state.notifier = notifier
    engine.notifier = notifier


async def _backtest_slot(request: Request):
    """Una sola corrida CPU pesada a la vez; las demás esperan su turno."""
    lock = request.app.state.backtest_lock
    async with lock:
        yield


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
    # La ventana es parte del experimento: el mismo CSV puede contener años y
    # un backtest de 2025 no debe arrastrar 2026 solo porque esta en el archivo.
    start: str | None = None
    end: str | None = None


def _day_bound(value: str | None, field: str) -> datetime | None:
    """Convierte AAAA-MM-DD a medianoche UTC; el corte es exclusivo."""
    if value is None or not value.strip():
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(
            status_code=422, detail=f"{field} debe ser una fecha AAAA-MM-DD"
        ) from error
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


class CompareRequest(BaseModel):
    dataset_path: str
    strategies: list[str] | None = None
    save: bool = False
    run_group: str | None = None


@router.get("/health")
def health(request: Request) -> dict[str, Any]:
    """¿Sigue vivo el proceso... y el motor?

    Un ``200 ok`` que solo prueba que FastAPI responde es el tipo de salud que
    tranquiliza sin informar. Aquí va también el latido del motor: estado, edad
    de la última vela y si hay feed enganchado.
    """
    from . import __version__

    payload: dict[str, Any] = {"status": "ok", "version": __version__}
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        return payload
    last_ts = getattr(engine.state, "last_bar_ts", None)
    age: float | None = None
    if isinstance(last_ts, datetime):
        aware = last_ts if last_ts.tzinfo else last_ts.replace(tzinfo=timezone.utc)
        age = max(0.0, (datetime.now(timezone.utc) - aware).total_seconds())
    payload["engine"] = {
        "status": engine.state.status,
        "mode": engine.mode,
        "feed": getattr(getattr(engine, "feed", None), "name", None),
        "last_bar_age_s": None if age is None else round(age, 1),
        "session": getattr(engine.state, "session", None),
    }
    return payload


@router.get("/ready")
def ready(request: Request) -> JSONResponse:
    """Readiness operativa: motor en marcha, latido y feed frescos."""
    from .readiness import assess

    engine = _engine(request)
    payload = assess(engine, engine.store)
    return JSONResponse(status_code=200 if payload["ready"] else 503, content=payload)


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


@router.get("/update")
def get_update() -> dict[str, Any]:
    """Versión publicada frente a la que corre: solo lectura y con caché.

    No descarga ni instala nada; devuelve qué hay publicado y dónde. Se puede
    apagar con `EZUR_UPDATE_CHECK=0` y apuntar a otro manifiesto con
    `EZUR_UPDATE_URL`.
    """
    from . import __version__ as current_version
    from .env import env, env_flag
    from .update import DEFAULT_URL, current_status, empty_status

    if not env_flag("UPDATE_CHECK", True):
        return empty_status(current_version, "comprobación desactivada")
    return current_status(env("UPDATE_URL", DEFAULT_URL) or DEFAULT_URL, current_version)


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
    # El resto de la configuración es la viva (alertas, feed, etc.); solo el
    # riesgo configurado se conserva aparte para que la reducción efectiva por
    # promoción no se convierta en el nuevo valor guardado.
    engine = _engine(request)
    payload = engine.settings.model_dump(mode="json")
    configured = getattr(request.app.state, "configured_settings", None)
    if configured is not None:
        payload["risk"]["risk_per_trade_pct"] = configured.risk.risk_per_trade_pct
    return payload


@router.put("/config")
async def put_config(request: Request, body: ConfigPatch) -> dict[str, Any]:
    engine = _engine(request)
    previous_alerts = engine.settings.alerts
    configured = getattr(request.app.state, "configured_settings", None) or engine.settings
    try:
        updated = apply_settings(configured, body.patch)
        risk_patch = body.patch.get("risk")
        if isinstance(risk_patch, dict) and "initial_capital" in risk_patch:
            if (
                float(risk_patch["initial_capital"]) != engine.settings.risk.initial_capital
                and (
                    _store(request).count_trades()
                    or engine.execution.position is not None
                    or engine.execution.has_pending()
                )
            ):
                raise ValueError("no se puede cambiar el capital inicial con operaciones registradas")
        # Validate the plugin parameters before they reach the running engine:
        # a bad payload must be a 422, not a dead replay loop.
        resolve_strategy(updated.strategy.id, updated.strategy.params)
        effective, verdict = effective_settings_and_verdict(updated)
        engine.update_settings(effective)
    except (ValueError, KeyError, OSError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    save_settings(updated, request.app.state.config_path)
    request.app.state.settings = effective
    request.app.state.configured_settings = updated
    request.app.state.promotion_verdict = verdict
    _refresh_promotion(request, engine)

    # Activar alertas desde la interfaz tiene que activarlas de verdad: el
    # notifier se construye al arrancar, así que un cambio en `alerts` se
    # reconstruye aquí. Si no, la UI diría «guardado» y no llegaría nada.
    if updated.alerts != previous_alerts:
        _rebuild_notifier(request, engine, updated.alerts)
    return updated.model_dump(mode="json")


@router.post("/config/reset")
async def reset_config(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    if _store(request).count_trades() or engine.execution.position is not None or engine.execution.has_pending():
        raise HTTPException(
            status_code=409,
            detail="no se puede restablecer el capital con operaciones o exposición registradas",
        )
    fresh = Settings()
    effective, verdict = effective_settings_and_verdict(fresh)
    engine.update_settings(effective)
    save_settings(fresh, request.app.state.config_path)
    request.app.state.settings = effective
    request.app.state.configured_settings = fresh
    request.app.state.promotion_verdict = verdict
    _refresh_promotion(request, engine)
    _rebuild_notifier(request, engine, fresh.alerts)
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
        verdict = getattr(request.app.state, "promotion_verdict", None)
        if (
            engine.settings.promotion.required
            and engine.settings.promotion.mode == "block"
            and verdict is not None
            and not verdict.get("passed")
        ):
            reason = verdict.get("reason") or "la estrategia no está promovida"
            raise HTTPException(status_code=409, detail=f"sin promoción: {reason}")
        try:
            engine.start()
            await engine.start_task()
        except RuntimeError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    elif action == "pause":
        engine.pause()
    elif action == "stop":
        engine.stop()
        await engine.stop_task()
    else:
        raise HTTPException(status_code=404, detail=f"unknown action {action}")
    # Captura el estado antes de publicar: `publish_now` cede el turno y un
    # replay que termina en el acto cambiaría la respuesta bajo nuestros pies.
    status = engine.state.status
    await engine.publish_now()
    return {"status": status}


@router.post("/position/close")
async def close_position(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    trade = engine.execution.close("manual")
    if trade is not None:
        engine._on_trade_closed(trade)
        engine._persist()
    return {"closed": trade is not None}


@router.post("/orders/cancel")
async def cancel_orders(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    # El número real de órdenes canceladas: responder «true» con cero
    # pendientes hacía que la terminal anunciara una acción inexistente.
    cancelled = engine.execution.cancel_all()
    engine.state.orders = list(engine.execution.orders)
    return {"cancelled": cancelled > 0, "count": cancelled}


@router.get("/orders")
def list_orders(request: Request) -> list[dict[str, Any]]:
    engine = _engine(request)
    return [order.model_dump(mode="json") for order in engine.execution.orders]


@router.post("/emergency")
async def emergency_on(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    engine.emergency_on()
    return {"emergency": True}


@router.delete("/emergency")
async def emergency_off(request: Request) -> dict[str, Any]:
    engine = _engine(request)
    engine.emergency_off()
    return {"emergency": False}


@router.get("/trades")
def list_trades(
    request: Request,
    limit: int = Query(100, ge=1, le=5000),
    offset: int = Query(0, ge=0),
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
    limit: int = Query(5000, ge=1, le=5000),
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
def list_events(request: Request, limit: int = Query(200, ge=1, le=5000), level: str | None = None):
    return _store(request).list_events(limit=limit, level=level)


@router.get("/stats")
def get_stats(request: Request) -> dict[str, Any]:
    store = _store(request)
    engine = _engine(request)
    stats = aggregate(
        store.all_trades(mode=engine.mode),
        engine.settings.risk.initial_capital,
        timezone_name=engine.settings.instruments.template_for(
            engine.settings.instruments.primary
        ).timezone,
    )
    # Las marcas intradía viven en su tabla y no son cierres: se envían como
    # serie aparte para que el gráfico no las mezcle con la curva auditada.
    stats["equity_marks"] = store.equity_marks()
    return stats


@router.get("/stats/reset/preview")
def preview_stats_reset(request: Request) -> dict[str, Any]:
    return {"would_delete": _store(request).stats_counts()}


@router.post("/stats/reset")
async def reset_stats(request: Request, body: ResetStatsRequest | None = None) -> dict[str, Any]:
    engine = _engine(request)
    if engine.state.status != "stopped" or engine.execution.position is not None or engine.execution.has_pending():
        raise HTTPException(
            status_code=409,
            detail="detén el motor y cierra la posición antes de borrar el historial",
        )
    payload = body or ResetStatsRequest()
    deleted = _store(request).reset_stats(include_backtests=payload.include_backtests, mode=engine.mode)
    engine.execution.orders = []
    engine.state.orders = []
    engine.state.position = None
    engine.state.day_stats = DayStats()
    engine.state.equity = engine.settings.risk.initial_capital
    engine.peak_equity = engine.settings.risk.initial_capital
    engine.state.block_reason = None
    engine.state.block_count = 0
    engine._rejections.clear()
    engine._rejection_totals.clear()
    engine.invalidate_stats()
    engine._persist()
    return {"deleted": deleted}


@router.get("/validation")
def get_validation(request: Request) -> dict[str, Any]:
    store = _store(request)
    engine = _engine(request)
    payload = aggregate(
        store.all_trades(mode=engine.mode),
        engine.settings.risk.initial_capital,
        timezone_name=engine.settings.instruments.template_for(
            engine.settings.instruments.primary
        ).timezone,
    )
    report = evaluate_gates(payload, initial_capital=engine.settings.risk.initial_capital)
    return report.model_dump(mode="json")


@router.get("/review/2025-15m")
def get_review_2025() -> dict[str, Any]:
    """Comparación 2025 leída de los artefactos de la review.

    Es solo lectura: no recalcula operaciones. Si faltan los artefactos o el
    dataset, la tarjeta debe poder decirlo sin inventar cifras.
    """
    from .review import ReviewUnavailable, review_2025

    try:
        return review_2025()
    except ReviewUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/chart/history")
def chart_history(request: Request, tf: str = "1m", limit: int = Query(500, ge=1, le=500)) -> dict[str, Any]:
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
    path = Path(body.path)
    if path.suffix.lower() != ".csv":
        raise HTTPException(status_code=422, detail="el dataset debe ser un CSV")
    try:
        size = path.stat().st_size
    except OSError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if size > 250 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="el dataset supera el límite de 250 MB")
    report = validate_dataset(path, engine.settings.instruments.symbols)
    return report.as_dict()


@router.get("/experiments")
def list_experiments(request: Request, limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    from .experiments import load, summary

    path = request.app.state.experiment_ledger
    entries = load(path)
    return {"summary": summary(path), "entries": list(reversed(entries))[:limit]}


@router.get("/funnel")
def get_funnel(request: Request) -> dict[str, Any]:
    from .experiments import load
    from .funnel import build_funnel

    return build_funnel(load(request.app.state.experiment_ledger))


@router.post("/backtest/run", dependencies=[Depends(_backtest_slot)])
def post_backtest(request: Request, body: BacktestRequest) -> dict[str, Any]:
    from .backtest import run_backtest
    from .experiments import record
    from .gates import evaluate_gates
    from .stats import aggregate
    from .stress import measure_gates

    engine = _engine(request)
    # El backtest reproduce el perfil guardado, no la copia efectiva a la que
    # la promocion le redujo el riesgo: el CLI parte del archivo de config y
    # este boton debe dar la misma corrida que ese comando.
    settings = getattr(request.app.state, "configured_settings", None) or engine.settings
    initial = settings.risk.initial_capital
    start = _day_bound(body.start, "start")
    end = _day_bound(body.end, "end")
    if start is not None and end is not None and start >= end:
        raise HTTPException(status_code=422, detail="start debe ser anterior a end")
    try:
        result = run_backtest(
            settings,
            body.dataset_path,
            run_group=body.run_group,
            start=start,
            end=end,
        )
    except HoldoutSealed as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
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
        measured = measure_gates(settings, body.dataset_path, start=start, end=end)
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
        # El DD de `result.metrics` es pico-valle sobre la curva marcada a
        # mercado; G6 y el informe del CLI usan las operaciones cerradas. Se
        # devuelven ambos para que la tarjeta no enseñe un DD que la puerta no
        # está midiendo.
        "metrics_closed": stats["closed"],
        "trades": len(result.trades),
        # Sin esto, una corrida de 0 operaciones parece una estrategia muda
        # cuando en realidad puede haber descartado cien señales.
        "diagnostics": result.diagnostics,
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


@router.post("/backtest/compare", dependencies=[Depends(_backtest_slot)])
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
        except HoldoutSealed as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
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
                        "expectancy_ci80_low",
                        "max_drawdown",
                        "pnl_net",
                        "pnl_gross",
                        "fees",
                        "top5_share",
                    )
                },
                "rejections": result.diagnostics.get("rejections", {}),
                "open_position": result.diagnostics.get("open_position"),
                "pending_orders": result.diagnostics.get("pending_orders", 0),
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
def get_backtest_runs(request: Request, cursor: str | None = None, limit: int = Query(25, ge=1, le=200)):
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
