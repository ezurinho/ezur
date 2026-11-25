"""Domain models.

No instrument name and no strategy concept lives here. Every symbol is a string
key supplied by configuration.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Side = Literal["long", "short"]
EngineStatus = Literal["stopped", "running", "paused", "error"]
RunMode = Literal["backtest", "dry_run", "paper", "live"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Bar(_Model):
    t: datetime
    o: float
    h: float
    l: float
    c: float
    v: float = 0.0


class Tick(_Model):
    ts: datetime
    bars: dict[str, Bar]


class SessionInfo(_Model):
    id: str
    label: str = "session"
    is_open: bool = False
    open_ts: datetime | None = None
    close_ts: datetime | None = None
    phase: Literal["pre", "open", "close", "closed"] = "closed"


class Order(_Model):
    id: str
    symbol: str
    side: Side
    units: int
    kind: Literal["market", "limit"] = "market"
    price: float
    status: Literal["pending", "filled", "cancelled", "rejected"] = "pending"
    created_ts: datetime
    stop_price: float | None = None
    target_price: float | None = None
    signal_key: str = ""


class Position(_Model):
    symbol: str
    side: Side
    units: int
    entry_price: float
    stop_price: float
    target_price: float | None = None
    opened_ts: datetime
    entry_fees: float = 0.0
    entry_slippage: float = 0.0
    signal_key: str = ""


class TradeRecord(_Model):
    id: str | None = None
    symbol: str
    side: Side
    units: int
    entry_price: float
    exit_price: float
    stop_price: float | None = None
    target_price: float | None = None
    opened_ts: datetime
    closed_ts: datetime
    pnl_gross: float = 0.0
    fees: float = 0.0
    pnl_net: float = 0.0
    r_multiple: float = 0.0
    exit_reason: str = ""
    mode: RunMode = "paper"
    signal_key: str = ""
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DayStats(_Model):
    trades: int = 0
    wins: int = 0
    losses: int = 0
    pnl: float = 0.0
    consecutive_losses: int = 0


class PortfolioState(_Model):
    equity: float = 0.0
    peak_equity: float = 0.0
    open_risk: float = 0.0
    # P&L de la posicion abierta, neto de las comisiones de los dos lados.
    unrealized: float = 0.0
    daily_pnl: float = 0.0
    daily_trades: int = 0
    consecutive_losses: int = 0
    last_exit_ts: datetime | None = None
    emergency: bool = False
    has_open_position: bool = False
    has_pending_order: bool = False
    last_price: float | None = None


class RiskDecision(_Model):
    approved: bool
    code: str = ""
    message: str = ""
    units: int = 0
    risk_per_unit: float = 0.0
    # 1.0 = tamaño completo; por debajo, el freno está operando a media máquina.
    size_factor: float = 1.0


class EngineState(_Model):
    status: EngineStatus = "stopped"
    mode: RunMode = "paper"
    session: SessionInfo | None = None
    provider: str = ""
    quality: Literal["ok", "degraded", "stale", "unknown"] = "unknown"
    last_bar_ts: datetime | None = None
    staleness_ms: int = 0
    bars_available: int = 0
    position: Position | None = None
    orders: list[Order] = Field(default_factory=list)
    day_stats: DayStats = Field(default_factory=DayStats)
    equity: float = 0.0
    open_risk: float = 0.0
    unrealized: float = 0.0
    emergency: bool = False
    block_reason: str | None = None
    block_count: int = 0
