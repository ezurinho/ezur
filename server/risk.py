"""Risk manager.

The single authority that can authorise a signal. Checks run in a fixed order
and every rejection carries a machine-readable code, so the UI and the tests
agree about why nothing was traded.
"""

from __future__ import annotations

from datetime import datetime

from .config import InstrumentConfig, RiskConfig
from .models import PortfolioState, RiskDecision
from .strategy.base import Signal
from .timeutil import to_zone


def _hhmm(value: str) -> tuple[int, int]:
    hours, minutes = value.split(":")
    return int(hours), int(minutes)


class RiskManager:
    def __init__(self, config: RiskConfig) -> None:
        self.config = config

    def evaluate(
        self,
        signal: Signal,
        portfolio: PortfolioState,
        instrument: InstrumentConfig,
        *,
        clock: datetime | None = None,
        timezone_name: str | None = None,
    ) -> RiskDecision:
        cfg = self.config

        def reject(code: str, message: str) -> RiskDecision:
            return RiskDecision(approved=False, code=code, message=message)

        if portfolio.emergency:
            return reject("emergency_active", "parada de emergencia activa")
        if portfolio.has_pending_order:
            return reject("order_pending", "ya hay una orden pendiente")
        if portfolio.has_open_position:
            return reject("position_open", "ya hay una posición abierta")
        if portfolio.daily_trades >= cfg.max_trades_per_day:
            return reject("max_trades_reached", "límite de operaciones diarias")
        if cfg.no_trade_after_consecutive_losses and (
            portfolio.consecutive_losses >= cfg.no_trade_after_consecutive_losses
        ):
            return reject("consecutive_losses", "racha de pérdidas alcanzada")
        if cfg.max_drawdown_pct and portfolio.peak_equity > 0:
            # Peak-to-trough on realised equity, not on the sum of trade ratios:
            # a ratios-based guard is not a drawdown guard (freqtrade learned it).
            drawdown = (portfolio.peak_equity - portfolio.equity) / portfolio.peak_equity
            if drawdown * 100 >= cfg.max_drawdown_pct:
                return reject(
                    "max_drawdown_reached",
                    f"drawdown {drawdown * 100:.2f}% desde el pico",
                )

        entry = portfolio.last_price if portfolio.last_price is not None else None
        if entry is None:
            return reject("no_price", "sin precio de referencia")

        stop_distance = abs(entry - signal.stop_price)
        if stop_distance <= 0:
            return reject("invalid_stop", "el stop no puede estar en el precio de entrada")

        stop_ticks = stop_distance / instrument.tick_size
        if stop_ticks > cfg.max_stop_ticks:
            return reject("stop_too_wide", f"stop de {stop_ticks:.0f} ticks supera el máximo")

        if clock is not None and timezone_name is not None:
            window_code = self._outside_window(clock, timezone_name)
            if window_code:
                return reject(window_code[0], window_code[1])

        daily_loss_limit = -abs(cfg.initial_capital * cfg.max_daily_loss_pct / 100)
        if portfolio.daily_pnl <= daily_loss_limit:
            return reject("daily_loss_limit", "límite de pérdida diaria alcanzado")

        if cfg.max_daily_profit_pct:
            profit_limit = cfg.initial_capital * cfg.max_daily_profit_pct / 100
            if portfolio.daily_pnl >= profit_limit:
                return reject("daily_profit_limit", "límite de beneficio diario alcanzado")

        if cfg.cooldown_minutes and portfolio.last_exit_ts is not None and clock is not None:
            elapsed = (clock - portfolio.last_exit_ts).total_seconds() / 60
            if 0 <= elapsed < cfg.cooldown_minutes:
                return reject("cooldown_active", "cooldown tras la última salida")

        risk_per_unit = stop_distance / instrument.tick_size * instrument.tick_value
        budget = portfolio.equity * cfg.risk_per_trade_pct / 100
        units = int(budget // risk_per_unit) if risk_per_unit > 0 else 0
        units = min(units, cfg.max_units_per_trade)
        if units < 1:
            return reject("size_below_minimum", "el dimensionado resulta en menos de una unidad")

        return RiskDecision(
            approved=True,
            code="approved",
            message="",
            units=units,
            risk_per_unit=risk_per_unit,
        )

    def _outside_window(self, clock: datetime, timezone_name: str) -> tuple[str, str] | None:
        cfg = self.config
        local = to_zone(clock, timezone_name)
        minute_of_day = local.hour * 60 + local.minute

        def minutes(value: str) -> int:
            hours, mins = _hhmm(value)
            return hours * 60 + mins

        if not (minutes(cfg.trade_window_start) <= minute_of_day < minutes(cfg.trade_window_end)):
            return ("outside_window", "fuera de la ventana de entradas")
        if cfg.entry_exclusion_start and cfg.entry_exclusion_end:
            if minutes(cfg.entry_exclusion_start) <= minute_of_day < minutes(cfg.entry_exclusion_end):
                return ("excluded_window", "ventana de exclusión activa")
        return None
