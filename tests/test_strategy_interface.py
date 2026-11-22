from __future__ import annotations

import pytest
from pydantic import ValidationError

from server.strategy.base import BaseStrategy, StrategyOutput, Warmup
from server.strategy.null_strategy import NullStrategy
from server.strategy.registry import available, resolve_strategy, strategy_schema


def test_null_strategy_satisfies_protocol():
    strategy = NullStrategy()
    assert isinstance(strategy, BaseStrategy)
    assert strategy.id == "null"
    assert strategy.version == "0.0.0"


def test_warmup_requirements_are_empty():
    assert NullStrategy().warmup_requirements() == Warmup(bars={}, session_ready=False)


def test_null_strategy_emits_no_signal(md_fixture):
    output = NullStrategy().evaluate(md_fixture)
    assert isinstance(output, StrategyOutput)
    assert output.signal is None
    assert output.state == "disabled"
    assert output.phases == []
    assert output.metrics == {}
    assert output.zones == []
    assert output.markers == []


def test_registry_rejects_unknown_id():
    with pytest.raises(KeyError):
        resolve_strategy("does-not-exist", {})


def test_registry_rejects_invalid_params():
    with pytest.raises(ValidationError):
        resolve_strategy("null", {"unexpected": 1})


def test_registry_lists_available():
    assert "null" in available()


def test_strategy_schema_is_derived_from_plugin():
    schema = strategy_schema("null")
    assert schema["id"] == "null"
    assert schema["params_schema"]["type"] == "object"


def test_signal_requires_stop_price():
    from server.strategy.base import Signal
    from tests.conftest import NOW

    with pytest.raises(ValidationError):
        Signal(key="k", side="long", reason="r", ts=NOW, stop_price=None)
