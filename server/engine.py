"""Trading engine.

Owns the cycle: session detection, execution, strategy evaluation, risk
authorisation, persistence and snapshot emission. It knows nothing about any
instrument name or any strategy rule.
"""

from __future__ import annotations

import asyncio
import csv
import json
import time
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from .config import Settings
from .db import Store
from .equity import audit as equity_audit
from .execution import ExecutionEngine
from .market.feed import MarketFeed
from .models import (
    Bar,
    DayStats,
    EngineState,
    PortfolioState,
    Position,
    SessionInfo,
    Tick,
    TradeRecord,
)
from .risk import RiskManager
from .resample import BarAggregator, timeframe_minutes
from .edge import EdgeGuard, measure_path
from .snapshot import SnapshotBuilder
from .stats import aggregate
from .strategy.base import BaseStrategy, MarketData, Phase, StrategyOutput
from .strategy.indicators import atr
from .strategy.registry import resolve_strategy
from .timeutil import now_utc, parse_hhmm, same_session, session_for, to_zone

logger = logging.getLogger(__name__)

# One event per rejection reason per window keeps the console readable.
REJECTION_LOG_INTERVAL_S = 120

# At 50x replay a snapshot per tick is ~3.4 MiB/s per client for no benefit:
# the UI cannot render faster than this and the payload carries full candles.
SNAPSHOT_MIN_INTERVAL_S = 0.1

# Pause between looped replays so the restart is visible in the console.
RESTART_PAUSE_S = 0.5

MAX_BARS = 500
# El chart puede mirar más atrás que la estrategia: 500 velas de 30m
# necesitan 15.000 velas de 1m. Este buffer no viaja en el snapshot.
CHART_MAX_BARS = 16_000
WATCHDOG_INTERVAL_S = 30
PENDING_ORDER_TTL_S = 120
EXECUTION_REJECTIONS = {
    "below_min_notional",
    "gap_through_stop",
    "gap_through_target",
    "risk_budget_exceeded",
}

SnapshotHook = Callable[[dict[str, Any]], Awaitable[None] | None]


