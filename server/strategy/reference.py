"""Reference strategy.

It exists to exercise the whole pipeline end to end: phases, metrics, zones,
markers, signals, risk, execution and statistics. It is a moving-average
crossover with an ATR stop, and it is **not** validated and **not** an edge.

Anything it earns on synthetic data says nothing about live performance. Its
purpose is to prove the infrastructure works, not to make money.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..models import Bar
from .base import (
    BaseStrategy,
    MarketData,
    Marker,
    Metric,
    Phase,
    Signal,
    StrategyOutput,
    Warmup,
    Zone,
)


class ReferenceParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast: int = Field(default=9, ge=2, le=200, description="Periodo de la media rápida")
    slow: int = Field(default=21, ge=3, le=500, description="Periodo de la media lenta")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    stop_atr: float = Field(default=1.5, gt=0, le=10, description="Stop en múltiplos de ATR")
    rr: float = Field(default=1.5, gt=0, le=10, description="Objetivo en múltiplos del riesgo")

    @model_validator(mode="after")
    def _ordered_periods(self) -> "ReferenceParams":
        if self.slow <= self.fast:
            raise ValueError("slow must be greater than fast")
        return self


def sma(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def atr(bars: list[Bar], period: int) -> float | None:
    if len(bars) < period + 1:
        return None
    ranges: list[float] = []
    for previous, current in zip(bars[-period - 1 : -1], bars[-period:]):
        ranges.append(
            max(
                current.h - current.l,
                abs(current.h - previous.c),
                abs(current.l - previous.c),
            )
        )
    return sum(ranges) / len(ranges)


class ReferenceStrategy(BaseStrategy):
    id = "reference"
    name = "Referencia (sin validar)"
    version = "0.1.0"
    params_model = ReferenceParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = ReferenceParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.slow, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars.get(md.primary, [])
        needed = max(self.params.slow, self.params.atr_period) + 2
        fast_period = self.params.fast
        slow_period = self.params.slow

        phases = [
            Phase(
                key="warmup",
                label="Calentamiento",
                status="done" if len(bars) >= needed else "active",
                ts=bars[-1].t if bars else None,
                detail=f"{len(bars)}/{needed} velas",
            )
        ]

        if len(bars) < needed:
            return StrategyOutput(
                state="warmup",
                state_label="Calentando",
                phases=phases,
                metrics={
                    "bars": Metric(
                        label="Velas", value=len(bars), format="number", unit="barras"
                    )
                },
            )

        closes = [bar.c for bar in bars]
        fast = sma(closes, fast_period)
        slow = sma(closes, slow_period)
        volatility = atr(bars, self.params.atr_period)
        if fast is None or slow is None or volatility is None or volatility <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        previous = (sma(closes[:-1], fast_period), sma(closes[:-1], slow_period))
        crossed_up = (
            previous[0] is not None
            and previous[1] is not None
            and previous[0] <= previous[1]
            and fast > slow
        )
        crossed_down = (
            previous[0] is not None
            and previous[1] is not None
            and previous[0] >= previous[1]
            and fast < slow
        )

        bias = "long" if fast > slow else "short" if fast < slow else "flat"
        phases.append(
            Phase(
                key="bias",
                label="Sesgo",
                status="done",
                ts=bars[-1].t,
                detail=f"{bias} ({fast:.2f} vs {slow:.2f})",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Disparo",
                status="active" if (crossed_up or crossed_down) else "pending",
                ts=bars[-1].t,
                detail="cruce" if (crossed_up or crossed_down) else "sin cruce",
            )
        )

        last = bars[-1]
        metrics = {
            "fast": Metric(label=f"SMA({fast_period})", value=round(fast, 4), format="price"),
            "slow": Metric(label=f"SMA({slow_period})", value=round(slow, 4), format="price"),
            "atr": Metric(
                label=f"ATR({self.params.atr_period})",
                value=round(volatility, 4),
                format="price",
            ),
            "spread": Metric(
                label="Separación",
                value=round(fast - slow, 4),
                format="price",
                tone="good" if fast > slow else "bad" if fast < slow else "neutral",
            ),
            "bias": Metric(
                label="Sesgo", value=bias, format="text", tone="neutral"
            ),
        }

        output = StrategyOutput(
            state="armed" if (crossed_up or crossed_down) else "scanning",
            state_label="Señal lista" if (crossed_up or crossed_down) else "Buscando",
            phases=phases,
            metrics=metrics,
        )

        if not (crossed_up or crossed_down):
            output.zones.append(
                Zone(
                    id=f"band-{md.session.id}",
                    kind="band",
                    label="Rango ATR",
                    from_ts=bars[-1].t,
                    price_low=round(last.c - volatility, 4),
                    price_high=round(last.c + volatility, 4),
                    style={"color": "#4c8dff", "opacity": 0.12, "line": "none"},
                    active=True,
                )
            )
            return output

        side = "long" if crossed_up else "short"
        distance = volatility * self.params.stop_atr
        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.rr
            if side == "long"
            else last.c - distance * self.params.rr
        )
        signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"cruce SMA{fast_period}/SMA{slow_period}",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(target_price, 4),
            strength=min(1.0, abs(fast - slow) / volatility) if volatility else None,
        )
        output.signal = signal
        output.zones.append(
            Zone(
                id=f"risk-{_stamp(last.t)}",
                kind="box",
                label="Riesgo/objetivo",
                from_ts=last.t,
                price_low=min(stop_price, target_price),
                price_high=max(stop_price, target_price),
                style={"color": "#2ea043" if side == "long" else "#f85149", "opacity": 0.1},
                active=True,
            )
        )
        output.markers.append(
            Marker(
                id=f"marker-{_stamp(last.t)}",
                ts=last.t,
                price=last.c,
                kind="entry",
                side=side,
                label=f"Señal {side}",
            )
        )
        return output


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")
