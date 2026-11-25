from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

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
    assert stats["pnl_gross"] == 0.0


def test_gross_is_net_plus_fees():
    """La comisión se ve aparte para que un bruto positivo no pase por ganancia."""
    trades = [_trade(0, 20.0), _trade(1, -10.0)]
    stats = compute_stats(trades)
    assert stats["pnl_gross"] == stats["pnl_net"] + stats["fees"]
    assert stats["pnl_gross"] == pytest.approx(10.0 + 2 * 1.24)


def test_profit_factor_and_expectancy():
    trades = [_trade(0, 20.0), _trade(1, -10.0), _trade(2, -10.0), _trade(3, 40.0)]
    stats = compute_stats(trades, initial_equity=1000.0)
    assert stats["trades"] == 4
    assert stats["wins"] == 2
    assert stats["losses"] == 2
    assert stats["win_rate"] == 0.5
    assert stats["profit_factor"] == 3.0
    assert stats["pnl_net"] == 40.0
    # El bruto dice si la ventaja existe antes de pagar el peaje.
    assert stats["pnl_gross"] == pytest.approx(44.96)
    assert stats["pnl_gross"] - stats["fees"] == pytest.approx(stats["pnl_net"])
    assert stats["expectancy_r"] == (2.0 - 1.0 - 1.0 + 4.0) / 4
    assert stats["best_trade"] == 40.0
    assert stats["worst_trade"] == -10.0
    assert stats["avg_duration_minutes"] == 30.0


def test_drawdown_is_measured_on_closed_equity():
    trades = [_trade(0, -50.0), _trade(1, 20.0), _trade(2, -30.0)]
    stats = compute_stats(trades, initial_equity=1000.0)
    # 1000 -> 950 -> 970 -> 940 : peak 1000, trough 940
    assert stats["max_drawdown"] == 60.0


def test_drawdown_uses_the_marked_curve_when_given():
    trades = [_trade(0, 100.0)]
    # El cierre gana 100, pero la curva llego a 940 antes de recuperar: el
    # drawdown realizado seria 0.
    stats = compute_stats(
        trades, initial_equity=1000.0, equity=[1100.0, 940.0, 1100.0]
    )
    assert stats["max_drawdown"] == 160.0


def test_an_open_loss_counts_without_closed_trades():
    stats = compute_stats([], initial_equity=1000.0, equity=[980.0])
    assert stats["max_drawdown"] == 20.0


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
    assert set(payload) == {
        "closed",
        "timezone",
        "by_hour",
        "by_weekday",
        "by_month",
        "by_side",
        "by_day",
        "equity",
    }
    assert payload["closed"]["trades"] == 2
    assert len(payload["equity"]) == 2


def test_aggregate_says_which_clock_the_buckets_use():
    trades = [_trade(0, 10.0)]
    assert aggregate(trades, 0.0)["timezone"] == "UTC"
    assert aggregate(trades, 0.0, timezone_name="America/New_York")["timezone"] == "America/New_York"


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


def test_impossible_durations_are_counted_not_hidden():
    good = _trade(0, -10.0)
    bad = _trade(1, -10.0)
    bad.closed_ts = bad.opened_ts - timedelta(minutes=45)
    stats = compute_stats([good, bad])
    assert stats["impossible_durations"] == 1
    # El dato se conserva: la media sigue incluyendo la duración imposible.
    assert stats["avg_duration_minutes"] == pytest.approx((30 - 45) / 2)


def _timed_trade(closed_ts, pnl: float = 10.0):
    from datetime import timedelta

    from server.models import TradeRecord

    return TradeRecord(
        symbol="PRIMARY",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=101.0,
        opened_ts=closed_ts - timedelta(minutes=5),
        closed_ts=closed_ts,
        pnl_gross=pnl,
        pnl_net=pnl,
        fees=0.0,
        exit_reason="target",
        mode="paper",
        r_multiple=1.0,
    )


def test_hour_buckets_use_the_session_timezone():
    from datetime import datetime, timezone

    stamp = datetime(2026, 11, 20, 14, 30, tzinfo=timezone.utc)  # 09:30 New York
    trades = [_timed_trade(stamp)]

    utc = aggregate(trades, 0.0)
    ny = aggregate(trades, 0.0, timezone_name="America/New_York")

    assert list(utc["by_hour"]) == ["14:00"]
    assert list(ny["by_hour"]) == ["09:00"]


def test_day_buckets_use_the_session_timezone():
    from datetime import datetime, timezone

    # 00:30 UTC on the 21st is still the 20th in New York.
    stamp = datetime(2026, 11, 21, 0, 30, tzinfo=timezone.utc)
    trades = [_timed_trade(stamp)]

    assert list(aggregate(trades, 0.0)["by_day"]) == ["2026-11-21"]
    assert list(aggregate(trades, 0.0, timezone_name="America/New_York")["by_day"]) == [
        "2026-11-20"
    ]


def test_stats_endpoint_reports_session_hours(client):
    payload = client.get("/api/stats").json()
    assert "by_hour" in payload
    assert "by_day" in payload


def test_r_distribution_buckets_every_trade():
    from server.stats import R_BUCKETS, r_distribution

    counts = r_distribution([-3.0, -1.5, -0.75, -0.2, 0.3, 0.75, 1.5, 2.5])
    assert sum(counts.values()) == 8
    assert list(counts) == [label for label, _, _ in R_BUCKETS]
    assert counts["<= -2R"] == 1
    assert counts["-2R a -1R"] == 1
    assert counts["> 2R"] == 1


def test_r_distribution_places_zero_and_boundaries():
    from server.stats import r_distribution

    counts = r_distribution([0.0, 1.0, 2.0, -1.0])
    # Buckets are (low, high]: the boundary closes the bucket below it.
    assert counts["-0.5R a 0"] == 1  # 0.0
    assert counts["0.5R a 1R"] == 1  # 1.0
    assert counts["1R a 2R"] == 1  # 2.0
    assert counts["-2R a -1R"] == 1  # -1.0
    assert sum(counts.values()) == 4


def test_median_is_robust_to_the_tail():
    from server.stats import _median

    assert _median([1.0, 2.0, 3.0]) == 2.0
    assert _median([1.0, 2.0, 3.0, 100.0]) == 2.5
    assert _median([]) == 0.0


def test_compute_stats_includes_r_median_and_distribution():
    trades = [_trade(index, 10.0 * (index + 1)) for index in range(3)]
    stats = compute_stats(trades)
    assert "r_median" in stats
    assert sum(stats["r_distribution"].values()) == 3
