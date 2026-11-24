"""OKX public market data feed (spot, keys never needed).

Why OKX: it is the exchange whose public REST endpoints answered from the
machine this was built on (Binance and Bybit return 451/403 by region), it
serves 1-minute candles with no key and no signing, and its payload is small
enough to parse with the standard library.

Two things this feed does that the replay feeds do not:

* **Backfill first.** The strategy needs warmup bars; without them the first
  signals would be computed on an empty history and the chart would start
  mid-air.
* **Never block the event loop.** Fetching happens in a worker thread through
  ``asyncio.to_thread`` and the loop awaits the poll interval, so the websocket
  keeps publishing snapshots while the HTTP call is in flight.

The engine only sees ``Tick`` objects, exactly like with the synthetic feed: the
adapter is the only place that knows the exchange exists.
"""

from __future__ import annotations

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Iterator

from ..models import Bar, Tick
from .feed import MarketFeed

BASE_URL = "https://www.okx.com"
CANDLES_PATH = "/api/v5/market/candles"
MAX_LIMIT = 300


class FeedError(RuntimeError):
    """The venue answered something we cannot use."""


def parse_candles(payload: dict[str, Any]) -> list[Bar]:
    """Convert an OKX candle payload into bars, oldest first.

    OKX returns newest first as ``[ts, o, h, l, c, vol, volCcy, volCcyQuote,
    confirm]`` with millisecond timestamps as strings.
    """
    if payload.get("code") not in (None, "0"):
        raise FeedError(f"OKX error {payload.get('code')}: {payload.get('msg')}")
    rows = payload.get("data") or []
    bars: list[Bar] = []
    for row in rows:
        if len(row) < 6:
            continue
        # La última vela llega en curso (`confirm = "0"`): su cierre todavía
        # cambia. Colarla como cerrada fija un cierre parcial y, como la vela
        # definitiva trae el mismo `t`, el motor ya no la procesa.
        if len(row) > 8 and str(row[8]) == "0":
            continue
        try:
            stamp = datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc)
            bars.append(
                Bar(
                    t=stamp,
                    o=float(row[1]),
                    h=float(row[2]),
                    l=float(row[3]),
                    c=float(row[4]),
                    v=float(row[5]),
                )
            )
        except (TypeError, ValueError) as error:
            raise FeedError(f"vela inválida de OKX: {row!r}") from error
    bars.sort(key=lambda bar: bar.t)
    return bars


def aligned_ticks(series: dict[str, list[Bar]]) -> Iterator[Tick]:
    """Yield ticks only where every instrument has a bar for that minute.

    A context symbol with holes would otherwise produce a tick with a missing
    bar and silently drop the primary's candle.
    """
    if not series:
        return
    indexed = {symbol: {bar.t: bar for bar in bars} for symbol, bars in series.items()}
    common = set.intersection(*(set(bars) for bars in indexed.values())) if indexed else set()
    for stamp in sorted(common):
        yield Tick(ts=stamp, bars={symbol: indexed[symbol][stamp] for symbol in indexed})


class OKXFeed(MarketFeed):
    name = "okx"

    def __init__(
        self,
        symbol_map: dict[str, str],
        *,
        bars: int = 240,
        poll_interval_s: float = 5.0,
        timeout_s: float = 10.0,
        max_ticks: int | None = None,
        base_url: str = BASE_URL,
    ) -> None:
        if not symbol_map:
            raise ValueError("symbol_map no puede estar vacío")
        self.symbol_map = dict(symbol_map)
        self.bars = max(2, min(bars, MAX_LIMIT))
        self.poll_interval_s = max(0.0, poll_interval_s)
        self.timeout_s = timeout_s
        self.max_ticks = max_ticks
        self.base_url = base_url.rstrip("/")
        self.last_error: str | None = None
        self.polls = 0
        self.failures = 0
        self._last_ts: datetime | None = None

    # --- HTTP -------------------------------------------------------------
    def _request(self, inst_id: str, limit: int, after: str | None = None) -> dict[str, Any]:
        query = {"instId": inst_id, "bar": "1m", "limit": str(min(limit, MAX_LIMIT))}
        if after:
            query["after"] = after
        url = f"{self.base_url}{CANDLES_PATH}?{urllib.parse.urlencode(query)}"
        request = urllib.request.Request(url, headers={"User-Agent": "ezur/0.1"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def fetch(self, limit: int, after: str | None = None) -> dict[str, list[Bar]]:
        """One HTTP round trip per instrument; returns bars oldest first."""
        result: dict[str, list[Bar]] = {}
        for internal, inst_id in self.symbol_map.items():
            payload = self._request(inst_id, limit, after)
            result[internal] = parse_candles(payload)
        return result

    # --- sync interface (kept for parity with the other feeds) ------------
    def iter_ticks(self) -> Iterator[Tick]:  # pragma: no cover - async is the real path
        raise NotImplementedError("OKXFeed is async: use iter_ticks_async() from the engine")

    async def iter_ticks_async(self) -> AsyncIterator[Tick]:
        emitted = 0
        try:
            backfill = await asyncio.to_thread(self.fetch, self.bars)
        except Exception as error:  # noqa: BLE001 - surfacing it as a stale feed is the point
            self.failures += 1
            self.last_error = str(error)
            raise FeedError(f"backfill de OKX falló: {error}") from error

        for tick in aligned_ticks(backfill):
            self._last_ts = tick.ts
            emitted += 1
            yield tick
            if self.max_ticks is not None and emitted >= self.max_ticks:
                return

        while True:
            await asyncio.sleep(self.poll_interval_s)
            # Tras un fallo puede haber un hueco mayor que la ventana de 5
            # velas: se pide el backfill entero para no perder minutos.
            recovering = self.last_error is not None
            try:
                batch = await asyncio.to_thread(
                    self.fetch, self.bars if recovering else 5
                )
                self.polls += 1
                self.last_error = None
            except Exception as error:  # noqa: BLE001 - a dead venue must degrade, not crash
                self.failures += 1
                self.last_error = str(error)
                # Back off without stopping: the engine decides when it is too stale.
                await asyncio.sleep(min(30.0, self.poll_interval_s * self.failures))
                continue
            fresh = {
                symbol: [bar for bar in bars if self._last_ts is None or bar.t > self._last_ts]
                for symbol, bars in batch.items()
            }
            if not all(fresh.values()):
                continue
            for tick in aligned_ticks(fresh):
                self._last_ts = tick.ts
                emitted += 1
                yield tick
                if self.max_ticks is not None and emitted >= self.max_ticks:
                    return
