"""Mean reversion against a Bollinger band. Third plugin, opposite logic.

Where the reference and Donchian strategies trade breakouts, this one buys the
stretch below the lower band and sells the stretch above the upper band. It is
here to prove the base holds two contradictory ideas at once without touching
the engine: the pipeline does not care what the strategy believes.

**Not validated.** On a trending synthetic series this is the strategy that gets
run over. The verdict belongs in the ledger.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

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
from .indicators import atr, sma, stdev


class FadeParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: int = Field(default=20, ge=5, le=300, description="Periodo de la media y la banda")
    sigma: float = Field(default=2.0, gt=0, le=6, description="Ancho de la banda en desviaciones")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    stop_atr: float = Field(default=1.0, gt=0, le=10, description="Stop en múltiplos de ATR")
    require_close_inside: bool = Field(
        default=True, description="Exige que la vela cierre de vuelta dentro de la banda"
    )


class FadeStrategy(BaseStrategy):
    id = "fade"
    name = "Reversión a la media con bandas (sin validar)"
    version = "0.1.0"
    params_model = FadeParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = FadeParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.period, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars.get(md.primary, [])
        needed = max(self.params.period, self.params.atr_period) + 2
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

        last = bars[-1]
        closes = [bar.c for bar in bars]
        middle = sma(closes, self.params.period)
        deviation = stdev(closes, self.params.period)
        volatility = atr(bars, self.params.atr_period)
        if (
            middle is None
            or deviation is None
            or deviation <= 0
            or volatility is None
            or volatility <= 0
        ):
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        upper = middle + self.params.sigma * deviation
        lower = middle - self.params.sigma * deviation

        below = last.c < lower
        above = last.c > upper
        if self.params.require_close_inside:
            below = below or last.l < lower  # touched the band...
            above = above or last.h > upper
            inside_below = last.c >= lower
            inside_above = last.c <= upper
            below = below and inside_below
            above = above and inside_above

        side = "long" if below else "short" if above else None

        phases.append(
            Phase(
                key="band",
                label="Banda",
                status="done",
                ts=last.t,
                detail=f"{lower:.2f} – {upper:.2f}",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Reversión",
                status="active" if side else "pending",
                ts=last.t,
                detail=side or "sin extremo",
            )
        )

        zscore = (last.c - middle) / deviation
        metrics = {
            "middle": Metric(label=f"SMA({self.params.period})", value=round(middle, 4), format="price"),
            "upper": Metric(label="Banda superior", value=round(upper, 4), format="price"),
            "lower": Metric(label="Banda inferior", value=round(lower, 4), format="price"),
            "z": Metric(
                label="Z-score",
                value=round(zscore, 2),
                format="ratio",
                tone="bad" if abs(zscore) > self.params.sigma else "good",
            ),
            "atr": Metric(
                label=f"ATR({self.params.atr_period})", value=round(volatility, 4), format="price"
            ),
        }

        output = StrategyOutput(
            state="armed" if side else "scanning",
            state_label="Extremo detectado" if side else "Dentro de la banda",
            phases=phases,
            metrics=metrics,
            zones=[
                Zone(
                    id=f"bands-{md.session.id}",
                    kind="band",
                    label="Bandas",
                    from_ts=last.t,
                    price_low=round(lower, 4),
                    price_high=round(upper, 4),
                    style={"color": "#d29922", "opacity": 0.10, "line": "dashed"},
                    active=True,
                ),
                Zone(
                    id=f"mean-{md.session.id}",
                    kind="line",
                    label="Media",
                    from_ts=last.t,
                    price_low=round(middle, 4),
                    price_high=round(middle, 4),
                    style={"color": "#8b949e", "line": "solid"},
                    active=True,
                ),
            ],
        )
        if side is None:
            return output

        distance = volatility * self.params.stop_atr
        stop_price = last.c - distance if side == "long" else last.c + distance
        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"extremo en banda {self.params.sigma}σ",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(middle, 4),
            strength=min(1.0, abs(zscore) / (self.params.sigma * 2)),
        )
        output.zones.append(
            Zone(
                id=f"risk-{_stamp(last.t)}",
                kind="box",
                label="Riesgo/objetivo",
                from_ts=last.t,
                price_low=min(stop_price, middle),
                price_high=max(stop_price, middle),
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
                label=f"Reversión {side}",
            )
        )
        return output


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")
