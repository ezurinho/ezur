"""Aggregate feed bars into a slower timeframe.

The feed decides how often the engine can act; it does not decide what the
strategy sees. Aggregating on the way in keeps execution on every feed bar (a
stop can be touched inside a higher-timeframe candle) while the strategy only
ever reads closed candles of its own timeframe.

Without this, a profile validated on 1h candles runs a 21-bar average over 21
minutes of data: the same parameters, a different system.
"""

from __future__ import annotations

from datetime import datetime

from .models import Bar

_UNIT_MINUTES = {"m": 1, "h": 60, "d": 1440}


def timeframe_minutes(value: str) -> int:
    """``1m``, ``15m``, ``4h``, ``1d`` or any positive multiple of those."""
    text = value.strip().lower()
    unit = text[-1:]
    amount = text[:-1]
    if unit not in _UNIT_MINUTES or not amount.isdigit():
        raise ValueError(f"timeframe no soportado: {value!r}")
    minutes = int(amount) * _UNIT_MINUTES[unit]
    if minutes < 1:
        raise ValueError(f"timeframe no soportado: {value!r}")
    return minutes


def bucket_start(stamp: datetime, minutes: int) -> datetime:
    """Start of the bucket ``stamp`` belongs to, in its own timezone."""
    epoch = stamp.timestamp()
    step = minutes * 60
    return datetime.fromtimestamp(epoch - epoch % step, tz=stamp.tzinfo)


class BarAggregator:
    """Aggregate bars into ``minutes`` buckets.

    ``bars`` holds closed buckets only: the one being built never reaches the
    strategy. A plugin that reads a half-built candle changes its mind inside
    the same candle and trades the noise it was supposed to filter.
    """

    def __init__(self, minutes: int, limit: int = 500) -> None:
        if minutes < 1:
            raise ValueError("minutes must be >= 1")
        self.minutes = minutes
        self.limit = limit
        self.bars: list[Bar] = []
        self.current: Bar | None = None

    def add(self, bar: Bar) -> None:
        start = bucket_start(bar.t, self.minutes)
        current = self.current
        if current is None:
            self.current = self._open(start, bar)
            return
        if start == current.t:
            current.h = max(current.h, bar.h)
            current.l = min(current.l, bar.l)
            current.c = bar.c
            current.v += bar.v
            return
        self.bars.append(current)
        if self.limit > 0:
            del self.bars[:-self.limit]
        self.current = self._open(start, bar)

    @staticmethod
    def _open(start: datetime, bar: Bar) -> Bar:
        return Bar(t=start, o=bar.o, h=bar.h, l=bar.l, c=bar.c, v=bar.v)
