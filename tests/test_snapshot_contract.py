from __future__ import annotations

import logging
from datetime import timedelta

from server.models import EngineState, SessionInfo
from server.schemas import Snapshot, SnapshotData
from server.snapshot import SnapshotBuilder
from server.strategy.base import Metric, Phase, StrategyOutput, Zone
from tests.conftest import NOW


def _state() -> EngineState:
    return EngineState(
        status="stopped",
        mode="paper",
        session=SessionInfo(id="2026-01-15:RTH", label="RTH", is_open=True),
        provider="simulated",
        quality="ok",
        equity=25000.0,
    )


def test_snapshot_validates_against_schema(settings):
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    Snapshot.model_validate(snapshot)
    assert snapshot["v"] == 1
    assert snapshot["data"]["strategy"]["signal"] is None
    assert snapshot["data"]["strategy"]["phases"] == []


def test_stopped_engine_keeps_the_configured_strategy_label(settings):
    settings.strategy.id = "reference"
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    strategy = snapshot["data"]["strategy"]
    assert strategy["state"] == "idle"
    assert strategy["state_label"] == "Motor detenido"


def test_data_payload_also_validates(settings):
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    SnapshotData.model_validate(snapshot["data"])


def test_live_snapshot_ages_quality_during_a_silent_feed_outage(settings):
    state = _state()
    state.provider = "okx"
    state.last_bar_ts = NOW - timedelta(minutes=20)
    state.quality = "ok"
    snapshot = SnapshotBuilder(settings).build(state, None)
    assert snapshot["data"]["data"]["quality"] == "stale"
    assert snapshot["data"]["data"]["staleness_ms"] >= 19 * 60_000

    state.mode = "backtest"
    replay = SnapshotBuilder(settings).build(state, None)
    assert replay["data"]["data"]["quality"] == "ok"


def test_quotes_follow_configured_instruments(settings):
    settings.instruments.items = [
        settings.instruments.by_symbol("PRIMARY"),
    ]
    builder = SnapshotBuilder(settings)
    snapshot = builder.build(_state(), None, quotes={"PRIMARY": {"last": 100.0}})
    assert set(snapshot["data"]["quotes"]) == {"PRIMARY"}
    assert {item["symbol"] for item in snapshot["data"]["instruments"]} == {"PRIMARY"}


def test_added_instrument_appears_without_code_change(settings):
    from server.config import InstrumentConfig

    settings.instruments.items.append(InstrumentConfig(symbol="CTX_A"))
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    assert set(snapshot["data"]["quotes"]) == {"PRIMARY", "CTX_A"}
    assert {"PRIMARY", "CTX_A"} == {item["symbol"] for item in snapshot["data"]["instruments"]}


def test_removed_instrument_leaves_no_orphan_quote(settings):
    builder = SnapshotBuilder(settings)
    snapshot = builder.build(_state(), None, quotes={"GHOST": {"last": 1.0}})
    assert "GHOST" not in snapshot["data"]["quotes"]


def test_phases_arbitrary_length(settings):
    builder = SnapshotBuilder(settings)
    for count in (0, 3, 12):
        output = StrategyOutput(
            state="running",
            state_label="Estado",
            phases=[
                Phase(key=f"p{index}", label=f"Fase {index}", status="pending")
                for index in range(count)
            ],
        )
        snapshot = builder.build(_state(), output)
        assert len(snapshot["data"]["strategy"]["phases"]) == count
        Snapshot.model_validate(snapshot)


def test_metrics_are_rendered_from_backend_hints(settings):
    output = StrategyOutput(
        state="running",
        state_label="Estado",
        metrics={
            "atr_14": Metric(label="ATR(14)", value=12.5, format="price", unit="pts", tone="neutral"),
            "bias": Metric(label="Sesgo", value="neutral", format="text", tone="warn"),
        },
    )
    snapshot = SnapshotBuilder(settings).build(_state(), output)
    metrics = snapshot["data"]["strategy"]["metrics"]
    assert metrics["atr_14"]["format"] == "price"
    assert metrics["bias"]["value"] == "neutral"


def test_unknown_zone_kind_is_dropped_and_logged(settings, caplog):
    output = StrategyOutput(
        state="running",
        state_label="Estado",
        zones=[
            Zone(id="z1", kind="band", from_ts=NOW, price_low=1.0, price_high=2.0),
            Zone.model_construct(id="z2", kind="hexagon", from_ts=NOW, price_low=1.0, price_high=2.0, label=None, to_ts=None, style={}, active=True),
        ],
    )
    with caplog.at_level(logging.WARNING):
        snapshot = SnapshotBuilder(settings).build(_state(), output)
    kinds = [zone["kind"] for zone in snapshot["data"]["chart"]["zones"]]
    assert kinds == ["band"]
    assert "unsupported zone kind" in caplog.text


