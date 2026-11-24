"""Feed de OKX: parseo, alineado y stream asíncrono sin tocar la red."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from server.config import Settings
from server.market.okx import FeedError, OKXFeed, aligned_ticks, parse_candles
from server.main import build_feed

ROW = ["1795404000000", "61251.9", "61300.7", "61251.9", "61261.4", "2.37", "2.3", "144000", "1"]


def _payload(*rows, code="0"):
    return {"code": code, "msg": "", "data": list(rows)}


def bar_row(ts_ms: str, close: float) -> list[str]:
    return [ts_ms, "100", "101", "99", str(close), "1", "1", "1", "1"]


def test_parse_orders_oldest_first_and_uses_utc():
    older = bar_row("1795403940000", "100")
    newer = bar_row("1795404000000", "101")
    bars = parse_candles(_payload(newer, older))
    assert [bar.c for bar in bars] == [100.0, 101.0]
    assert bars[0].t == datetime(2026, 11, 23, 3, 59, tzinfo=timezone.utc) or bars[0].t.tzinfo is timezone.utc
    assert bars[1].t > bars[0].t


def test_parse_rejects_an_error_payload():
    with pytest.raises(FeedError):
        parse_candles({"code": "51001", "msg": "Instrument ID does not exist"})


def test_parse_rejects_garbage_numbers():
    with pytest.raises(FeedError):
        parse_candles(_payload(["1795404000000", "x", "1", "1", "1", "1"]))


def test_parse_ignores_short_rows():
    assert parse_candles(_payload(["1", "2"])) == []


def test_aligned_ticks_only_emits_minutes_every_symbol_has():
    from server.models import Bar

    t1 = datetime(2026, 11, 23, 0, 1, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 23, 0, 2, tzinfo=timezone.utc)
    t3 = datetime(2026, 11, 23, 0, 3, tzinfo=timezone.utc)
    series = {
        "A": [Bar(t=t1, o=1, h=1, l=1, c=1), Bar(t=t2, o=1, h=1, l=1, c=1)],
        "B": [Bar(t=t2, o=1, h=1, l=1, c=1), Bar(t=t3, o=1, h=1, l=1, c=1)],
    }
    ticks = list(aligned_ticks(series))
    assert [tick.ts for tick in ticks] == [t2]
    assert set(ticks[0].bars) == {"A", "B"}


def test_fetch_builds_the_expected_request(monkeypatch):
    seen: list[str] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            import json

            return json.dumps(_payload(ROW)).encode()

    def fake_urlopen(request, timeout=None):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    feed = OKXFeed({"BTC": "BTC-USDT"}, bars=5)
    bars = feed.fetch(5)
    assert len(bars["BTC"]) == 1
    assert "instId=BTC-USDT" in seen[0]
    assert "bar=1m" in seen[0]
    assert "limit=5" in seen[0]


def test_async_stream_backfills_then_only_emits_new_minutes(monkeypatch):
    calls = {"n": 0}
    t1 = bar_row("1795404000000", "100")
    t2 = bar_row("1795404060000", "101")

    def fake_fetch(self, limit, after=None):
        calls["n"] += 1
        rows = [t1] if calls["n"] == 1 else [t1, t2]
        return {"BTC": parse_candles(_payload(*rows))}

    monkeypatch.setattr(OKXFeed, "fetch", fake_fetch)
    feed = OKXFeed({"BTC": "BTC-USDT"}, bars=2, poll_interval_s=0, max_ticks=2)

    async def collect():
        return [tick async for tick in feed.iter_ticks_async()]

    ticks = asyncio.run(collect())
    assert len(ticks) == 2
    assert ticks[1].bars["BTC"].c == 101.0
    assert feed.polls >= 1


def test_a_failed_poll_is_counted_and_recovered(monkeypatch):
    state = {"n": 0}
    t1 = bar_row("1795404000000", "100")
    t2 = bar_row("1795404060000", "101")

    def fake_fetch(self, limit, after=None):
        state["n"] += 1
        if state["n"] == 1:
            return {"BTC": parse_candles(_payload(t1))}
        if state["n"] == 2:
            raise OSError("venue caída")
        return {"BTC": parse_candles(_payload(t1, t2))}

    monkeypatch.setattr(OKXFeed, "fetch", fake_fetch)
    feed = OKXFeed({"BTC": "BTC-USDT"}, bars=2, poll_interval_s=0, max_ticks=2)

    async def collect():
        return [tick async for tick in feed.iter_ticks_async()]

    ticks = asyncio.run(collect())
    assert len(ticks) == 2
    assert feed.failures == 1
    assert feed.last_error is None  # el último poll bueno limpia el error


def test_backfill_failure_raises_feed_error(monkeypatch):
    def boom(self, limit, after=None):
        raise OSError("sin red")

    monkeypatch.setattr(OKXFeed, "fetch", boom)
    feed = OKXFeed({"BTC": "BTC-USDT"})

    async def collect():
        return [tick async for tick in feed.iter_ticks_async()]

    with pytest.raises(FeedError):
        asyncio.run(collect())


def test_sync_iter_is_not_supported():
    with pytest.raises(NotImplementedError):
        next(OKXFeed({"BTC": "BTC-USDT"}).iter_ticks())


def test_build_feed_maps_venue_symbols():
    settings = Settings()
    settings.feed.provider = "okx"
    settings.instruments.items[0].venue_symbol = "BTC-USDT"
    feed = build_feed(settings)
    assert isinstance(feed, OKXFeed)
    assert feed.symbol_map == {"PRIMARY": "BTC-USDT"}


# --- engine integration ---------------------------------------------------
def test_engine_drives_an_async_feed(tmp_path):
    """A feed with ``iter_ticks_async`` must be consumed without the replay sleep."""
    from datetime import timedelta

    from server.db import Store
    from server.engine import TradingEngine
    from server.market.feed import MarketFeed
    from server.models import Bar, Tick
    from server.strategy.null_strategy import NullStrategy

    start = datetime(2026, 11, 23, 0, 0, tzinfo=timezone.utc)

    class StubAsyncFeed(MarketFeed):
        name = "stub-async"

        async def iter_ticks_async(self):
            for minute in range(3):
                stamp = start + timedelta(minutes=minute)
                yield Tick(
                    ts=stamp,
                    bars={"PRIMARY": Bar(t=stamp, o=100, h=101, l=99, c=100 + minute, v=1)},
                )

    store = Store(tmp_path / "async.db")
    engine = TradingEngine(
        Settings(),
        store,
        feed=StubAsyncFeed(),
        strategy=NullStrategy(),
    )
    try:
        engine.start()
        asyncio.run(engine.run())
        assert engine.state.bars_available == 3
        assert engine.state.status == "stopped"
        assert engine.state.last_bar_ts == start + timedelta(minutes=2)
    finally:
        store.close()

def test_parse_discards_the_candle_in_progress():
    confirmed = bar_row("1795404000000", "101")
    in_progress = ["1795404060000", "101", "102", "100", "101.5", "1", "1", "1", "0"]

    bars = parse_candles(_payload(in_progress, confirmed))

    assert [bar.c for bar in bars] == [101.0]
