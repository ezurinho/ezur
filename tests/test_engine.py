from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import BaseModel

from server.engine import TradingEngine
from server.models import Bar, Position, Tick, TradeRecord
from server.strategy.base import MarketData, StrategyOutput, Warmup
from server.strategy.null_strategy import NullParams, NullStrategy

DAY_ONE = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
DAY_TWO = DAY_ONE + timedelta(days=1)


def _tick(stamp: datetime, price: float = 100.0, symbol: str = "PRIMARY") -> Tick:
    return Tick(
        ts=stamp,
        bars={
            symbol: Bar(t=stamp, o=price, h=price + 1, l=price - 1, c=price + 0.5, v=10)
        },
    )


def test_engine_starts_stopped(engine):
    assert engine.state.status == "stopped"
    assert engine.snapshot()["data"]["strategy"]["signal"] is None
    assert engine.state.position is None


def test_paper_account_ignores_trades_from_other_modes(settings, store):
    store.insert_trade(
        TradeRecord(
            symbol="PRIMARY",
            side="long",
            units=1,
            entry_price=100.0,
            exit_price=101.0,
            stop_price=99.5,
            target_price=102.0,
            opened_ts=DAY_ONE,
            closed_ts=DAY_ONE,
            pnl_gross=1.0,
            fees=0.0,
            pnl_net=100.0,
            r_multiple=2.0,
            exit_reason="target",
            mode="backtest",
            signal_key="foreign-mode",
        )
    )
    paper = TradingEngine(settings, store, feed=None, mode="paper")
    assert paper.state.equity == pytest.approx(settings.risk.initial_capital)
    assert paper.stats()["closed"]["trades"] == 0


def test_engine_does_not_trade_with_null_strategy(engine):
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert engine.execution.pending_orders() == []
    assert engine.state.position is None


def test_session_change_resets_daily_counters(engine):
    engine._process(_tick(DAY_ONE))
    first_session = engine.state.session.id
    engine.state.day_stats.trades = 2
    engine._process(_tick(DAY_TWO))
    assert engine.state.session.id != first_session
    assert engine.state.day_stats.trades == 0
    assert any(event["category"] == "session" for event in engine.store.list_events(20))


class SpyStrategy(NullStrategy):
    id = "spy"
    name = "Spy"
    version = "0.0.1"

    def __init__(self) -> None:
        self.calls = 0
        self.params = NullParams()

    def warmup_requirements(self) -> Warmup:
        return Warmup(bars={}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        self.calls += 1
        return StrategyOutput(state="running", state_label="Evaluando")


class EmptyParams(BaseModel):
    pass


SpyStrategy.params_model = EmptyParams  # type: ignore[assignment]


def test_strategy_not_evaluated_when_paused(settings, store):
    spy = SpyStrategy()
    engine = TradingEngine(settings, store, feed=None, strategy=spy)
    engine.start()
    engine.pause()
    engine._process(_tick(DAY_ONE))
    assert spy.calls == 0


def test_strategy_evaluated_when_running(settings, store):
    spy = SpyStrategy()
    engine = TradingEngine(settings, store, feed=None, strategy=spy)
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert spy.calls == 1
    assert engine.snapshot()["data"]["strategy"]["state"] == "running"


def test_streak_block_expires_when_the_cooldown_ends(settings, store):
    settings.risk.loss_streak_cooldown_min = 45
    settings.risk.no_trade_after_consecutive_losses = 3
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.state.block_reason = "consecutive_losses"
    engine.state.block_count = 3
    engine.state.day_stats.consecutive_losses = settings.risk.no_trade_after_consecutive_losses
    engine.last_exit_ts = DAY_ONE - timedelta(minutes=45)
    engine._expire_blocks(DAY_ONE)
    assert engine.state.block_reason is None
    assert engine.state.block_count == 0


def test_streak_block_survives_inside_the_cooldown(settings, store):
    settings.risk.loss_streak_cooldown_min = 45
    settings.risk.no_trade_after_consecutive_losses = 3
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.state.block_reason = "consecutive_losses"
    engine.state.day_stats.consecutive_losses = settings.risk.no_trade_after_consecutive_losses
    engine.last_exit_ts = DAY_ONE - timedelta(minutes=44)
    engine._expire_blocks(DAY_ONE)
    assert engine.state.block_reason == "consecutive_losses"


def test_emergency_persists_across_restart(settings, store):
    first = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    first.emergency_on()
    second = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    assert second.state.emergency is True
    assert second.snapshot()["data"]["risk"]["blocked"] is True


def test_emergency_blocks_start(settings, store):
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.emergency_on()
    try:
        engine.start()
    except RuntimeError as error:
        assert "emergency" in str(error)
    else:  # pragma: no cover
        raise AssertionError("start should fail while emergency is active")


def test_emergency_can_be_disabled(settings, store):
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.emergency_on()
    engine.emergency_off()
    engine.start()
    assert engine.state.status == "running"


def test_restart_restores_position_and_bracket(settings, store):
    stamp = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)
    store.kv_set(
        "position",
        Position(
            symbol="PRIMARY",
            side="long",
            units=2,
            entry_price=100.5,
            stop_price=99.75,
            target_price=102.25,
            opened_ts=stamp,
        ).model_dump(mode="json"),
    )
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    assert engine.state.position is not None
    assert engine.state.position.stop_price == 99.75
    assert engine.state.position.target_price == 102.25


