"""Multi-session market simulation.

Drives the real engine over deterministic synthetic sessions so the whole
pipeline — warmup, signals, risk, fills, brackets, session resets, statistics —
runs end to end. Synthetic data validates plumbing, never profitability.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from itertools import islice
from pathlib import Path

from .config import Settings
from .db import Store
from .engine import TradingEngine
from .market import synthetic
from .models import Tick
from .gates import evaluate_gates
from .stats import aggregate
from .strategy.registry import resolve_strategy
from .timeutil import session_open_utc


def session_start_utc(settings: Settings, day: date, *, bars_shift: int = 0) -> datetime:
    template = settings.instruments.template_for(settings.instruments.primary)
    return session_open_utc(template, day) + timedelta(minutes=bars_shift)


def trading_days(settings: Settings, count: int, *, end: date | None = None) -> list[date]:
    template = settings.instruments.template_for(settings.instruments.primary)
    cursor = end or date.today()
    days: list[date] = []
    while len(days) < count:
        if cursor.weekday() in template.weekdays:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(days)


def simulated_ticks(
    settings: Settings,
    days: list[date],
    *,
    bars: int = 390,
) -> "list[Tick]":
    symbols = settings.instruments.symbols
    ticks: list[Tick] = []
    for day in days:
        start = session_start_utc(settings, day)
        series = {
            symbol: synthetic.generate_session(
                day.isoformat(),
                symbol,
                start=start,
                bars=bars,
                tick_size=settings.instruments.by_symbol(symbol).tick_size,
            )
            for symbol in symbols
        }
        for index in range(bars):
            ticks.append(
                Tick(
                    ts=series[symbols[0]][index].t,
                    bars={symbol: series[symbol][index] for symbol in symbols},
                )
            )
    return ticks


def run_simulation(
    settings: Settings,
    *,
    days: int = 20,
    bars: int = 390,
    db_path: str | Path | None = None,
    max_ticks: int | None = None,
    measured: dict | None = None,
) -> dict:
    """Run the engine over several sessions and return real statistics.

    ``measured`` carries gate outcomes obtained by re-running (G8 doubled costs,
    G2 determinism); this function itself only measures one pass.
    """
    calendar = trading_days(settings, days)
    store = Store(db_path or ":memory:")
    strategy = resolve_strategy(settings.strategy.id, settings.strategy.params)
    engine = TradingEngine(settings, store, feed=None, strategy=strategy, mode="dry_run")
    try:
        engine.start()
        ticks = simulated_ticks(settings, calendar, bars=bars)
        if max_ticks is not None:
            ticks = ticks[:max_ticks]
        for tick in ticks:
            engine._process(tick)
        trades = store.all_trades()
        stats = aggregate(trades, settings.risk.initial_capital)
        stats["simulation"] = {
            "strategy_id": strategy.id,
            "strategy_version": strategy.version,
            "sessions": len(calendar),
            "bars_per_session": bars,
            "ticks": len(ticks),
            "first_session": calendar[0].isoformat() if calendar else None,
            "last_session": calendar[-1].isoformat() if calendar else None,
            "data_source": "synthetic",
            "note": "Resultados sobre datos sintéticos: validan la infraestructura, no una ventaja.",
        }
        report = evaluate_gates(
            stats,
            initial_capital=settings.risk.initial_capital,
            measured=measured,
        )
        stats["validation"] = report.model_dump(mode="json")
        stats["events"] = len(store.list_events(limit=100_000))
        return stats
    finally:
        store.close()


def measure_simulation_gates(
    settings: Settings,
    base: dict,
    *,
    days: int,
    bars: int,
    multiplier: float = 2.0,
) -> dict:
    """G8 and G2 for a synthetic run: re-run instead of estimating."""
    from .stress import cost_outcome, determinism_outcome, stressed_settings

    repeat = run_simulation(settings, days=days, bars=bars)
    stressed = run_simulation(
        stressed_settings(settings, multiplier), days=days, bars=bars
    )
    deterministic = _result_key(repeat) == _result_key(base)
    return {
        "G8": cost_outcome(base["closed"], stressed["closed"], multiplier),
        "G2": determinism_outcome(deterministic),
    }


def _result_key(result: dict) -> str:
    payload = {
        "closed": result["closed"],
        "by_side": result["by_side"],
        "by_day": result["by_day"],
    }
    return json.dumps(payload, sort_keys=True, default=str)


def _dataset_id(strategy_id: str, days: int, bars: int) -> str:
    """Deterministic identity for a synthetic run: same inputs, same dataset id."""
    payload = f"synthetic|{strategy_id}|{days}|{bars}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulación multi-sesión determinista")
    parser.add_argument("--days", type=int, default=20)
    parser.add_argument("--bars", type=int, default=390)
    parser.add_argument("--strategy", default="reference")
    parser.add_argument("--db", default=":memory:")
    parser.add_argument("--out", default="reports/backtest/simulation.json")
    parser.add_argument("--max-ticks", type=int, default=None)
    parser.add_argument(
        "--ledger",
        default=os.getenv("TERMINAL_EXPERIMENT_LEDGER", "reports/experiments.jsonl"),
        help="Ledger JSONL donde registrar el experimento",
    )
    parser.add_argument(
        "--no-ledger", action="store_true", help="No registrar el experimento"
    )
    parser.add_argument(
        "--no-stress",
        action="store_true",
        help="No re-ejecutar para medir G8 (costes x2) y G2 (determinismo)",
    )
    args = parser.parse_args()

    settings = Settings()
    settings.strategy.id = args.strategy
    settings.strategy.params = {}

    first = run_simulation(
        settings,
        days=args.days,
        bars=args.bars,
        db_path=args.db,
        max_ticks=args.max_ticks,
    )
    measured = None
    if not args.no_stress and args.max_ticks is None:
        measured = measure_simulation_gates(
            settings, first, days=args.days, bars=args.bars
        )
        result = run_simulation(
            settings,
            days=args.days,
            bars=args.bars,
            db_path=args.db,
            max_ticks=args.max_ticks,
            measured=measured,
        )
    else:
        result = first

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")

    experiment_id = None
    if not args.no_ledger:
        from .experiments import record

        experiment_id = record(
            args.ledger,
            kind="simulation",
            strategy_id=settings.strategy.id,
            strategy_version=result["simulation"]["strategy_version"],
            dataset_id=_dataset_id(args.strategy, args.days, args.bars),
            config=settings.model_dump(mode="json"),
            metrics={k: v for k, v in result.items() if k != "trades"},
            verdict=result["validation"]["verdict"],
            notes=f"sintético {args.days}d x {args.bars} velas",
        )["experiment_id"]

    closed = result["closed"]
    print(
        json.dumps(
            {
                "sessions": result["simulation"]["sessions"],
                "ticks": result["simulation"]["ticks"],
                "trades": closed["trades"],
                "wins": closed["wins"],
                "losses": closed["losses"],
                "win_rate": round(closed["win_rate"], 4),
                "profit_factor": round(closed["profit_factor"], 4),
                "expectancy_r": round(closed["expectancy_r"], 4),
                "pnl_net": round(closed["pnl_net"], 2),
                "fees": round(closed["fees"], 2),
                "max_drawdown": round(closed["max_drawdown"], 2),
                "avg_duration_minutes": round(closed["avg_duration_minutes"], 1),
                "verdict": result["validation"]["verdict"],
                "failed_gates": result["validation"]["failed"],
                "not_measured": result["validation"]["not_measured"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
