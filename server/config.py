"""Configuration groups, validation and atomic persistence.

Nothing in this module names an instrument or a strategy rule: instruments are
data and strategy parameters are an opaque validated mapping.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Callable
from datetime import time
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .resample import timeframe_minutes

DEFAULT_CONFIG_PATH = Path("data/config.json")
MIN_TICK_SIZE = 1e-12


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


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

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone {value!r}") from error
        return value

    @field_validator("weekdays")
    @classmethod
    def _valid_weekdays(cls, value: list[int]) -> list[int]:
        if not value or any(day < 0 or day > 6 for day in value):
            raise ValueError("weekdays must contain ISO days 0..6")
        if len(value) != len(set(value)):
            raise ValueError("duplicate weekday")
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
    # Exchange-side identifier; defaults to ``symbol`` when the venue is internal.
    venue_symbol: str | None = None
    enabled: bool = True
    tick_size: float = 0.25
    tick_value: float = 0.5
    lot_size: int = Field(default=1, strict=True)
    min_notional: float | None = None
    contract_size: float | None = None
    point_value: float | None = None
    reference_price: float | None = None
    currency: str = "USD"
    decimals: int = 2
    session_template: str = "RTH"

    @field_validator("tick_size")
    @classmethod
    def _tick_size_range(cls, value: float) -> float:
        if value < MIN_TICK_SIZE:
            raise ValueError(f"tick_size must be at least {MIN_TICK_SIZE}")
        return value

    @field_validator("tick_value", "point_value", "reference_price", "contract_size")
    @classmethod
    def _positive_metadata(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("instrument metadata must be positive")
        return value

    @field_validator("decimals")
    @classmethod
    def _decimals_range(cls, value: int) -> int:
        if not 0 <= value <= 12:
            raise ValueError("decimals must be in [0, 12]")
        return value

    @field_validator("lot_size")
    @classmethod
    def _lot_size_range(cls, value: int) -> int:
        if value < 1:
            raise ValueError("lot_size must be at least 1")
        return value

    @field_validator("min_notional")
    @classmethod
    def _min_notional_range(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("min_notional must be positive")
        return value

    @model_validator(mode="after")
    def _notional_requires_contract_size(self) -> "InstrumentConfig":
        if self.min_notional is not None and self.contract_size is None:
            raise ValueError("min_notional requires an explicit contract_size")
        return self


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
        template_names = [template.name for template in self.templates]
        if len(template_names) != len(set(template_names)):
            raise ValueError("duplicate session template names")
        missing = sorted({item.session_template for item in self.items} - set(template_names))
        if missing:
            raise ValueError(f"unknown session templates: {', '.join(missing)}")
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
    # Lo que ve la estrategia. El motor sigue ejecutando sobre cada vela del
    # feed; esto solo agrega las que lee el plugin. Cambiarlo sin volver a
    # medir no cambia de sistema: los parametros estan en velas de este marco.
    timeframe: str = "1m"
    # Timeframe que ve la estrategia (signal timeframe). Si no se especifica,
    # usa timeframe. Permite ejecutar riesgo/ejecucion en 1m y estrategia en 1h/4h/1d.
    timeframe_signal: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timeframe")
    @classmethod
    def _known_timeframe(cls, value: str) -> str:
        timeframe_minutes(value)
        return value

    @field_validator("timeframe_signal")
    @classmethod
    def _known_timeframe_signal(cls, value: str | None) -> str | None:
        if value is not None:
            timeframe_minutes(value)
        return value


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
    min_stop_ticks: int = 0
    # Peaje de ida y vuelta máximo, en fracción del riesgo de la señal (1 R).
    # 0 lo apaga. Un perfil que opera de verdad lo fija en el límite del
    # estudio (0,25 R); los escenarios sintéticos con costes irreales lo dejan
    # apagado para seguir midiendo la infraestructura.
    max_cost_r: float = 0.0
    trade_window_start: str = "09:00"
    trade_window_end: str = "15:30"
    entry_exclusion_start: str | None = None
    entry_exclusion_end: str | None = None
    close_at_session_end: bool = True
    session_close_time: str = "15:55"
    cooldown_minutes: int = 0
    no_trade_after_consecutive_losses: int = 0
    loss_streak_cooldown_min: int = 0
    soft_brakes: bool = False
    soft_brake_floor: float = 0.25
    soft_brake_halt_multiple: float = 2.0
    # Vol targeting sizing (Barroso & Santa-Clara)
    sizing: Literal["fixed_fractional", "vol_target", "kelly"] = "fixed_fractional"
    target_vol_annual: float | None = Field(default=None, gt=0, le=3)
    max_gross_leverage: float | None = Field(default=None, gt=0)
    max_mdd_budget: float = 0.0
    # Kelly sizing
    kelly_fraction: float = Field(default=0.5, ge=0.0, le=1.0, description="Fracción de Kelly a usar (0.5 = half-Kelly)")

    @field_validator("soft_brake_floor")
    @classmethod
    def _floor_range(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("soft_brake_floor debe estar en (0, 1]")
        return value

    @field_validator("soft_brake_halt_multiple")
    @classmethod
    def _halt_range(cls, value: float) -> float:
        if value < 1:
            raise ValueError("soft_brake_halt_multiple no puede ser menor que 1")
        return value

    @field_validator("loss_streak_cooldown_min")
    @classmethod
    def _cooldown_range(cls, value: int) -> int:
        if value < 0 or value > 1440:
            raise ValueError("loss_streak_cooldown_min debe estar entre 0 y 1440")
        return value

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

    @field_validator(
        "initial_capital",
        "max_daily_loss_pct",
        "max_trades_per_day",
        "max_concurrent_positions",
        "max_units_per_trade",
        "max_stop_ticks",
    )
    @classmethod
    def _positive_limit(cls, value: float | int) -> float | int:
        if value <= 0:
            raise ValueError("risk limits must be positive")
        return value

    @field_validator(
        "max_daily_profit_pct",
        "cooldown_minutes",
        "no_trade_after_consecutive_losses",
        "min_stop_ticks",
        "max_cost_r",
    )
    @classmethod
    def _nonnegative_limit(cls, value: float | int) -> float | int:
        if value < 0:
            raise ValueError("risk limits cannot be negative")
        return value

    @field_validator(
        "trade_window_start",
        "trade_window_end",
        "session_close_time",
        "entry_exclusion_start",
        "entry_exclusion_end",
    )
    @classmethod
    def _valid_clock(cls, value: str | None) -> str | None:
        if value is not None:
            _parse_hhmm(value)
        return value

    @field_validator("target_vol_annual")
    @classmethod
    def _vol_range(cls, value: float | None) -> float | None:
        if value is not None and (value <= 0 or value > 3):
            raise ValueError("target_vol_annual must be in (0, 3]")
        return value

    @field_validator("max_gross_leverage")
    @classmethod
    def _leverage_range(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("max_gross_leverage must be positive")
        return value

    @field_validator("max_mdd_budget")
    @classmethod
    def _mdd_budget_range(cls, value: float) -> float:
        if not 0 <= value <= 1:
            raise ValueError("max_mdd_budget must be in [0, 1]")
        return value


class ExecutionConfig(_Model):
    commission_per_unit_side: float = 0.62
    commission_pct_side: float = 0.0
    slippage_ticks: int = 1
    max_slippage_ticks: int = 4
    fill_model: Literal["next_open", "signal_price"] = "next_open"
    simulate_partial_fills: bool = False
    partial_fill_ratio: float = 0.6
    # Cost model fields (from strategy_spec)
    fee_maker_bps: float = 2.0
    fee_taker_bps: float = 5.0
    half_spread_bps: float = 0.07
    assumed_fill: Literal["taker", "maker", "mixed"] = "taker"
    impact_model: Literal["none", "sqrt_law", "ofi"] = "none"
    funding: Literal["real_timestamps", "none"] = "none"
    cooldown_bars: int = 0
    stop_floor_frac: float = 0.0

    @field_validator("commission_per_unit_side")
    @classmethod
    def _nonnegative_fee(cls, value: float) -> float:
        if value < 0:
            raise ValueError("commission cannot be negative")
        return value

    @field_validator("slippage_ticks", "max_slippage_ticks", "cooldown_bars")
    @classmethod
    def _nonnegative_slippage(cls, value: int) -> int:
        if value < 0:
            raise ValueError("slippage/cooldown cannot be negative")
        return value

    @field_validator("partial_fill_ratio")
    @classmethod
    def _fill_ratio(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("partial_fill_ratio must be in (0, 1]")
        return value

    @field_validator("stop_floor_frac")
    @classmethod
    def _stop_floor_range(cls, value: float) -> float:
        if not 0 <= value <= 0.2:
            raise ValueError("stop_floor_frac must be in [0, 0.2]")
        return value

    @field_validator("fee_maker_bps", "fee_taker_bps", "half_spread_bps")
    @classmethod
    def _nonnegative_cost(cls, value: float) -> float:
        if value < 0:
            raise ValueError("cost cannot be negative")
        return value

    @model_validator(mode="after")
    def _partial_fills_are_not_silently_ignored(self) -> "ExecutionConfig":
        if self.simulate_partial_fills:
            raise ValueError("los fills parciales aún no están implementados")
        return self

    @model_validator(mode="after")
    def _inert_options_are_not_silently_ignored(self) -> "ExecutionConfig":
        # Ningún camino del motor lee estas dos. Aceptar un valor distinto del
        # neutro sería prometer un comportamiento que no existe; fallan al
        # cargar. Se conservan en el modelo porque forman parte del hash con el
        # que la evidencia de promoción firma la configuración.
        if self.funding != "none":
            raise ValueError("funding no está implementado: solo se admite 'none'")
        if self.stop_floor_frac != 0.0:
            raise ValueError("stop_floor_frac no está implementado: solo se admite 0")
        return self


class FeedConfig(_Model):
    provider: Literal["simulated", "csv", "live", "okx"] = "simulated"
    csv_path: str = "data/bars.csv"
    replay_speed: float = 2.5
    loop_sessions: bool = False
    start_date: str | None = None
    latency_ms: int = 0
    poll_interval_s: float = 5.0
    backfill_bars: int = 240


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


class PromotionConfig(_Model):
    """La puerta de promoción del estudio, aplicada antes de arrancar.

    Apagada por defecto: activarla es una decisión del perfil, no del código.
    Con `mode="block"` una configuración sin promoción no arranca; con
    `mode="reduce"` arranca con el riesgo por operación multiplicado por
    `size_factor`, para seguir midiendo sin sangrar a tamaño completo.
    """

    required: bool = False
    mode: Literal["block", "reduce"] = "block"
    size_factor: float = 0.25
    evidence: str | None = None
    stress_evidence: str | None = None
    cycle: str | None = None

    @field_validator("size_factor")
    @classmethod
    def _factor_range(cls, value: float) -> float:
        if not 0 < value <= 1:
            raise ValueError("size_factor debe estar en (0, 1]")
        return value


class Settings(_Model):
    version: Literal[1] = 1
    instruments: InstrumentsConfig = Field(default_factory=InstrumentsConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    promotion: PromotionConfig = Field(default_factory=PromotionConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    feed: FeedConfig = Field(default_factory=FeedConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    # The engine runs by itself on boot. A terminal that needs a human to press
    # "start" every morning is a toy; this is the default and the UI says so.
    auto_start: bool = True


def load_settings(
    path: str | Path | None = None,
    *,
    on_error: Callable[[str], None] | None = None,
) -> Settings:
    """Load settings, archiving a corrupt file and falling back to a stopped profile.

    El respaldo mantiene la interfaz en pie, pero es un perfil distinto: quien
    llame puede pasarse ``on_error`` para dejar constancia en vez de que el
    arranque parezca normal. Sin configuración válida el motor no arranca solo.
    """
    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not target.exists():
        # Primer arranque sin perfil: la UI puede funcionar, pero el motor no
        # arranca con límites que nadie ha confirmado.
        return Settings(auto_start=False)
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
        execution = raw.get("execution") if isinstance(raw, dict) else None
        if isinstance(execution, dict) and execution.get("fill_model") == "intrabar":
            # Alias histórico: tenía el mismo comportamiento que next_open.
            execution["fill_model"] = "next_open"
        return Settings.model_validate(raw)
    except (json.JSONDecodeError, ValueError) as error:
        shutil.copy2(target, target.with_suffix(target.suffix + ".broken"))
        if on_error is not None:
            on_error(f"config inválida en {target}: {error}")
        return Settings(auto_start=False)


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
