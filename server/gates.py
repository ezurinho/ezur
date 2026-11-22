"""Validation gates, as data.

The thresholds are configurable and versioned; the verdict is mechanical. A
strategy is not approved because it looks good, and not rejected because the
author feels bad about it: it is evaluated against these rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Verdict = Literal["APROBADA", "RECHAZADA", "INCONCLUSO"]
GateStatus = Literal["pass", "fail", "not_measured"]


class GateThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    min_trades: int = 80
    min_trades_per_side: int = 20
    min_profit_factor: float = 1.25
    min_expectancy_r: float = 0.10
    max_drawdown_pct: float = 2.0
    max_loss_streak: int = 8
    min_bootstrap_low: float = 0.0
    max_top5_share: float = 0.50
    max_ambiguous_pct: float = 5.0


class GateOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    status: GateStatus
    measured: float | None = None
    threshold: str = ""
    detail: str = ""


class GateReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Verdict
    thresholds_version: str
    outcomes: list[GateOutcome] = Field(default_factory=list)
    failed: list[str] = Field(default_factory=list)
    not_measured: list[str] = Field(default_factory=list)


@dataclass
class _Context:
    closed: dict[str, Any]
    by_side: dict[str, dict[str, Any]]
    thresholds: GateThresholds
    initial_capital: float


def _pct(value: float, capital: float) -> float:
    return (value / capital * 100) if capital else 0.0


def _gate_sample(ctx: _Context) -> GateOutcome:
    trades = int(ctx.closed.get("trades", 0))
    sides = {side: int(stats.get("trades", 0)) for side, stats in ctx.by_side.items()}
    smallest = min(sides.values()) if sides else 0
    ok = trades >= ctx.thresholds.min_trades and (
        smallest >= ctx.thresholds.min_trades_per_side
        if sides
        else False
    )
    return GateOutcome(
        id="G4",
        description="Muestra mínima y por dirección",
        status="pass" if ok else "fail",
        measured=float(trades),
        threshold=f">= {ctx.thresholds.min_trades} ops, >= {ctx.thresholds.min_trades_per_side} por dirección",
        detail=f"{trades} ops, mínimo por dirección {smallest}",
    )


def _gate_edge(ctx: _Context) -> GateOutcome:
    pf = float(ctx.closed.get("profit_factor", 0.0))
    expectancy = float(ctx.closed.get("expectancy_r", 0.0))
    ok = pf >= ctx.thresholds.min_profit_factor and expectancy >= ctx.thresholds.min_expectancy_r
    return GateOutcome(
        id="G5",
        description="Profit Factor y expectativa",
        status="pass" if ok else "fail",
        measured=round(expectancy, 4),
        threshold=f"PF >= {ctx.thresholds.min_profit_factor} y expectativa >= {ctx.thresholds.min_expectancy_r} R",
        detail=f"PF {pf:.3f}, expectativa {expectancy:+.3f} R",
    )


def _gate_drawdown(ctx: _Context) -> GateOutcome:
    drawdown = float(ctx.closed.get("max_drawdown", 0.0))
    drawdown_pct = _pct(drawdown, ctx.initial_capital)
    streak = int(ctx.closed.get("max_loss_streak", 0))
    ok = drawdown_pct <= ctx.thresholds.max_drawdown_pct and streak <= ctx.thresholds.max_loss_streak
    return GateOutcome(
        id="G6",
        description="Drawdown y peor racha",
        status="pass" if ok else "fail",
        measured=round(drawdown_pct, 3),
        threshold=f"DD <= {ctx.thresholds.max_drawdown_pct}% y racha <= {ctx.thresholds.max_loss_streak}",
        detail=f"DD {drawdown_pct:.2f}% ({drawdown:.2f}), racha {streak}",
    )


def _gate_concentration(ctx: _Context) -> GateOutcome:
    without_top5 = float(ctx.closed.get("pnl_without_top5", 0.0))
    share = float(ctx.closed.get("top5_share", 0.0))
    ok = without_top5 > 0 and share <= ctx.thresholds.max_top5_share
    return GateOutcome(
        id="G9/G10",
        description="Concentración del beneficio",
        status="pass" if ok else "fail",
        measured=round(share, 4),
        threshold=f"P&L sin top-5 > 0 y top-5 <= {ctx.thresholds.max_top5_share:.0%}",
        detail=f"sin top-5 {without_top5:+.2f}, top-5 {share:.1%}",
    )


def _gate_bootstrap(ctx: _Context) -> GateOutcome:
    low = float(ctx.closed.get("expectancy_ci80_low", 0.0))
    ok = low > ctx.thresholds.min_bootstrap_low
    return GateOutcome(
        id="G11",
        description="Significancia (IC bootstrap 80 %)",
        status="pass" if ok else "fail",
        measured=round(low, 4),
        threshold=f"límite inferior > {ctx.thresholds.min_bootstrap_low}",
        detail=f"IC80 inferior {low:+.4f} R",
    )


def _gate_ambiguous(ctx: _Context) -> GateOutcome:
    trades = int(ctx.closed.get("trades", 0))
    ambiguous = int(ctx.closed.get("ambiguous_trades", 0))
    pct = (ambiguous / trades * 100) if trades else 0.0
    ok = pct <= ctx.thresholds.max_ambiguous_pct
    return GateOutcome(
        id="G13",
        description="Barras ambiguas",
        status="pass" if ok else "fail",
        measured=round(pct, 3),
        threshold=f"<= {ctx.thresholds.max_ambiguous_pct}%",
        detail=f"{ambiguous}/{trades} operaciones ({pct:.2f}%)",
    )


def _gate_not_measured(gate_id: str, description: str, why: str) -> GateOutcome:
    return GateOutcome(
        id=gate_id,
        description=description,
        status="not_measured",
        threshold="requiere datos reales",
        detail=why,
    )


GATE_BUILDERS = (
    _gate_sample,
    _gate_edge,
    _gate_drawdown,
    _gate_concentration,
    _gate_bootstrap,
    _gate_ambiguous,
)


def evaluate_gates(
    aggregate_payload: dict[str, Any],
    *,
    initial_capital: float = 25_000.0,
    thresholds: GateThresholds | None = None,
) -> GateReport:
    """Evaluate the measurable gates and name the ones this run cannot answer."""
    limits = thresholds or GateThresholds()
    context = _Context(
        closed=aggregate_payload.get("closed", {}),
        by_side=aggregate_payload.get("by_side", {}),
        thresholds=limits,
        initial_capital=initial_capital,
    )
    outcomes = [builder(context) for builder in GATE_BUILDERS]
    outcomes.extend(
        [
            _gate_not_measured(
                "G1/G3/G14",
                "Integridad del dataset y de los rolls",
                "requiere dataset real validado y hash reproducible",
            ),
            _gate_not_measured(
                "G8",
                "Costes duplicados",
                "requiere re-ejecución con el doble de comisión y slippage",
            ),
            _gate_not_measured(
                "G2",
                "Determinismo",
                "lo verifica el golden test del backtest, no las estadísticas",
            ),
            _gate_not_measured(
                "H1-H5",
                "Holdout",
                "sellado: solo se abre si todas las puertas de desarrollo pasan",
            ),
        ]
    )

    failed = [outcome.id for outcome in outcomes if outcome.status == "fail"]
    not_measured = [outcome.id for outcome in outcomes if outcome.status == "not_measured"]

    if failed:
        verdict: Verdict = "RECHAZADA"
    elif not_measured:
        verdict = "INCONCLUSO"
    else:
        verdict = "APROBADA"

    return GateReport(
        verdict=verdict,
        thresholds_version=limits.version,
        outcomes=outcomes,
        failed=failed,
        not_measured=not_measured,
    )
