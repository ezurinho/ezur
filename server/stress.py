"""Gates that need a second run instead of a different statistic.

G8 (doubled costs) and G2 (determinism) cannot be answered from a single
backtest's metrics: they are claims about what happens when the same experiment
is executed again under worse conditions or under identical ones. So they are
measured by re-running, not by estimating.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backtest import BacktestResult, fingerprint, run_backtest
from .config import Settings
from .gates import GateOutcome
from .stats import aggregate
from .strategy.base import BaseStrategy


@dataclass
class StressReport:
    base: dict[str, Any]
    stressed: dict[str, Any]
    multiplier: float
    deterministic: bool


def stressed_settings(settings: Settings, multiplier: float = 2.0) -> Settings:
    """Same configuration with commission and slippage multiplied."""
    clone = settings.model_copy(deep=True)
    clone.execution.commission_per_unit_side = (
        settings.execution.commission_per_unit_side * multiplier
    )
    clone.execution.slippage_ticks = settings.execution.slippage_ticks * multiplier
    clone.execution.max_slippage_ticks = max(
        settings.execution.max_slippage_ticks,
        clone.execution.slippage_ticks,
    )
    return clone


def run_stress(
    settings: Settings,
    dataset_path: str | Path,
    strategy: BaseStrategy | None = None,
    *,
    multiplier: float = 2.0,
) -> StressReport:
    first = run_backtest(settings, dataset_path, strategy)
    again = run_backtest(settings, dataset_path, strategy)
    stressed = run_backtest(stressed_settings(settings, multiplier), dataset_path, strategy)
    return StressReport(
        base=first.metrics,
        stressed=stressed.metrics,
        multiplier=multiplier,
        deterministic=fingerprint(first) == fingerprint(again),
    )


def cost_outcome(
    base: dict[str, Any], stressed: dict[str, Any], multiplier: float = 2.0
) -> GateOutcome:
    """G8: the edge must survive doubled commission and slippage."""
    expectancy = float(stressed.get("expectancy_r", 0.0))
    profit_factor = float(stressed.get("profit_factor", 0.0))
    base_expectancy = float(base.get("expectancy_r", 0.0))
    ok = expectancy > 0 and profit_factor >= 1.0
    return GateOutcome(
        id="G8",
        description="Costes duplicados",
        status="pass" if ok else "fail",
        measured=round(expectancy, 4),
        threshold=f"PF >= 1.0 y expectativa > 0 con costes x{multiplier:g}",
        detail=(
            f"expectativa {base_expectancy:+.3f} R -> {expectancy:+.3f} R "
            f"(PF {profit_factor:.3f}, costes x{multiplier:g})"
        ),
    )


def determinism_outcome(deterministic: bool) -> GateOutcome:
    return GateOutcome(
        id="G2",
        description="Determinismo",
        status="pass" if deterministic else "fail",
        threshold="dos ejecuciones, mismo fingerprint",
        detail="fingerprints idénticos" if deterministic else "dos ejecuciones difieren",
    )


def measure_gates(
    settings: Settings,
    dataset_path: str | Path,
    strategy: BaseStrategy | None = None,
    *,
    multiplier: float = 2.0,
) -> dict[str, GateOutcome]:
    """G8 and G2 as real outcomes, ready to override the placeholders."""
    report = run_stress(settings, dataset_path, strategy, multiplier=multiplier)
    return {
        "G8": cost_outcome(report.base, report.stressed, multiplier),
        "G2": determinism_outcome(report.deterministic),
    }


def aggregate_of(result: BacktestResult, initial_capital: float) -> dict[str, Any]:
    return aggregate(result.trades, initial_capital)