def test_snapshot_has_no_strategy_specific_keys(settings):
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    assert set(snapshot["data"]["strategy"]) == {
        "id",
        "name",
        "version",
        "timeframe",  # marco del motor, no del plugin
        "state",
        "state_label",
        "phases",
        "metrics",
        "signal",
        "rejection",
        "rejections",
    }


def test_stale_position_open_reason_is_dropped(settings):
    state = _state()
    state.block_reason = "position_open"
    snapshot = SnapshotBuilder(settings).build(state, None)
    risk = snapshot["data"]["risk"]
    assert risk["block_reason"] is None
    assert risk["blocked"] is False


def test_position_open_reason_survives_with_a_pending_order(settings):
    from server.models import Order

    state = _state()
    state.block_reason = "position_open"
    state.orders = [
        Order(
            id="o1",
            symbol="PRIMARY",
            side="long",
            units=1,
            price=100.0,
            status="pending",
            created_ts=NOW,
            risk_budget=250.0,
        )
    ]
    snapshot = SnapshotBuilder(settings).build(state, None)
    assert snapshot["data"]["risk"]["block_reason"] == "position_open"
    assert snapshot["data"]["orders"][0]["risk_budget"] == 250.0


def test_stale_max_trades_reason_is_dropped(settings):
    state = _state()
    state.block_reason = "max_trades_reached"
    state.day_stats.trades = settings.risk.max_trades_per_day - 1
    risk = SnapshotBuilder(settings).build(state, None)["data"]["risk"]
    assert risk["block_reason"] is None
    assert risk["blocked"] is False


def test_max_trades_reason_survives_at_the_cap(settings):
    state = _state()
    state.block_reason = "max_trades_reached"
    state.day_stats.trades = settings.risk.max_trades_per_day
    risk = SnapshotBuilder(settings).build(state, None)["data"]["risk"]
    assert risk["block_reason"] == "max_trades_reached"


def test_stale_daily_loss_reason_is_dropped(settings):
    state = _state()
    state.block_reason = "daily_loss_limit"
    state.day_stats.pnl = 0.0
    risk = SnapshotBuilder(settings).build(state, None)["data"]["risk"]
    assert risk["block_reason"] is None


def test_stale_order_pending_reason_is_dropped(settings):
    state = _state()
    state.block_reason = "order_pending"
    risk = SnapshotBuilder(settings).build(state, None)["data"]["risk"]
    assert risk["block_reason"] is None


def test_stale_consecutive_losses_reason_is_dropped(settings):
    settings.risk.no_trade_after_consecutive_losses = 2
    state = _state()
    state.block_reason = "consecutive_losses"
    state.day_stats.consecutive_losses = 1
    risk = SnapshotBuilder(settings).build(state, None)["data"]["risk"]
    assert risk["block_reason"] is None


def test_consecutive_losses_reason_survives_with_the_streak(settings):
    settings.risk.no_trade_after_consecutive_losses = 2
    state = _state()
    state.block_reason = "consecutive_losses"
    state.day_stats.consecutive_losses = 2
    risk = SnapshotBuilder(settings).build(state, None)["data"]["risk"]
    assert risk["block_reason"] == "consecutive_losses"


def test_snapshot_carries_rejection_totals(settings):
    snapshot = SnapshotBuilder(settings).build(
        _state(), None, rejections={"stop_too_wide": 7, "no_price": 2}
    )
    assert snapshot["data"]["strategy"]["rejections"] == {"stop_too_wide": 7, "no_price": 2}


def test_risk_limits_use_the_same_wall_as_the_engine(settings):
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    limits = snapshot["data"]["risk"]["limits"]
    expected = settings.risk.initial_capital * settings.risk.max_daily_loss_pct / 100
    # risk.py rechaza sobre initial_capital; la UI no puede inventar otro muro.
    assert limits["daily_loss_limit"] == expected
    assert limits["initial_capital"] == settings.risk.initial_capital
    if settings.risk.soft_brakes:
        assert limits["soft_brake_at"] == expected * 0.8


def test_pending_order_with_brackets_validates(settings):
    from datetime import datetime, timezone

    from server.models import EngineState, Order

    state = EngineState(
        status="running",
        mode="paper",
        equity=25000.0,
        orders=[
            Order(
                id="o1",
                symbol="PRIMARY",
                side="long",
                units=2,
                price=100.0,
                created_ts=datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc),
                stop_price=99.5,
                target_price=101.5,
                signal_key="sig-1",
            )
        ],
    )
    snapshot = SnapshotBuilder(settings).build(state, None)
    order = snapshot["data"]["orders"][0]
    assert order["stop_price"] == 99.5
    assert order["target_price"] == 101.5
    assert order["signal_key"] == "sig-1"
    Snapshot.model_validate(snapshot)
