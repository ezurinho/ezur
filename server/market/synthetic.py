"""Deterministic synthetic market data.

Seeded by date and symbol, so the same session always produces the same bars.
Useful for smoke tests and UI demos; never for calibration.
"""

from __future__ import annotations

import hashlib
import math
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
    reference_price: float | None = None,
    volatility_pct: float = 0.0005,
) -> list[Bar]:
    if reference_price is not None and (
        not math.isfinite(reference_price) or reference_price <= 0
    ):
        raise ValueError("reference_price must be positive and finite")
    if not math.isfinite(volatility_pct) or volatility_pct <= 0:
        raise ValueError("volatility_pct must be positive and finite")
    if not math.isfinite(tick_size) or tick_size <= 0:
        raise ValueError("tick_size must be positive and finite")
    precision = max(6, min(15, math.ceil(-math.log10(tick_size)) + 2))
    rng = random.Random(_seed(date_key, symbol))
    start_price = reference_price if reference_price is not None else base_price(symbol)
    price = max(tick_size, round(start_price / tick_size) * tick_size)
    out: list[Bar] = []
    for index in range(bars):
        if reference_price is None:
            # Serie legacy: dos draws de mecha independientes y escala absoluta.
            drift = rng.gauss(0, tick_size * 2)
            high_wick = abs(rng.gauss(0, tick_size))
            low_wick = abs(rng.gauss(0, tick_size))
        else:
            # La volatilidad sintética es relativa al precio: un tick de 0,01 no
            # puede significar el mismo recorrido a 150 que a 60.000, o las
            # comisiones acaban dominando unas métricas que parecen de otro activo.
            scale = max(tick_size, price * volatility_pct)
            drift = rng.gauss(0, max(tick_size * 2, scale))
            wick_scale = max(tick_size, price * volatility_pct * 0.5)
            high_wick = abs(rng.gauss(0, wick_scale))
            low_wick = abs(rng.gauss(0, wick_scale))
        open_price = price
        close_price = max(tick_size, open_price + drift)
        high = max(open_price, close_price) + high_wick
        low = max(tick_size, min(open_price, close_price) - low_wick)
        volume = float(rng.randint(50, 2000))
        price = close_price
        out.append(
            Bar(
                t=start + timedelta(minutes=index * interval_minutes),
                o=round(open_price, precision),
                h=round(high, precision),
                l=round(low, precision),
                c=round(close_price, precision),
                v=volume,
            )
        )
    return out


def session_start(date_key: str, hour: int = 9, minute: int = 30) -> datetime:
    day = datetime.fromisoformat(date_key).replace(tzinfo=timezone.utc)
    return day + timedelta(hours=hour, minutes=minute)
