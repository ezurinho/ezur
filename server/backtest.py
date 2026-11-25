"""Backtest runner.

It does not reimplement the engine: it drives the same TradingEngine over a
dataset, so risk, fills, fees and the ambiguous-bar rule are identical to the
paper mode by construction.
"""

from __future__ import annotations

import argparse
import hashlib
import uuid
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .config import Settings
from .db import Store
from .engine import TradingEngine
from .market.csv_data import validate_dataset
from .market.feed import CSVFeed
from .models import TradeRecord
from .promotion import cost_metrics, execution_model
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
        if target.suffix.lower() != ".csv":
            raise ValueError("el dataset debe ser un CSV")
        if target.stat().st_size > 250 * 1024 * 1024:
            raise ValueError("el dataset supera el límite de 250 MB")
        digest = hashlib.sha256()
        with target.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return cls(path=target, dataset_id=digest.hexdigest(), symbols=list(symbols))


# Campos que no pueden mover un P&L. Si entran en el hash, cambiar el tema de
# la interfaz invalida la comparabilidad de dos corridas identicas.
NON_ECONOMIC_SECTIONS = ("ui", "alerts", "live", "promotion")


def config_fingerprint(settings: Settings) -> str:
    """Hash de lo que puede cambiar un resultado, no de todo el perfil.

    El tema, el webhook de alertas o el auto-arranque no tocan una operacion:
    incluirlos hacia que dos corridas comparables dejaran de serlo.
    """
    from .confirmatory import canonical_hash

    payload = settings.model_dump(mode="json")
    for section in NON_ECONOMIC_SECTIONS:
        payload.pop(section, None)
    payload.pop("auto_start", None)
    return canonical_hash(payload)[:16]


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
    open_position = None
    pending_count = 0
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
        rows = list(reversed(store.list_trades(limit=1_000_000, mode="backtest")))
        equity = [point["equity"] for point in store.equity_curve(limit=1_000_000)]
        open_position = engine.execution.position
        pending_count = len(engine.execution.pending_orders())
    finally:
        store.close()

    trades = [TradeRecord.model_validate(_trade_row(row)) for row in rows]
    metrics = compute_stats(
        trades, initial_equity=settings.risk.initial_capital, equity=equity
    )
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
        diagnostics={
            "dataset_sessions": report.sessions,
            "rows": report.rows,
            "rejections": engine.rejection_totals(),
            # La curva es realizada. Si el dataset termina con exposición, el
            # informe lo dice en vez de presentar el último cierre como el final.
            "open_position": open_position.model_dump(mode="json") if open_position else None,
            "pending_orders": pending_count,
            "marked_to_market": False,
        },
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
        "funding": row.get("funding", 0.0),
        "pnl_net": row["pnl_net"],
        "r_multiple": row["r_multiple"],
        "exit_reason": row["exit_reason"],
        "mode": row["mode"],
        "signal_key": row["signal_key"],
        "diagnostics": json.loads(row["diagnostics"] or "{}"),
    }


