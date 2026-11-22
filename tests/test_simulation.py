from __future__ import annotations

from datetime import date, timedelta

from server.config import Settings
from server.simulation import run_simulation, simulated_ticks, trading_days


def _settings() -> Settings:
    settings = Settings()
    settings.strategy.id = "reference"
    settings.strategy.params = {"fast": 3, "slow": 5, "atr_period": 2}
    return settings


def test_trading_days_skip_weekends():
    days = trading_days(_settings(), 5, end=date(2026, 1, 19))
    assert all(day.weekday() < 5 for day in days)
    assert days == sorted(days)
    assert len(days) == 5


def test_simulated_ticks_are_aligned_across_symbols():
    settings = _settings()
    settings.instruments.items.append(
        type(settings.instruments.items[0])(symbol="CTX_A")
    )
    days = trading_days(settings, 1, end=date(2026, 1, 16))
    ticks = simulated_ticks(settings, days, bars=10)
    assert len(ticks) == 10
    assert set(ticks[0].bars) == {"PRIMARY", "CTX_A"}
    assert ticks[0].bars["PRIMARY"].t == ticks[0].bars["CTX_A"].t


def test_simulation_produces_trades_and_statistics():
    result = run_simulation(_settings(), days=2, bars=90)
    closed = result["closed"]
    assert result["simulation"]["sessions"] == 2
    assert result["simulation"]["ticks"] == 180
    assert closed["trades"] > 0
    assert closed["fees"] > 0
    assert "by_hour" in result and "by_side" in result
    assert len(result["equity"]) == closed["trades"]


def test_simulation_is_deterministic():
    first = run_simulation(_settings(), days=2, bars=60)
    second = run_simulation(_settings(), days=2, bars=60)
    assert first["closed"] == second["closed"]
    assert first["equity"] == second["equity"]


def test_simulation_reports_that_data_is_synthetic():
    result = run_simulation(_settings(), days=1, bars=60)
    assert result["simulation"]["data_source"] == "synthetic"
    assert "sintéticos" in result["simulation"]["note"]


def test_simulation_with_null_strategy_has_no_trades():
    settings = Settings()
    result = run_simulation(settings, days=1, bars=60)
    assert result["closed"]["trades"] == 0


def test_session_boundaries_reset_daily_counters():
    settings = _settings()
    settings.risk.max_trades_per_day = 100
    result = run_simulation(settings, days=3, bars=120)
    by_day = result["by_day"]
    assert len(by_day) <= 3
    assert sum(day["trades"] for day in by_day.values()) == result["closed"]["trades"]
