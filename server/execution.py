"""Paper execution engine.

Fill, bracket and close. The rule that matters: when a bar touches both the
stop and the target, the stop wins and the trade says so in its diagnostics.

Fill models (all declared instead of assumed):

* ``next_open`` (default) market order at the next bar's open, slippage bounded
  by ``max_slippage_ticks``. The entry bar counts: if it reaches the stop, the
  trade dies on the bar it was born on and says ``same_bar_exit``.
* ``signal_price`` uses the price the signal was generated at, but only when the
  next bar actually traded through it. If the bar opened past it, the fill
  degrades to ``next_open`` and says ``fill_fallback`` in the diagnostics. If
  OHLC cannot establish whether a stop or target extreme happened before that
  fill, it also degrades instead of using future information.
* ``intrabar`` deprecated alias for ``next_open``.

Every model rejects an entry whose opening fill is already through the stop
or has already reached the target. A later stop gap fills at the bar open with
adverse slippage, never at the stale stop price.

Cost model (from strategy_spec):
- fee_maker_bps / fee_taker_bps: per-side fees in basis points
- half_spread_bps: half the bid-ask spread in basis points
- assumed_fill: "taker" | "maker" | "mixed" (how the entry is classified)
- impact_model: "none" | "sqrt_law" | "ofi" (market impact model)
- funding: "real_timestamps" | "none" (whether funding is applied)
- cooldown_bars: minimum bars between entries
- stop_floor_frac: minimum stop distance as fraction of price

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
        self._entry_bar_index: dict[str, int] = {}  # symbol -> bar index when armed

    # --- helpers ----------------------------------------------------------
    def _instrument(self, symbol: str) -> InstrumentConfig:
        return self.instruments[symbol]

    def _pnl(self, symbol: str, side: str, entry: float, exit_price: float, units: int) -> float:
        spec = self._instrument(symbol)
        ticks = (exit_price - entry) / spec.tick_size
        if side == "short":
            ticks = -ticks
        return ticks * spec.tick_value * units

    def _round_trip_bps(self, symbol: str, is_maker: bool | None = None) -> float:
        """Round-trip cost in basis points for one side (entry or exit).

        If assumed_fill is "mixed", uses 50/50 maker/taker split.
        Includes half_spread_bps for both legs.
        """
        cfg = self.config
        if cfg.assumed_fill == "maker":
            fee_bps = cfg.fee_maker_bps
        elif cfg.assumed_fill == "taker":
            fee_bps = cfg.fee_taker_bps
        else:  # mixed
            fee_bps = (cfg.fee_maker_bps + cfg.fee_taker_bps) / 2

        # One side pays fee + half spread; round trip is 2 * (fee + half_spread)
        return 2 * (fee_bps + cfg.half_spread_bps)

    def _impact_bps(self, symbol: str, notional_usd: float, units: int, side: str) -> float:
        """Market impact in basis points for a given notional."""
        cfg = self.config
        if cfg.impact_model == "none" or notional_usd <= 0:
            return 0.0
        spec = self._instrument(symbol)
        # Daily volume estimate (simplified: use a fixed ADV or derive from data)
        # For now, use a simple sqrt law: impact ~ 0.1 * sqrt(notional / adv) bps
        # where ADV is approximated from the instrument's tick value and typical volume
        adv_usd = 1_000_000_000  # $1B daily volume default (placeholder)
        if cfg.impact_model == "sqrt_law":
            return 0.1 * (notional_usd / adv_usd) ** 0.5 * 10000  # in bps
        elif cfg.impact_model == "ofi":
            # Order flow imbalance model - simplified
            return 0.05 * (notional_usd / adv_usd) ** 0.5 * 10000
        return 0.0

    def _fees(self, symbol: str, units: int, price: float, is_maker: bool | None = None) -> float:
        """Fee for one side (entry or exit) in quote currency.

        Uses fee_maker_bps / fee_taker_bps + half_spread_bps.
        If assumed_fill is "mixed", averages maker/taker.
        """
        cfg = self.config
        spec = self._instrument(symbol)

        # Determine which fee to use
        if cfg.assumed_fill == "maker":
            fee_bps = cfg.fee_maker_bps
        elif cfg.assumed_fill == "taker":
            fee_bps = cfg.fee_taker_bps
        else:  # mixed
            fee_bps = (cfg.fee_maker_bps + cfg.fee_taker_bps) / 2

        # Total bps per side = fee + half_spread
        total_bps = fee_bps + cfg.half_spread_bps

        # Impact
        contract = spec.tick_value / spec.tick_size if spec.tick_size else 0.0
        notional = units * contract * price
        impact_bps = self._impact_bps(symbol, notional, units, "long")

        # Commission (per unit or percentage)
        pct = cfg.commission_pct_side
        if pct > 0:
            return units * contract * price * pct + (notional * (total_bps + impact_bps) * 1e-4)
        return cfg.commission_per_unit_side * units + (notional * (total_bps + impact_bps) * 1e-4)

    def open_pnl(self, position: Position, price: float) -> float:
        """Lo que dejaria la posicion si se cerrara ahora a `price`.

        Cobra la comision de entrada ya pagada y la de salida: un
        mark-to-market que solo mira el precio pinta un drawdown menor que el
        que se llevaria la cuenta al cerrar.
        """
        return (
            self._pnl(
                position.symbol,
                position.side,
                position.entry_price,
                price,
                position.units,
            )
            - position.entry_fees
            - self._fees(position.symbol, position.units, price)
        )

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
        # Cooldown check
        if self.config.cooldown_bars > 0:
            last_entry_bar = self._entry_bar_index.get(symbol)
            if last_entry_bar is not None:
                # We'd need the current bar index - simplified for now
                pass
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

    def on_bar(self, bars: dict[str, Bar], bar_index: int = 0) -> list[ExecutionEvent]:
        events: list[ExecutionEvent] = []
        pending = [order for order in self.orders if order.status == "pending"]
        for order in pending:
            if order.status != "pending":
                continue
            bar = bars.get(order.symbol)
            if bar is None:
                continue
            # Cooldown check at fill time
            if self.config.cooldown_bars > 0 and self._entry_bar_index.get(order.symbol, -999) + self.config.cooldown_bars > bar_index:
                order.status = "rejected"
                events.append(
                    ExecutionEvent(
                        type="cancel",
                        symbol=order.symbol,
                        units=order.units,
                        reason="cooldown_active",
                        diagnostics={
                            "signal_price": order.price,
                            "bar_open": bar.o,
                            "cooldown_bars": self.config.cooldown_bars,
                            "order_id": order.id,
                            "signal_key": order.signal_key,
                        },
                    )
                )
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
                entry_fees=self._fees(order.symbol, order.units, fill),
                entry_slippage=abs(fill - bar.o),
                signal_key=order.signal_key,
            )
            self._entry_bar_index[order.symbol] = bar_index
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
                    diagnostics = dict(hit.diagnostics)
                    if bar.t == self.position.opened_ts:
                        diagnostics["same_bar_exit"] = True
                    price = hit.price
                    if hit.reason == "stop":
                        price, slip = self._exit_slippage(self.position, price)
                        diagnostics["exit_slippage"] = slip
                    events.append(
                        ExecutionEvent(
                            type="exit",
                            symbol=self.position.symbol,
                            price=price,
                            units=self.position.units,
                            reason=hit.reason,
                            trade=self.close(hit.reason, price, bar.t, diagnostics),
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
        long = position.side == "long"
        stop_fill = min(bar.o, stop) if long else max(bar.o, stop)
        gap = bar.o < stop if long else bar.o > stop
        stop_hit = bar.l <= stop + tol if long else bar.h >= stop - tol
        target_hit = target is not None and (
            bar.h >= target - tol if long else bar.l <= target + tol
        )
        diagnostics: dict[str, Any] = {}
        if gap:
            diagnostics["gap_through_stop"] = True
            diagnostics["gap_stop"] = True
        if stop_hit and target_hit:
            diagnostics["ambiguous_bar"] = True
        if stop_hit:
            return _Hit(price=stop_fill, reason="stop", diagnostics=diagnostics)
        if target_hit and target is not None:
            return _Hit(price=target, reason="target", diagnostics={})
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
            exit_price = self.last_price
        else:
            exit_price = position.entry_price
        stamp = when or datetime.now(timezone.utc)
        if price is None:
            exit_price, slip = self._exit_slippage(position, exit_price)
            close_diagnostics["exit_slippage"] = slip
        pnl_gross = self._pnl(position.symbol, position.side, position.entry_price, exit_price, position.units)
        fees = self._fees(
            position.symbol, position.units, position.entry_price
        ) + self._fees(position.symbol, position.units, exit_price)
        risk = self._risk_per_unit(position)
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

    def _exit_slippage(self, position: Position, price: float) -> tuple[float, float]:
        """Salida a mercado: siempre en contra, con el mismo tope que la entrada."""
        spec = self._instrument(position.symbol)
        ticks = min(self.config.slippage_ticks, self.config.max_slippage_ticks)
        slip = ticks * spec.tick_size
        return (price - slip if position.side == "long" else price + slip), slip

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