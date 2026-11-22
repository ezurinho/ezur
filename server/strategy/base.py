"""Strategy contract.

This module is the only place where a strategy may be described. It defines
WHAT a strategy is allowed to return, never HOW it decides. Infrastructure
imports this module; this module imports nothing from infrastructure.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from ..models import Bar, SessionInfo

PhaseStatus = Literal["pending", "active", "done", "failed", "skipped"]
MetricFormat = Literal[
    "number", "price", "pct", "ratio", "text", "duration", "boolean"
]
MetricTone = Literal["neutral", "good", "bad", "warn"]
ZoneKind = Literal["band", "line", "box", "region"]
MarkerKind = Literal["entry", "exit", "phase", "note", "warning"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Warmup(_Model):
    """Minimum data before ``evaluate`` is meaningful.

    ``bars`` keys are symbols; the key ``"*"`` means every configured
    instrument. The engine refuses to evaluate until the requirement is met.
    """

    bars: dict[str, int] = Field(default_factory=dict)
    session_ready: bool = False


class MarketData(_Model):
    session: SessionInfo
    clock: datetime
    primary: str
    bars: dict[str, list[Bar]]
    params: BaseModel = Field(default_factory=lambda: _Model())
    context: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)


class Signal(_Model):
    key: str
    side: Literal["long", "short"]
    reason: str = ""
    ts: datetime
    stop_price: float
    strength: float | None = None
    valid_until: datetime | None = None
    target_price: float | None = None


class Phase(_Model):
    key: str
    label: str
    status: PhaseStatus = "pending"
    ts: datetime | None = None
    detail: str | None = None


class Zone(_Model):
    id: str
    kind: ZoneKind
    from_ts: datetime
    price_low: float
    price_high: float
    label: str | None = None
    to_ts: datetime | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class Marker(_Model):
    id: str
    ts: datetime
    price: float
    kind: MarkerKind = "note"
    side: Literal["long", "short", "none"] = "none"
    label: str | None = None


class Metric(_Model):
    label: str
    value: float | str | bool | None = None
    format: MetricFormat = "number"
    unit: str | None = None
    tone: MetricTone = "neutral"
    group: str | None = None


class StrategyOutput(_Model):
    state: str = "idle"
    state_label: str = ""
    phases: list[Phase] = Field(default_factory=list)
    signal: Signal | None = None
    rejection: dict[str, str] | None = None
    metrics: dict[str, Metric] = Field(default_factory=dict)
    zones: list[Zone] = Field(default_factory=list)
    markers: list[Marker] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


@runtime_checkable
class BaseStrategy(Protocol):
    id: str
    name: str
    version: str
    params_model: type[BaseModel]

    def warmup_requirements(self) -> Warmup: ...

    def evaluate(self, md: MarketData) -> StrategyOutput: ...
