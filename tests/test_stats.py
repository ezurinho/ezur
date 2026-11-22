from __future__ import annotations

from datetime import datetime, timedelta, timezone

from server.models import TradeRecord
from server.stats import aggregate, by_dimension, compute_stats, equity_curve

BASE = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def _trade(index: int, pnl: float, *, side: str = "long", minutes: int = 30) -> TradeRecord:
    opened = BASE + timedelta(hours=index)
    return TradeRecord(
        symbol="PRIMARY",
        side=side,  # type: ignore[arg-type]
        units=1,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        stop_price=99.0,
        target_price=102.0,
        opened_ts=opened,
        closed_ts=opened + timedelta(minutes=minutes),
        pnl_gross=pnl + 1.24,
        fees=1.24,
        pnl_net=pnl,
        r_multiple=pnl / 10.0,
        exit_reason="target" if pnl > 0 else "stop",
        mode="dry_run",
        signal_key=f"k{index}",
    )


def test_empty_stats_are_zeroed():
    stats = compute_stats([])
    assert stats["trades"] == 0
    assert stats["profit_factor"] == 0.0
    assert stats["max_drawdown"] == 0.0


def test_profit_factor_and_expectancy():
    trades = [_trade(0, 20.0), _trade(1, -10.0), _trade(2, -10.0), _trade(3, 40.0)]
    stats = compute_stats(trades, initial_equity=1000.0)
    assert stats["trades"] == 4
    assert stats["wins"] == 2
    assert stats["losses"] == 2
    assert stats["win_rate"] == 0.5
    assert stats["profit_factor"] == 3.0
    assert stats["pnl_net"] == 40.0
    assert stats["expectancy_r"] == (2.0 - 1.0 - 1.0 + 4.0) / 4
    assert stats["best_trade"] == 40.0
    assert stats["worst_trade"] == -10.0
    assert stats["avg_duration_minutes"] == 30.0


def test_drawdown_is_measured_on_closed_equity():
    trades = [_trade(0, -50.0), _trade(1, 20.0), _trade(2, -30.0)]
    stats = compute_stats(trades, initial_equity=1000.0)
    # 1000 -> 950 -> 970 -> 940 : peak 1000, trough 940
    assert stats["max_drawdown"] == 60.0


def test_by_dimension_splits_by_side_and_hour():
    trades = [_trade(0, 10.0, side="long"), _trade(1, -5.0, side="short"), _trade(2, 7.0, side="long")]
    by_side = by_dimension(trades, "side")
    assert by_side["long"]["trades"] == 2
    assert by_side["short"]["trades"] == 1
    assert by_side["long"]["pnl_net"] == 17.0

    by_hour = by_dimension(trades, "hour")
    assert set(by_hour) == {"15:00", "16:00", "17:00"}


def test_equity_curve_is_chronological_and_cumulative():
    trades = [_trade(2, 5.0), _trade(0, 10.0)]
    curve = equity_curve(trades, 1000.0)
    assert [point["equity"] for point in curve] == [1010.0, 1015.0]


def test_aggregate_exposes_every_breakdown():
    trades = [_trade(0, 10.0), _trade(1, -4.0)]
    payload = aggregate(trades, 1000.0)
    assert set(payload) == {"closed", "by_hour", "by_weekday", "by_month", "by_side", "by_day", "equity"}
    assert payload["closed"]["trades"] == 2
    assert len(payload["equity"]) == 2


def test_aggregate_can_filter_by_window():
    trades = [_trade(0, 10.0), _trade(5, 20.0)]
    payload = aggregate(trades, 0.0, start=BASE + timedelta(hours=1))
    assert payload["closed"]["trades"] == 1
    assert payload["closed"]["pnl_net"] == 20.0


def test_loss_streak_is_counted():
    trades = [_trade(0, -5.0), _trade(1, -5.0), _trade(2, -5.0), _trade(3, 6.0), _trade(4, -5.0)]
    stats = compute_stats(trades)
    assert stats["max_loss_streak"] == 3


def test_concentration_metrics():
    trades = [_trade(0, 100.0)] + [_trade(index + 1, -10.0) for index in range(9)]
    stats = compute_stats(trades)
    assert stats["pnl_net"] == 10.0
    assert stats["top5_share"] == 1.0
    assert stats["pnl_without_top5"] == -90.0


def test_bootstrap_low_is_negative_for_a_losing_sample():
    trades = [_trade(index, -10.0) for index in range(20)]
    stats = compute_stats(trades)
    assert stats["expectancy_ci80_low"] < 0


def test_ambiguous_trades_are_counted():
    trade = _trade(0, -10.0)
    trade.diagnostics = {"ambiguous_bar": True}
    assert compute_stats([trade])["ambiguous_trades"] == 1
