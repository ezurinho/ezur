from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.models import Bar
from server.resample import BarAggregator, bucket_start, timeframe_minutes

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def _bar(minute: int, price: float = 100.0) -> Bar:
    stamp = NOW + timedelta(minutes=minute)
    return Bar(t=stamp, o=price, h=price + 1, l=price - 1, c=price + 0.5, v=1)


def test_timeframe_parsing():
    assert timeframe_minutes("1m") == 1
    assert timeframe_minutes("15m") == 15
    assert timeframe_minutes("4h") == 240
    assert timeframe_minutes("1d") == 1440
    assert timeframe_minutes("7m") == 7


@pytest.mark.parametrize("value", ["1w", "m", "0m", "", "1.5h"])
def test_unknown_timeframe_raises(value):
    with pytest.raises(ValueError):
        timeframe_minutes(value)


def test_bucket_start_aligns_to_the_bucket():
    assert bucket_start(NOW + timedelta(minutes=37), 60) == NOW
    assert bucket_start(NOW + timedelta(minutes=37), 15) == NOW + timedelta(minutes=30)


def test_the_open_bucket_never_reaches_the_strategy():
    aggregator = BarAggregator(60)
    for minute in range(60):
        aggregator.add(_bar(minute))
    assert aggregator.bars == []

    aggregator.add(_bar(60))
    assert len(aggregator.bars) == 1


def test_ohlcv_is_aggregated():
    aggregator = BarAggregator(60)
    aggregator.add(Bar(t=NOW, o=100, h=101, l=99, c=100.5, v=2))
    aggregator.add(Bar(t=NOW + timedelta(minutes=1), o=100.5, h=103, l=100, c=102, v=3))
    aggregator.add(Bar(t=NOW + timedelta(minutes=60), o=102, h=104, l=101, c=103, v=1))

    closed = aggregator.bars[0]
    assert (closed.t, closed.o, closed.h, closed.l, closed.c, closed.v) == (
        NOW,
        100,
        103,
        99,
        102,
        5,
    )


def test_the_series_is_capped():
    aggregator = BarAggregator(1, limit=2)
    for minute in range(4):
        aggregator.add(_bar(minute))
    assert len(aggregator.bars) == 2
    assert aggregator.bars[-1].t == NOW + timedelta(minutes=2)


def test_a_bad_timeframe_is_rejected_by_the_config():
    from server.config import Settings

    with pytest.raises(ValueError):
        Settings.model_validate({"strategy": {"timeframe": "1w"}})
