"""Configuration groups, validation and atomic persistence.

Nothing in this module names an instrument or a strategy rule: instruments are
data and strategy parameters are an opaque validated mapping.
"""

from __future__ import annotations

import json
import os
import shutil
from datetime import time
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG_PATH = Path("data/config.json")


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _parse_hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


class SessionTemplate(_Model):
    name: str
    timezone: str = "America/New_York"
    open: str = "09:30"
    close: str = "16:00"
    weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4])

    @field_validator("open", "close")
    @classmethod
    def _valid_hhmm(cls, value: str) -> str:
        _parse_hhmm(value)
        return value

    @property
    def open_time(self) -> time:
        return _parse_hhmm(self.open)

    @property
    def close_time(self) -> time:
        return _parse_hhmm(self.close)


class InstrumentConfig(_Model):
    symbol: str
    role: Literal["primary", "context"] = "context"
    enabled: bool = True
    tick_size: float = 0.25
    tick_value: float = 0.5
    point_value: float | None = None
    currency: str = "USD"
    decimals: int = 2
    session_template: str = "RTH"


class InstrumentsConfig(_Model):
    items: list[InstrumentConfig] = Field(
        default_factory=lambda: [InstrumentConfig(symbol="PRIMARY", role="primary")]
    )
    primary: str = "PRIMARY"
    templates: list[SessionTemplate] = Field(
        default_factory=lambda: [SessionTemplate(name="RTH")]
    )

    @model_validator(mode="after")
    def _consistent(self) -> "InstrumentsConfig":
        symbols = [item.symbol for item in self.items]
        if len(symbols) != len(set(symbols)):
            raise ValueError("duplicate instrument symbols")
        if self.primary not in symbols:
            raise ValueError(f"primary {self.primary!r} is not in instruments")
        roles = {item.symbol: item.role for item in self.items}
        if roles[self.primary] != "primary":
            raise ValueError("primary instrument must have role=primary")
        enabled_primary = [i for i in self.items if i.role == "primary" and i.enabled]
        if len(enabled_primary) != 1:
            raise ValueError("exactly one enabled primary instrument is required")
        return self

    def by_symbol(self, symbol: str) -> InstrumentConfig:
        for item in self.items:
            if item.symbol == symbol:
                return item
        raise KeyError(symbol)

    @property
    def enabled(self) -> list[InstrumentConfig]:
        return [item for item in self.items if item.enabled]

    @property
    def symbols(self) -> list[str]:
        return [item.symbol for item in self.items]

    def template_for(self, symbol: str) -> SessionTemplate:
        name = self.by_symbol(symbol).session_template
        for template in self.templates:
            if template.name == name:
                return template
        raise KeyError(f"unknown session template {name!r}")


class StrategyConfig(_Model):
    id: str = "null"
    enabled: bool = True
    version: str = "0.0.0"
    params: dict[str, Any] = Field(default_factory=dict)


class RiskConfig(_Model):
    initial_capital: float = 25000.0
    risk_per_trade_pct: float = 1.0
    max_daily_loss_pct: float = 3.0
    max_daily_profit_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    max_trades_per_day: int = 3
    max_concurrent_positions: int = 1
    max_units_per_trade: int = 5
    max_stop_ticks: int = 200
    trade_window_start: str = "09:00"
    trade_window_end: str = "15:30"
    entry_exclusion_start: str | None = None
    entry_exclusion_end: str | None = None
    close_at_session_end: bool = True
    session_close_time: str = "15:55"
    cooldown_minutes: int = 0
    no_trade_after_consecutive_losses: int = 0

    @field_validator("max_drawdown_pct")
    @classmethod
    def _drawdown_range(cls, value: float) -> float:
        if not 0 <= value <= 100:
            raise ValueError("max_drawdown_pct must be in [0, 100]")
        return value

    @field_validator("risk_per_trade_pct")
    @classmethod
    def _pct_range(cls, value: float) -> float:
        if not 0 < value <= 100:
            raise ValueError("risk_per_trade_pct must be in (0, 100]")
        return value


class ExecutionConfig(_Model):
    commission_per_unit_side: float = 0.62
    slippage_ticks: int = 1
    max_slippage_ticks: int = 4
    fill_model: Literal["next_open", "signal_price", "intrabar"] = "next_open"
    simulate_partial_fills: bool = False
    partial_fill_ratio: float = 0.6


class FeedConfig(_Model):
    provider: Literal["simulated", "csv", "live"] = "simulated"
    csv_path: str = "data/bars.csv"
    replay_speed: float = 2.5
    loop_sessions: bool = False
    start_date: str | None = None
    latency_ms: int = 0


class LiveConfig(_Model):
    broker: str = "none"
    environment: str = "demo"
    account_ref: str | None = None
    data_feed: str | None = None
    live_enabled: bool = False
    live_confirmation: str | None = None
    adapter_implemented: bool = False

    def can_start(self) -> bool:
        return bool(
            self.adapter_implemented
            and self.live_enabled
            and self.live_confirmation
            and self.broker != "none"
        )


class AlertsConfig(_Model):
    """Out-of-band notifications. Off by default: no URL, no traffic."""

    enabled: bool = False
    webhook_url: str | None = None
    min_level: Literal["warn", "error"] = "warn"
    timeout_s: float = 5.0
    max_retries: int = 3
    dedupe_window_s: float = 60.0


class UIConfig(_Model):
    panels: list[str] = Field(
        default_factory=lambda: ["strategy_state", "quotes", "position"]
    )
    theme: Literal["dark", "light"] = "dark"
    locale: str = "es"


class Settings(_Model):
    version: int = 1
    instruments: InstrumentsConfig = Field(default_factory=InstrumentsConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    feed: FeedConfig = Field(default_factory=FeedConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)


def load_settings(path: str | Path | None = None) -> Settings:
    """Load settings, archiving a corrupt file and falling back to defaults."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not target.exists():
        return Settings()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        return Settings.model_validate(raw)
    except (json.JSONDecodeError, ValueError):
        shutil.copy2(target, target.with_suffix(target.suffix + ".broken"))
        return Settings()


def save_settings(settings: Settings, path: str | Path | None = None) -> None:
    """Write settings atomically: temp file in the same directory, then replace."""
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(settings.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    os.replace(tmp, target)


def apply_settings(settings: Settings, patch: dict[str, Any]) -> Settings:
    """Apply a partial, validated patch without mutating the input."""
    merged = settings.model_dump(mode="python")
    for key, value in patch.items():
        if key not in Settings.model_fields:
            raise ValueError(f"unknown settings group {key!r}")
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return Settings.model_validate(merged)