def test_live_requires_three_conditions(settings, store):
    try:
        TradingEngine(settings, store, feed=None, strategy=NullStrategy(), mode="live")
    except RuntimeError as error:
        assert "LIVE" in str(error)
    else:  # pragma: no cover
        raise AssertionError("live mode must be refused")


def test_history_resamples(engine):
    for index in range(10):
        engine._process(
            _tick(DAY_ONE + timedelta(minutes=index), price=100.0 + index)
        )
    one_minute = engine.history("1m", 100)
    five_minute = engine.history("5m", 100)
    assert len(one_minute) == 10
    assert len(five_minute) == 2
    assert five_minute[0]["o"] == one_minute[0]["o"]


def test_position_is_flattened_at_session_close(settings, store):
    from server.models import RiskDecision
    from server.strategy.base import Signal

    settings.risk.session_close_time = "15:00"
    settings.risk.close_at_session_end = True
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.start()
    engine._process(_tick(DAY_ONE, price=100.0))

    signal = Signal(
        key="k-close",
        side="long",
        reason="test",
        ts=DAY_ONE,
        stop_price=90.0,
        target_price=200.0,
    )
    engine.execution.arm(
        RiskDecision(approved=True, units=1, risk_per_unit=1.0),
        signal,
        "PRIMARY",
        100.0,
        DAY_ONE,
    )
    engine._process(_tick(DAY_ONE + timedelta(minutes=1), price=100.0))
    assert engine.execution.position is not None

    late = DAY_ONE + timedelta(hours=5, minutes=5)  # 20:05 UTC = 15:05 local
    engine._process(_tick(late, price=101.0))
    assert engine.execution.position is None
    assert engine.store.count_trades() == 1
    assert engine.store.list_trades()[0]["exit_reason"] == "session_close"


def test_freshness_is_measured_between_ticks_not_against_wall_clock(engine):
    engine._process(_tick(DAY_ONE))
    assert engine.state.quality == "ok"
    engine._process(_tick(DAY_ONE + timedelta(minutes=1)))
    assert engine.state.quality == "ok"
    assert engine.state.staleness_ms == 60_000
    engine._process(_tick(DAY_ONE + timedelta(minutes=20)))
    assert engine.state.quality == "stale"


def test_emergency_allows_closing_the_open_position(settings, store):
    from server.models import RiskDecision
    from server.strategy.base import Signal

    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.start()
    signal = Signal(key="k1", side="long", reason="t", ts=DAY_ONE, stop_price=90.0)
    engine.execution.arm(
        RiskDecision(approved=True, units=1, risk_per_unit=1.0),
        signal,
        "PRIMARY",
        100.0,
        DAY_ONE,
    )
    engine._process(_tick(DAY_ONE, price=100.0))
    assert engine.execution.position is not None

    engine.emergency_on()
    assert engine.state.status == "paused"
    trade = engine.execution.close("manual", price=101.0, when=DAY_ONE)
    assert trade is not None
    assert engine.execution.position is None


