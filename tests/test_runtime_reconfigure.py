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
            await engine.start_task()
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


def test_reconfigure_synchronizes_the_feed_provider():
    settings = _settings()
    store = Store(":memory:")
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    try:
        live = Settings()
        live.feed.provider = "okx"
        engine.update_settings(live)
        assert engine.state.provider == "okx"

        replay = Settings()
        replay.feed.provider = "csv"
        engine.update_settings(replay)
        assert engine.state.provider == "csv"
    finally:
        store.close()


def test_a_finished_replay_stops_the_engine_and_can_be_restarted(settings, store):
    import asyncio

    from server.engine import TradingEngine
    from server.market.feed import MarketFeed
    from server.models import Bar, Tick
    from server.strategy.null_strategy import NullStrategy

    class TwoTickFeed(MarketFeed):
        name = "two"

        def __init__(self):
            self.starts = 0

        def iter_ticks(self):
            self.starts += 1
            for minute in range(2):
                stamp = __import__("datetime").datetime(2026, 11, 20, 14, 30 + minute)
                yield Tick(
                    ts=stamp,
                    bars={
                        symbol: Bar(t=stamp, o=100, h=101, l=99, c=100, v=1)
                        for symbol in settings.instruments.symbols
                    },
                )

    feeds: list[TwoTickFeed] = []

    def factory(_settings):
        feed = TwoTickFeed()
        feeds.append(feed)
        return feed

    settings.feed.replay_speed = 1000.0
    settings.feed.loop_sessions = False

    async def drain(engine):
        for _ in range(300):
            if engine._task is None or engine._task.done():
                return
            await asyncio.sleep(0.01)

    async def scenario():
        engine = TradingEngine(
            settings,
            store,
            feed=factory(settings),
            strategy=NullStrategy(),
            feed_factory=factory,
        )
        engine.start()
        await engine.start_task()
        await drain(engine)
        finished = (engine.state.status, engine.state.bars_available)

        # A stopped engine must not resurrect itself on a config change.
        engine.update_settings(settings.model_copy(deep=True))
        await asyncio.sleep(0.05)
        after_config = engine.state.status

        engine.start()
        await engine.start_task()
        await drain(engine)
        return engine, feeds, finished, after_config

    engine, feeds, finished, after_config = asyncio.run(scenario())
    assert finished == ("stopped", 2)
    assert after_config == "stopped"
    assert len(feeds) == 2  # the feed was rebuilt on reconfigure
    assert engine.state.bars_available == 2  # and the restart replays it


def _api_pair(tmp_path):
    """A live app whose engine can be inspected between requests."""
    from fastapi.testclient import TestClient

    from server.main import create_app

    settings = _settings()
    config_path = tmp_path / "config.json"
    config_path.write_text(settings.model_dump_json(), encoding="utf-8")
    app = create_app(
        config_path=config_path,
        db_path=tmp_path / "runtime.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    client = TestClient(app)
    client.__enter__()
    return client, app.state.engine


def test_switching_strategy_rebuilds_the_plugin(tmp_path):
    client, engine = _api_pair(tmp_path)
    try:
        assert engine.strategy.id == "null"
        response = client.put(
            "/api/config",
            json={"patch": {"strategy": {"id": "fade", "params": {"period": 10}}}},
        )
        assert response.status_code == 200
        assert engine.strategy.id == "fade"
        assert engine.strategy.params.period == 10
    finally:
        client.__exit__(None, None, None)


def test_invalid_strategy_params_are_a_422_not_a_dead_loop(tmp_path):
    client, engine = _api_pair(tmp_path)
    try:
        before = engine.strategy.id
        response = client.put(
            "/api/config",
            json={"patch": {"strategy": {"id": "fade", "params": {"periodo": 10}}}},
        )
        assert response.status_code == 422
        assert engine.strategy.id == before
    finally:
        client.__exit__(None, None, None)


def test_unknown_strategy_id_is_rejected(tmp_path):
    client, engine = _api_pair(tmp_path)
    try:
        response = client.put("/api/config", json={"patch": {"strategy": {"id": "nope"}}})
        assert response.status_code == 422
        assert engine.strategy.id == "null"
    finally:
        client.__exit__(None, None, None)
