"""Walk-forward evaluation over development windows.

The protocol splits development into consecutive windows W1..W6. A single
backtest answers "did this parameter set work once"; a walk-forward answers "did
it keep working", which is the only question that matters before a holdout.

This module reports. It does **not** pick a winner: the caller reads the table
and the holdout is sealed by a human decision, not by an argmax over synthetic
data.
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Iterable, Sequence

from .config import Settings
from .experiments import DEFAULT_LEDGER, record
from .simulation import run_simulation, trading_days


@dataclass
class WindowRun:
    window: int
    params: dict[str, Any]
    trades: int
    expectancy_r: float
    profit_factor: float
    pnl_net: float
    max_drawdown: float
    verdict: str
    first_day: str
    last_day: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "window": self.window,
            "params": self.params,
            "trades": self.trades,
            "expectancy_r": self.expectancy_r,
            "profit_factor": self.profit_factor,
            "pnl_net": self.pnl_net,
            "max_drawdown": self.max_drawdown,
            "verdict": self.verdict,
            "first_day": self.first_day,
            "last_day": self.last_day,
        }


@dataclass
class Combination:
    params: dict[str, Any]
    runs: list[WindowRun] = field(default_factory=list)

    @property
    def windows_run(self) -> int:
        return len(self.runs)

    @property
    def positive_windows(self) -> int:
        return sum(1 for run in self.runs if run.pnl_net > 0)

    @property
    def mean_expectancy(self) -> float:
        if not self.runs:
            return 0.0
        return sum(run.expectancy_r for run in self.runs) / len(self.runs)

    @property
    def worst_window(self) -> float:
        return min((run.pnl_net for run in self.runs), default=0.0)

    @property
    def total_trades(self) -> int:
        return sum(run.trades for run in self.runs)

    def as_dict(self) -> dict[str, Any]:
        return {
            "params": self.params,
            "windows": self.windows_run,
            "trades": self.total_trades,
            "mean_expectancy_r": round(self.mean_expectancy, 4),
            "worst_window_pnl": round(self.worst_window, 2),
            "consistency": round(self.positive_windows / self.windows_run, 3)
            if self.windows_run
            else 0.0,
            "runs": [run.as_dict() for run in self.runs],
        }


def grid_combinations(grid: dict[str, Sequence[Any]]) -> list[dict[str, Any]]:
    """Cartesian product of the grid, or one empty combination if it is empty."""
    if not grid:
        return [{}]
    keys = sorted(grid)
    return [
        dict(zip(keys, values))
        for values in itertools.product(*(list(grid[key]) for key in keys))
    ]


def split_windows(days: Sequence[date], count: int) -> list[list[date]]:
    if count <= 0:
        raise ValueError("windows must be positive")
    if len(days) < count:
        raise ValueError("not enough trading days for the requested windows")
    size = len(days) // count
    windows = [list(days[index * size : (index + 1) * size]) for index in range(count)]
    # Any remainder goes into the last window so no day is silently dropped.
    windows[-1].extend(days[count * size :])
    return windows


def run_walk_forward(
    settings: Settings,
    *,
    strategy_id: str | None = None,
    grid: dict[str, Sequence[Any]] | None = None,
    windows: int = 3,
    days_per_window: int = 10,
    bars: int = 390,
    ledger: str | Path | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Run every combination over every window and return the full table."""
    target_id = strategy_id or settings.strategy.id
    calendar = trading_days(settings, windows * days_per_window, end=end)
    chunks = split_windows(calendar, windows)
    combinations = [Combination(params=params) for params in grid_combinations(grid or {})]
    recorded: list[str] = []

    for index, chunk in enumerate(chunks):
        for combination in combinations:
            config = settings.model_copy(deep=True)
            config.strategy.id = target_id
            config.strategy.params = dict(combination.params)
            stats = run_simulation(
                config,
                days=len(chunk),
                bars=bars,
                calendar_days=chunk,
            )
            closed = stats["closed"]
            combination.runs.append(
                WindowRun(
                    window=index + 1,
                    params=dict(combination.params),
                    trades=int(closed["trades"]),
                    expectancy_r=round(float(closed["expectancy_r"]), 4),
                    profit_factor=round(float(closed["profit_factor"]), 4),
                    pnl_net=round(float(closed["pnl_net"]), 2),
                    max_drawdown=round(float(closed["max_drawdown"]), 2),
                    verdict=str(stats["validation"]["verdict"]),
                    first_day=chunk[0].isoformat(),
                    last_day=chunk[-1].isoformat(),
                )
            )
            if ledger:
                entry = record(
                    ledger,
                    kind="walkforward",
                    strategy_id=target_id,
                    strategy_version=str(stats["simulation"]["strategy_version"]),
                    dataset_id=_window_id(target_id, chunk, bars),
                    config=config.model_dump(mode="json"),
                    metrics={
                        "window": index + 1,
                        "closed": closed,
                    },
                    verdict=str(stats["validation"]["verdict"]),
                    notes=f"ventana W{index + 1} {chunk[0]}..{chunk[-1]}",
                )
                recorded.append(entry["experiment_id"])

    ranked = sorted(
        combinations,
        key=lambda item: (item.mean_expectancy, item.worst_window),
        reverse=True,
    )
    return {
        "strategy": target_id,
        "windows": [
            {
                "window": index + 1,
                "days": len(chunk),
                "first_day": chunk[0].isoformat(),
                "last_day": chunk[-1].isoformat(),
            }
            for index, chunk in enumerate(chunks)
        ],
        "combinations": [item.as_dict() for item in combinations],
        "ranking": [item.params for item in ranked],
        "note": (
            "La tabla no elige ganador. Un máximo sobre datos de desarrollo no es "
            "evidencia: el holdout se sella y se abre una vez."
        ),
        "experiments": recorded,
    }