def test_emergency_blocks_new_entries(settings, store):
    from server.models import RiskDecision
    from server.strategy.base import Signal

    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.emergency_on()
    signal = Signal(key="k2", side="long", reason="t", ts=DAY_ONE, stop_price=90.0)
    portfolio = engine_portfolio(engine)
    decision = engine.risk.evaluate(
        signal,
        portfolio,
        settings.instruments.by_symbol("PRIMARY"),
        clock=DAY_ONE,
        timezone_name="America/New_York",
    )
    assert decision.approved is False
    assert decision.code == "emergency_active"


def engine_portfolio(engine):
    from server.models import PortfolioState

    return PortfolioState(
        equity=engine.state.equity,
        emergency=engine.state.emergency,
        last_price=100.0,
    )


class _NoParams(__import__("pydantic").BaseModel):
    pass


class _AlwaysSignalStrategy:
    """Fires on every bar so the rejection throttling can be observed."""

    id = "always"
    version = "0.0.0"
    params = {}
    params_model = _NoParams

    def warmup_requirements(self):
        from server.strategy.base import Warmup

        return Warmup(bars={"*": 1})

    def evaluate(self, md):
        from server.strategy.base import Signal, StrategyOutput

        return StrategyOutput(
            state="active",
            state_label="Activo",
            signal=Signal(
                key="always",
                side="long",
                reason="t",
                ts=md.clock,
                stop_price=md.bars[md.primary][-1].c - 5,
            ),
        )


class _OneSignalStrategy(_AlwaysSignalStrategy):
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, md):
        self.calls += 1
        if self.calls > 1:
            return StrategyOutput(state="active", state_label="Activo")
        return super().evaluate(md)


class _SignalExpiryStrategy(_AlwaysSignalStrategy):
    def __init__(self, valid_until: datetime) -> None:
        self.valid_until = valid_until

    def evaluate(self, md):
        output = super().evaluate(md)
        output.signal = output.signal.model_copy(update={"valid_until": self.valid_until})
        return output


def _risk_events(store):
    return [e for e in store.list_events(limit=500) if e["category"] == "risk"]


def test_repeated_rejections_are_counted_but_logged_once(settings, store):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.start()
    settings.risk.max_trades_per_day = 0

    for minute in range(30):
        engine._process(_tick(DAY_ONE + timedelta(minutes=minute)))

    from server.engine import REJECTION_LOG_INTERVAL_S

    expected = 1 + (29 * 60) // REJECTION_LOG_INTERVAL_S
    assert engine.state.block_count == 30
    assert len(_risk_events(store)) == expected
    assert expected < 30


def test_a_closed_session_cannot_arm_an_order(settings, store):
    settings.instruments.templates[0].open = "16:00"
    settings.instruments.templates[0].close = "17:00"
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.start()
    engine._process(_tick(DAY_ONE))  # 15:00, antes de la apertura
    assert engine.execution.pending_orders() == []
    assert engine.state.block_reason == "outside_window"


def test_a_signal_specific_veto_does_not_outlive_the_signal(engine):
    engine.start()
    engine.state.block_reason = "stop_too_wide"
    engine.state.block_count = 4
    engine._process(_tick(DAY_ONE))
    assert engine.state.block_reason is None
    assert engine.state.block_count == 0


def test_cooldown_block_expires_with_the_clock(engine):
    engine.settings.risk.cooldown_minutes = 5
    engine.last_exit_ts = DAY_ONE
    engine.state.block_reason = "cooldown_active"
    engine._process(_tick(DAY_ONE + timedelta(minutes=6)))
    assert engine.state.block_reason is None


