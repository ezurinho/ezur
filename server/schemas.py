"""Snapshot contract v1.

Every field the browser can see is declared here. Adding a field means editing
this module, ``snapshot.py``, ``frontend/src/types.ts`` and a test — in that
order. Removing or renaming a field requires bumping ``SNAPSHOT_VERSION``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SNAPSHOT_VERSION = 1

PhaseStatus = Literal["pending", "active", "done", "failed", "skipped"]
MetricFormat = Literal[
    "number", "price", "pct", "ratio", "text", "duration", "boolean"
]
MetricTone = Literal["neutral", "good", "bad", "warn"]
ZoneKind = Literal["band", "line", "box", "region"]
MarkerKind = Literal["entry", "exit", "phase", "note", "warning"]
SeriesMode = Literal["raw", "normalized", "percent"]
SeriesAxis = Literal["overlay", "secondary"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QuoteModel(_Model):
    last: float | None = None
    bid: float | None = None
    ask: float | None = None
    change: float | None = None
    change_pct: float | None = None
    ts: datetime | None = None


class InstrumentModel(_Model):
    symbol: str
    role: Literal["primary", "context"]
    enabled: bool = True
    tick_size: float
    tick_value: float
    point_value: float | None = None
    currency: str = "USD"
    decimals: int = 2


class PhaseModel(_Model):
    key: str
    label: str
    status: PhaseStatus = "pending"
    ts: datetime | None = None
    detail: str | None = None


class KvEntryModel(_Model):
    label: str
    value: float | str | bool | None = None
    format: MetricFormat = "number"
    unit: str | None = None
    tone: MetricTone = "neutral"
    group: str | None = None


class SignalModel(_Model):
    key: str
    side: Literal["long", "short"]
    strength: float | None = None
    reason: str | None = None
    ts: datetime
    valid_until: datetime | None = None
    stop_price: float
    target_price: float | None = None


class ZoneModel(_Model):
    id: str
    kind: ZoneKind
    from_ts: datetime
    price_low: float
    price_high: float
    label: str | None = None
    to_ts: datetime | None = None
    style: dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    source: Literal["strategy", "engine", "user"] = "strategy"
    meta: dict[str, Any] = Field(default_factory=dict)


class MarkerModel(_Model):
    id: str
    ts: datetime
    price: float
    kind: MarkerKind = "note"
    side: Literal["long", "short", "none"] = "none"
    label: str | None = None
    source: Literal["strategy", "engine", "user"] = "strategy"
    meta: dict[str, Any] = Field(default_factory=dict)


class SeriesValue(_Model):
    t: datetime
    v: float


class SeriesModel(_Model):
    symbol: str
    label: str | None = None
    mode: SeriesMode = "raw"
    axis: SeriesAxis = "overlay"
    visible: bool = True
    values: list[SeriesValue] = Field(default_factory=list)


class CandleModel(_Model):
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


class ChartModel(_Model):
    primary: str
    timeframe: str = "1m"
    timeframes: list[str] = Field(default_factory=lambda: ["1m", "5m", "15m", "30m"])
    candles: list[CandleModel] = Field(default_factory=list)
    series: list[SeriesModel] = Field(default_factory=list)
    zones: list[ZoneModel] = Field(default_factory=list)
    markers: list[MarkerModel] = Field(default_factory=list)


class StrategyBlock(_Model):
    id: str
    name: str
    version: str
    state: str
    state_label: str
    phases: list[PhaseModel] = Field(default_factory=list)
    metrics: dict[str, KvEntryModel] = Field(default_factory=dict)
    signal: SignalModel | None = None
    rejection: dict[str, str] | None = None


class SessionModel(_Model):
    id: str
    label: str
    is_open: bool
    open_ts: datetime | None = None
    close_ts: datetime | None = None
    phase: Literal["pre", "open", "close", "closed"] = "closed"


class DataInfo(_Model):
    provider: str
    quality: Literal["ok", "degraded", "stale", "unknown"] = "unknown"
    last_bar_ts: datetime | None = None
    staleness_ms: int = 0
    bars_available: int = 0


class PositionModel(_Model):
    symbol: str
    side: Literal["long", "short"]
    units: int
    entry_price: float
    stop_price: float
    target_price: float | None = None
    opened_ts: datetime
    unrealized: float | None = None
    r_open: float | None = None


class OrderModel(_Model):
    id: str
    symbol: str
    side: Literal["long", "short"]
    units: int
    kind: Literal["market", "limit"]
    price: float
    status: Literal["pending", "filled", "cancelled", "rejected"]
    created_ts: datetime
    stop_price: float | None = None
    target_price: float | None = None
    signal_key: str = ""


class RiskModel(_Model):
    equity: float
    open_risk: float = 0.0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    blocked: bool = False
    block_reason: str | None = None
    block_count: int = 0
    limits: dict[str, float] = Field(default_factory=dict)


class UIModel(_Model):
    panels: list[str] = Field(default_factory=list)
    theme: Literal["dark", "light"] = "dark"
    locale: str = "es"


class SnapshotData(_Model):
    status: Literal["stopped", "running", "paused", "error"]
    mode: Literal["backtest", "dry_run", "paper", "live"]
    session: SessionModel
    data: DataInfo
    instruments: list[InstrumentModel] = Field(default_factory=list)
    quotes: dict[str, QuoteModel] = Field(default_factory=dict)
    chart: ChartModel
    strategy: StrategyBlock
    position: PositionModel | None = None
    orders: list[OrderModel] = Field(default_factory=list)
    risk: RiskModel
    stats: dict[str, Any] = Field(default_factory=dict)
    day_stats: dict[str, Any] = Field(default_factory=dict)
    settings: dict[str, Any] = Field(default_factory=dict)
    ui: UIModel = Field(default_factory=UIModel)


class Snapshot(_Model):
    type: Literal["snapshot"] = "snapshot"
    v: int = SNAPSHOT_VERSION
    ts: datetime
    data: SnapshotData


class EventMessage(_Model):
    type: Literal["event"] = "event"
    ts: datetime
    data: dict[str, Any]
