"""Gates that need a second run instead of a different statistic.

G8 (doubled costs) and G2 (determinism) cannot be answered from a single
backtest's metrics: they are claims about what happens when the same experiment
is executed again under worse conditions or under identical ones. So they are
measured by re-running, not by estimating.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
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
    clone.execution.commission_pct_side = (
        settings.execution.commission_pct_side * multiplier
    )
    # El modelo en pb sustituye a la comisión explícita: si el perfil lo usa,
    # duplicar sólo la comisión no duplicaría nada.
    clone.execution.fee_maker_bps = settings.execution.fee_maker_bps * multiplier
    clone.execution.fee_taker_bps = settings.execution.fee_taker_bps * multiplier
    clone.execution.half_spread_bps = settings.execution.half_spread_bps * multiplier
    # `slippage_ticks` es un recuento entero: pydantic no revalida al asignar y
    # un 2.0 viajaba hasta el informe como si fuera otra unidad.
    clone.execution.slippage_ticks = max(
        1, round(settings.execution.slippage_ticks * multiplier)
    )
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
    start: datetime | None = None,
    end: datetime | None = None,
    holdout_permit: str | None = None,
) -> StressReport:
    # Las tres corridas son sub-corridas del mismo estudio. Si hay holdout, el
    # permiso lo abre el runner/CLI/API y aquí solo se reutiliza; no se consume
    # una lectura por cada pasada.
    permit_id = (
        holdout_permit
        if isinstance(holdout_permit, str)
        else getattr(holdout_permit, "permit_id", None)
    )
    first = run_backtest(
        settings,
        dataset_path,
        strategy,
        start=start,
        end=end,
        holdout_permit=permit_id,
        holdout_study=True,
    )
    if permit_id is None:
        permit_id = (first.diagnostics.get("holdout") or {}).get("permit_id")
    again = run_backtest(
        settings,
        dataset_path,
        strategy,
        start=start,
        end=end,
        holdout_permit=permit_id,
        holdout_study=True,
    )
    stressed = run_backtest(
        stressed_settings(settings, multiplier),
        dataset_path,
        strategy,
        start=start,
        end=end,
        holdout_permit=permit_id,
        holdout_study=True,
    )
    if holdout_permit is None and permit_id:
        from .holdout import consume_study

        consume_study(
            permit_id,
            {
                "dataset_id": first.dataset_id,
                "strategy": {
                    "id": first.strategy_id,
                    "version": first.strategy_version,
                },
                "stress": {
                    "base": first.metrics,
                    "again": again.metrics,
                    "stressed": stressed.metrics,
                },
            },
        )
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
    start: datetime | None = None,
    end: datetime | None = None,
    holdout_permit: str | None = None,
) -> dict[str, GateOutcome]:
    """G8, G2 and G1/G3/G14 as real outcomes, ready to override the placeholders."""
    from .integrity import measure_integrity

    report = run_stress(
        settings,
        dataset_path,
        strategy,
        multiplier=multiplier,
        start=start,
        end=end,
        holdout_permit=holdout_permit,
    )
    return {
        "G8": cost_outcome(report.base, report.stressed, multiplier),
        "G2": determinism_outcome(report.deterministic),
        "G1/G3/G14": measure_integrity(dataset_path, settings.instruments.symbols),
    }


def aggregate_of(result: BacktestResult, initial_capital: float) -> dict[str, Any]:
    return aggregate(result.trades, initial_capital)
