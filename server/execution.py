"""Paper execution engine.

Fill, bracket and close. The rule that matters: when a bar touches both the
stop and the target, the stop wins and the trade says so in its diagnostics.
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

    # --- lifecycle --------------------------------------------------------
    def arm(
        self,
        decision: RiskDecision,
        signal: Signal,
        symbol: str,
        reference_price: float,
        now: datetime | None = None,
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
        self._seen_signals.add(signal.key)
        return order

    def on_bar(self, bars: dict[str, Bar]) -> list[ExecutionEvent]:
        events: list[ExecutionEvent] = []
        pending = [order for order in self.orders if order.status == "pending"]
        for order in pending:
            bar = bars.get(order.symbol)
            if bar is None:
                continue
            fill = self._fill_price(order.side, bar, order.symbol)
            order.status = "filled"
            order.price = fill
            spec = self._instrument(order.symbol)
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
                    reason="next_open",
                )
            )

        if self.position is not None:
            bar = bars.get(self.position.symbol)
            if bar is not None:
                self.last_price = bar.c
                hit = self._bracket_hit(self.position, bar)
                if hit is not None:
                    events.append(
                        ExecutionEvent(
                            type="exit",
                            symbol=self.position.symbol,
                            price=hit.price,
                            units=self.position.units,
                            reason=hit.reason,
                            trade=self.close(hit.reason, hit.price, bar.t, hit.diagnostics),
                            diagnostics=hit.diagnostics,
                        )
                    )
        return events

    def _fill_price(self, side: str, bar: Bar, symbol: str) -> float:
        spec = self._instrument(symbol)
        ticks = min(self.config.slippage_ticks, self.config.max_slippage_ticks)
        slip = ticks * spec.tick_size
        if self.config.fill_model == "signal_price":
            return bar.o
        return bar.o + slip if side == "long" else bar.o - slip

    def _bracket_hit(self, position: Position, bar: Bar) -> "_Hit | None":
        spec = self._instrument(position.symbol)
        tol = spec.tick_size / 2
        stop = position.stop_price
        target = position.target_price
        if position.side == "long":
            stop_hit = bar.l <= stop + tol
            target_hit = target is not None and bar.h >= target - tol
            if stop_hit and target_hit:
                return _Hit(price=stop, reason="stop", diagnostics={"ambiguous_bar": True})
            if stop_hit:
                return _Hit(price=stop, reason="stop", diagnostics={})
            if target_hit and target is not None:
                return _Hit(price=target, reason="target", diagnostics={})
        else:
            stop_hit = bar.h >= stop - tol
            target_hit = target is not None and bar.l <= target + tol
            if stop_hit and target_hit:
                return _Hit(price=stop, reason="stop", diagnostics={"ambiguous_bar": True})
            if stop_hit:
                return _Hit(price=stop, reason="stop", diagnostics={})
            if target_hit and target is not None:
                return _Hit(price=target, reason="target", diagnostics={})
        return None

    def close(
        self,
        reason: str,
        price: float | None = None,
        when: datetime | None = None,
        diagnostics: dict[str, Any] | None = None,
    ) -> TradeRecord | None:
        if self.position is None:
            return None
        position = self.position
        exit_price = price if price is not None else (self.last_price or position.entry_price)
        stamp = when or datetime.now(timezone.utc)
        pnl_gross = self._pnl(position.symbol, position.side, position.entry_price, exit_price, position.units)
        fees = self.config.commission_per_unit_side * position.units * 2
        risk = self._risk_per_unit(position)
        pnl_net = pnl_gross - fees
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
            pnl_net=pnl_net,
            r_multiple=(pnl_net / (risk * position.units)) if risk * position.units else 0.0,
            exit_reason=reason,
            mode=self.mode,  # type: ignore[arg-type]
            diagnostics=diagnostics or {},
        )
        self.position = None
        return trade

    def _risk_per_unit(self, position: Position) -> float:
        spec = self._instrument(position.symbol)
        return abs(position.entry_price - position.stop_price) / spec.tick_size * spec.tick_value

    def cancel_all(self) -> None:
        for order in self.orders:
            if order.status == "pending":
                order.status = "cancelled"

    def restore(self, position: Position | None) -> None:
        self.position = position

    def pending_orders(self) -> list[Order]:
        return [order for order in self.orders if order.status == "pending"]


class _Hit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float
    reason: str
    diagnostics: dict[str, Any] = Field(default_factory=dict)