def test_expired_signal_is_vetoed_before_arming(settings, store):
    engine = TradingEngine(
        settings,
        store,
        feed=None,
        strategy=_SignalExpiryStrategy(DAY_ONE - timedelta(seconds=1)),
    )
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert engine.execution.pending_orders() == []
    assert engine.state.block_reason == "stale_signal"
    assert engine.rejection_totals().get("stale_signal") == 1


def test_unexpired_signal_can_arm(settings, store):
    engine = TradingEngine(
        settings,
        store,
        feed=None,
        strategy=_SignalExpiryStrategy(DAY_ONE + timedelta(minutes=1)),
    )
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1
    assert engine.state.block_reason is None


def test_signal_is_valid_at_the_exact_expiry_boundary(settings, store):
    engine = TradingEngine(
        settings,
        store,
        feed=None,
        strategy=_SignalExpiryStrategy(DAY_ONE),
    )
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1


def test_expired_signal_does_not_mask_an_active_hard_risk_block(settings, store):
    from server.timeutil import session_for

    engine = TradingEngine(
        settings,
        store,
        feed=None,
        strategy=_SignalExpiryStrategy(DAY_ONE - timedelta(seconds=1)),
    )
    engine.state.session = session_for(DAY_ONE, settings.instruments.template_for(settings.instruments.primary))
    engine.state.day_stats.pnl = -settings.risk.initial_capital * settings.risk.max_daily_loss_pct / 100
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert engine.execution.pending_orders() == []
    assert engine.state.block_reason == "daily_loss_limit"


def test_live_signal_expiry_uses_wall_clock(settings, store, monkeypatch):
    engine = TradingEngine(
        settings,
        store,
        feed=None,
        strategy=_SignalExpiryStrategy(DAY_ONE + timedelta(seconds=30)),
    )
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(seconds=31))
    engine._process(_tick(DAY_ONE))
    assert engine.execution.pending_orders() == []
    assert engine.state.block_reason == "stale_signal"


def test_stale_feed_blocks_a_new_entry(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))
    engine.execution.cancel_all()
    engine.state.orders = list(engine.execution.orders)

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))
    engine._process(_tick(DAY_ONE + timedelta(minutes=1)))

    assert engine.state.quality == "stale"
    assert engine.state.block_reason == "stale_data"
    assert engine.execution.pending_orders() == []


def test_stale_block_clears_when_fresh_data_returns(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))
    engine.execution.cancel_all()
    engine.state.orders = list(engine.execution.orders)
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))
    engine._process(_tick(DAY_ONE + timedelta(minutes=1)))
    assert engine.state.block_reason == "stale_data"

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=18))
    engine._process(_tick(DAY_ONE + timedelta(minutes=18)))

    assert engine.state.quality == "ok"
    assert engine.state.block_reason is None


def test_stale_feed_cancels_a_pending_entry_before_it_can_fill(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))
    engine._process(_tick(DAY_ONE + timedelta(minutes=1)))

    assert engine.state.quality == "stale"
    assert engine.execution.position is None
    assert engine.execution.pending_orders() == []
    assert engine.execution.orders[-1].status == "cancelled"
    assert engine.state.block_reason == "stale_data"


def test_live_recovery_backfill_cannot_fill_with_wall_clock_stale_data(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))
    engine._process(_tick(DAY_ONE + timedelta(minutes=1)))

    assert engine.state.quality == "stale"
    assert engine.state.staleness_ms >= 19 * 60_000
    assert engine.execution.position is None
    assert engine.execution.pending_orders() == []


def test_live_watchdog_cancels_pending_during_silence(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))
    engine._check_live_freshness()

    assert engine.state.quality == "stale"
    assert engine.state.staleness_ms >= 19 * 60_000
    assert engine.execution.position is None
    assert engine.execution.pending_orders() == []
    assert engine.execution.orders[-1].status == "cancelled"
    assert engine.state.block_reason == "stale_data"


def test_live_order_expires_even_when_fresh_data_returns(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=3))
    engine._process(_tick(DAY_ONE + timedelta(minutes=3)))

    assert engine.state.quality == "ok"
    assert engine.execution.position is None
    assert engine.execution.pending_orders() == []
    assert engine.execution.orders[-1].status == "cancelled"
    assert any("señal antigua" in event["message"] for event in store.list_events(limit=20))
    assert engine.state.block_reason == "stale_order"


