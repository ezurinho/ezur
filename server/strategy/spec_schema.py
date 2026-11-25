"""Strategy specification — Pydantic models + JSON Schema validator.

This module is the single source of truth for what a `strategy_spec` looks like.
The runner, the registry API, and the backtest all import from here.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# --------------------------------------------------------------------------- #
# Enums / literals
# --------------------------------------------------------------------------- #

Family = Literal["trend", "breakout", "orb", "mean_reversion", "regime", "momentum"]
Instrument = Literal["BTCUSDT_PERP", "BTCUSDT_SPOT"]
Timeframe = Literal["5m", "15m", "30m", "1h", "2h", "4h", "12h", "1d"]
EntryRule = Literal["donchian_breakout", "ema_state", "zscore_fade", "orb_session"]
FillType = Literal["taker", "maker", "mixed"]
ImpactModel = Literal["none", "sqrt_law", "ofi"]
FundingMode = Literal["real_timestamps", "none"]
SizingMode = Literal["fixed_fractional", "vol_target", "kelly"]
Weighting = Literal["equal", "explicit"]
DatasetName = Literal["klines_5m", "funding_rate"]
Timezone = Literal["UTC"]
SignalBar = Literal["closed"]
FillBar = Literal["next_bar_open"]
IntrabarPriority = Literal["stop_first"]
GapFill = Literal["bar_open"]
PhaseStatus = Literal["pending", "active", "done", "failed", "skipped"]


# --------------------------------------------------------------------------- #
# Base model with forbidden extras
# --------------------------------------------------------------------------- #

class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


# --------------------------------------------------------------------------- #
# Data requirements
# --------------------------------------------------------------------------- #

class Integrity(_StrictModel):
    gaps: int = Field(ge=0)
    duplicates: int = Field(ge=0)
    timezone: Timezone = "UTC"


class DataRequirements(_StrictModel):
    datasets: list[DatasetName] = Field(min_length=1)
    min_coverage: str  # YYYY-MM-DD/YYYY-MM-DD
    integrity: Integrity

    @field_validator("datasets")
    @classmethod
    def _unique_datasets(cls, v: list[DatasetName]) -> list[DatasetName]:
        if len(v) != len(set(v)):
            raise ValueError("datasets must be unique")
        return v

    @field_validator("min_coverage")
    @classmethod
    def _coverage_format(cls, v: str) -> str:
        if not re.match(r"^\d{4}-\d{2}-\d{2}/\d{4}-\d{2}-\d{2}$", v):
            raise ValueError("min_coverage must be YYYY-MM-DD/YYYY-MM-DD")
        return v


# --------------------------------------------------------------------------- #
# Entry / Exit
# --------------------------------------------------------------------------- #

class Entry(_StrictModel):
    rule: EntryRule
    long: str | None = Field(default=None, max_length=200)
    short: str | None = Field(default=None, max_length=200)
    cooldown_bars: int = Field(default=0, ge=0)
    sessions: list[str] = Field(default_factory=list)

    @field_validator("sessions")
    @classmethod
    def _session_format(cls, v: list[str]) -> list[str]:
        for s in v:
            if not re.match(r"^[0-2][0-9]:[0-5][0-9]$", s):
                raise ValueError(f"session '{s}' must be HH:MM (UTC)")
        return v


class Exit(_StrictModel):
    stop: str = Field(max_length=120)
    target: str = Field(max_length=120)
    time_stop_bars: int = Field(ge=1)
    trailing: str | None = None


# --------------------------------------------------------------------------- #
# Params — open but with known keys constrained
# --------------------------------------------------------------------------- #

class Params(_StrictModel):
    atr_k: float = Field(gt=0)
    tp_r: float = Field(gt=0)
    N: int | None = Field(default=None, ge=2)
    fast: int | None = Field(default=None, ge=2)
    slow: int | None = Field(default=None, ge=3)
    z: float | None = Field(default=None, gt=0)
    range_bars: int | None = Field(default=None, ge=1)
    stop_floor_frac: float | None = Field(default=None, ge=0, le=0.2)

    # allow additional numeric/string keys for future rules
    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------- #
# Risk
# --------------------------------------------------------------------------- #

class Risk(_StrictModel):
    sizing: SizingMode
    risk_per_trade: float = Field(gt=0, le=0.05)
    target_vol_annual: float | None = Field(default=None, gt=0, le=3)
    kelly_fraction: float | None = Field(default=None, ge=0, le=0.5)
    max_gross_leverage: float | None = Field(default=None, gt=0)
    max_mdd_budget: float = Field(gt=0, le=1)


# --------------------------------------------------------------------------- #
# Costs
# --------------------------------------------------------------------------- #

class Costs(_StrictModel):
    fee_maker_bps: float = Field(ge=0)
    fee_taker_bps: float = Field(ge=0)
    assumed_fill: FillType
    half_spread_bps: float = Field(ge=0)
    impact_model: ImpactModel
    funding: FundingMode


# --------------------------------------------------------------------------- #
# Execution (fixed by design)
# --------------------------------------------------------------------------- #

class Execution(_StrictModel):
    signal_bar: SignalBar = "closed"
    fill: FillBar = "next_bar_open"
    intrabar_priority: IntrabarPriority = "stop_first"
    gap_fill: GapFill = "bar_open"


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

class Bootstrap(_StrictModel):
    block: int = Field(ge=1)
    reps: int = Field(ge=100)


class WFA(_StrictModel):
    train_years: float | None = Field(default=None, gt=0)
    test_months: int | None = Field(default=None, ge=1)
    min_trades_per_fold: int | None = Field(default=None, ge=1)


class Validation(_StrictModel):
    trials_declared: int = Field(ge=1)
    is_oos_split: str  # "0.60/0.20/0.20"
    wfa: WFA | None = None
    seed: int = Field(ge=0, default=7)
    bootstrap: Bootstrap = Field(default_factory=lambda: Bootstrap(block=5, reps=4000))

    @field_validator("is_oos_split")
    @classmethod
    def _split_sums_to_one(cls, v: str) -> str:
        parts = v.split("/")
        if len(parts) != 3:
            raise ValueError("is_oos_split must be three fractions like '0.60/0.20/0.20'")
        total = sum(float(p) for p in parts)
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"is_oos_split fractions sum to {total:.6f}, must be 1.00")
        return v


# --------------------------------------------------------------------------- #
# Portfolio (optional)
# --------------------------------------------------------------------------- #

class PortfolioComponent(_StrictModel):
    label: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,32}$")
    params: dict[str, int | float] = Field(default_factory=dict)
    weight: float | None = Field(default=None, gt=0, le=1)


class Portfolio(_StrictModel):
    components: list[PortfolioComponent] = Field(min_length=2)
    weighting: Weighting
    rationale: str = Field(min_length=40)

    @model_validator(mode="after")
    def _weights_for_explicit(self) -> "Portfolio":
        if self.weighting == "explicit":
            for c in self.components:
                if c.weight is None:
                    raise ValueError("explicit weighting requires weight on every component")
        return self


# --------------------------------------------------------------------------- #
# Expected / failure modes
# --------------------------------------------------------------------------- #

class Expected(_StrictModel):
    turnover_per_year: float | None = None
    cost_R_per_trade: float | None = None
    capacity_usd: float | None = None


# --------------------------------------------------------------------------- #
# Full Spec
# --------------------------------------------------------------------------- #

class StrategySpec(_StrictModel):
    id: str = Field(pattern=r"^BTC-[A-Z0-9]+(-[A-Z0-9]+)*$")
    name: str = Field(min_length=3, max_length=120)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    parent_version: str | None = Field(default=None, pattern=r"^\d+\.\d+\.\d+$")
    change: str | None = Field(default=None, max_length=400)
    label: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]{1,48}$")
    family: Family
    hypothesis: str = Field(min_length=40)
    instrument: Instrument
    timeframe_signal: Timeframe
    timeframe_context: Timeframe | None = None
    data_requirements: DataRequirements
    entry: Entry
    exit: Exit
    params: Params
    risk: Risk
    costs: Costs
    execution: Execution
    validation: Validation
    portfolio: Portfolio | None = None
    expected: Expected | None = None
    failure_modes: list[str] = Field(default_factory=list)

    # ----------------------------------------------------------------------- #
    # Derived / helpers
    # ----------------------------------------------------------------------- #

    @property
    def spec_hash(self) -> str:
        """Stable hash of the spec as executed (key order and whitespace independent)."""
        import hashlib

        # `model_dump_json` no ordena claves: el hash tenía que pasar por json
        # para seguir siendo estable ante el orden del fichero.
        raw = json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(raw).hexdigest()

    def validate_params_for_rule(self) -> None:
        """Cross-check params against entry.rule."""
        rule = self.entry.rule
        p = self.params
        if rule in ("donchian_breakout", "zscore_fade") and p.N is None:
            raise ValueError(f"rule {rule!r} requires params.N")
        if rule == "ema_state" and (p.fast is None or p.slow is None):
            raise ValueError("rule ema_state requires params.fast and params.slow")
        if rule == "orb_session" and not self.entry.sessions:
            raise ValueError("rule orb_session requires entry.sessions")


# --------------------------------------------------------------------------- #
# Schema loader + validator
# --------------------------------------------------------------------------- #

SCHEMA_PATH = Path(__file__).resolve().parent / "strategy_spec.schema.json"


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_spec(spec: dict[str, Any]) -> list[str]:
    """Minimal JSON Schema 2020-12 validator covering the keywords our schema uses."""
    schema = load_schema()
    errors: list[str] = []

    def _type_ok(value: Any, name: str) -> bool:
        if name == "integer":
            return isinstance(value, int) and not isinstance(value, bool)
        if name == "number":
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        types = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
        py = types.get(name)
        return py is not None and isinstance(value, py)

    def _validate(instance: Any, sch: dict, path: str = "$") -> None:
        if "type" in sch:
            names = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
            if not any(_type_ok(instance, n) for n in names):
                errors.append(f"{path}: expected {'|'.join(names)}, got {type(instance).__name__}")
                return

        if "enum" in sch and instance not in sch["enum"]:
            errors.append(f"{path}: {instance!r} not in {sch['enum']}")

        if isinstance(instance, str):
            if "pattern" in sch and not re.search(sch["pattern"], instance):
                errors.append(f"{path}: {instance!r} does not match {sch['pattern']}")
            if "minLength" in sch and len(instance) < sch["minLength"]:
                errors.append(f"{path}: shorter than {sch['minLength']}")
            if "maxLength" in sch and len(instance) > sch["maxLength"]:
                errors.append(f"{path}: longer than {sch['maxLength']}")

        if isinstance(instance, (int, float)) and not isinstance(instance, bool):
            if "minimum" in sch and instance < sch["minimum"]:
                errors.append(f"{path}: < minimum {sch['minimum']}")
            if "maximum" in sch and instance > sch["maximum"]:
                errors.append(f"{path}: > maximum {sch['maximum']}")
            if "exclusiveMinimum" in sch and instance <= sch["exclusiveMinimum"]:
                errors.append(f"{path}: <= exclusiveMinimum {sch['exclusiveMinimum']}")
            if "exclusiveMaximum" in sch and instance >= sch["exclusiveMaximum"]:
                errors.append(f"{path}: >= exclusiveMaximum {sch['exclusiveMaximum']}")

        if isinstance(instance, dict):
            for key in sch.get("required", []):
                if key not in instance:
                    errors.append(f"{path}: missing required property {key!r}")
            props = sch.get("properties", {})
            extra = sch.get("additionalProperties", True)
            for key, value in instance.items():
                if key in props:
                    _validate(value, props[key], f"{path}.{key}")
                elif extra is False:
                    errors.append(f"{path}: unexpected property {key!r}")
                elif isinstance(extra, dict):
                    _validate(value, extra, f"{path}.{key}")

        if isinstance(instance, list):
            if "minItems" in sch and len(instance) < sch["minItems"]:
                errors.append(f"{path}: fewer than {sch['minItems']} items")
            if sch.get("uniqueItems") and len(set(map(repr, instance))) != len(instance):
                errors.append(f"{path}: items are not unique")
            if isinstance(sch.get("items"), dict):
                for i, item in enumerate(instance):
                    _validate(item, sch["items"], f"{path}[{i}]")

    _validate(spec, schema)
    return errors


def load_spec(path: str | Path) -> StrategySpec:
    """Load and validate a spec file (JSON Schema + Pydantic)."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    schema_errors = validate_spec(data)
    if schema_errors:
        raise ValueError("spec inválida (JSON Schema):\n  " + "\n  ".join(schema_errors))
    spec = StrategySpec.model_validate(data)
    spec.validate_params_for_rule()
    return spec


def spec_path_display(path: Path, root: Path | None = None) -> str:
    resolved = path.resolve()
    if root is None:
        root = Path.cwd()
    try:
        return str(resolved.relative_to(root.resolve()))
    except ValueError:
        return str(resolved)
