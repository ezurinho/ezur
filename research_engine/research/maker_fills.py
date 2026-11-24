"""Maker-limit fills with a queue and adverse selection.

The research dataset has no L2 book, so this is an *explicit approximation*, not
a reconstruction of the exchange queue:

* the order rests at the signal close;
* a fill requires the next bar to trade through that price, not to open through
  it (a gap is not a passive fill);
* the aggressor volume at the touch is estimated from the bar's taker-buy split
  and from how far the bar penetrated the limit;
* ``queue_fraction`` of that touch volume is assumed to be ahead of us.  The
  rest is available to our order.  A fraction below ``min_fill_fraction`` is a
  miss, not a partial fill silently rounded up;
* a favorable close (the price rebounding away from our limit) lowers the fill
  fraction.  This is the adverse-selection term: passive fills are more likely
  when the bar closes against the order, which is exactly when the next move is
  more likely to be toxic.

The model is deliberately conservative: it does not assume that a touch is a
fill, and it does not assume that a maker fee buys a fill.  Every assumption is
a parameter and is reported by the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

Side = Literal["long", "short"]


@dataclass(frozen=True)
class MakerFillConfig:
    """Parameters of the queue/adverse-selection model.

    ``order_notional_usd`` is the notional the queue must absorb.  At retail
    size it is small relative to a 5m bar, so the queue rarely binds; the
    sensitivity runs use a capacity-sized order to show that distinction
    instead of pretending the queue is the main cost.
    """

    queue_fraction: float = 0.5
    order_notional_usd: float = 10_000.0
    max_wait_bars: int = 1
    adverse_rebound_bps: float = 10.0
    rebound_penalty: float = 1.0
    min_fill_fraction: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.queue_fraction < 1.0:
            raise ValueError("queue_fraction debe estar en [0, 1)")
        if self.order_notional_usd <= 0:
            raise ValueError("order_notional_usd debe ser positivo")
        if self.max_wait_bars < 1:
            raise ValueError("max_wait_bars debe ser >= 1")
        if self.adverse_rebound_bps < 0:
            raise ValueError("adverse_rebound_bps no puede ser negativo")
        if not 0.0 <= self.rebound_penalty <= 1.0:
            raise ValueError("rebound_penalty debe estar en [0, 1]")
        if not 0.0 < self.min_fill_fraction <= 1.0:
            raise ValueError("min_fill_fraction debe estar en (0, 1]")


@dataclass(frozen=True)
class MakerFill:
    filled: bool
    reason: str
    fill_ts: pd.Timestamp | None = None
    fill_price: float = 0.0
    fill_fraction: float = 0.0
    best_fraction: float = 0.0
    attempts: int = 0
    touch_bars: int = 0
    gap_bars: int = 0
    favorable_bps: float = 0.0
    queue_notional_usd: float = 0.0
    touch_notional_usd: float = 0.0


def _timestamp(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_localize("UTC") if stamp.tzinfo is None else stamp.tz_convert("UTC")


def try_maker_fill(
    exec_bars: pd.DataFrame,
    start_ts: object,
    side: Side,
    limit_price: float,
    config: MakerFillConfig,
) -> MakerFill:
    """Try to fill a resting maker order in the next ``max_wait_bars`` hours.

    ``exec_bars`` must be 5m execution bars with ``ts``, ``open``, ``high``,
    ``low``, ``close``, ``volume`` and ``taker_buy_volume``.  ``start_ts`` is
    the first bar in which the order can trade (the open of the bar after the
    signal bar).  The fill price is always the limit; no price improvement or
    slippage is invented.
    """
    if side not in ("long", "short"):
        raise ValueError("side debe ser 'long' o 'short'")
    if limit_price <= 0:
        raise ValueError("limit_price debe ser positivo")
    required = {"ts", "open", "high", "low", "close", "volume", "taker_buy_volume"}
    missing = required - set(exec_bars.columns)
    if missing:
        raise ValueError(f"faltan columnas de ejecución: {sorted(missing)}")

    start = _timestamp(start_ts)
    end = start + pd.Timedelta(hours=config.max_wait_bars)
    # ``Series.searchsorted`` is O(log n) and avoids rebuilding a 700k-row
    # timestamp vector for every one of the ~1,000 signals.
    ts_series = exec_bars["ts"]
    left = int(ts_series.searchsorted(start, side="left"))
    right = int(ts_series.searchsorted(end, side="left"))
    window = exec_bars.iloc[left:right]
    if window.empty:
        return MakerFill(False, "no_data", attempts=0)

    sign = 1 if side == "long" else -1
    best = 0.0
    best_reason = "no_touch"
    touch_bars = 0
    adverse_touches = 0
    gap_bars = 0
    last_favorable = 0.0
    last_queue = 0.0
    last_touch = 0.0

    for row in window.itertuples(index=False):
        open_price = float(row.open)
        high = float(row.high)
        low = float(row.low)
        close = float(row.close)
        volume = max(0.0, float(row.volume))
        taker_buy = min(volume, max(0.0, float(row.taker_buy_volume)))

        if sign == 1:
            # A gap below the limit is not a passive fill: the order would have
            # crossed the market at the open.  Leave it out instead of booking a
            # maker fill that a real venue would classify as taker.
            if open_price < limit_price:
                gap_bars += 1
                continue
            if low > limit_price:
                continue
            span = high - low
            penetration = 1.0 if span <= 0 else (limit_price - low) / span
            aggressor = volume - taker_buy
        else:
            if open_price > limit_price:
                gap_bars += 1
                continue
            if high < limit_price:
                continue
            span = high - low
            penetration = 1.0 if span <= 0 else (high - limit_price) / span
            aggressor = taker_buy

        penetration = min(1.0, max(0.0, penetration))
        touch_notional = max(0.0, aggressor) * penetration * limit_price
        if touch_notional <= 0:
            continue
        touch_bars += 1

        # The queue ahead is a fraction of the volume that actually traded at
        # our price.  A small retail order clears it; a capacity-sized order
        # does not, which is the point of the queue term.
        queue_notional = config.queue_fraction * touch_notional
        available = max(0.0, touch_notional - queue_notional)
        fraction = min(1.0, available / config.order_notional_usd)

        # Adverse selection: if the bar closes away from our limit, the price
        # moved before our queue could clear.  The more favorable the close,
        # the less likely the fill.  A bar that closes through the limit gets
        # the full queue fraction.
        favorable_bps = max(0.0, sign * (close - limit_price) / limit_price * 1e4)
        if config.adverse_rebound_bps > 0:
            rebound = min(1.0, favorable_bps / config.adverse_rebound_bps)
        else:
            rebound = 1.0 if favorable_bps > 0 else 0.0
        quality = max(0.0, 1.0 - config.rebound_penalty * rebound)
        fraction *= quality

        last_favorable = favorable_bps
        last_queue = queue_notional
        last_touch = touch_notional
        if quality <= 0:
            adverse_touches += 1
        if fraction > best:
            best = fraction
            best_reason = "adverse_rebound" if quality <= 0 else "queue"

        if fraction >= config.min_fill_fraction:
            return MakerFill(
                filled=True,
                reason="filled",
                fill_ts=_timestamp(row.ts),
                fill_price=limit_price,
                fill_fraction=fraction,
                best_fraction=best,
                attempts=len(window),
                touch_bars=touch_bars,
                gap_bars=gap_bars,
                favorable_bps=favorable_bps,
                queue_notional_usd=queue_notional,
                touch_notional_usd=touch_notional,
            )

    if touch_bars == 0:
        reason = "gap_through_limit" if gap_bars else "no_touch"
    elif best < config.min_fill_fraction:
        reason = "adverse_rebound" if adverse_touches == touch_bars else "queue"
    else:
        reason = best_reason
    return MakerFill(
        filled=False,
        reason=reason,
        best_fraction=best,
        attempts=len(window),
        touch_bars=touch_bars,
        gap_bars=gap_bars,
        favorable_bps=last_favorable,
        queue_notional_usd=last_queue,
        touch_notional_usd=last_touch,
    )