def test_watchdog_expires_an_old_order_before_data_becomes_stale(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(seconds=121))
    engine._check_live_freshness()

    assert engine.state.quality == "ok"
    assert engine.execution.pending_orders() == []
    assert engine.state.block_reason == "stale_order"


def test_order_ttl_starts_when_armed_not_at_candle_open(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE - timedelta(seconds=60)))
    assert len(engine.execution.pending_orders()) == 1

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(seconds=61))
    engine._check_live_freshness()

    assert len(engine.execution.pending_orders()) == 1
    assert engine.state.block_reason != "stale_order"


def test_fresh_unique_signal_clears_an_expired_order_block(settings, store, monkeypatch):
    class UniqueSignalStrategy(_AlwaysSignalStrategy):
        def evaluate(self, md):
            output = super().evaluate(md)
            output.signal = output.signal.model_copy(update={"key": f"unique-{md.clock.isoformat()}"})
            return output

    engine = TradingEngine(settings, store, feed=None, strategy=UniqueSignalStrategy())
    engine.state.provider = "okx"
    engine.start()
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE)
    engine._process(_tick(DAY_ONE))

    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(seconds=121))
    engine._check_live_freshness()
    assert engine.state.block_reason == "stale_order"

    engine._process(_tick(DAY_ONE + timedelta(seconds=121)))

    assert engine.state.block_reason is None
    assert len(engine.execution.pending_orders()) == 1


def test_watchdog_does_not_age_a_historical_replay(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy(), mode="backtest")
    engine.state.provider = "okx"
    engine.state.last_bar_ts = DAY_ONE
    engine.state.quality = "ok"
    engine.state.staleness_ms = 60_000
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(days=30))

    engine._check_live_freshness()

    assert engine.state.quality == "ok"
    assert engine.state.staleness_ms == 60_000


def test_watchdog_task_runs_without_ticks(settings, store, monkeypatch):
    from server.market.feed import MarketFeed

    class SilentFeed(MarketFeed):
        async def iter_ticks_async(self):
            await asyncio.Event().wait()
            if False:
                yield Tick()

    async def scenario():
        engine = TradingEngine(settings, store, feed=SilentFeed(), strategy=NullStrategy())
        engine.state.provider = "okx"
        engine.state.last_bar_ts = DAY_ONE
        published = []

        async def hook(snapshot):
            published.append(snapshot)

        engine.subscribe(hook)
        monkeypatch.setattr("server.engine.WATCHDOG_INTERVAL_S", 0.001)
        monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))
        try:
            engine.start()
            await engine.start_task()
            await asyncio.sleep(0.02)
            assert engine.state.quality == "stale"
            assert engine._watchdog_task is not None
            assert any(item["data"]["data"]["quality"] == "stale" for item in published)
        finally:
            await engine.stop_task()
        assert engine._watchdog_task is None

    asyncio.run(scenario())


def test_historical_gap_does_not_cancel_or_block_entries(settings, store):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy(), mode="backtest")
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    engine._process(_tick(DAY_ONE + timedelta(minutes=16)))

    assert engine.execution.position is not None
    assert engine.state.block_reason != "stale_data"


def test_queued_refresh_cannot_restart_a_stopped_engine(settings, store):
    from server.market.feed import MarketFeed

    active = 0

    class CountingFeed(MarketFeed):
        async def iter_ticks_async(self):
            nonlocal active
            active += 1
            try:
                await asyncio.Event().wait()
                if False:
                    yield Tick()
            finally:
                active -= 1

    async def scenario():
        engine = TradingEngine(
            settings,
            store,
            feed=CountingFeed(),
            strategy=NullStrategy(),
            feed_factory=lambda cfg: CountingFeed(),
        )
        try:
            engine.start()
            await engine.start_task()
            updated = settings.model_copy(deep=True)
            updated.feed.replay_speed = 1000
            engine.update_settings(updated)
            engine.stop()
            await engine.stop_task()
            await asyncio.sleep(0)
            assert engine.state.status == "stopped"
            assert engine._task is None
            assert active == 0
        finally:
            await engine.stop_task()

    asyncio.run(scenario())


