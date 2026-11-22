from __future__ import annotations

import logging

import pytest

from server.models import EngineState
from server.snapshot import SnapshotBuilder
from server.strategy.base import Marker, Phase, StrategyOutput
from tests.conftest import NOW


def _state() -> EngineState:
    return EngineState(status="stopped", mode="paper", equity=25000.0)


def test_unknown_marker_kind_is_dropped(settings, caplog):
    output = StrategyOutput(
        state="running",
        state_label="Estado",
        markers=[
            Marker(id="m1", ts=NOW, price=100.0, kind="entry", side="long"),
            Marker.model_construct(id="m2", ts=NOW, price=100.0, kind="arrow", side="long", label=None),
        ],
    )
    with caplog.at_level(logging.WARNING):
        snapshot = SnapshotBuilder(settings).build(_state(), output)
    kinds = [marker["kind"] for marker in snapshot["data"]["chart"]["markers"]]
    assert kinds == ["entry"]
    assert "unsupported marker kind" in caplog.text


def test_series_for_unconfigured_symbol_is_dropped(settings, caplog):
    series = [{"symbol": "GHOST", "mode": "raw", "axis": "overlay", "values": []}]
    with caplog.at_level(logging.WARNING):
        snapshot = SnapshotBuilder(settings).build(_state(), None, series=series)
    assert snapshot["data"]["chart"]["series"] == []
    assert "unconfigured symbol" in caplog.text


def test_series_for_configured_symbol_is_kept(settings):
    primary = settings.instruments.primary
    series = [{"symbol": primary, "mode": "normalized", "axis": "overlay", "values": []}]
    snapshot = SnapshotBuilder(settings).build(_state(), None, series=series)
    kept = snapshot["data"]["chart"]["series"][0]
    assert kept["symbol"] == primary
    assert kept["mode"] == "normalized"


@pytest.mark.parametrize("count", [0, 1, 12])
def test_phase_timeline_contract_survives_any_length(settings, count):
    output = StrategyOutput(
        state="running",
        state_label="Estado",
        phases=[Phase(key=f"p{index}", label="x") for index in range(count)],
    )
    snapshot = SnapshotBuilder(settings).build(_state(), output)
    assert len(snapshot["data"]["strategy"]["phases"]) == count
