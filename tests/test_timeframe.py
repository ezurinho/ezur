from __future__ import annotations

from datetime import datetime, timedelta, timezone

from server.engine import TradingEngine
from server.models import Bar, Tick

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def _tick(minute: int) -> Tick:
    stamp = NOW + timedelta(minutes=minute)
    return Tick(
        ts=stamp,
        bars={"PRIMARY": Bar(t=stamp, o=100, h=101, l=99, c=100.5, v=1)},
    )


def test_the_strategy_sees_closed_hourly_candles(settings, store):
    settings.strategy.timeframe = "1h"
    engine = TradingEngine(settings, store, feed=None)

    for minute in range(121):
        engine._process(_tick(minute))

    bars = engine._bar_source()["PRIMARY"]
    assert len(bars) == 2
    assert bars[0].t == NOW
    assert bars[1].t == NOW + timedelta(hours=1)
    assert bars[0].v == 60
    assert engine._bars["PRIMARY"][-1].t == NOW + timedelta(minutes=120)


def test_the_default_timeframe_is_the_feed_itself(settings, store):
    engine = TradingEngine(settings, store, feed=None)

    for minute in range(3):
        engine._process(_tick(minute))

    assert len(engine._bar_source()["PRIMARY"]) == 3