def main() -> None:
    """Corre una estrategia sobre un CSV con el motor real, desde la terminal.

    Es el mismo `run_backtest` que usa el Laboratorio: si el resultado de aquí y
    el de la UI difieren, es un bug, no dos motores.
    """
    from .config import load_settings
    from .gates import evaluate_gates
    from .stats import aggregate

    parser = argparse.ArgumentParser(description="Backtest sobre un dataset CSV")
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--config", default=None, help="config.json del perfil")
    parser.add_argument("--strategy", default=None, help="id de estrategia")
    parser.add_argument("--params", default=None, help="parámetros en JSON")
    parser.add_argument(
        "--commission-per-unit",
        type=float,
        default=None,
        help="comisión por unidad y lado (moneda de cotización); pisa la del perfil",
    )
    parser.add_argument("--gates", action="store_true", help="evalúa las puertas G4-G13")
    parser.add_argument(
        "--split",
        default=None,
        help="fecha ISO (AAAA-MM-DD): lo cerrado antes es in-sample, lo demás out-of-sample",
    )
    parser.add_argument(
        "--years",
        action="store_true",
        help="desglose por año natural de cierre (un total puede esconder años perdedores)",
    )
    parser.add_argument(
        "--max-stop-ticks",
        type=int,
        default=None,
        help=(
            "tope de stop en ticks para esta corrida; el perfil intradía rechaza "
            "las señales de velas grandes por stop_too_wide"
        ),
    )
    parser.add_argument(
        "--min-stop-ticks",
        type=int,
        default=None,
        help=(
            "mínimo de stop en ticks para esta corrida; recorta la cola de "
            "señales con coste alto (0 = sin filtro)"
        ),
    )
    parser.add_argument("--json", action="store_true", help="imprime el resultado como JSON")
    parser.add_argument("--out", default=None, help="escribe ese JSON en una ruta")
    args = parser.parse_args()

    settings = load_settings(args.config).model_copy(deep=True)
    if args.strategy:
        settings.strategy.id = args.strategy
    if args.params:
        settings.strategy.params = json.loads(args.params)
    if args.commission_per_unit is not None:
        settings.execution.commission_per_unit_side = args.commission_per_unit
    if args.max_stop_ticks is not None:
        settings.risk.max_stop_ticks = args.max_stop_ticks
    if args.min_stop_ticks is not None:
        settings.risk.min_stop_ticks = args.min_stop_ticks

    result = run_backtest(settings, args.dataset)
    primary = settings.instruments.primary
    timezone_name = settings.instruments.template_for(primary).timezone
    stats = aggregate(
        result.trades, settings.risk.initial_capital, timezone_name=timezone_name
    )
    closed = stats["closed"]
    print(f"dataset   {args.dataset}")
    print(f"estrategia {result.strategy_id} v{result.strategy_version}")
    print(f"hash      {result.dataset_id[:16]}  config {result.config_hash}")
    print(
        "ops {trades} · acierto {win:.1%} · PF {pf:.3f} · esperanza {exp:+.3f} R "
        "(IC80 {ci:+.3f}) · P&L {pnl:+.2f} (bruto {gross:+.2f}) · DD {dd:.2f} · "
        "fees {fees:.2f}".format(
            trades=closed.get("trades", 0),
            win=closed.get("win_rate", 0.0),
            pf=closed.get("profit_factor", 0.0),
            exp=closed.get("expectancy_r", 0.0),
            ci=closed.get("expectancy_ci80_low", 0.0),
            pnl=closed.get("pnl_net", 0.0),
            gross=closed.get("pnl_gross", 0.0),
            dd=closed.get("max_drawdown", 0.0),
            fees=closed.get("fees", 0.0),
        )
    )
    if args.years:
        _print_years(result.trades)

    report = None
    if args.gates:
        report = evaluate_gates(stats, initial_capital=settings.risk.initial_capital)
        print(f"veredicto {report.verdict} · falla {', '.join(report.failed) or '—'}")
        for outcome in report.outcomes:
            if outcome.status == "fail":
                print(f"  {outcome.id}: {outcome.detail}")

    _report_run(args, settings, result, stats, report)


def _print_years(trades) -> None:
    """Un año por línea, con bruto y fees: el total agregado puede esconder que
    un solo año carga el resultado y los demás pierden."""
    from .stats import compute_stats

    years: dict[int, list[Any]] = {}
    for trade in trades:
        years.setdefault(trade.closed_ts.year, []).append(trade)
    print("año     ops   PF     IC80 R   neto      bruto     fees")
    for year in sorted(years):
        stats = compute_stats(years[year])
        print(
            f"{year}  {stats['trades']:>5}  {stats['profit_factor']:.3f}  "
            f"{stats['expectancy_ci80_low']:+.3f}  {stats['pnl_net']:+9.2f}  "
            f"{stats['pnl_gross']:+9.2f}  {stats['fees']:8.2f}"
        )


def partition_by_split(trades, cut):
    """Parte por fecha de cierre: antes del corte es in-sample, el resto OOS."""
    inside = [trade for trade in trades if trade.closed_ts < cut]
    outside = [trade for trade in trades if trade.closed_ts >= cut]
    return inside, outside


