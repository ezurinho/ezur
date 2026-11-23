"""Backtest runner.

It does not reimplement the engine: it drives the same TradingEngine over a
dataset, so risk, fills, fees and the ambiguous-bar rule are identical to the
paper mode by construction.
"""

from __future__ import annotations

import hashlib
import uuid
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .db import Store
from .engine import TradingEngine
from .market.csv_data import validate_dataset
from .market.feed import CSVFeed
from .models import TradeRecord
from .stats import compute_stats
from .strategy.base import BaseStrategy
from .strategy.registry import resolve_strategy


class BacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    dataset_id: str
    config_hash: str = ""
    run_group: str | None = None
    strategy_id: str
    strategy_version: str
    trades: list[TradeRecord] = Field(default_factory=list)
    equity: list[float] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


@dataclass
class Dataset:
    path: Path
    dataset_id: str
    symbols: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path, symbols: list[str]) -> "Dataset":
        target = Path(path)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return cls(path=target, dataset_id=digest, symbols=list(symbols))


def config_fingerprint(settings: Settings) -> str:
    """Hash of the effective settings: two runs with the same hash are comparable."""
    from .confirmatory import canonical_hash

    return canonical_hash(settings.model_dump(mode="json"))[:16]


def run_backtest(
    settings: Settings,
    dataset_path: str | Path,
    strategy: BaseStrategy | None = None,
    *,
    run_group: str | None = None,
) -> BacktestResult:
    symbols = settings.instruments.symbols
    dataset = Dataset.load(dataset_path, symbols)
    report = validate_dataset(dataset.path, symbols)
    if not report.ok:
        raise ValueError(f"invalid dataset: {[issue.code for issue in report.errors]}")

    engine_strategy = strategy or resolve_strategy(
        settings.strategy.id, settings.strategy.params
    )
    store = Store(":memory:")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=CSVFeed(dataset.path, symbols),
            strategy=engine_strategy,
            mode="backtest",
        )
        engine.start()
        for tick in CSVFeed(dataset.path, symbols).iter_ticks():
            engine._process(tick)
        rows = list(reversed(store.list_trades(limit=1_000_000)))
        equity = [point["equity"] for point in store.equity_curve(limit=1_000_000)]
    finally:
        store.close()

    trades = [TradeRecord.model_validate(_trade_row(row)) for row in rows]
    metrics = compute_stats(trades, initial_equity=settings.risk.initial_capital)
    return BacktestResult(
        # El hash del dataset identifica los datos; el run_id, esta ejecución.
        # Antes eran lo mismo y dos estrategias sobre el mismo CSV no se podían
        # distinguir en un informe.
        run_id=uuid.uuid4().hex[:12],
        dataset_id=dataset.dataset_id,
        config_hash=config_fingerprint(settings),
        run_group=run_group,
        strategy_id=engine_strategy.id,
        strategy_version=engine_strategy.version,
        trades=trades,
        equity=equity,
        metrics=metrics,
        diagnostics={"dataset_sessions": report.sessions, "rows": report.rows},
    )


def _trade_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "symbol": row["symbol"],
        "side": row["side"],
        "units": row["units"],
        "entry_price": row["entry_price"],
        "exit_price": row["exit_price"],
        "stop_price": row["stop_price"],
        "target_price": row["target_price"],
        "opened_ts": row["opened_ts"],
        "closed_ts": row["closed_ts"],
        "pnl_gross": row["pnl_gross"],
        "fees": row["fees"],
        "pnl_net": row["pnl_net"],
        "r_multiple": row["r_multiple"],
        "exit_reason": row["exit_reason"],
        "mode": row["mode"],
        "signal_key": row["signal_key"],
        "diagnostics": json.loads(row["diagnostics"] or "{}"),
    }


def fingerprint(result: BacktestResult) -> str:
    payload = {
        "dataset": result.dataset_id,
        "strategy": (result.strategy_id, result.strategy_version),
        "trades": [trade.model_dump(mode="json") for trade in result.trades],
        "equity": result.equity,
        "metrics": result.metrics,
    }
    return hashlib.sha256(repr(sorted(payload.items())).encode()).hexdigest()
