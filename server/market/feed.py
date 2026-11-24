"""Market feeds.

A feed yields ``Tick`` objects whose ``bars`` mapping is keyed by every enabled
instrument. Nothing here knows which symbols exist: they arrive as a list.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from ..models import Bar, Tick
from . import synthetic


class MarketFeed:
    name = "base"

    def iter_ticks(self) -> Iterator[Tick]:  # pragma: no cover - interface
        raise NotImplementedError


class SimulatedFeed(MarketFeed):
    name = "simulated"

    def __init__(
        self,
        seed_date: str,
        instruments: list[str],
        *,
        bars: int = 390,
        interval_minutes: int = 1,
        tick_size: float = 0.25,
        reference_prices: dict[str, float] | None = None,
        start: datetime | None = None,
    ) -> None:
        self.seed_date = seed_date
        self.instruments = list(instruments)
        self.bars_count = bars
        self.interval_minutes = interval_minutes
        self.tick_size = tick_size
        self.reference_prices = dict(reference_prices or {})
        self.start = start

    def iter_ticks(self) -> Iterator[Tick]:
        start = self.start or synthetic.session_start(self.seed_date)
        series = {
            symbol: synthetic.generate_session(
                self.seed_date,
                symbol,
                start=start,
                bars=self.bars_count,
                interval_minutes=self.interval_minutes,
                tick_size=self.tick_size,
                reference_price=self.reference_prices.get(symbol),
            )
            for symbol in self.instruments
        }
        for index in range(self.bars_count):
            stamps = [series[symbol][index].t for symbol in self.instruments]
            yield Tick(
                ts=stamps[0],
                bars={symbol: series[symbol][index] for symbol in self.instruments},
            )


class CSVFeed(MarketFeed):
    name = "csv"

    def __init__(self, path: str | Path, instruments: list[str]) -> None:
        self.path = Path(path)
        self.instruments = list(instruments)

    def iter_ticks(self) -> Iterator[Tick]:
        """Lee vela a vela, sin cargar el dataset entero en memoria.

        El formato guarda las velas ordenadas por tiempo e intercala los
        símbolos, así que basta con un cubo: cuando cambia el `ts` se emite el
        anterior si están todos los instrumentos. Un fichero desordenado se
        rechaza en vez de emitir ticks fuera de orden que el motor descartaría.
        """
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        current_stamp: datetime | None = None
        current: dict[str, Bar] = {}
        with self.path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                symbol = row["symbol"]
                if symbol not in self.instruments:
                    continue
                stamp = _parse_ts(row["ts"])
                if current_stamp is not None and stamp < current_stamp:
                    raise ValueError(
                        f"dataset no ordenado por ts: {stamp.isoformat()} "
                        f"después de {current_stamp.isoformat()}"
                    )
                if current_stamp is not None and stamp != current_stamp:
                    if len(current) == len(self.instruments):
                        yield Tick(
                            ts=current_stamp,
                            bars={name: current[name] for name in self.instruments},
                        )
                    current = {}
                current_stamp = stamp
                current[symbol] = Bar(
                    t=stamp,
                    o=float(row["o"]),
                    h=float(row["h"]),
                    l=float(row["l"]),
                    c=float(row["c"]),
                    v=float(row.get("v") or 0.0),
                )
        if current_stamp is not None and len(current) == len(self.instruments):
            yield Tick(
                ts=current_stamp,
                bars={name: current[name] for name in self.instruments},
            )


class LiveFeed(MarketFeed):
    name = "live"

    def iter_ticks(self) -> Iterator[Tick]:
        raise NotImplementedError(
            "LiveFeed has no adapter: configure one before enabling LIVE"
        )


def _parse_ts(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    stamp = datetime.fromisoformat(text)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp
