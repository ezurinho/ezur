"""Regression: changing instruments at runtime must rebuild the feed.

The bug this pins: a sync FastAPI endpoint called ``update_settings`` from a
threadpool, ``asyncio.get_running_loop()`` raised, the exception was swallowed
and the replay kept feeding the old instrument list. The symbol appeared in
``quotes`` with no data and the chart stayed empty.
"""

from __future__ import annotations

import asyncio

from server.config import InstrumentConfig, Settings
from server.db import Store
from server.engine import TradingEngine
from server.main import build_feed
from server.strategy.null_strategy import NullStrategy


def _settings() -> Settings:
    settings = Settings()
    settings.feed.replay_speed = 500.0
    return settings


def test_new_instrument_gets_bars_after_reconfigure():
    async def scenario() -> dict[str, int]:
        settings = _settings()
        store = Store(":memory:")
        engine = TradingEngine(
            settings,
            store,
            feed=build_feed(settings),
            strategy=NullStrategy(),
            feed_factory=build_feed,
        )
        try:
            engine.start()
            engine.start_task()
            await asyncio.sleep(0.15)

            updated = Settings()
            updated.feed.replay_speed = 500.0
            updated.instruments.items = [
                InstrumentConfig(symbol="PRIMARY", role="primary"),
                InstrumentConfig(symbol="CTX_A", role="context"),
            ]
            engine.update_settings(updated)
            await asyncio.sleep(0.3)

            quotes = engine.quotes()
            return {
                "primary_bars": len(engine._bars.get("PRIMARY", [])),
                "context_bars": len(engine._bars.get("CTX_A", [])),
                "quotes": len(quotes),
                "series": len(engine.series()),
            }
        finally:
            await engine.stop_task()
            store.close()

    result = asyncio.run(scenario())
    assert result["context_bars"] > 0
    assert result["primary_bars"] > 0
    assert result["quotes"] == 2
    assert result["series"] == 1


def test_reconfigure_updates_risk_and_execution():
    settings = _settings()
    store = Store(":memory:")
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    try:
        updated = Settings()
        updated.risk.max_trades_per_day = 9
        updated.execution.slippage_ticks = 3
        engine.update_settings(updated)
        assert engine.risk.config.max_trades_per_day == 9
        assert engine.execution.config.slippage_ticks == 3
        assert engine.builder.settings.risk.max_trades_per_day == 9
    finally:
        store.close()
