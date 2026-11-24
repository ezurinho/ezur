"""Descriptive statistics computed from closed trades.

Everything here is descriptive: no metric estimates future returns, and a
positive number is not evidence of an edge.
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any, Iterable, Literal

from .models import TradeRecord
from .timeutil import to_zone

Dimension = Literal["hour", "weekday", "month", "side", "day"]

EMPTY_STATS: dict[str, Any] = {
    "trades": 0,
    "wins": 0,
    "losses": 0,
    "win_rate": 0.0,
    "profit_factor": 0.0,
    "expectancy_r": 0.0,
    "pnl_net": 0.0,
    "pnl_gross": 0.0,
    "fees": 0.0,
    "r_total": 0.0,
    "max_drawdown": 0.0,
    "avg_win": 0.0,
    "avg_loss": 0.0,
    "best_trade": 0.0,
    "worst_trade": 0.0,
    "avg_duration_minutes": 0.0,
    "max_loss_streak": 0,
    "pnl_without_top5": 0.0,
    "top5_share": 0.0,
    "ambiguous_trades": 0,
    # Operaciones cuyo cierre es anterior a su apertura: fechas imposibles que
    # el histórico conserva tal cual. Se cuentan para que la UI pueda avisar de
    # que la duración media y el orden de la curva incluyen datos inválidos.
    "impossible_durations": 0,
    "expectancy_ci80_low": 0.0,
    "r_median": 0.0,
    "r_distribution": {},
}

# Fixed buckets so two runs are comparable and a histogram cannot flatter a tail.
R_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("<= -2R", float("-inf"), -2.0),
    ("-2R a -1R", -2.0, -1.0),
    ("-1R a -0.5R", -1.0, -0.5),
    ("-0.5R a 0", -0.5, 0.0),
    ("0 a 0.5R", 0.0, 0.5),
    ("0.5R a 1R", 0.5, 1.0),
    ("1R a 2R", 1.0, 2.0),
    ("> 2R", 2.0, float("inf")),
)


def r_distribution(values: list[float]) -> dict[str, int]:
    """Count trades per R bucket. Buckets are (low, high]: the boundary belongs
    to the bucket that ends on it, so a flat -2R trade is not counted twice."""
    counts = {label: 0 for label, _, _ in R_BUCKETS}
    for value in values:
        for label, low, high in R_BUCKETS:
            if low < value <= high:
                counts[label] += 1
                break
    return counts


def _max_loss_streak(records: list[TradeRecord]) -> int:
    streak = 0
    worst = 0
    for trade in sorted(records, key=lambda item: item.closed_ts):
        if trade.pnl_net < 0:
            streak += 1
            worst = max(worst, streak)
        elif trade.pnl_net > 0:
            streak = 0
    return worst


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _bootstrap_low(
    values: list[float], *, resamples: int = 10_000, seed: int = 20250102
) -> float:
    """Lower bound of the 80 % bootstrap interval of the mean."""
    if not values:
        return 0.0
    rng = random.Random(seed)
    size = len(values)
    means = sorted(
        sum(rng.choices(values, k=size)) / size for _ in range(resamples)
    )
    return means[int(0.10 * resamples)]


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
    fees = sum(trade.fees for trade in records)
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

    pnls = sorted((trade.pnl_net for trade in records), reverse=True)
    gross_positive = sum(value for value in pnls if value > 0)
    # Only winning trades count towards concentration: a single outlier winner
    # must fail the gate, not pass it because losing trades filled the top five.
    top5 = sum(value for value in pnls[:5] if value > 0)

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
        "pnl_gross": pnl_net + fees,
        "fees": fees,
        "r_total": sum(trade.r_multiple for trade in records),
        "max_drawdown": max_drawdown,
        "avg_win": (gross_win / len(wins)) if wins else 0.0,
        "avg_loss": (-gross_loss / len(losses)) if losses else 0.0,
        "best_trade": max(trade.pnl_net for trade in records),
        "worst_trade": min(trade.pnl_net for trade in records),
        "avg_duration_minutes": sum(durations) / len(durations),
        "max_loss_streak": _max_loss_streak(records),
        "pnl_without_top5": pnl_net - top5,
        "top5_share": (top5 / gross_positive) if gross_positive else 0.0,
        "ambiguous_trades": sum(
            1 for trade in records if trade.diagnostics.get("ambiguous_bar")
        ),
        # Se informa, no se corrige: el histórico es la fuente y borrarlo o
        # recortarlo sería reescribir lo que pasó (aunque haya sido imposible).
        "impossible_durations": sum(1 for minutes in durations if minutes < 0),
        "expectancy_ci80_low": _bootstrap_low(
            [trade.r_multiple for trade in records]
        ),
        "r_median": _median([trade.r_multiple for trade in records]),
        "r_distribution": r_distribution([trade.r_multiple for trade in records]),
        "first_ts": min(trade.closed_ts for trade in records).isoformat(),
        "last_ts": max(trade.closed_ts for trade in records).isoformat(),
    }


def _bucket(trade: TradeRecord, dimension: Dimension, timezone_name: str = "UTC") -> str:
    # Operators think in session time, not UTC: a 14:30 UTC close is 09:30 in
    # New York and must land in the 09:00 bucket of the hour breakdown.
    stamp = to_zone(trade.closed_ts, timezone_name)
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
    trades: Iterable[TradeRecord],
    dimension: Dimension,
    timezone_name: str = "UTC",
) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[TradeRecord]] = {}
    for trade in trades:
        groups.setdefault(_bucket(trade, dimension, timezone_name), []).append(trade)
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
    timezone_name: str = "UTC",
) -> dict[str, Any]:
    records = [
        trade
        for trade in trades
        if (start is None or trade.closed_ts >= start)
        and (end is None or trade.closed_ts <= end)
    ]
    return {
        "closed": compute_stats(records, initial_equity),
        # Los tramos salen del reloj de la sesión, no del del navegador; sin
        # decir cuál es, «08:00» puede leerse como la hora de quien mira.
        "timezone": timezone_name,
        "by_hour": by_dimension(records, "hour", timezone_name),
        "by_weekday": by_dimension(records, "weekday", timezone_name),
        "by_month": by_dimension(records, "month", timezone_name),
        "by_side": by_dimension(records, "side", timezone_name),
        "by_day": by_dimension(records, "day", timezone_name),
        "equity": equity_curve(records, initial_equity),
    }
