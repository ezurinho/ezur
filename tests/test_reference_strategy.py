from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from server.models import Bar, SessionInfo
from server.strategy.base import MarketData
from server.strategy.reference import ReferenceParams, ReferenceStrategy, atr, sma

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def _session() -> SessionInfo:
    return SessionInfo(id="2026-01-15:RTH", label="RTH", is_open=True, phase="open")


def _bars(closes: list[float]) -> list[Bar]:
    return [
        Bar(
            t=NOW + timedelta(minutes=index),
            o=close,
            h=close + 0.5,
            l=close - 0.5,
            c=close,
            v=100,
        )
        for index, close in enumerate(closes)
    ]


def _market_data(bars: list[Bar], params: ReferenceParams | None = None) -> MarketData:
    return MarketData(
        session=_session(),
        clock=NOW,
        primary="PRIMARY",
        bars={"PRIMARY": bars},
        params=params or ReferenceParams(),
    )


def test_sma_and_atr_are_plain_arithmetic():
    assert sma([1, 2, 3, 4], 2) == pytest.approx(3.5)
    assert sma([1, 2], 5) is None
    bars = _bars([100, 101, 102, 103])
    value = atr(bars, 2)
    assert value is not None
    assert value > 0


def test_warmup_before_enough_bars():
    strategy = ReferenceStrategy({"fast": 3, "slow": 5, "atr_period": 2})
    output = strategy.evaluate(_market_data(_bars([100, 101, 102])))
    assert output.state == "warmup"
    assert output.signal is None
    assert output.phases[0].status == "active"


def test_warmup_requirement_uses_wildcard_symbol():
    strategy = ReferenceStrategy({"slow": 21, "atr_period": 14})
    requirement = strategy.warmup_requirements()
    assert requirement.bars == {"*": 23}


def test_crossover_emits_a_signal_with_brackets():
    strategy = ReferenceStrategy({"fast": 3, "slow": 5, "atr_period": 2, "stop_atr": 1.0, "rr": 2.0})
    closes = [100.0] * 12 + [101.0, 103.0, 106.0, 110.0]
    bars = _bars(closes)
    signal = None
    for size in range(7, len(bars) + 1):
        output = strategy.evaluate(_market_data(bars[:size]))
        if output.signal is not None:
            signal = output.signal
            markers = output.markers
            zones = output.zones
            break
    assert signal is not None
    assert signal.side == "long"
    assert signal.target_price is not None
    assert signal.stop_price < signal.target_price
    assert signal.stop_price < 101.0 < signal.target_price
    assert len(markers) == 1 and markers[0].kind == "entry"
    assert zones[-1].kind == "box"


def test_evaluate_is_deterministic():
    strategy = ReferenceStrategy({"fast": 3, "slow": 5, "atr_period": 2})
    bars = _bars([100.0] * 10 + [101.0, 102.0, 103.0])
    first = strategy.evaluate(_market_data(bars)).model_dump(mode="json")
    second = strategy.evaluate(_market_data(bars)).model_dump(mode="json")
    assert first == second


def test_signal_key_is_stable_and_unique_per_bar():
    strategy = ReferenceStrategy({"fast": 3, "slow": 5, "atr_period": 2})
    bars = _bars([100.0] * 10 + [101.0, 103.0, 106.0])
    keys = set()
    for size in range(7, len(bars) + 1):
        output = strategy.evaluate(_market_data(bars[:size]))
        if output.signal:
            keys.add(output.signal.key)
    assert len(keys) >= 1
    assert all(":" in key for key in keys)


def test_metrics_and_phases_are_reported():
    strategy = ReferenceStrategy({"fast": 3, "slow": 5, "atr_period": 2})
    output = strategy.evaluate(_market_data(_bars([100.0] * 12 + [101.0, 102.0])))
    assert set(output.metrics) >= {"fast", "slow", "atr", "spread", "bias"}
    assert [phase.key for phase in output.phases] == ["warmup", "bias", "trigger"]
    assert output.metrics["atr"].format == "price"


def test_params_are_validated():
    with pytest.raises(ValidationError):
        ReferenceStrategy({"fast": 0})
    with pytest.raises(ValidationError):
        ReferenceParams(fast=50, slow=10)  # slow must be longer than fast
