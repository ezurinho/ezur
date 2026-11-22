from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from server.config import (
    InstrumentConfig,
    InstrumentsConfig,
    Settings,
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


def test_corrupt_config_is_archived_and_defaults_restored(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{not json", encoding="utf-8")
    settings = load_settings(path)
    assert settings.risk.risk_per_trade_pct == 1.0
    assert (tmp_path / "config.json.broken").exists()


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
