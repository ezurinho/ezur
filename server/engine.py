"""Trading engine.

Owns the cycle: session detection, execution, strategy evaluation, risk
authorisation, persistence and snapshot emission. It knows nothing about any
instrument name or any strategy rule.
"""

from __future__ import annotations

import asyncio
import json
import time
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from .config import Settings
from .db import Store
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
from .snapshot import SnapshotBuilder
from .stats import aggregate
from .strategy.base import BaseStrategy, MarketData, Phase, StrategyOutput
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
        # Peak equity is what the trailing drawdown guard measures against.
        self.peak_equity = settings.risk.initial_capital
        self._bars: dict[str, list[Bar]] = {
            symbol: [] for symbol in settings.instruments.symbols
        }
        self._output: StrategyOutput | None = None
        self._subscribers: list[SnapshotHook] = []
        self._task: asyncio.Task[None] | None = None
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
        if self.state.session is None:
            primary = settings.instruments.primary
            self.state.session = session_for(
                now_utc(), settings.instruments.template_for(primary)
            )
        self._restore_day_stats()

    # --- lifecycle --------------------------------------------------------
    def start(self) -> None:
        self.invalidate_publish()
        if self.state.emergency:
            raise RuntimeError("emergency stop is active; disable it first")
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
        self.settings = settings
        self.risk = RiskManager(settings.risk)
        self.execution.config = settings.execution
        self.execution.instruments = {
            item.symbol: item for item in settings.instruments.items
        }
        self.builder.settings = settings
        self.invalidate_stats()
        self._sync_strategy_meta()
        if self.strategy_factory is not None and _strategy_key(settings) != self._strategy_key:
            # Swapping the plugin or its parameters keeps the engine honest: the
            # old instance would validate the new parameters against its own model.
            self.strategy = self.strategy_factory(settings)
            self._strategy_key = _strategy_key(settings)
            self._sync_strategy_meta()
            self._output = None
            self._rejections.clear()
            self.state.block_reason = None
            self.state.block_count = 0
        for symbol in settings.instruments.symbols:
            self._bars.setdefault(symbol, [])
        if self.feed_factory is not None and self.feed is not None:
            # A new instrument needs data: rebuild the feed and drop stale bars
            # rather than mixing two sessions of the same timestamps.
            self.feed = self.feed_factory(settings)
            self._bars = {symbol: [] for symbol in settings.instruments.symbols}
            self._previous_tick_ts = None
            self.state.bars_available = 0
            self.state.last_bar_ts = None
            if self.state.status == "running":
                # Restart even when the previous replay had already finished:
                # otherwise the operator changes instruments and watches an
                # empty chart forever, with the engine still claiming "running".
                try:
                    asyncio.get_running_loop().create_task(self.refresh_task())
                except RuntimeError:
                    pass

    def _sync_strategy_meta(self) -> None:
        self.builder.strategy_meta = {
            "id": self.strategy.id,
            "name": getattr(self.strategy, "name", self.strategy.id),
            "version": self.strategy.version,
        }

    async def refresh_task(self) -> None:
        await self.stop_task()
        self.start_task()

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

    def start_task(self) -> None:
        if self._task is None or self._task.done():
            # Cada tarea consume su propio flujo: la guarda de orden no puede
            # comparar el primer tick de un replay con el último del anterior.
            self._previous_tick_ts = None
            self._task = asyncio.create_task(self.run())

    async def stop_task(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None

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

        for symbol, bar in tick.bars.items():
            if symbol not in self._bars:
                continue
            self._bars[symbol].append(bar)
            del self._bars[symbol][:-MAX_BARS]

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

        if self.execution.position is not None and self.settings.risk.close_at_session_end:
            self._maybe_close_at_session_end(tick)
        self.state.position = self.execution.position
        self.state.orders = list(self.execution.orders)

        if self.state.status == "running":
            self._evaluate(tick, session)

        # En un backtest el estado vive en memoria y nadie reinicia a mitad: no
        # hay nada que restaurar. Persistirlo en cada vela son ~250.000
        # escrituras por corrida que solo cuestan tiempo (17,9 s -> 13,1 s).
        if self.mode != "backtest":
            self._persist()
        self._update_open_risk()

    def _warmup_progress(self) -> tuple[bool, str]:
        requirement = self.strategy.warmup_requirements()
        if not requirement.bars:
            return True, ""
        for symbol, needed in requirement.bars.items():
            targets = (
                self._bars.values()
                if symbol == "*"
                else [self._bars.get(symbol, [])]
            )
            have = min((len(values) for values in targets), default=0)
            if have < needed:
                return False, f"{have}/{needed} velas"
        return True, ""

    def _evaluate(self, tick: Tick, session: SessionInfo) -> None:
        primary = self.settings.instruments.primary
        bars = {symbol: list(values) for symbol, values in self._bars.items()}
        if not bars.get(primary):
            return
        ready, detail = self._warmup_progress()
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
        )
        output = self.strategy.evaluate(md)
        self._output = output
        if output.signal is None:
            return

        spec = self.settings.instruments.by_symbol(primary)
        template = self.settings.instruments.template_for(primary)
        last_price = tick.bars[primary].c if primary in tick.bars else None
        portfolio = PortfolioState(
            equity=self.state.equity,
            peak_equity=max(self.peak_equity, self.state.equity),
            open_risk=self.state.open_risk,
            daily_pnl=self.state.day_stats.pnl,
            daily_trades=self.state.day_stats.trades,
            consecutive_losses=self.state.day_stats.consecutive_losses,
            last_exit_ts=self.last_exit_ts,
            emergency=self.state.emergency,
            has_open_position=self.execution.position is not None,
            has_pending_order=self.execution.has_pending(),
            last_price=last_price,
        )
        decision = self.risk.evaluate(
            output.signal,
            portfolio,
            spec,
            clock=tick.ts,
            timezone_name=template.timezone,
        )
        if not decision.approved:
            self.state.block_reason = decision.code
            self._note_rejection(decision.code, decision.message, tick.ts)
            return

        self.state.block_reason = None
        self.state.block_count = 0
        order = self.execution.arm(
            decision, output.signal, primary, last_price or output.signal.stop_price, tick.ts
        )
        if order is not None:
            self.state.orders = list(self.execution.orders)
            self._event(
                "info",
                "execution",
                "orden armada",
                {"symbol": primary, "units": decision.units, "side": output.signal.side},
            )

    def rejection_totals(self) -> dict[str, int]:
        """Señales rechazadas en toda la corrida, por código de riesgo."""
        return dict(self._rejection_totals)

    def _note_rejection(self, code: str, message: str, when: datetime) -> None:
        """Count every rejection, log the first one and then at most one per window.

        A strategy that fires on every bar would otherwise write thousands of
        identical events and bury the console.
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
        """El día se cuenta desde el libro, no desde lo último que quedó en `kv`.

        Al arrancar, la sesión se fija en la de ahora, así que el cambio de
        sesión nunca salta en el primer tick y el contador de ayer sobrevivía al
        reinicio: el límite diario llegaba agotado y el bot no abría nada. Solo
        se respeta lo guardado si pertenece a la sesión actual; si no, se
        reconstruye con las operaciones cerradas hoy.
        """
        current = self.state.session
        saved = self.store.kv_get("day_stats")
        stored_session = self.store.kv_get("session_id")
        if saved and current is not None and stored_session == current.id:
            try:
                self.state.day_stats = DayStats.model_validate(saved)
                return
            except ValueError:
                logger.warning("discarded unreadable day stats")
        self.state.day_stats = DayStats()
        if current is None:
            return
        start, end = _aware(current.open_ts), _aware(current.close_ts)
        closed = [
            trade
            for trade in self.store.all_trades()
            if start <= _aware(trade.closed_ts) < end
        ]
        closed.sort(key=lambda trade: trade.closed_ts)
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

    def _on_new_session(self, session: SessionInfo) -> None:
        self.state.session = session
        self.state.day_stats = DayStats()
        self._rejections.clear()
        self.state.block_count = 0
        if session.is_open:
            self._event("info", "session", f"nueva sesión {session.id}", {"session": session.id})
            self.store.kv_set("session_id", session.id)

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
        computed = self.settings.risk.initial_capital + self.store.realized_pnl()
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
            return
        spec = self.settings.instruments.by_symbol(position.symbol)
        ticks = abs(position.entry_price - position.stop_price) / spec.tick_size
        self.state.open_risk = ticks * spec.tick_value * position.units

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
        bars = self._bars.get(primary, [])
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
                self.store.all_trades(),
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
        return self.builder.build(
            self.state,
            self._output,
            quotes=self.quotes(),
            candles=self._bars.get(primary, []),
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


def _strategy_key(settings: Settings) -> tuple[str, str]:
    """Identity of the configured plugin: id plus its parameters, order-insensitive."""
    return (
        settings.strategy.id,
        json.dumps(settings.strategy.params, sort_keys=True, default=str),
    )


def _timeframe_minutes(timeframe: str) -> int:
    """Closed enum: an unknown timeframe is an error, not a silent downgrade.

    Returning 1m candles labelled as "7m" would make the chart lie.
    """
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"timeframe inválido: {timeframe!r}; válidos {TIMEFRAMES}")
    return int(timeframe.rstrip("m"))
