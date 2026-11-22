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
        start: datetime | None = None,
    ) -> None:
        self.seed_date = seed_date
        self.instruments = list(instruments)
        self.bars_count = bars
        self.interval_minutes = interval_minutes
        self.tick_size = tick_size
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
        if not self.path.exists():
            raise FileNotFoundError(self.path)
        buckets: dict[datetime, dict[str, Bar]] = {}
        with self.path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                symbol = row["symbol"]
                if symbol not in self.instruments:
                    continue
                stamp = _parse_ts(row["ts"])
                buckets.setdefault(stamp, {})[symbol] = Bar(
                    t=stamp,
                    o=float(row["o"]),
                    h=float(row["h"]),
                    l=float(row["l"]),
                    c=float(row["c"]),
                    v=float(row.get("v") or 0.0),
                )
        for stamp in sorted(buckets):
            bars = buckets[stamp]
            if len(bars) != len(self.instruments):
                continue
            yield Tick(ts=stamp, bars={symbol: bars[symbol] for symbol in self.instruments})


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
