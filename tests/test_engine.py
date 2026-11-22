from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from server.engine import TradingEngine
from server.models import Bar, Position, Tick
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
