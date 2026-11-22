"""Descriptive statistics computed from closed trades.

Everything here is descriptive: no metric estimates future returns, and a
positive number is not evidence of an edge.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Literal

from .models import TradeRecord

Dimension = Literal["hour", "weekday", "month", "side", "day"]

EMPTY_STATS: dict[str, Any] = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "win_rate": 0.0,
    "profit_factor": 0.0,
    "expectancy_r": 0.0,
    "pnl_net": 0.0,
    "fees": 0.0,
    "r_total": 0.0,
    "max_drawdown": 0.0,
    "avg_win": 0.0,
    "avg_loss": 0.0,
    "best_trade": 0.0,
    "worst_trade": 0.0,
    "avg_duration_minutes": 0.0,
}


def compute_stats(
    trades: Iterable[TradeRecord], initial_equity: float = 0.0
) -> dict[str, Any]:
    records = list(trades)
    if not records:
        return dict(EMPTY_STATS)

    wins = [trade for trade in records if trade.pnl_net > 0]
    losses = [trade for trade in records if trade.pnl_net < 0]
    gross_win = sum(trade.pnl_net for trade in wins)
    gross_loss = abs(sum(trade.pnl_net for trade in losses))
    pnl_net = sum(trade.pnl_net for trade in records)
    durations = [
        (trade.closed_ts - trade.opened_ts).total_seconds() / 60 for trade in records
    ]

    equity = initial_equity
    peak = equity
    max_drawdown = 0.0
    for trade in sorted(records, key=lambda item: item.closed_ts):
        equity += trade.pnl_net
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)

    return {
        "trades": len(records),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": len(wins) / len(records),
        "profit_factor": (gross_win / gross_loss)
        if gross_loss
        else float(gross_win > 0),
        "expectancy_r": sum(trade.r_multiple for trade in records) / len(records),
        "pnl_net": pnl_net,
        "fees": sum(trade.fees for trade in records),
        "r_total": sum(trade.r_multiple for trade in records),
        "max_drawdown": max_drawdown,
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (-gross_loss / len(losses)) if losses else 0.0,
        "best_trade": max(trade.pnl_net for trade in records),
        "worst_trade": min(trade.pnl_net for trade in records),
        "avg_duration_minutes": sum(durations) / len(durations),
        "first_ts": min(trade.closed_ts for trade in records).isoformat(),
        "last_ts": max(trade.closed_ts for trade in records).isoformat(),
    }


def _bucket(trade: TradeRecord, dimension: Dimension) -> str:
    stamp = trade.closed_ts
    if dimension == "hour":
        return f"{stamp.hour:02d}:00"
    if dimension == "weekday":
        return stamp.strftime("%a")
    if dimension == "month":
        return stamp.strftime("%Y-%m")
    if dimension == "day":
        return stamp.date().isoformat()
    return trade.side


def by_dimension(
    trades: Iterable[TradeRecord], dimension: Dimension
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        groups.setdefault(_bucket(trade, dimension), []).append(trade)
    return {name: compute_stats(group) for name, group in sorted(groups.items())}


def equity_curve(
    trades: Iterable[TradeRecord], initial: float
) -> list[dict[str, Any]]:
    curve: list[dict[str, Any]] = []
    equity = initial
    for trade in sorted(trades, key=lambda item: item.closed_ts):
        equity += trade.pnl_net
        curve.append({"ts": trade.closed_ts.isoformat(), "equity": round(equity, 2)})
    return curve


def aggregate(
    trades: Iterable[TradeRecord],
    initial_equity: float = 0.0,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    records = [
        trade
        for trade in trades
        if (start is None or trade.closed_ts >= start)
        and (end is None or trade.closed_ts <= end)
    ]
    return {
        "closed": compute_stats(records, initial_equity),
        "by_hour": by_dimension(records, "hour"),
        "by_weekday": by_dimension(records, "weekday"),
        "by_month": by_dimension(records, "month"),
        "by_side": by_dimension(records, "side"),
        "by_day": by_dimension(records, "day"),
        "equity": equity_curve(records, initial_equity),
    }