def test_refresh_rechecks_stop_after_teardown(settings, store):
    from server.market.feed import MarketFeed

    starts = 0

    class CountingFeed(MarketFeed):
        async def iter_ticks_async(self):
            nonlocal starts
            starts += 1
            await asyncio.Event().wait()
            if False:
                yield Tick()

    async def scenario():
        engine = TradingEngine(settings, store, feed=CountingFeed(), strategy=NullStrategy())
        original = engine._stop_tasks_unlocked

        async def teardown_then_stop():
            await original()
            engine.stop()

        try:
            engine.start()
            await engine.start_task()
            await asyncio.sleep(0)
            assert starts == 1
            engine._stop_tasks_unlocked = teardown_then_stop
            await engine.refresh_task()
            assert starts == 1
            assert engine._task is None
        finally:
            engine._stop_tasks_unlocked = original
            await engine.stop_task()

    asyncio.run(scenario())


def test_concurrent_refreshes_leave_only_one_feed_consumer(settings, store):
    from server.market.feed import MarketFeed

    starts = 0
    active = 0

    class CountingFeed(MarketFeed):
        async def iter_ticks_async(self):
            nonlocal starts, active
            starts += 1
            active += 1
            try:
                await asyncio.Event().wait()
                if False:
                    yield Tick()
            finally:
                active -= 1

    async def scenario():
        engine = TradingEngine(settings, store, feed=CountingFeed(), strategy=NullStrategy())
        try:
            engine.start()
            await engine.start_task()
            await asyncio.gather(engine.refresh_task(), engine.refresh_task())
            await asyncio.sleep(0)
            assert starts == 3
            assert active == 1
            assert engine._task is not None and not engine._task.done()
        finally:
            await engine.stop_task()
        await asyncio.sleep(0)
        assert active == 0

    asyncio.run(scenario())


def test_gap_rejection_is_accounted_with_fill_diagnostics(settings, store):
    settings.execution.slippage_ticks = 0
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    engine._process(_tick(DAY_ONE + timedelta(minutes=1), price=90.0))

    assert engine.execution.position is None
    assert engine.rejection_totals()["gap_through_stop"] == 1
    assert engine.state.block_reason == "gap_through_stop"
    assert engine.snapshot()["data"]["risk"]["block_reason"] == "gap_through_stop"
    event = next(
        row
        for row in store.list_events(limit=50)
        if row["category"] == "execution"
        and json.loads(row["meta"]).get("reason") == "gap_through_stop"
    )
    diagnostics = json.loads(event["meta"])["diagnostics"]
    assert diagnostics["candidate_fill"] == pytest.approx(90.0)
    assert diagnostics["stop_price"] == pytest.approx(95.5)


def test_notional_block_clears_when_the_signal_disappears(engine):
    from server.timeutil import session_for

    engine.start()
    engine.state.session = session_for(DAY_ONE, engine.settings.instruments.template_for(engine.settings.instruments.primary))
    engine.state.block_reason = "below_min_notional"
    engine.state.block_count = 1
    engine._process(_tick(DAY_ONE))
    assert engine.state.block_reason is None
    assert engine.state.block_count == 0


def test_notional_block_clears_during_warmup(settings, store):
    from server.strategy.base import Warmup

    class WarmingStrategy(NullStrategy):
        def warmup_requirements(self):
            return Warmup(bars={"*": 100})

    engine = TradingEngine(settings, store, feed=None, strategy=WarmingStrategy())
    engine.start()
    engine.state.block_reason = "below_min_notional"
    engine.state.block_count = 1
    engine._process(_tick(DAY_ONE))
    assert engine.state.block_reason is None
    assert engine.state.block_count == 0


