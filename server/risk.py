"""Risk manager.

The single authority that can authorise a signal. Checks run in a fixed order
and every rejection carries a machine-readable code, so the UI and the tests
agree about why nothing was traded.
"""

from __future__ import annotations

from datetime import datetime, timezone

from .config import InstrumentConfig, RiskConfig
from .models import PortfolioState, RiskDecision
from .strategy.base import Signal
from .timeutil import to_zone


def _hhmm(value: str) -> tuple[int, int]:
    hours, minutes = value.split(":")
    return int(hours), int(minutes)


def _aware(value: datetime) -> datetime:
    """Una fecha sin zona se interpreta en UTC.

    Restar una fecha ingenua de otra con zona lanza TypeError y tumba el motor
    en el camino del cooldown; el resto del riesgo ya normaliza así.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


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
        fee_per_unit: float = 0.0,
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
        # Multiplicador que acumulan los frenos suaves. Con `soft_brakes`
        # apagado se queda en 1 y todo se comporta como antes: rechazo.
        factor = 1.0
        brakes: list[str] = []
        if cfg.no_trade_after_consecutive_losses and (
            portfolio.consecutive_losses >= cfg.no_trade_after_consecutive_losses
        ) and not _cooldown_elapsed(cfg, portfolio, clock):
            if cfg.soft_brakes:
                factor *= max(cfg.soft_brake_floor, 0.5)
                brakes.append(f"racha de {portfolio.consecutive_losses}")
            elif cfg.loss_streak_cooldown_min:
                return reject(
                    "consecutive_losses",
                    f"racha de pérdidas: {cfg.loss_streak_cooldown_min} min desde la última salida",
                )
            else:
                return reject("consecutive_losses", "racha de pérdidas alcanzada")
        if cfg.max_drawdown_pct and portfolio.peak_equity > 0:
            # Peak-to-trough on realised equity, not on the sum of trade ratios:
            # a ratios-based guard is not a drawdown guard (freqtrade learned it).
            drawdown = (portfolio.peak_equity - portfolio.equity) / portfolio.peak_equity
            drawdown_pct = drawdown * 100
            if cfg.soft_brakes:
                if drawdown_pct >= cfg.max_drawdown_pct * cfg.soft_brake_halt_multiple:
                    return reject(
                        "max_drawdown_reached",
                        f"drawdown {drawdown_pct:.2f}% supera el tope duro del freno",
                    )
                step = _drawdown_size(drawdown_pct, cfg.max_drawdown_pct, cfg.soft_brake_floor)
                if step < 1.0:
                    factor *= step
                    brakes.append(f"drawdown {drawdown_pct:.2f}%")
            elif drawdown_pct >= cfg.max_drawdown_pct:
                return reject(
                    "max_drawdown_reached",
                    f"drawdown {drawdown_pct:.2f}% desde el pico",
                )

        entry = portfolio.last_price if portfolio.last_price is not None else None
        if entry is None:
            return reject("no_price", "sin precio de referencia")

        stop_distance = abs(entry - signal.stop_price)
        if stop_distance <= 0:
            return reject("invalid_stop", "el stop no puede estar en el precio de entrada")

        # El stop tiene que estar del lado que pierde y el objetivo del lado que
        # gana. Un plugin con el signo cambiado abre una operación que «salta el
        # stop» en la primera vela y se apunta como si fuera una pérdida de
        # mercado: el ledger miente sin que nada falle.
        is_long = signal.side == "long"
        if (is_long and signal.stop_price > entry) or (
            not is_long and signal.stop_price < entry
        ):
            return reject(
                "invalid_stop_side",
                "el stop de un %s debe quedar %s de la entrada"
                % (signal.side, "por debajo" if is_long else "por encima"),
            )
        if signal.target_price is not None and (
            (is_long and signal.target_price <= entry)
            or (not is_long and signal.target_price >= entry)
        ):
            return reject(
                "invalid_target_side",
                "el objetivo de un %s debe quedar %s de la entrada"
                % (signal.side, "por encima" if is_long else "por debajo"),
            )

        stop_ticks = stop_distance / instrument.tick_size
        # 0 es sin tope, igual que en min_stop_ticks: si no, subir el límite
        # con --max-stop-ticks 0 rechazaba todas las señales.
        if cfg.max_stop_ticks and stop_ticks > cfg.max_stop_ticks:
            return reject("stop_too_wide", f"stop de {stop_ticks:.0f} ticks supera el máximo")
        if cfg.min_stop_ticks and stop_ticks < cfg.min_stop_ticks:
            return reject(
                "stop_too_tight",
                f"stop de {stop_ticks:.0f} ticks por debajo del mínimo",
            )

        risk_per_unit = stop_distance / instrument.tick_size * instrument.tick_value
        # El coste también es riesgo: una operación que paga 0,3 R de comisión
        # necesita acertar tres de cada diez más solo para empatar. El peaje se
        # mide contra la pérdida en el stop, que es el 1 R de la señal.
        if cfg.max_cost_r and fee_per_unit > 0 and risk_per_unit > 0:
            cost_r = fee_per_unit / risk_per_unit
            if cost_r > cfg.max_cost_r:
                return reject(
                    "cost_above_budget",
                    f"el peaje de ida y vuelta cuesta {cost_r:.3f} R y el máximo "
                    f"es {cfg.max_cost_r:g} R: el stop es demasiado estrecho",
                )

        if clock is not None and timezone_name is not None:
            window_code = self._outside_window(clock, timezone_name)
            if window_code:
                return reject(window_code[0], window_code[1])

        daily_loss_limit = -abs(cfg.initial_capital * cfg.max_daily_loss_pct / 100)
        if cfg.soft_brakes and daily_loss_limit and portfolio.daily_pnl <= daily_loss_limit * 0.8:
            # Antes del muro, media máquina: el día sigue vivo y el límite duro
            # sigue siendo duro.
            factor *= 0.5
            brakes.append("pérdida diaria al 80%")
        if portfolio.daily_pnl <= daily_loss_limit:
            return reject("daily_loss_limit", "límite de pérdida diaria alcanzado")

        if cfg.max_daily_profit_pct:
            profit_limit = cfg.initial_capital * cfg.max_daily_profit_pct / 100
            if portfolio.daily_pnl >= profit_limit:
                return reject("daily_profit_limit", "límite de beneficio diario alcanzado")

        if cfg.cooldown_minutes and portfolio.last_exit_ts is not None and clock is not None:
            elapsed = (
                _aware(clock) - _aware(portfolio.last_exit_ts)
            ).total_seconds() / 60
            if 0 <= elapsed < cfg.cooldown_minutes:
                return reject("cooldown_active", "cooldown tras la última salida")

        budget = portfolio.equity * cfg.risk_per_trade_pct / 100
        units = int(budget // risk_per_unit) if risk_per_unit > 0 else 0
        units = min(units, cfg.max_units_per_trade)
        base_units = units
        if factor < 1.0:
            units = int(units * factor)
        lot = instrument.lot_size
        if lot < 1:
            raise ValueError("lot_size must be at least 1")
        units = (units // lot) * lot
        realized_factor = units / base_units if base_units > 0 else 0.0
        if units < 1:
            return reject(
                "size_below_minimum",
                "el dimensionado resulta en menos de un lote"
                + (f" con el freno a {factor:.0%}" if factor < 1.0 else ""),
            )
        if instrument.min_notional is not None:
            if instrument.contract_size is None:
                raise ValueError("min_notional requires contract_size")
            notional = entry * instrument.contract_size * units
            if notional < instrument.min_notional:
                return reject(
                    "below_min_notional",
                    f"notional {notional:.2f} por debajo del mínimo {instrument.min_notional:.2f}",
                )

        details = list(brakes)
        if units < int(base_units * factor):
            details.append("redondeo de lote")
        return RiskDecision(
            approved=True,
            code="approved",
            message=(
                f"tamaño al {realized_factor:.0%} ({', '.join(details)})"
                if realized_factor < 1.0 and details
                else ""
            ),
            units=units,
            risk_per_unit=risk_per_unit,
            risk_budget=budget,
            size_factor=round(realized_factor, 4),
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


def _drawdown_size(drawdown_pct: float, limit: float, floor: float) -> float:
    """Tamaño según el drawdown: completo hasta medio límite, `floor` al límite.

    Lineal entre los dos puntos. Pasado el límite se mantiene el suelo: el tope
    duro lo pone el llamante con `soft_brake_halt_multiple`.
    """
    half = limit / 2
    if drawdown_pct <= half or limit <= 0:
        return 1.0
    if drawdown_pct >= limit:
        return floor
    progress = (drawdown_pct - half) / (limit - half)
    return 1.0 - progress * (1.0 - floor)


def _cooldown_elapsed(
    cfg: RiskConfig, portfolio: PortfolioState, clock: datetime | None
) -> bool:
    """¿Ya pasó la pausa que sigue a la racha de pérdidas?

    Con ``loss_streak_cooldown_min == 0`` la respuesta es siempre «no»: el
    bloqueo dura hasta el cambio de sesión, que es el comportamiento histórico.
    """
    if not cfg.loss_streak_cooldown_min:
        return False
    if portfolio.last_exit_ts is None:
        return False
    now = _aware(clock or datetime.now(timezone.utc))
    return (now - _aware(portfolio.last_exit_ts)).total_seconds() >= (
        cfg.loss_streak_cooldown_min * 60
    )
