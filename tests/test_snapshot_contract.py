from __future__ import annotations

import logging

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


def test_data_payload_also_validates(settings):
    snapshot = SnapshotBuilder(settings).build(_state(), None)
    SnapshotData.model_validate(snapshot["data"])


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
        "state",
        "state_label",
        "phases",
        "metrics",
        "signal",
        "rejection",
    }


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