def test_fill_notional_rejection_is_persisted_with_its_cause(settings, store):
    instrument = settings.instruments.by_symbol(settings.instruments.primary)
    instrument.contract_size = 1
    instrument.min_notional = 500
    settings.execution.slippage_ticks = 0
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.start()
    engine._process(_tick(DAY_ONE))
    assert len(engine.execution.pending_orders()) == 1

    engine._process(_tick(DAY_ONE + timedelta(minutes=1), price=99.25))

    assert engine.execution.position is None
    assert engine.execution.orders[-1].status == "rejected"
    event = next(
        row
        for row in store.list_events(limit=50)
        if row["category"] == "execution"
        and json.loads(row["meta"]).get("reason") == "below_min_notional"
    )
    assert json.loads(event["meta"])["diagnostics"]["fill_price"] == pytest.approx(99.25)
    assert engine.rejection_totals()["below_min_notional"] == 1


def test_fill_rejection_survives_a_no_signal_tick_then_clears(settings, store):
    instrument = settings.instruments.by_symbol(settings.instruments.primary)
    instrument.contract_size = 1
    instrument.min_notional = 500
    settings.execution.slippage_ticks = 0
    engine = TradingEngine(settings, store, feed=None, strategy=_OneSignalStrategy())
    engine.start()
    engine._process(_tick(DAY_ONE))
    engine._process(_tick(DAY_ONE + timedelta(minutes=1), price=99.25))
    assert engine.state.block_reason == "below_min_notional"
    assert engine.state.block_count == 1
    assert engine.snapshot()["data"]["risk"]["block_reason"] == "below_min_notional"

    engine._process(_tick(DAY_ONE + timedelta(minutes=2), price=100.0))
    assert engine.state.block_reason is None
    assert engine.state.block_count == 0


def test_stale_feed_still_manages_an_open_position(settings, store, monkeypatch):
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.state.provider = "okx"
    engine.execution.restore(
        Position(
            symbol="PRIMARY",
            side="long",
            units=5,
            entry_price=100.0,
            stop_price=99.5,
            target_price=102.0,
            opened_ts=DAY_ONE,
        )
    )
    engine.state.position = engine.execution.position
    monkeypatch.setattr("server.engine.now_utc", lambda: DAY_ONE + timedelta(minutes=20))

    engine._process(_tick(DAY_ONE + timedelta(minutes=1), price=99.0))

    assert engine.state.quality == "stale"
    assert engine.execution.position is None
    trades = store.all_trades(mode="paper")
    assert len(trades) == 1
    assert trades[0].exit_reason == "stop"


def test_watchdog_survives_a_failed_check(settings, store, monkeypatch):
    from server.market.feed import MarketFeed

    class SilentFeed(MarketFeed):
        async def iter_ticks_async(self):
            await asyncio.Event().wait()
            if False:
                yield Tick()

    async def scenario():
        engine = TradingEngine(settings, store, feed=SilentFeed(), strategy=NullStrategy())
        engine.state.provider = "okx"
        engine.state.last_bar_ts = DAY_ONE
        calls = 0

        def flaky():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("one bad check")
            engine.state.quality = "stale"
            return True

        monkeypatch.setattr(engine, "_check_live_freshness", flaky)
        monkeypatch.setattr("server.engine.WATCHDOG_INTERVAL_S", 0.001)
        try:
            engine.start()
            await engine.start_task()
            # Esperar la condición, no un tiempo fijo: un ciclo lento de la
            # máquina no convierte esta prueba en un flake.
            deadline = asyncio.get_running_loop().time() + 2.0
            while asyncio.get_running_loop().time() < deadline:
                if calls >= 2 and engine.state.quality == "stale":
                    break
                await asyncio.sleep(0.002)
            assert calls >= 2
            assert engine.state.quality == "stale"
            assert engine._watchdog_task is not None and not engine._watchdog_task.done()
        finally:
            await engine.stop_task()

    asyncio.run(scenario())


def test_rejection_is_logged_again_after_the_window(settings, store):
    engine = TradingEngine(settings, store, feed=None, strategy=_AlwaysSignalStrategy())
    engine.start()
    settings.risk.max_trades_per_day = 0

    engine._process(_tick(DAY_ONE))
    engine._process(_tick(DAY_ONE + timedelta(minutes=1)))
    engine._process(_tick(DAY_ONE + timedelta(minutes=5)))

    assert len(_risk_events(store)) == 2
    assert engine.state.block_count == 3


