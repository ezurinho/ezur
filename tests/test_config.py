from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from server.config import (
    InstrumentConfig,
    InstrumentsConfig,
    Settings,
    ExecutionConfig,
    apply_settings,
    load_settings,
    save_settings,
)


def test_defaults_match_spec():
    settings = Settings()
    assert settings.risk.risk_per_trade_pct == 1.0
    assert settings.risk.max_daily_loss_pct == 3.0
    assert settings.risk.max_trades_per_day == 3
    assert settings.risk.max_units_per_trade == 5
    assert settings.execution.fill_model == "next_open"
    assert settings.execution.commission_per_unit_side == 0.62
    assert settings.live.live_enabled is False
    assert settings.live.can_start() is False
    assert settings.instruments.items[0].lot_size == 1
    assert settings.instruments.items[0].min_notional is None
    assert settings.instruments.items[0].contract_size is None


def test_strategy_timeframe_defaults_to_one_minute():
    assert Settings().strategy.timeframe == "1m"


def test_strategy_timeframe_rejects_unknown():
    with pytest.raises(ValidationError):
        Settings.model_validate({"strategy": {"timeframe": "1w"}})


def test_corrupt_config_is_archived_and_defaults_restored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    settings = load_settings(path)
    assert settings.risk.risk_per_trade_pct == 1.0
    assert settings.auto_start is False
    assert (tmp_path / "config.json.broken").exists()


def test_missing_profile_does_not_auto_start(tmp_path):
    assert load_settings(tmp_path / "missing.json").auto_start is False


def test_future_schema_version_is_rejected():
    with pytest.raises(ValidationError):
        Settings.model_validate({"version": 999})


def test_non_finite_risk_and_negative_costs_are_rejected():
    with pytest.raises(ValidationError):
        Settings.model_validate({"risk": {"max_daily_loss_pct": float("nan")}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"execution": {"commission_per_unit_side": -0.1}})


def test_instrument_metadata_is_validated_before_the_engine_sees_it():
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", tick_size=0)
    with pytest.raises(ValidationError):
        InstrumentsConfig(
            items=[InstrumentConfig(symbol="AAA", role="primary", session_template="missing")],
            primary="AAA",
        )


def test_synthetic_reference_price_is_explicit_and_positive():
    assert InstrumentConfig(symbol="AAA", reference_price=60_000).reference_price == 60_000
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", reference_price=0)


def test_tick_size_below_supported_precision_is_rejected():
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", tick_size=1e-13)


def test_lot_and_notional_metadata_are_validated():
    instrument = InstrumentConfig(symbol="AAA", lot_size=5, min_notional=100, contract_size=2)
    assert instrument.lot_size == 5
    assert instrument.min_notional == 100
    assert instrument.contract_size == 2
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", lot_size=0)
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", min_notional=0)
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", min_notional=100)


@pytest.mark.parametrize("value", [True, 1.5, "2", -1])
def test_lot_size_must_be_a_positive_integer(value):
    with pytest.raises(ValidationError):
        InstrumentConfig(symbol="AAA", lot_size=value)


def test_tiny_positive_tick_value_remains_valid():
    assert InstrumentConfig(symbol="AAA", tick_value=1e-13).tick_value == 1e-13


def test_intrabar_alias_is_not_accepted_as_a_fill_model():
    with pytest.raises(ValidationError):
        ExecutionConfig(fill_model="intrabar")


def test_legacy_intrabar_profile_migrates_to_next_open(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"auto_start": True, "execution": {"fill_model": "intrabar"}}),
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert settings.execution.fill_model == "next_open"
    assert settings.auto_start is True


def test_save_is_atomic(tmp_path):
    path = tmp_path / "config.json"
    save_settings(Settings(), path)
    assert json.loads(path.read_text(encoding="utf-8"))["risk"]["risk_per_trade_pct"] == 1.0
    assert not (tmp_path / "config.json.tmp").exists()


def test_roundtrip_preserves_values(tmp_path):
    path = tmp_path / "config.json"
    settings = Settings.model_validate({"risk": {"max_trades_per_day": 7}})
    save_settings(settings, path)
    assert load_settings(path).risk.max_trades_per_day == 7


def test_apply_rejects_invalid_patch():
    with pytest.raises(ValidationError):
        apply_settings(Settings(), {"risk": {"risk_per_trade_pct": 150}})


def test_apply_is_partial_and_does_not_mutate():
    original = Settings()
    updated = apply_settings(original, {"risk": {"max_trades_per_day": 9}})
    assert updated.risk.max_trades_per_day == 9
    assert original.risk.max_trades_per_day == 3


def test_apply_rejects_unknown_group():
    with pytest.raises(ValueError):
        apply_settings(Settings(), {"nope": {}})


def test_duplicate_symbols_rejected():
    with pytest.raises(ValidationError):
        InstrumentsConfig(
            items=[
                InstrumentConfig(symbol="AAA", role="primary"),
                InstrumentConfig(symbol="AAA"),
            ],
            primary="AAA",
        )


def test_primary_must_be_configured():
    with pytest.raises(ValidationError):
        InstrumentsConfig(items=[InstrumentConfig(symbol="AAA", role="primary")], primary="BBB")


def test_exactly_one_enabled_primary():
    with pytest.raises(ValidationError):
        InstrumentsConfig(
            items=[InstrumentConfig(symbol="AAA", role="primary", enabled=False)],
            primary="AAA",
        )


def test_live_requires_all_three_conditions():
    settings = Settings()
    settings.live.broker = "some-broker"
    settings.live.live_enabled = True
    assert settings.live.can_start() is False
    settings.live.live_confirmation = "yes"
    assert settings.live.can_start() is False
    settings.live.adapter_implemented = True
    assert settings.live.can_start() is True

def test_funding_fails_instead_of_being_ignored():
    with pytest.raises(ValidationError):
        ExecutionConfig(funding="real_timestamps")


def test_stop_floor_fails_instead_of_being_ignored():
    with pytest.raises(ValidationError):
        ExecutionConfig(stop_floor_frac=0.01)