class TradingEngine:
    def __init__(
        self,
        settings: Settings,
        store: Store,
        feed: MarketFeed | None = None,
        strategy: BaseStrategy | None = None,
        mode: str = "paper",
        feed_factory: Callable[[Settings], MarketFeed] | None = None,
        strategy_factory: Callable[[Settings], Any] | None = None,
        notifier: Any | None = None,
    ) -> None:
        self.settings = settings
        self.notifier = notifier
        self.store = store
        self.feed = feed
        self.feed_factory = feed_factory
        self.strategy_factory = strategy_factory
        self._strategy_key = _strategy_key(settings)
        self.strategy = strategy or resolve_strategy(
            settings.strategy.id, settings.strategy.params
        )
        if mode == "live" and not settings.live.can_start():
            raise RuntimeError("LIVE requires an implemented adapter, live_enabled and confirmation")
        self.mode = mode
        self.risk = RiskManager(settings.risk)
        self.execution = ExecutionEngine(
            settings.execution,
            {item.symbol: item for item in settings.instruments.items},
            mode=mode,
        )
        self.builder = SnapshotBuilder(settings, store)
        self.builder.strategy_meta = {
            "id": self.strategy.id,
            "name": getattr(self.strategy, "name", self.strategy.id),
            "version": self.strategy.version,
        }
        self.state = EngineState(
            status="stopped",
            mode=mode,  # type: ignore[arg-type]
            provider=settings.feed.provider,
            equity=settings.risk.initial_capital,
        )
        self.edge_guard: EdgeGuard | None = None
        self._refresh_edge_guard()
        # Peak equity is what the trailing drawdown guard measures against.
        self.peak_equity = settings.risk.initial_capital
        self._bars: dict[str, list[Bar]] = {
                    symbol: [] for symbol in settings.instruments.symbols
        }
        self._chart_bars: list[Bar] = []
        self._chart_symbol: str | None = None
        self._aggregated = self._aggregators_for(settings)
        self._aggregated_minutes = timeframe_minutes(settings.strategy.timeframe)
        # Signal timeframe aggregators (what the strategy reads)
        self._signal_aggregated = self._signal_aggregators_for(settings)
        self._signal_minutes = timeframe_minutes(
                    settings.strategy.timeframe_signal or settings.strategy.timeframe
        )
        self._bar_index = 0
        self._last_signal_ts: datetime | None = None
        self._output: StrategyOutput | None = None
        self._subscribers: list[SnapshotHook] = []
        self._task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self.last_exit_ts: datetime | None = None
        self._previous_tick_ts: datetime | None = None
        # Barrera del backfill: velas anteriores a la posición restaurada no se
        # procesan (cerrarían la operación antes de que existiera).
        self._replay_barrier: datetime | None = None
        self._last_publish_at = 0.0
        self._stats_cache: dict[str, Any] | None = None
        self._rejections: dict[str, dict[str, object]] = {}
        # Acumulado de toda la corrida: `_rejections` se vacía en cada sesión y
        # en un backtest de años solo quedaría el último día.
        self._rejection_totals: dict[str, int] = {}
        self._restore()
        self._load_chart_seed()
        if self.state.session is None:
            primary = settings.instruments.primary
            self.state.session = session_for(
                now_utc(), settings.instruments.template_for(primary)
            )
        self._restore_day_stats()
        self.equity_audit = self._equity_snapshot()
        if not self.equity_audit["ok"]:
            self.state.block_reason = "equity_mismatch"
            logger.error(
                "equity no cuadra con el libro: %s",
                ", ".join(self.equity_audit["issues"]),
            )

    def _refresh_edge_guard(self) -> None:
        """Mide la ventaja contra el coste una vez por arranque.

        Solo paper/live: un backtest es la medición y no puede vetarse con su
        propio resultado. Sin evidencia no hay guarda, no se inventa una.
        """
        guard = (
            measure_path(self.settings.promotion.evidence, self.settings)
            if self.mode in {"paper", "live"}
            else None
        )
        self.edge_guard = guard
        self.builder.edge_guard = guard
        if self.state.block_reason == "edge_below_cost" and (
            guard is None or guard.passes is not False
        ):
            self.state.block_reason = None
            self.state.block_count = 0

    # --- lifecycle --------------------------------------------------------
    def _equity_snapshot(self) -> dict[str, Any]:
        """El guard solo aplica a motores con una base persistente.

        Backtest, simulaciones y walk-forward usan `:memory:`: ahí no hay una
        curva guardada que pueda contradecir al libro, y abrir el path como
        fichero fallaría. El paper real sí se audita.
        """
        if self.mode not in {"paper", "live"} or str(self.store.path) == ":memory:":
            return {
                "ok": True,
                "uninitialized": True,
                "issues": [],
                "differences": {},
            }
        return equity_audit(
            self.store.path, self.settings.risk.initial_capital, self.mode
        )

    def _require_reconciled_equity(self) -> None:
        """El arranque no puede operar sobre una curva o un estado desviados.

        Se recalcula en cada intento: si alguien corrigió la base con
        `python -m server.equity --apply` mientras el proceso estaba parado,
        el siguiente arranque debe poder continuar sin reiniciar el proceso.
        """
        self.equity_audit = self._equity_snapshot()
        if self.equity_audit["ok"]:
            return
        self.state.status = "error"
        self.state.block_reason = "equity_mismatch"
        detail = ", ".join(self.equity_audit["issues"]) or "desconocido"
        self._event(
            "error",
            "accounting",
            "arranque bloqueado: la equity no cuadra con el libro",
            {
                "issues": self.equity_audit["issues"],
                "differences": self.equity_audit["differences"],
            },
        )
        raise RuntimeError(
            "equity no cuadra con el libro ("
            f"{detail}); ejecuta python -m server.equity --apply y vuelve a arrancar"
        )

    def start(self) -> None:
        self.invalidate_publish()
        if self.state.emergency:
            raise RuntimeError("emergency stop is active; disable it first")
        self._require_reconciled_equity()
        if self.state.block_reason == "equity_mismatch":
            self.state.block_reason = None
        self.state.status = "running"
        self._event("info", "engine", "motor iniciado", {"mode": self.mode})
        self._persist()

    def pause(self) -> None:
        self.invalidate_publish()
        if self.state.status == "running":
            self.state.status = "paused"
            self._event("info", "engine", "motor en pausa")
            self._persist()

    def stop(self) -> None:
        self.invalidate_publish()
        self.state.status = "stopped"
        self._event("info", "engine", "motor detenido")
        self._persist()

    def emergency_on(self) -> None:
        self.invalidate_publish()
        self.state.emergency = True
        self.state.block_reason = "emergency_active"
        self.execution.cancel_all()
        self.state.status = "paused"
        self._event("warn", "risk", "parada de emergencia activada")
        self._persist()

    def emergency_off(self) -> None:
        self.invalidate_publish()
        self.state.emergency = False
        if self.state.block_reason == "emergency_active":
            self.state.block_reason = None
        self._event("info", "risk", "parada de emergencia desactivada")
        self._persist()

    def subscribe(self, hook: SnapshotHook) -> None:
        self._subscribers.append(hook)

    def update_settings(self, settings: Settings) -> None:
        """Apply validated settings at runtime without restarting the process."""
        exposed = {
            order.symbol for order in self.execution.orders if order.status == "pending"
        }
        if self.execution.position is not None:
            exposed.add(self.execution.position.symbol)
        if exposed:
            new_symbols = set(settings.instruments.symbols)
            missing = exposed - new_symbols
            old_primary = self.settings.instruments.primary
            if missing or settings.instruments.primary != old_primary:
                raise ValueError(
                    "no se puede cambiar el instrumento principal ni retirar uno con exposición"
                )

        # Construir antes de tocar estado: si el feed o el plugin rechazan la
        # configuración, el motor sigue con la última que sí era válida.
        next_strategy_key = _strategy_key(settings)
        next_strategy = (
            self.strategy_factory(settings)
            if self.strategy_factory is not None and next_strategy_key != self._strategy_key
            else None
        )
        next_feed = self.feed_factory(settings) if self.feed_factory is not None else None

        self.settings = settings
        self.state.provider = settings.feed.provider
        self.risk = RiskManager(settings.risk)
        self.execution.config = settings.execution
        self.execution.instruments = {
            item.symbol: item for item in settings.instruments.items
        }
        self.builder.settings = settings
        self._refresh_edge_guard()
        self.invalidate_stats()
        if next_strategy is not None:
            self.strategy = next_strategy
            self._strategy_key = next_strategy_key
            self._output = None
            self._rejections.clear()
            self.state.block_reason = None
            self.state.block_count = 0
        self._sync_strategy_meta()
        for symbol in settings.instruments.symbols:
            self._bars.setdefault(symbol, [])
        minutes = timeframe_minutes(settings.strategy.timeframe)
        if minutes != self._aggregated_minutes:
            # Otro marco es otro sistema: no se mezclan buckets del anterior
            # con los nuevos, y la estrategia vuelve a calentar.
            self._aggregated_minutes = minutes
            self._aggregated = self._aggregators_for(settings)
        if next_feed is not None and self.feed is not None:
            self.feed = next_feed
            self._bars = {symbol: [] for symbol in settings.instruments.symbols}
            self._chart_bars = []
            self._chart_symbol = None
            self._aggregated = self._aggregators_for(settings)
            self._previous_tick_ts = None
            self.state.bars_available = 0
            self.state.last_bar_ts = None
            if self.state.status == "running":
                try:
                    asyncio.get_running_loop().create_task(self.refresh_task())
                except RuntimeError:
                    pass
        if self.state.status == "running":
            try:
                self._start_watchdog()
            except RuntimeError:
                pass

    def _sync_strategy_meta(self) -> None:
        self.builder.strategy_meta = {
            "id": self.strategy.id,
            "name": getattr(self.strategy, "name", self.strategy.id),
            "version": self.strategy.version,
        }

    async def refresh_task(self) -> None:
        async with self._lifecycle_lock:
            if self.state.status in {"stopped", "error"}:
                return
            await self._stop_tasks_unlocked()
            if self.state.status in {"stopped", "error"}:
                return
            self._start_task_unlocked()

    async def run(self) -> None:
        if self.feed is None:
            raise RuntimeError("engine has no feed")
        delay = 1.0 / max(self.settings.feed.replay_speed, 0.01)
        stream = getattr(self.feed, "iter_ticks_async", None)
        try:
            if stream is not None:
                # Live venues pace themselves; the engine must not sleep between
                # ticks or it would fall behind the market.
                await self._run_live(stream)
                return
            while True:
                for tick in self.feed.iter_ticks():
                    self._process(tick)
                    await self._publish()
                    await asyncio.sleep(delay)
                if not self.settings.feed.loop_sessions or self.state.status != "running":
                    break
                # A looped demo replay starts the session again from scratch: the
                # bars are rebuilt, the trades and the equity keep accumulating.
                self._bars = {symbol: [] for symbol in self.settings.instruments.symbols}
                self._chart_bars = []
                self._chart_symbol = None
                self._aggregated = self._aggregators_for(self.settings)
                self._previous_tick_ts = None
                self.state.bars_available = 0
                self.state.last_bar_ts = None
                if self.feed_factory is not None:
                    self.feed = self.feed_factory(self.settings)
                self._event("info", "engine", "replay reiniciado", {"mode": "loop"})
                await asyncio.sleep(RESTART_PAUSE_S)
            if self.state.status == "running":
                # The feed ended and looping is off: claiming "running" would be a lie.
                self.state.status = "stopped"
                self._event("info", "engine", "replay finalizado")
                self._persist()
                await self._publish()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # a dead replay loop must be visible, not silent
            logger.exception("replay loop failed")
            self.state.status = "error"
            self._event("error", "engine", f"bucle detenido: {error}")
            self._persist()

    async def _run_live(self, stream: Any) -> None:
        async for tick in stream():
            self._process(tick)
            await self._publish()
        # A live stream that ends is a stop, not a pause.
        if self.state.status == "running":
            self.state.status = "stopped"
            self._event("info", "engine", "feed en vivo terminado")
            self._persist()
            await self._publish()

    def _start_watchdog(self) -> None:
        if self.mode not in {"paper", "live"} or self.state.provider not in {"okx", "live"}:
            return
        if self._watchdog_task is None or self._watchdog_task.done():
            self._watchdog_task = asyncio.create_task(self._watchdog())

    async def _watchdog(self) -> None:
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL_S)
            if self._task is None or self._task.done():
                return
            try:
                if self._check_live_freshness():
                    await self._publish()
            except Exception:
                logger.exception("watchdog de frescura falló; continúa vigilando")

    def _cancel_stale_pending(self) -> None:
        if self.state.block_reason != "stale_data":
            self.state.block_reason = "stale_data"
            self.state.block_count = 0
        if not self.execution.has_pending():
            return
        cancelled = self.execution.cancel_all()
        self.state.orders = list(self.execution.orders)
        self._event(
            "warn",
            "risk",
            "orden pendiente cancelada por datos obsoletos",
            {"cancelled": cancelled},
        )

    def _check_live_freshness(self, tick_ts: datetime | None = None) -> bool:
        """Envejece datos live y cancela entradas pendientes incluso sin ticks."""
        if self.mode not in {"paper", "live"} or self.state.provider not in {"okx", "live"}:
            return False
        stamp = tick_ts or self.state.last_bar_ts
        if stamp is None:
            return False
        before = (self.state.quality, self.state.staleness_ms, self.state.block_reason)
        age_ms = max(0.0, (now_utc() - _aware(stamp)).total_seconds() * 1000)
        self.state.staleness_ms = max(self.state.staleness_ms, int(age_ms))
        if age_ms > 900_000:
            self.state.quality = "stale"
        elif age_ms > 180_000:
            self.state.quality = "degraded"
        else:
            self.state.quality = "ok"
        if self.state.quality == "stale":
            self._cancel_stale_pending()
        elif self.execution.has_pending():
            expired = self.execution.expire_pending(PENDING_ORDER_TTL_S, now_utc())
            if expired:
                self.state.orders = list(self.execution.orders)
                self.state.block_reason = "stale_order"
                self.state.block_count = 0
                self._event(
                    "warn",
                    "execution",
                    "orden pendiente cancelada por señal antigua",
                    {"expired": expired},
                )
        return before != (self.state.quality, self.state.staleness_ms, self.state.block_reason)

    async def _stop_tasks_unlocked(self) -> None:
        if self._watchdog_task is not None and not self._watchdog_task.done():
            self._watchdog_task.cancel()
            try:
                await self._watchdog_task
            except asyncio.CancelledError:
                pass
        self._watchdog_task = None
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

    def _start_task_unlocked(self) -> None:
        self._require_reconciled_equity()
        # Cada consumidor empieza con historia vacía: un replay o backfill no
        # duplica velas que ya estaban en el chart.
        self._bars = {symbol: [] for symbol in self.settings.instruments.symbols}
        self._chart_bars = []
        self._chart_symbol = None
        self._previous_tick_ts = None
        if self.execution.position is not None:
            self._replay_barrier = self.execution.position.opened_ts
        self._task = asyncio.create_task(self.run())
        self._start_watchdog()

    async def start_task(self) -> None:
        async with self._lifecycle_lock:
            if self.state.status in {"stopped", "error"}:
                return
            await self._stop_tasks_unlocked()
            if self.state.status in {"stopped", "error"}:
                return
            self._start_task_unlocked()

    async def stop_task(self) -> None:
        async with self._lifecycle_lock:
            await self._stop_tasks_unlocked()

    # --- cycle ------------------------------------------------------------
    def _process(self, tick: Tick) -> None:
        # Un feed con backfill repite velas anteriores a la posición restaurada.
        # Procesarlas cerraría la operación «en el pasado» y dejaría una salida
        # anterior a la entrada: se espera a que el mercado alcance la posición.
        barrier = self._replay_barrier
        if barrier is not None and tick.ts < barrier:
            return
        if barrier is not None:
            self._replay_barrier = None
            self._event(
                "info",
                "engine",
                "el mercado alcanzó la posición restaurada",
                {"desde": barrier.isoformat()},
            )

        # El feed puede repetir o entregar fuera de orden una vela ya procesada
        # (backfill que solapa con el sondeo, reconexión). Ejecutarla cerraría
        # una posición con una barra vieja y el libro acabaría con una salida
        # anterior a la entrada, que es una fila imposible.
        previous = self._previous_tick_ts
        if previous is not None and tick.ts <= previous:
            return

        primary = self.settings.instruments.primary
        template = self.settings.instruments.template_for(primary)
        session = session_for(tick.ts, template)

        if not same_session(self.state.session, session):
            self._on_new_session(session)

        needed = max(self.strategy.warmup_requirements().bars.values(), default=0)
        bar_limit = max(MAX_BARS, needed + 1)
        for symbol, bar in tick.bars.items():
            if symbol not in self._bars:
                continue
            self._bars[symbol].append(bar)
            # Una estrategia con warmup mayor que el tope general nunca podría
            # salir de calentamiento. El límite crece solo lo que ella declara.
            del self._bars[symbol][:-bar_limit]
            if symbol == primary:
                if self._chart_symbol != primary:
                    self._chart_bars = []
                    self._chart_symbol = primary
                self._chart_bars.append(bar)
                del self._chart_bars[:-CHART_MAX_BARS]
            # Execution timeframe aggregator
            aggregator = self._aggregated.get(symbol)
            if aggregator is not None:
                aggregator.add(bar)
            # Signal timeframe aggregator
            sig_aggregator = self._signal_aggregated.get(symbol)
            if sig_aggregator is not None:
                sig_aggregator.add(bar)

        self.state.session = session
        self.state.last_bar_ts = tick.ts
        self.state.bars_available = len(self._bars.get(primary, []))
        # Freshness is measured against the previous tick, not the wall clock:
        # a replay of an old session is not stale, a stalled feed is.
        gap_ms = 0.0
        if self._previous_tick_ts is not None:
            gap_ms = (tick.ts - self._previous_tick_ts).total_seconds() * 1000
        self.state.staleness_ms = max(0, int(gap_ms))
        if self._previous_tick_ts is None:
            self.state.quality = "ok"
        elif gap_ms <= 180_000:
            self.state.quality = "ok"
        elif gap_ms <= 900_000:
            self.state.quality = "degraded"
        else:
            self.state.quality = "stale"
        self._previous_tick_ts = tick.ts
        self._check_live_freshness(tick.ts)

        rejections_before = dict(self._rejection_totals)
        execution_rejections: list[str] = []
        for event in self.execution.on_bar(tick.bars):
            if event.type == "exit" and event.trade is not None:
                self._on_trade_closed(event.trade)
            elif event.type == "fill":
                self._event(
                    "info",
                    "execution",
                    "orden ejecutada",
                    {"symbol": event.symbol, "price": event.price, "units": event.units},
                )
            elif event.type == "cancel":
                if event.reason in EXECUTION_REJECTIONS:
                    execution_rejections.append(event.reason)
                    self.state.block_reason = event.reason
                self._event(
                    "warn",
                    "execution",
                    "orden no ejecutada",
                    {
                        "symbol": event.symbol,
                        "units": event.units,
                        "reason": event.reason,
                        "diagnostics": event.diagnostics,
                    },
                )

        if not execution_rejections and self.state.block_reason in EXECUTION_REJECTIONS:
            self.state.block_reason = None
            self.state.block_count = 0

        self._update_trailing_stop()

        if self.execution.position is not None and self.settings.risk.close_at_session_end:
            self._maybe_close_at_session_end(tick)
        self.state.position = self.execution.position
        self.state.orders = list(self.execution.orders)

        self._expire_blocks(tick.ts)
        if self.state.status == "running":
            self._evaluate(tick, session)
        for reason in execution_rejections:
            # Si la evaluación de esta vela ya contó el mismo motivo, no duplicar.
            if self._rejection_totals.get(reason, 0) == rejections_before.get(reason, 0):
                self._note_rejection(reason, "orden no ejecutada", tick.ts)

        # En un backtest el estado vive en memoria y nadie reinicia a mitad: no
        # hay nada que restaurar. Persistirlo en cada vela son ~250.000
        # escrituras por corrida que solo cuestan tiempo (17,9 s -> 13,1 s).
        if self.mode != "backtest":
            self._persist()
        self._update_open_risk()
        self._record_equity_point(tick.ts)

    def _record_equity_point(self, stamp: datetime) -> None:
        """Marca a mercado mientras hay posición.

        Va a `equity_marks`, no a la curva auditada: esa curva tiene una fila
        por operación cerrada. Mezclar marcas con cierres dejó 463 filas frente
        a 14 trades, desvió el último punto y bloqueó el arranque.
        """
        if self.execution.position is None:
            return
        self.store.append_equity_mark(
            self.state.equity + self.state.unrealized, stamp
        )

    def _update_trailing_stop(self) -> None:
        """Sube el stop de la posición abierta con el máximo desde la entrada.

        Solo actúa si la spec declara `trail_atr_k`; sin esa clave el motor no
        toca el stop. Se ejecuta después de procesar la vela, así que el nivel
        nuevo rige desde la siguiente y nunca usa el recorrido de la vela que
        todavía se está evaluando.
        """
        position = self.execution.position
        if position is None:
            return
        params = self.settings.strategy.params or {}
        raw_k = params.get("trail_atr_k")
        if raw_k is None:
            return
        try:
            trail_k = float(raw_k)
            period = int(params.get("atr_period", 14) or 14)
        except (TypeError, ValueError):
            return
        if trail_k <= 0 or period <= 0:
            return
        bars = self._bar_source().get(position.symbol, [])
        if len(bars) < period + 1:
            return
        start = next(
            (index for index, bar in enumerate(bars) if bar.t >= position.opened_ts),
            None,
        )
        if start is None:
            return
        since = bars[start:]
        if not since:
            return
        volatility = atr(bars, period)
        if volatility is None or volatility <= 0:
            return
        tick_size = self.settings.instruments.by_symbol(position.symbol).tick_size
        last_close = since[-1].c
        if position.side == "long":
            candidate = min(
                max(bar.h for bar in since) - trail_k * volatility,
                last_close - tick_size,
            )
            if candidate > position.stop_price:
                position.stop_price = round(candidate, 10)
        else:
            candidate = max(
                min(bar.l for bar in since) + trail_k * volatility,
                last_close + tick_size,
            )
            if candidate < position.stop_price:
                position.stop_price = round(candidate, 10)

    def _aggregators_for(self, settings: Settings) -> dict[str, BarAggregator]:
        minutes = timeframe_minutes(settings.strategy.timeframe)
        if minutes <= 1:
            return {}
        return {
            symbol: BarAggregator(minutes, MAX_BARS)
            for symbol in settings.instruments.symbols
        }

    def _signal_aggregators_for(self, settings: Settings) -> dict[str, BarAggregator]:
        minutes = timeframe_minutes(
            settings.strategy.timeframe_signal or settings.strategy.timeframe
        )
        if minutes <= 1:
            return {}
        return {
            symbol: BarAggregator(minutes, MAX_BARS)
            for symbol in settings.instruments.symbols
        }

    def _bar_source(self) -> dict[str, list[Bar]]:
        """Lo que lee la estrategia: buckets cerrados del timeframe de señal."""
        # Use signal timeframe aggregators if available
        if self._signal_aggregated:
            return {
                symbol: aggregator.bars
                for symbol, aggregator in self._signal_aggregated.items()
            }
        # Fall back to execution timeframe aggregators
        if self._aggregated:
            return {
                symbol: aggregator.bars
                for symbol, aggregator in self._aggregated.items()
            }
        return self._bars

    def _strategy_bars(self, clock: datetime) -> dict[str, list[Bar]]:
        """Velas de la estrategia: agrega el feed al marco configurado.

        OKX entrega 1m. Una estrategia de 15m no puede mirar la vela de 1m: se
        agrupa por cubo UTC y se descarta el cubo todavía abierto, para que la
        señal use el mismo cierre que el backtest.
        """
        minutes = _timeframe_minutes(self.settings.strategy.timeframe)
        if minutes <= 1:
            return {symbol: list(values) for symbol, values in self._bars.items()}
        step = minutes * 60
        result: dict[str, list[Bar]] = {}
        for symbol, bars in self._bars.items():
            buckets: dict[int, Bar] = {}
            for bar in bars:
                bucket = int(bar.t.timestamp()) // step
                current = buckets.get(bucket)
                if current is None:
                    buckets[bucket] = Bar(
                        t=datetime.fromtimestamp(bucket * step, tz=timezone.utc),
                        o=bar.o,
                        h=bar.h,
                        l=bar.l,
                        c=bar.c,
                        v=bar.v,
                    )
                else:
                    current.h = max(current.h, bar.h)
                    current.l = min(current.l, bar.l)
                    current.c = bar.c
                    current.v += bar.v
            result[symbol] = [
                bar
                for bar in buckets.values()
                if bar.t + timedelta(minutes=minutes) <= clock
            ]
        return result

    def _warmup_progress(self, clock: datetime) -> tuple[bool, str]:
        requirement = self.strategy.warmup_requirements()
        if not requirement.bars:
            return True, ""
        series = self._bar_source()
        for symbol, needed in requirement.bars.items():
            targets = (
                series.values() if symbol == "*" else [series.get(symbol, [])]
            )
            have = min((len(values) for values in targets), default=0)
            if have < needed:
                return False, f"{have}/{needed} velas"
        return True, ""

    def _evaluate(self, tick: Tick, session: SessionInfo) -> None:
        primary = self.settings.instruments.primary
        bars = {symbol: list(values) for symbol, values in self._bar_source().items()}
        if not bars.get(primary):
            return
        # Una vela de senal nueva por evaluacion: con ejecucion de 5 m, la misma
        # vela de 1 h llegaba doce veces y repetia la entrada y el trailing.
        signal_ts = bars[primary][-1].t
        if signal_ts == self._last_signal_ts:
            return
        self._last_signal_ts = signal_ts
        ready, detail = self._warmup_progress(tick.ts)
        if not ready:
            self._output = StrategyOutput(
                state="warmup",
                state_label="Calentando",
                phases=[Phase(key="warmup", label="Calentamiento", status="active", detail=detail)],
            )
            return
        md = MarketData(
            session=session,
            clock=tick.ts,
            primary=primary,
            bars=bars,
            params=self.strategy.params,
            context={"tick_size": self.settings.instruments.by_symbol(primary).tick_size},
        )
        output = self.strategy.evaluate(md)
        self._output = output
        if output.signal is None:
            # Un veto de geometría/tamaño pertenece a la señal anterior; sin
            # señal nueva no puede seguir presentándose como bloqueo actual.
            if self.state.block_reason in {
                "risk_per_trade",
                "stop_too_wide",
                "stop_too_tight",
                "invalid_stop",
                "invalid_stop_side",
                "invalid_target_side",
                "size_below_minimum",
                "no_price",
            }:
                self.state.block_reason = None
                self.state.block_count = 0
            return
        if self.execution.seen_signal(output.signal.key):
            # `arm` descarta una clave repetida; evaluarla antes de riesgo
            # contaba un rechazo que nunca podía convertirse en orden.
            return
        if not session.is_open:
            self.state.block_reason = "outside_window"
            self._note_rejection("outside_window", "la sesión está cerrada", tick.ts)
            return
        if (
            self.mode in {"paper", "live"}
            and self.state.provider in {"okx", "live"}
            and self.state.quality == "stale"
        ):
            # Una conexión viva no basta: sin velas frescas no se autoriza una
            # entrada nueva. El feed puede seguir gestionando la posición.
            self.state.block_reason = "stale_data"
            self._note_rejection("stale_data", "el feed está obsoleto", tick.ts)
            return
        guard = self.edge_guard
        if guard is not None and guard.passes is False:
            # Sin ventaja medida por encima del coste no se abre nada: acertar
            # más de lo que se pierde no basta si el peaje se come la ventaja.
            self.state.block_reason = "edge_below_cost"
            self._note_rejection("edge_below_cost", guard.detail(), tick.ts)
            return
        spec = self.settings.instruments.by_symbol(primary)
        template = self.settings.instruments.template_for(primary)
        last_price = tick.bars[primary].c if primary in tick.bars else None
        portfolio = PortfolioState(
            equity=self.state.equity,
            peak_equity=max(self.peak_equity, self.state.equity),
            open_risk=self.state.open_risk,
            unrealized=self.state.unrealized,
            daily_pnl=self.state.day_stats.pnl,
            daily_trades=self.state.day_stats.trades,
            consecutive_losses=self.state.day_stats.consecutive_losses,
            last_exit_ts=self.last_exit_ts,
            emergency=self.state.emergency,
            has_open_position=self.execution.position is not None,
            has_pending_order=self.execution.has_pending(),
            last_price=last_price,
        )
        # Peaje real de ida y vuelta por unidad. Riesgo lo compara con lo que se
        # pierde en el stop: si la comisión se come una parte grande del riesgo,
        # la señal no tiene edge aunque acierte.
        fee_per_unit = (
            self.execution.round_trip_fee_per_unit(primary, last_price)
            if last_price
            else 0.0
        )
        decision = self.risk.evaluate(
            output.signal,
            portfolio,
            spec,
            clock=tick.ts,
            timezone_name=template.timezone,
            fee_per_unit=fee_per_unit,
        )
        if not decision.approved:
            self.state.block_reason = decision.code
            self._note_rejection(decision.code, decision.message, tick.ts)
            return
        if output.signal.valid_until is not None:
            live = self.mode in {"paper", "live"} and self.state.provider in {"okx", "live"}
            clock = now_utc() if live else tick.ts
            if _aware(clock) > _aware(output.signal.valid_until):
                # Riesgo ya evaluó el estado duro para no enmascarar un muro
                # activo; la caducidad veta antes de crear cualquier orden.
                self.state.block_reason = "stale_signal"
                self._note_rejection("stale_signal", "la señal venció", clock)
                return

        prior_block = self.state.block_reason
        live = self.mode in {"paper", "live"} and self.state.provider in {"okx", "live"}
        order = self.execution.arm(
            decision,
            output.signal,
            primary,
            last_price or output.signal.stop_price,
            tick.ts,
            armed_at=now_utc() if live else None,
        )
        if order is not None:
            self.state.block_reason = None
            self.state.block_count = 0
            self.state.orders = list(self.execution.orders)
            self._event(
                "info",
                "execution",
                "orden armada",
                {"symbol": primary, "units": decision.units, "side": output.signal.side},
            )
        elif prior_block == "stale_order" or prior_block in EXECUTION_REJECTIONS:
            self.state.block_reason = prior_block
            self.state.block_count = 0
        else:
            self.state.block_reason = None
            self.state.block_count = 0

    def _expire_blocks(self, clock: datetime) -> None:
        """Un bloqueo caduca cuando su condición deja de cumplirse, no solo al reevaluar."""
        reason = self.state.block_reason
        if reason is None:
            return
        cfg = self.settings.risk
        expired = False
        if reason == "consecutive_losses":
            if not cfg.no_trade_after_consecutive_losses:
                expired = True
            elif self.state.day_stats.consecutive_losses < cfg.no_trade_after_consecutive_losses:
                expired = True
            elif cfg.loss_streak_cooldown_min and self.last_exit_ts is not None:
                elapsed = (_aware(clock) - _aware(self.last_exit_ts)).total_seconds()
                expired = elapsed >= cfg.loss_streak_cooldown_min * 60
        elif reason == "cooldown_active":
            expired = (
                self.last_exit_ts is None
                or (_aware(clock) - _aware(self.last_exit_ts)).total_seconds()
                >= cfg.cooldown_minutes * 60
            )
        elif reason == "outside_window":
            template = self.settings.instruments.template_for(self.settings.instruments.primary)
            expired = bool(self.state.session and self.state.session.is_open) and self.risk._outside_window(
                clock, template.timezone
            ) is None
        elif reason == "max_drawdown_reached" and self.peak_equity > 0:
            drawdown_pct = (self.peak_equity - self.state.equity) / self.peak_equity * 100
            threshold = cfg.max_drawdown_pct * (
                cfg.soft_brake_halt_multiple if cfg.soft_brakes else 1.0
            )
            expired = drawdown_pct < threshold
        elif reason == "stale_data":
            expired = self.state.quality != "stale"
        if expired:
            self.state.block_reason = None
            self.state.block_count = 0

    def rejection_totals(self) -> dict[str, int]:
        """Señales rechazadas en toda la corrida, por código de riesgo."""
        return dict(self._rejection_totals)

    def _note_rejection(self, code: str, message: str, when: datetime) -> None:
        """Cuenta cada rechazo y registra el primero más uno por ventana.

        Una estrategia que dispara en cada vela no debe enterrar la consola.
        """
        entry = self._rejections.setdefault(
            code, {"count": 0, "last": None, "message": message}
        )
        entry["count"] = int(entry["count"]) + 1
        entry["message"] = message
        self._rejection_totals[code] = self._rejection_totals.get(code, 0) + 1
        self.state.block_count = int(entry["count"])
        last = entry["last"]
        first = last is None
        if not first and (when - last).total_seconds() < REJECTION_LOG_INTERVAL_S:
            return
        entry["last"] = when
        self._event(
            "warn" if first else "info",
            "risk",
            f"señal rechazada: {message}",
            {"code": code, "count": entry["count"]},
        )

    def _maybe_close_at_session_end(self, tick: Tick) -> None:
        template = self.settings.instruments.template_for(self.settings.instruments.primary)
        local = to_zone(tick.ts, template.timezone)
        close_h, close_m = parse_hhmm(self.settings.risk.session_close_time)
        if (local.hour, local.minute) < (close_h, close_m):
            return
        trade = self.execution.close("session_close", when=tick.ts)
        if trade is not None:
            self._on_trade_closed(trade)

    def _restore_day_stats(self) -> None:
        """Reconstruye el día desde el libro, nunca desde una caché que puede quedar a medias.

        El cierre de una operación y su `kv` no son una sola transacción: si el
        proceso muere entre ambos, confiar en `day_stats` haría que el límite
        diario contara menos de lo que realmente ocurrió.
        """
        current = self.state.session
        self.state.day_stats = DayStats()
        if current is None:
            return
        start, end = _aware(current.open_ts), _aware(current.close_ts)
        closed = [
            trade
            for trade in self.store.all_trades(mode=self.mode)
            if start <= _aware(trade.closed_ts) < end
        ]
        closed.sort(key=lambda trade: _aware(trade.closed_ts))
        for trade in closed:
            self.state.day_stats.trades += 1
            self.state.day_stats.pnl += trade.pnl_net
            if trade.pnl_net > 0:
                self.state.day_stats.wins += 1
                self.state.day_stats.consecutive_losses = 0
            else:
                self.state.day_stats.losses += 1
                self.state.day_stats.consecutive_losses += 1
        self.store.kv_set("session_id", current.id)
        self.store.kv_set("day_stats", self.state.day_stats.model_dump(mode="json"))

    def _on_new_session(self, session: SessionInfo) -> None:
        self.state.session = session
        self.state.day_stats = DayStats()
        self._rejections.clear()
        self.state.block_count = 0
        if session.is_open:
            self._event("info", "session", f"nueva sesión {session.id}", {"session": session.id})
            self.store.kv_set("session_id", session.id)
        else:
            # Una orden pendiente no puede cruzar el cierre: se ejecutaría en la
            # primera vela de la sesión siguiente con una señal ya vieja.
            pending = [order for order in self.execution.orders if order.status == "pending"]
            if pending:
                self.execution.cancel_all()
                self._event(
                    "info",
                    "execution",
                    f"{len(pending)} orden(es) pendiente(s) cancelada(s) al cerrar la sesión",
                )

    def _on_trade_closed(self, trade: TradeRecord) -> None:
        try:
            trade_id, is_new = self.store.insert_trade_once(trade)
        except ValueError as error:
            # Un cierre imposible (salida antes de la entrada) no se guarda ni
            # se suma: no ocurrió. Queda el evento para poder reconstruir qué
            # barra lo provocó.
            logger.error("operación descartada: %s", error)
            self._event(
                "error",
                "execution",
                "operación descartada: cierre anterior a la apertura",
                {"opened_ts": trade.opened_ts.isoformat(), "closed_ts": trade.closed_ts.isoformat()},
            )
            self.state.position = None
            return
        if not is_new:
            # La fila ya estaba en el libro: sumarla otra vez contaría dos veces el
            # mismo P&L en la equity, el día y la curva (reinicio con backfill,
            # reintento, replay). El registro es el mismo, así que la cuenta también.
            logger.warning("operación %s ya registrada; no se contabiliza otra vez", trade_id)
            self.state.position = None
            return
        self.invalidate_stats()
        self.state.equity += trade.pnl_net
        self.peak_equity = max(self.peak_equity, self.state.equity)
        self.state.day_stats.trades += 1
        self.state.day_stats.pnl += trade.pnl_net
        if trade.pnl_net > 0:
            self.state.day_stats.wins += 1
            self.state.day_stats.consecutive_losses = 0
        elif trade.pnl_net < 0:
            self.state.day_stats.losses += 1
            self.state.day_stats.consecutive_losses += 1
        self.last_exit_ts = trade.closed_ts
        self.store.append_equity(self.state.equity, trade.closed_ts)
        self.state.position = None
        self._event(
            "info",
            "execution",
            f"operación cerrada ({trade.exit_reason})",
            {"pnl_net": trade.pnl_net, "r": trade.r_multiple},
        )

    # --- persistence ------------------------------------------------------
    def _load_chart_seed(self) -> None:
        """Da contexto al gráfico aunque el paper esté parado.

        El feed solo llena ``_bars`` cuando corre el motor; con el motor
        detenido el dashboard se quedaba sin velas. Se usan las últimas velas
        de 1m ya descargadas, solo como historial de chart: no se arranca el
        feed ni el paper.

        El seed toca **solo** el gráfico. ``_bars`` es la entrada de la
        estrategia y ``last_bar_ts`` es la salud del feed; sembrarlos con un CSV
        viejo hacía que la terminal anunciara un mercado que llevaba semanas sin
        llegar (y que la estrategia pudiera evaluar velas de octubre mezcladas
        con las de hoy). Un historial de chart no es un tick.
        """
        if self.settings.feed.provider != "okx":
            return
        path = Path("data/recent_1m.csv")
        if not path.is_file():
            return
        primary = self.settings.instruments.primary
        bars: deque[Bar] = deque(maxlen=CHART_MAX_BARS)
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    if row.get("symbol") != primary:
                        continue
                    try:
                        stamp = datetime.fromisoformat(
                            str(row["ts"]).replace("Z", "+00:00")
                        )
                        bars.append(
                            Bar(
                                t=stamp,
                                o=float(row["o"]),
                                h=float(row["h"]),
                                l=float(row["l"]),
                                c=float(row["c"]),
                                v=float(row["v"]),
                            )
                        )
                    except (KeyError, TypeError, ValueError):
                        continue
        except OSError:
            return
        if not bars:
            return
        self._chart_bars = list(bars)
        self._chart_symbol = primary

    def _restore(self) -> None:
        position_raw = self.store.kv_get("position")
        if position_raw:
            try:
                self.execution.restore(Position.model_validate(position_raw))
                self.state.position = self.execution.position
            except ValueError:
                logger.warning("discarded unreadable position state")
        if self.state.position is not None:
            self._replay_barrier = self.state.position.opened_ts
        self.state.emergency = bool(self.store.kv_get("emergency") or False)
        if self.state.emergency:
            self.state.block_reason = "emergency_active"
        # El equity se recalcula desde el libro. La copia en `kv` puede venir de
        # un cierre contado dos veces (pasó: 24.210,09 guardados frente a
        # 24.356,41 reales) y entonces el panel miente hasta que alguien
        # reconstruya a mano.
        computed = self.settings.risk.initial_capital + self.store.realized_pnl(mode=self.mode)
        saved = self.store.kv_get("equity")
        if saved is not None and abs(float(saved) - computed) > 0.01:
            logger.warning(
                "equity guardada %.2f != libro %.2f; manda el libro",
                float(saved),
                computed,
            )
        self.state.equity = computed
        # El pico es lo que mide el drawdown: si no se guarda, cada reinicio
        # devuelve el freno a tamaño completo como si no hubiera pasado nada.
        saved_peak = self.store.kv_get("peak_equity")
        if saved_peak is not None:
            try:
                self.peak_equity = max(float(saved_peak), self.state.equity)
            except (TypeError, ValueError):
                logger.warning("discarded unreadable peak equity")
        # Sin copia (o ilegible), el capital inicial no es el pico de una cuenta
        # que ya ganó: el pico nunca puede quedar por debajo de la equity.
        self.peak_equity = max(self.peak_equity, self.state.equity)
        # La pausa tras una racha se cuenta desde la última salida: sin esto, un
        # reinicio del proceso dejaría el bloqueo sin fecha y sin final.
        last_exit = self.store.kv_get("last_exit_ts")
        if last_exit:
            try:
                self.last_exit_ts = datetime.fromisoformat(str(last_exit))
            except ValueError:
                logger.warning("discarded unreadable last_exit_ts")
        if self.last_exit_ts is None:
            recent = self.store.list_trades(limit=1)
            if recent:
                closed = recent[0].get("closed_ts")
                if closed:
                    try:
                        self.last_exit_ts = datetime.fromisoformat(str(closed))
                    except ValueError:
                        pass

    def _persist(self) -> None:
        self.store.kv_set("emergency", self.state.emergency)
        self.store.kv_set("equity", self.state.equity)
        self.store.kv_set("peak_equity", self.peak_equity)
        # Latido para que las herramientas de mantenimiento sepan que la base
        # está viva y no la reescriban bajo un motor que sigue operando.
        self.store.kv_set("heartbeat", datetime.now(timezone.utc).isoformat())
        if self.last_exit_ts is not None:
            self.store.kv_set("last_exit_ts", self.last_exit_ts.isoformat())
        self.store.kv_set("day_stats", self.state.day_stats.model_dump(mode="json"))
        if self.execution.position is not None:
            self.store.kv_set(
                "position", self.execution.position.model_dump(mode="json")
            )
        else:
            self.store.kv_delete("position")

    def _update_open_risk(self) -> None:
        position = self.execution.position
        if position is None:
            self.state.open_risk = 0.0
            self.state.unrealized = 0.0
            return
        spec = self.settings.instruments.by_symbol(position.symbol)
        ticks = abs(position.entry_price - position.stop_price) / spec.tick_size
        self.state.open_risk = ticks * spec.tick_value * position.units
        bars = self._bars.get(position.symbol) or []
        self.state.unrealized = (
            self.execution.open_pnl(position, bars[-1].c) if bars else 0.0
        )

    # --- output -----------------------------------------------------------
    def quotes(self) -> dict[str, dict[str, Any]]:
        payload: dict[str, dict[str, Any]] = {}
        for symbol, bars in self._bars.items():
            if not bars:
                continue
            last = bars[-1]
            first = bars[0]
            change = last.c - first.o
            payload[symbol] = {
                "last": last.c,
                "bid": last.c,
                "ask": last.c,
                "change": change,
                "change_pct": (change / first.o * 100) if first.o else 0.0,
                "ts": last.t,
            }
        return payload

    def series(self) -> list[dict[str, Any]]:
        primary = self.settings.instruments.primary
        base = self._bars.get(primary) or []
        if not base:
            return []
        base_close = base[0].o or 1.0
        result: list[dict[str, Any]] = []
        for symbol, bars in self._bars.items():
            if symbol == primary or not bars:
                continue
            result.append(
                {
                    "symbol": symbol,
                    "label": symbol,
                    "mode": "normalized",
                    "axis": "overlay",
                    "visible": True,
                    "values": [
                        {"t": bar.t, "v": (bar.c / (bars[0].o or 1.0)) - 1.0}
                        for bar in bars
                    ],
                }
            )
        _ = base_close
        return result

    def history(self, timeframe: str = "1m", limit: int = 500) -> list[dict[str, Any]]:
        """Resample the primary series into the requested timeframe."""
        primary = self.settings.instruments.primary
        minutes = _timeframe_minutes(timeframe)
        bars = (
            self._chart_bars
            if self._chart_symbol == primary and self._chart_bars
            else self._bars.get(primary, [])
        )
        if minutes <= 1:
            return [bar.model_dump(mode="json") for bar in bars][-limit:]
        buckets: dict[int, dict[str, Any]] = {}
        for bar in bars:
            bucket = int(bar.t.timestamp()) // (minutes * 60)
            current = buckets.get(bucket)
            if current is None:
                buckets[bucket] = {
                    "t": bar.t,
                    "o": bar.o,
                    "h": bar.h,
                    "l": bar.l,
                    "c": bar.c,
                    "v": bar.v,
                }
            else:
                current["h"] = max(current["h"], bar.h)
                current["l"] = min(current["l"], bar.l)
                current["c"] = bar.c
                current["v"] += bar.v
        return list(buckets.values())[-limit:]

    def stats(self) -> dict[str, Any]:
        """Aggregate stats, cached until a trade closes.

        The WebSocket snapshot carries stats too; recomputing them on every
        publish would read the whole trade table ten times per second.
        """
        if self._stats_cache is None:
            self._stats_cache = aggregate(
                self.store.all_trades(mode=self.mode),
                self.settings.risk.initial_capital,
                timezone_name=self.settings.instruments.template_for(
                    self.settings.instruments.primary
                ).timezone,
            )
        return self._stats_cache

    def invalidate_stats(self) -> None:
        self._stats_cache = None

    def snapshot(self, stats: dict[str, Any] | None = None) -> dict[str, Any]:
        primary = self.settings.instruments.primary
        # Con el motor parado no hay velas de estrategia: el gráfico sigue
        # mostrando el historial ya descargado, que es lo único que existe.
        candles = self._bars.get(primary) or (
            self._chart_bars[-MAX_BARS:] if self._chart_symbol == primary else []
        )
        return self.builder.build(
            self.state,
            self._output,
            quotes=self.quotes(),
            candles=candles,
            series=self.series(),
            stats=stats if stats is not None else self.stats(),
            rejections=self.rejection_totals(),
        )

    async def publish_now(self) -> None:
        """Push a snapshot after a control action.

        The publish loop is throttled, so a button could change the state and the
        UI would keep showing the old one until the next tick. A control that
        answers «running» while the screen says «stopped» is a bug the operator
        reads as a broken terminal.
        """
        self.invalidate_publish()
        await self._publish()

    def invalidate_publish(self) -> None:
        """Force the next tick to publish, e.g. after a control action."""
        self._last_publish_at = 0.0
        self._stats_cache: dict[str, Any] | None = None

    async def _publish(self) -> None:
        if not self._subscribers:
            return
        now = time.monotonic()
        if now - self._last_publish_at < SNAPSHOT_MIN_INTERVAL_S:
            return
        self._last_publish_at = now
        snapshot = self.snapshot()
        for hook in list(self._subscribers):
            result = hook(snapshot)
            if asyncio.iscoroutine(result):
                await result

    # --- events -----------------------------------------------------------
    def _event(self, level: str, category: str, message: str, meta: dict[str, Any] | None = None) -> None:
        self.store.insert_event(level, category, message, meta)
        # The notifier filters by level and dedupes; it never blocks this call.
        if self.notifier is not None:
            self.notifier.enqueue(level, category, message, meta)



TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "30m")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _strategy_key(settings: Settings) -> tuple[str, str, str]:
    """Identity of the configured plugin: id, timeframe and params."""
    return (
        settings.strategy.id,
        settings.strategy.timeframe,
        json.dumps(settings.strategy.params, sort_keys=True, default=str),
    )


def _timeframe_minutes(timeframe: str) -> int:
    """Closed enum: an unknown timeframe is an error, not a silent downgrade.

    Returning 1m candles labelled as "7m" would make the chart lie.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe inválido: {timeframe!r}; válidos {TIMEFRAMES}")
    return int(timeframe.rstrip("m"))
