"""Deterministic synthetic market data.

Seeded by date and symbol, so the same session always produces the same bars.
Useful for smoke tests and UI demos; never for calibration.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone

from ..models import Bar


def _seed(date_key: str, symbol: str) -> int:
    digest = hashlib.sha256(f"{date_key}:{symbol}".encode()).hexdigest()
    return int(digest[:12], 16)


def base_price(symbol: str) -> float:
    digest = hashlib.sha256(symbol.encode()).hexdigest()
    return 50.0 + (int(digest[:6], 16) % 4000) / 10.0


def generate_session(
    date_key: str,
    symbol: str,
    *,
    start: datetime,
    bars: int = 390,
    interval_minutes: int = 1,
    tick_size: float = 0.25,
) -> list[Bar]:
    rng = random.Random(_seed(date_key, symbol))
    price = round(base_price(symbol) / tick_size) * tick_size
    out: list[Bar] = []
    for index in range(bars):
        drift = rng.gauss(0, tick_size * 2)
        open_price = price
        close_price = max(tick_size, open_price + drift)
        high = max(open_price, close_price) + abs(rng.gauss(0, tick_size))
        low = min(open_price, close_price) - abs(rng.gauss(0, tick_size))
        volume = float(rng.randint(50, 2000))
        price = close_price
        out.append(
            Bar(
                t=start + timedelta(minutes=index * interval_minutes),
                o=round(open_price, 6),
                h=round(high, 6),
                l=round(low, 6),
                c=round(close_price, 6),
                v=volume,
            )
        )
    return out


def session_start(date_key: str, hour: int = 9, minute: int = 30) -> datetime:
    day = datetime.fromisoformat(date_key).replace(tzinfo=timezone.utc)
    return day + timedelta(hours=hour, minutes=minute)
