"""Paper execution engine.

Fill, bracket and close. The rule that matters: when a bar touches both the
stop and the target, the stop wins and the trade says so in its diagnostics.

Two fill models, both declared instead of assumed:

* ``next_open`` (default) market order at the next bar's open, slippage bounded
  by ``max_slippage_ticks``. The entry bar counts: if it reaches the stop, the
  trade dies on the bar it was born on and says ``same_bar_exit``.
* ``signal_price`` uses the price the signal was generated at, but only when the
  next bar actually traded through it. If the bar opened past it, the fill
  degrades to ``next_open`` and says ``fill_fallback`` in the diagnostics. If
  OHLC cannot establish whether a stop or target extreme happened before that
  fill, it also degrades instead of using future information.
* Every model rejects an entry whose opening fill is already through the stop
  or has already reached the target. A later stop gap fills at the bar open with
  adverse slippage, never at the stale stop price.

A model that does not change behaviour is a config option that lies, which is
worse than not offering it.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .config import ExecutionConfig, InstrumentConfig
from .models import Bar, Order, Position, RiskDecision, TradeRecord
from .strategy.base import Signal

ExitReason = Literal["stop", "target", "manual", "session_close", "cancel"]

# El histórico viaja en cada snapshot: acotarlo evita que el estado que sirve
# la API crezca con cada señal de una corrida de meses.
MAX_ORDERS = 200


class ExecutionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["fill", "exit", "cancel"]
    symbol: str
    price: float = 0.0
    units: int = 0
    reason: str = ""
    trade: TradeRecord | None = None
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class ExecutionEngine:
    def __init__(
        self,
        config: ExecutionConfig,
        instruments: dict[str, InstrumentConfig],
        mode: str = "paper",
    ) -> None:
        self.config = config
        self.instruments = instruments
        self.mode = mode
        self.position: Position | None = None
        self.orders: list[Order] = []
        self.last_price: float | None = None
        self._seen_signals: set[str] = set()
        self._armed_at: dict[str, datetime] = {}

    # --- helpers ----------------------------------------------------------
    def _instrument(self, symbol: str) -> InstrumentConfig:
        return self.instruments[symbol]

    def _pnl(self, symbol: str, side: str, entry: float, exit_price: float, units: int) -> float:
        spec = self._instrument(symbol)
        ticks = (exit_price - entry) / spec.tick_size
        if side == "short":
            ticks = -ticks
        return ticks * spec.tick_value * units

    def has_pending(self) -> bool:
        return any(order.status == "pending" for order in self.orders)

    def seen_signal(self, key: str) -> bool:
        """La clave ya se armó: reevaluarla solo inflaría los rechazos."""
        return key in self._seen_signals

    # --- lifecycle --------------------------------------------------------
    def arm(
        self,
        decision: RiskDecision,
        signal: Signal,
        symbol: str,
        reference_price: float,
        now: datetime | None = None,
        armed_at: datetime | None = None,
    ) -> Order | None:
        if not decision.approved:
            return None
        if signal.key in self._seen_signals:
            return None
        if self.position is not None or self.has_pending():
            return None
        stamp = now or datetime.now(timezone.utc)
        order = Order(
            id=uuid4().hex[:12],
            symbol=symbol,
            side=signal.side,
            units=decision.units,
            kind="market",
            price=reference_price,
            status="pending",
            created_ts=stamp,
            stop_price=signal.stop_price,
            target_price=signal.target_price,
            signal_key=signal.key,
        )
        self.orders.append(order)
        self._armed_at[order.id] = armed_at or stamp
        self._seen_signals.add(signal.key)
        self._trim_orders()
        return order

    def _trim_orders(self) -> None:
        if len(self.orders) <= MAX_ORDERS:
            return
        pending = [order for order in self.orders if order.status == "pending"]
        history = [order for order in self.orders if order.status != "pending"]
        room = max(0, MAX_ORDERS - len(pending))
        self.orders = (history[-room:] if room else []) + pending

    def on_bar(self, bars: dict[str, Bar]) -> list[ExecutionEvent]:
        events: list[ExecutionEvent] = []
        pending = [order for order in self.orders if order.status == "pending"]
        for order in pending:
            # Una cancelación puede haber llegado después de tomar la foto de
            # pendientes. El estado manda justo antes de tocar el libro.
            if order.status != "pending":
                continue
            bar = bars.get(order.symbol)
            if bar is None:
                continue
            plan = self._fill_plan(order, bar)
            if plan is None:
                order.status = "rejected"
                spec = self._instrument(order.symbol)
                slip = min(self.config.slippage_ticks, self.config.max_slippage_ticks) * spec.tick_size
                candidate_fill = bar.o + slip if order.side == "long" else bar.o - slip
                events.append(
                    ExecutionEvent(
                        type="cancel",
                        symbol=order.symbol,
                        units=order.units,
                        reason=self._entry_rejection(order, bar) or "gap_through_stop",
                        diagnostics={
                            "signal_price": order.price,
                            "bar_open": bar.o,
                            "candidate_fill": candidate_fill,
                            "stop_price": order.stop_price,
                            "target_price": order.target_price,
                            "fill_model": self.config.fill_model,
                            "order_id": order.id,
                            "signal_key": order.signal_key,
                        },
                    )
                )
                continue
            fill, reason, fill_diagnostics = plan
            notional_rejection = self._notional_rejection(order, fill)
            if notional_rejection is not None:
                order.status = "rejected"
                events.append(
                    ExecutionEvent(
                        type="cancel",
                        symbol=order.symbol,
                        units=order.units,
                        reason=notional_rejection,
                        diagnostics={
                            "fill_price": fill,
                            "fill_model": self.config.fill_model,
                            "notional": fill * self._instrument(order.symbol).contract_size * order.units,
                            "min_notional": self._instrument(order.symbol).min_notional,
                            "contract_size": self._instrument(order.symbol).contract_size,
                            "order_id": order.id,
                            "signal_key": order.signal_key,
                        },
                    )
                )
                continue
            order.status = "filled"
            order.price = fill
            self.position = Position(
                symbol=order.symbol,
                side=order.side,
                units=order.units,
                entry_price=fill,
                stop_price=order.stop_price or fill,
                target_price=order.target_price,
                opened_ts=bar.t,
                entry_fees=self.config.commission_per_unit_side * order.units,
                entry_slippage=abs(fill - bar.o),
                signal_key=order.signal_key,
            )
            events.append(
                ExecutionEvent(
                    type="fill",
                    symbol=order.symbol,
                    price=fill,
                    units=order.units,
                    reason=reason,
                    diagnostics=fill_diagnostics,
                )
            )
        if self.position is not None:
            bar = bars.get(self.position.symbol)
            if bar is not None:
                self.last_price = bar.c
                hit = self._bracket_hit(self.position, bar)
                if hit is not None:
                    # A trade that dies on the bar it was born on is worth
                    # flagging: it means the bracket was too tight for the open.
                    diagnostics = dict(hit.diagnostics)
                    if bar.t == self.position.opened_ts:
                        diagnostics["same_bar_exit"] = True
                    events.append(
                        ExecutionEvent(
                            type="exit",
                            symbol=self.position.symbol,
                            price=hit.price,
                            units=self.position.units,
                            reason=hit.reason,
                            trade=self.close(hit.reason, hit.price, bar.t, diagnostics),
                            diagnostics=diagnostics,
                        )
                    )
        return events

    def _entry_rejection(self, order: Order, bar: Bar) -> str | None:
        spec = self._instrument(order.symbol)
        slip = min(self.config.slippage_ticks, self.config.max_slippage_ticks) * spec.tick_size
        slipped = bar.o + slip if order.side == "long" else bar.o - slip
        if order.stop_price is not None:
            gapped = (
                slipped <= order.stop_price
                if order.side == "long"
                else slipped >= order.stop_price
            )
            if gapped:
                return "gap_through_stop"
        if order.target_price is not None:
            reached = (
                slipped >= order.target_price
                if order.side == "long"
                else slipped <= order.target_price
            )
            if reached:
                return "gap_through_target"
        return None

    def _notional_rejection(self, order: Order, fill: float) -> str | None:
        spec = self._instrument(order.symbol)
        if spec.min_notional is None:
            return None
        if spec.contract_size is None:
            raise ValueError("min_notional requires contract_size")
        if fill * spec.contract_size * order.units < spec.min_notional:
            return "below_min_notional"
        return None

    def _fill_plan(
        self, order: Order, bar: Bar
    ) -> tuple[float, str, dict[str, Any]] | None:
        """Price, reason and diagnostics for one pending order, or None to reject."""
        spec = self._instrument(order.symbol)
        ticks = min(self.config.slippage_ticks, self.config.max_slippage_ticks)
        slip = ticks * spec.tick_size
        slipped = bar.o + slip if order.side == "long" else bar.o - slip
        model = self.config.fill_model

        if self._entry_rejection(order, bar) is not None:
            return None

        if model == "signal_price":
            reference = order.price + slip if order.side == "long" else order.price - slip
            inside = bar.l <= reference <= bar.h
            if inside:
                if order.stop_price is not None:
                    tol = spec.tick_size / 2
                    # OHLC no dice si este extremo ocurrió antes o después de
                    # un fill dentro de la vela. Usarlo sería look-ahead; se
                    # degrada a la apertura, donde todo el rango es posterior.
                    pre_entry_stop = (
                        bar.l <= order.stop_price + tol
                        if order.side == "long"
                        else bar.h >= order.stop_price - tol
                    )
                    if pre_entry_stop:
                        return slipped, "next_open", {"fill_fallback": "pre_entry_stop_unknown"}
                if order.target_price is not None:
                    tol = spec.tick_size / 2
                    pre_entry_target = (
                        bar.h >= order.target_price - tol
                        if order.side == "long"
                        else bar.l <= order.target_price + tol
                    )
                    if pre_entry_target:
                        return slipped, "next_open", {"fill_fallback": "pre_entry_target_unknown"}
                return reference, "signal_price", {}
            return slipped, "next_open", {"fill_fallback": "outside_range"}

        return slipped, "next_open", {}

    def _bracket_hit(self, position: Position, bar: Bar) -> "_Hit | None":
        spec = self._instrument(position.symbol)
        tol = spec.tick_size / 2
        slip = min(self.config.slippage_ticks, self.config.max_slippage_ticks) * spec.tick_size
        stop = position.stop_price
        target = position.target_price
        if position.side == "long":
            # Un stop de mercado no garantiza el precio de un gap: sale a la
            # apertura, con deslizamiento adverso, no al nivel ya sobrepasado.
            if bar.o <= stop + tol:
                return _Hit(
                    price=bar.o - slip,
                    reason="stop",
                    diagnostics={"gap_stop": True, "bar_open": bar.o},
                )
            stop_hit = bar.l <= stop + tol
            target_hit = target is not None and bar.h >= target - tol
            if stop_hit and target_hit:
                return _Hit(price=stop, reason="stop", diagnostics={"ambiguous_bar": True})
            if stop_hit:
                return _Hit(price=stop, reason="stop", diagnostics={})
            if target_hit and target is not None:
                return _Hit(price=max(target, bar.o), reason="target", diagnostics={})
        else:
            if bar.o >= stop - tol:
                return _Hit(
                    price=bar.o + slip,
                    reason="stop",
                    diagnostics={"gap_stop": True, "bar_open": bar.o},
                )
            stop_hit = bar.h >= stop - tol
            target_hit = target is not None and bar.l <= target + tol
            if stop_hit and target_hit:
                return _Hit(price=stop, reason="stop", diagnostics={"ambiguous_bar": True})
            if stop_hit:
                return _Hit(price=stop, reason="stop", diagnostics={})
            if target_hit and target is not None:
                return _Hit(price=min(target, bar.o), reason="target", diagnostics={})
        return None

    def close(
        self,
        reason: str,
        price: float | None = None,
        when: datetime | None = None,
        diagnostics: dict[str, Any] | None = None,
        funding: float = 0.0,
    ) -> TradeRecord | None:
        if self.position is None:
            return None
        position = self.position
        close_diagnostics = dict(diagnostics or {})
        if price is not None:
            exit_price = price
        elif self.last_price is not None:
            spec = self._instrument(position.symbol)
            slip = min(self.config.slippage_ticks, self.config.max_slippage_ticks) * spec.tick_size
            exit_price = (
                self.last_price + slip if position.side == "long" else self.last_price - slip
            )
            close_diagnostics["exit_slippage"] = slip
        else:
            exit_price = position.entry_price
        stamp = when or datetime.now(timezone.utc)
        pnl_gross = self._pnl(position.symbol, position.side, position.entry_price, exit_price, position.units)
        fees = self.config.commission_per_unit_side * position.units * 2
        risk = self._risk_per_unit(position)
        # El funding se pasa explícitamente cuando una fuente lo mide; por
        # defecto 0, no un cargo inventado. El neto siempre es la suma de sus
        # componentes y así la equity puede reconstruirse desde ellos.
        pnl_net = pnl_gross - fees + funding
        trade = TradeRecord(
            symbol=position.symbol,
            side=position.side,
            units=position.units,
            entry_price=position.entry_price,
            exit_price=exit_price,
            stop_price=position.stop_price,
            target_price=position.target_price,
            opened_ts=position.opened_ts,
            closed_ts=stamp,
            pnl_gross=pnl_gross,
            fees=fees,
            funding=funding,
            pnl_net=pnl_net,
            r_multiple=(pnl_net / (risk * position.units)) if risk * position.units else 0.0,
            exit_reason=reason,
            mode=self.mode,  # type: ignore[arg-type]
            signal_key=position.signal_key,
            diagnostics=close_diagnostics,
        )
        self.position = None
        return trade

    def _risk_per_unit(self, position: Position) -> float:
        spec = self._instrument(position.symbol)
        return abs(position.entry_price - position.stop_price) / spec.tick_size * spec.tick_value

    def expire_pending(self, max_age_s: float, now: datetime) -> int:
        """Cancela órdenes de entrada demasiado antiguas antes de poder rellenarse."""
        if max_age_s <= 0:
            return 0
        stamp = now if now.tzinfo is not None else now.replace(tzinfo=timezone.utc)
        expired = 0
        for order in self.orders:
            if order.status != "pending":
                continue
            created = self._armed_at.get(order.id, order.created_ts)
            created = created if created.tzinfo is not None else created.replace(tzinfo=timezone.utc)
            if (stamp - created).total_seconds() > max_age_s:
                order.status = "cancelled"
                expired += 1
        return expired

    def cancel_all(self) -> int:
        cancelled = 0
        for order in self.orders:
            if order.status == "pending":
                order.status = "cancelled"
                cancelled += 1
        return cancelled

    def restore(self, position: Position | None) -> None:
        self.position = position

    def pending_orders(self) -> list[Order]:
        return [order for order in self.orders if order.status == "pending"]


class _Hit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    reason: str
    diagnostics: dict[str, Any] = Field(default_factory=dict)