def _report_run(args, settings, result, stats, report) -> None:
    """Lo que hace falta para juzgar una corrida: rechazos, coste real y IS/OOS.

    Sin esto, una corrida con un stop que rechaza 180 de 181 señales se lee como
    "el bot da una operación" y el número de operaciones no explica nada.
    """
    from .gates import evaluate_gates
    from .stats import aggregate

    closed = stats["closed"]
    budget = settings.risk.initial_capital * settings.risk.risk_per_trade_pct / 100
    execution = execution_model(settings)
    cut = None
    inside: list[TradeRecord] = []
    outside: list[TradeRecord] = []
    if args.split:
        cut = datetime.fromisoformat(args.split)
        if cut.tzinfo is None:
            cut = cut.replace(tzinfo=timezone.utc)
        inside, outside = partition_by_split(result.trades, cut)
    # La puerta mide PF y operaciones fuera de muestra: el coste tiene que
    # medirse sobre la misma muestra, no sobre el total que mezcla IS y OOS.
    cost_trades = outside if args.split else result.trades
    cost = cost_metrics(
        cost_trades,
        execution,
        budget=budget,
        max_units=settings.risk.max_units_per_trade,
    )
    cost_r = cost["cost_per_trade_r"]
    cost_r_simple = cost["cost_per_trade_r_simple"]
    cost_r_nominal = cost["cost_per_trade_r_nominal"]

    rejections = result.diagnostics.get("rejections") or {}
    if rejections:
        detail = ", ".join(f"{code} {count}" for code, count in sorted(rejections.items()))
        print(f"rechazos  {sum(rejections.values())} · {detail}")
        blockers = sum(
            count for code, count in rejections.items()
            if code in {"stop_too_wide", "stop_too_tight", "max_drawdown_reached"}
        )
        if blockers:
            print(
                "  aviso: el perfil bloqueó " f"{blockers} señales antes de operar; "
                "un backtest de validación necesita config/okx-daily.json"
            )
    if cost_r is not None:
        scope = "fuera de muestra" if args.split else "toda la corrida"
        print(
            f"coste     {cost_r:.3f} R ponderado (fees totales / riesgo total, {scope})"
        )
        if cost_r_simple is not None:
            print(
                f"  simple  {cost_r_simple:.3f} R (media por operación; distribución)"
            )
        if cost_r_nominal is not None:
            print(
                f"  nominal {cost_r_nominal:.3f} R "
                f"(fees / ops / presupuesto {budget:.2f})"
            )

    payload = {
        "dataset": str(args.dataset),
        "dataset_id": result.dataset_id,
        "config_hash": result.config_hash,
        "strategy": {"id": result.strategy_id, "version": result.strategy_version},
        "diagnostics": result.diagnostics,
        "metrics": closed,
        "execution": execution,
        "risk_budget": budget,
        "cost_per_trade_r": cost_r,
        "cost_per_trade_r_weighted": cost["cost_per_trade_r_weighted"],
        "cost_per_trade_r_simple": cost_r_simple,
        "cost_per_trade_r_median": cost["cost_per_trade_r_median"],
        "cost_per_trade_r_p90": cost["cost_per_trade_r_p90"],
        "cost_per_trade_r_p99": cost["cost_per_trade_r_p99"],
        "cost_above_1r": cost["cost_above_1r"],
        "cost_above_1r_rate": cost["cost_above_1r_rate"],
        "cost_min": cost["cost_min"],
        "cost_max": cost["cost_max"],
        "cost_per_trade_r_nominal": cost_r_nominal,
        "cost_method": "real_risk" if cost_r is not None else None,
        "cost_metric": "weighted" if cost_r is not None else None,
        "cost_scope": "out_of_sample" if args.split else "all",
        "cost_trades": cost["trades"],
        "avg_risk_per_trade": cost["avg_risk_per_trade"],
        "avg_stop_ticks": cost["avg_stop_ticks"],
        "risk_budget_utilization": cost["risk_budget_utilization"],
        "trades_at_cap": cost["trades_at_cap"],
        "cap_rate": cost["cap_rate"],
        "gates": (
            {"verdict": report.verdict, "failed": report.failed} if report else None
        ),
    }

    if args.split:
        zone = settings.instruments.template_for(settings.instruments.primary).timezone
        blocks = {}
        for name, subset in (("in_sample", inside), ("out_of_sample", outside)):
            subset_stats = aggregate(
                subset, settings.risk.initial_capital, timezone_name=zone
            )
            block = dict(subset_stats["closed"])
            if name == "out_of_sample" and args.gates and subset:
                oos_report = evaluate_gates(
                    subset_stats, initial_capital=settings.risk.initial_capital
                )
                block["verdict"] = oos_report.verdict
                block["failed"] = oos_report.failed
            blocks[name] = block
            print(
                f"{name:<14} {block['trades']:>4} ops · PF {block['profit_factor']:.3f}"
                f" · esperanza {block['expectancy_r']:+.3f} R"
                f" · P&L {block['pnl_net']:+.0f}"
                + (f" · {block['verdict']}" if "verdict" in block else "")
            )
        if blocks["in_sample"]["trades"] and blocks["out_of_sample"]["trades"]:
            base = blocks["in_sample"]["profit_factor"]
            ratio = blocks["out_of_sample"]["profit_factor"] / base if base else 0.0
            print(f"degradación   PF fuera / dentro {ratio:.2f}×")
        payload["split"] = {"at": cut.isoformat(), **blocks}

    document = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if args.json:
        print(document)
    if args.out:
        Path(args.out).write_text(document, encoding="utf-8")


def fingerprint(result: BacktestResult) -> str:
    payload = {
        "dataset": result.dataset_id,
        "strategy": (result.strategy_id, result.strategy_version),
        "trades": [trade.model_dump(mode="json") for trade in result.trades],
        "equity": result.equity,
        "metrics": result.metrics,
    }
    return hashlib.sha256(repr(sorted(payload.items())).encode()).hexdigest()


if __name__ == "__main__":
    main()