def _window_id(strategy_id: str, chunk: Sequence[date], bars: int) -> str:
    import hashlib

    payload = f"walkforward|{strategy_id}|{chunk[0]}..{chunk[-1]}|{bars}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def format_report(report: dict[str, Any]) -> str:
    lines = [f"Walk-forward {report['strategy']}", ""]
    lines.append("Ventanas:")
    for window in report["windows"]:
        lines.append(
            f"  W{window['window']}: {window['first_day']} .. {window['last_day']} ({window['days']} sesiones)"
        )
    lines.append("")
    lines.append("PARÁMETROS                          VENTANAS  OPS   EXP MEDIA  PEOR P&L  CONSIST.")
    for combination in report["combinations"]:
        params = json.dumps(combination["params"], sort_keys=True)
        lines.append(
            "  ".join(
                [
                    params[:34].ljust(34),
                    str(combination["windows"]).rjust(8),
                    str(combination["trades"]).rjust(4),
                    f"{combination['mean_expectancy_r']:+.4f}".rjust(10),
                    f"{combination['worst_window_pnl']:+.2f}".rjust(10),
                    f"{combination['consistency']:.0%}".rjust(8),
                ]
            )
        )
    lines.append("")
    lines.append(report["note"])
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Walk-forward sobre ventanas de desarrollo")
    parser.add_argument("--strategy", default="reference")
    parser.add_argument(
        "--grid",
        default="",
        help="pares clave=a,b,c separados por punto y coma, p.ej. channel=10,20",
    )
    parser.add_argument("--windows", type=int, default=3)
    parser.add_argument("--days", type=int, default=10, help="sesiones por ventana")
    parser.add_argument("--bars", type=int, default=390)
    parser.add_argument("--out", default="reports/backtest/walkforward.json")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--no-ledger", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    stream = getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

    grid = _parse_grid(args.grid)
    settings = Settings()
    report = run_walk_forward(
        settings,
        strategy_id=args.strategy,
        grid=grid,
        windows=args.windows,
        days_per_window=args.days,
        bars=args.bars,
        ledger=None if args.no_ledger else args.ledger,
    )

    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))
        print(f"\nGuardado en {target}")
    return 0


def _parse_grid(text: str) -> dict[str, list[Any]]:
    grid: dict[str, list[Any]] = {}
    for chunk in text.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise SystemExit(f"grid inválido: {chunk!r} (usa clave=a,b,c)")
        key, values = chunk.split("=", 1)
        parsed: list[Any] = []
        for value in values.split(","):
            value = value.strip()
            if not value:
                continue
            try:
                parsed.append(int(value))
            except ValueError:
                try:
                    parsed.append(float(value))
                except ValueError:
                    parsed.append(value)
        if not parsed:
            raise SystemExit(f"grid sin valores: {key!r}")
        grid[key.strip()] = parsed
    return grid


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