def _feed_bars(engine, start: datetime, count: int):
    for index in range(count):
        stamp = start + timedelta(minutes=index)
        bar = Bar(t=stamp, o=100 + index, h=101 + index, l=99 + index, c=100.5 + index, v=10)
        engine._bars.setdefault("PRIMARY", []).append(bar)


def test_history_passthrough_on_one_minute(engine):
    _feed_bars(engine, DAY_ONE, 10)
    assert len(engine.history("1m", 100)) == 10
    assert len(engine.history("1m", 4)) == 4


def test_history_resamples_open_high_low_close_volume(engine):
    _feed_bars(engine, DAY_ONE, 10)
    candles = engine.history("5m", 100)
    assert len(candles) == 2
    first = candles[0]
    assert first["o"] == 100  # first open of the bucket
    assert first["c"] == 104.5  # last close of the bucket
    assert first["h"] == 105  # max high
    assert first["l"] == 99  # min low
    assert first["v"] == 50  # summed volume
    second = candles[1]
    assert second["o"] == 105
    assert second["c"] == 109.5


def test_history_rejects_an_unknown_timeframe(engine):
    import pytest

    with pytest.raises(ValueError):
        engine.history("7m", 10)


def test_snapshot_publishing_is_rate_limited(settings, store):
    import asyncio

    from server.engine import SNAPSHOT_MIN_INTERVAL_S
    from server.market.feed import MarketFeed

    class BurstFeed(MarketFeed):
        name = "burst"

        def iter_ticks(self):
            for minute in range(60):
                stamp = DAY_ONE + timedelta(minutes=minute)
                yield _tick(stamp)

    published: list[dict] = []

    async def hook(snapshot):
        published.append(snapshot)

    async def scenario():
        settings.feed.replay_speed = 1000.0
        engine = TradingEngine(settings, store, feed=BurstFeed(), strategy=NullStrategy())
        engine.subscribe(hook)
        engine.start()
        await engine.start_task()
        while engine._task is not None and not engine._task.done():
            await asyncio.sleep(0.005)
        return engine

    engine = asyncio.run(scenario())
    assert engine.state.bars_available == 60
    # 60 ticks far faster than the interval: at most one publish per window.
    window = 60 * (1.0 / 1000.0)
    assert len(published) <= int(window / SNAPSHOT_MIN_INTERVAL_S) + 2
    assert len(published) < 60


def test_control_actions_force_a_publish(settings, store):
    import asyncio

    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())

    async def scenario():
        published: list[dict] = []

        async def hook(snapshot):
            published.append(snapshot)

        engine.subscribe(hook)
        await engine._publish()
        await engine._publish()  # throttled: same window
        engine.pause()
        await engine._publish()  # forced by the control action
        return published

    published = asyncio.run(scenario())
    assert len(published) == 2


def test_snapshot_carries_stats_and_caches_them(settings, store):
    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    first = engine.snapshot()["data"]["stats"]
    second = engine.snapshot()["data"]["stats"]
    assert first == second
    assert first["closed"]["trades"] == 0
    # The cache is invalidated when a trade is booked.
    assert engine.stats() is engine.stats()


def test_stats_cache_is_invalidated_after_a_trade(settings, store):
    from server.models import TradeRecord

    engine = TradingEngine(settings, store, feed=None, strategy=NullStrategy())
    engine.stats()
    trade = TradeRecord(
        id="t1",
        symbol="PRIMARY",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=101.0,
        opened_ts=DAY_ONE,
        closed_ts=DAY_ONE + timedelta(minutes=5),
        pnl_gross=1.0,
        pnl_net=0.9,
        fees=0.1,
        exit_reason="target",
        mode="paper",
        r_multiple=1.0,
    )
    engine._on_trade_closed(trade)
    assert engine.snapshot()["data"]["stats"]["closed"]["trades"] == 1
