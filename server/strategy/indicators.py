"""Indicator primitives shared by the strategy plugins.

They are plain functions over lists of bars: no state, no pandas, no numpy.
A plugin that needs something else can compute it inside ``evaluate``; nothing
in the engine depends on these.
"""

from __future__ import annotations

from ..models import Bar


def sma(values: list[float], period: int) -> float | None:
    if period <= 0 or len(values) < period:
        return None
    return sum(values[-period:]) / period


def stdev(values: list[float], period: int) -> float | None:
    """Population standard deviation of the last ``period`` values."""
    if period <= 1 or len(values) < period:
        return None
    window = values[-period:]
    mean = sum(window) / period
    variance = sum((value - mean) ** 2 for value in window) / period
    return variance**0.5


def atr(bars: list[Bar], period: int) -> float | None:
    if period <= 0 or len(bars) < period + 1:
        return None
    ranges: list[float] = []
    for previous, current in zip(bars[-period - 1 : -1], bars[-period:], strict=True):
        ranges.append(
            max(
                current.h - current.l,
                abs(current.h - previous.c),
                abs(current.l - previous.c),
            )
        )
    return sum(ranges) / len(ranges)


def highest(bars: list[Bar], period: int) -> float | None:
    if period <= 0 or len(bars) < period:
        return None
    return max(bar.h for bar in bars[-period:])


def lowest(bars: list[Bar], period: int) -> float | None:
    if period <= 0 or len(bars) < period:
        return None
    return min(bar.l for bar in bars[-period:])


def ema(values: list[float], period: int) -> float | None:
    """Exponential Moving Average using the standard smoothing factor."""
    if period <= 0 or len(values) < period:
        return None
    alpha = 2.0 / (period + 1)
    # Start with SMA for the first period values
    ema_val = sum(values[:period]) / period
    for value in values[period:]:
        ema_val = alpha * value + (1 - alpha) * ema_val
    return ema_val
