"""Cruce de medias filtrado por la marea de fondo.

La hipótesis: un cruce solo tiene ventaja si el fondo acompaña. La referencia
compra cruces dentro de tendencias bajistas y vende dentro de alcistas; el
filtro de media larga descarta justo esas operaciones, que son las que
convierten un sistema de tendencia en una máquina de perder.

Sin validar. Su veredicto sale del backtest con split fuera de muestra y de la
puerta de promoción, no de este docstring.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .base import (
    BaseStrategy,
    MarketData,
    Metric,
    Phase,
    Signal,
    StrategyOutput,
    Warmup,
    Zone,
)
from .indicators import atr, sma


class TrendParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast: int = Field(default=9, ge=2, le=200, description="Periodo de la media rápida")
    slow: int = Field(default=21, ge=3, le=500, description="Periodo de la media lenta")
    trend: int = Field(
        default=200, ge=5, le=1000, description="Media larga que define la marea"
    )
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    stop_atr: float = Field(default=1.5, gt=0, le=10, description="Stop en múltiplos de ATR")
    rr: float = Field(default=1.5, gt=0, le=10, description="Objetivo en múltiplos del riesgo")

    @model_validator(mode="after")
    def _ordered_periods(self) -> "TrendParams":
        if self.slow <= self.fast:
            raise ValueError("slow must be greater than fast")
        if self.trend < self.slow:
            raise ValueError("trend must be at least as long as slow")
        return self


class TrendStrategy(BaseStrategy):
    id = "trend"
    name = "Cruce filtrado por tendencia (sin validar)"
    version = "0.1.0"
    params_model = TrendParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = TrendParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.trend, self.params.slow, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        params = self.params
        bars = md.bars.get(md.primary, [])
        needed = max(params.trend, params.slow, params.atr_period) + 2
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
                    "bars": Metric(label="Velas", value=len(bars), format="number", unit="barras")
                },
            )

        closes = [bar.c for bar in bars]
        fast = sma(closes, params.fast)
        slow = sma(closes, params.slow)
        tide = sma(closes, params.trend)
        volatility = atr(bars, params.atr_period)
        if fast is None or slow is None or tide is None or volatility is None:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        previous = (sma(closes[:-1], params.fast), sma(closes[:-1], params.slow))
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

        last = bars[-1]
        tide_value = round(tide, 4)
        bias = "long" if last.c >= tide_value else "short"
        long_ok = crossed_up and last.c >= tide_value
        short_ok = crossed_down and last.c <= tide_value
        side = "long" if long_ok else "short" if short_ok else None
        blocked = (crossed_up or crossed_down) and side is None

        phases.append(
            Phase(
                key="tide",
                label="Marea",
                status="done",
                ts=last.t,
                detail=f"media {params.trend} en {tide_value:.2f}",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Disparo",
                status="active" if side else ("failed" if blocked else "pending"),
                ts=last.t,
                detail=(
                    side
                    if side
                    else "cruce contra la marea"
                    if blocked
                    else "sin cruce"
                ),
            )
        )

        metrics = {
            "fast": Metric(label=f"SMA({params.fast})", value=round(fast, 4), format="price"),
            "slow": Metric(label=f"SMA({params.slow})", value=round(slow, 4), format="price"),
            "trend": Metric(
                label=f"Marea SMA({params.trend})", value=tide_value, format="price"
            ),
            "atr": Metric(
                label=f"ATR({params.atr_period})",
                value=round(volatility, 4),
                format="price",
            ),
            "distance": Metric(
                label="Precio vs marea",
                value=round((last.c / tide_value - 1) * 100, 4) if tide_value else 0.0,
                format="pct",
                tone="good" if last.c >= tide_value else "bad",
            ),
            "spread": Metric(
                label="Separación",
                value=round(fast - slow, 4),
                format="price",
                tone="good" if fast > slow else "bad" if fast < slow else "neutral",
            ),
            "bias": Metric(label="Sesgo", value=bias, format="text", tone="neutral"),
        }

        output = StrategyOutput(
            state="armed" if side else "scanning",
            state_label="Cruce con marea" if side else "Buscando",
            phases=phases,
            metrics=metrics,
        )
        output.zones.append(
            Zone(
                id=f"tide-{md.session.id}",
                kind="line",
                label=f"Marea {params.trend}",
                from_ts=last.t,
                price_low=tide_value,
                price_high=tide_value,
                style={"color": "#58a6ff", "opacity": 0.35},
                active=True,
            )
        )
        if side is None:
            output.zones.append(
                Zone(
                    id=f"band-{md.session.id}",
                    kind="band",
                    label="Rango ATR",
                    from_ts=last.t,
                    price_low=round(last.c - volatility, 4),
                    price_high=round(last.c + volatility, 4),
                    style={"color": "#4c8dff", "opacity": 0.12, "line": "none"},
                    active=True,
                )
            )
            return output

        distance = volatility * params.stop_atr
        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * params.rr if side == "long" else last.c - distance * params.rr
        )
        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"cruce SMA{params.fast}/SMA{params.slow} con marea SMA{params.trend}",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(target_price, 4),
            strength=min(1.0, abs(fast - slow) / volatility) if volatility else None,
        )
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
        return output


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")
