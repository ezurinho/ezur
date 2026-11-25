"""Z-Score Fade (Mean Reversion) strategy.

Hypothesis: when price deviates significantly from its rolling mean (measured
in standard deviations), it tends to revert. Entry on z-score threshold,
stop at ATR multiple, target at R.
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
from .indicators import atr


class ZScoreParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    N: int = Field(default=20, ge=5, le=500, description="Ventana para media/desviación")
    z: float = Field(default=2.0, gt=0, le=5, description="Umbral de z-score para entrada")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    stop_atr: float = Field(default=1.0, gt=0, le=10, description="Stop en múltiplos de ATR")
    rr: float = Field(default=2.0, gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    stop_floor_frac: float = Field(
        default=0.0, ge=0, le=0.2, description="Suelo del stop como fracción del precio"
    )


class ZScoreStrategy(BaseStrategy):
    id = "zscore_fade"
    name = "Fade por Z-Score (sin validar)"
    version = "0.1.0"
    params_model = ZScoreParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = ZScoreParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.N, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars.get(md.primary, [])
        needed = max(self.params.N, self.params.atr_period) + 2
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
                metrics={"bars": Metric(label="Velas", value=len(bars), format="number", unit="barras")},
            )

        closes = [bar.c for bar in bars]
        atr_val = atr(bars, self.params.atr_period)

        if atr_val is None or atr_val <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        last = bars[-1]
        history = closes[:-1]

        # Rolling mean and std
        import statistics
        window = history[-self.params.N:]
        ma = statistics.mean(window)
        sd = statistics.stdev(window) if len(window) > 1 else 0

        if sd <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        z_score = (last.c - ma) / sd
        faded_up = z_score > self.params.z
        faded_down = z_score < -self.params.z
        side = "short" if faded_up else "long" if faded_down else None

        phases.append(
            Phase(
                key="levels",
                label="Niveles",
                status="done",
                ts=last.t,
                detail=f"MA={ma:.2f} SD={sd:.2f} z={z_score:.2f}",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Fade",
                status="active" if side else "pending",
                ts=last.t,
                detail=side or f"z={z_score:.2f} dentro de banda",
            )
        )

        metrics = {
            "mean": Metric(label=f"MA({self.params.N})", value=round(ma, 4), format="price"),
            "std": Metric(label=f"SD({self.params.N})", value=round(sd, 4), format="number"),
            "z_score": Metric(
                label="Z-Score",
                value=round(z_score, 3),
                format="number",
                tone="good" if abs(z_score) >= self.params.z else "neutral",
            ),
            "threshold": Metric(
                label=f"Umbral z={self.params.z}",
                value=self.params.z,
                format="number",
            ),
            "atr": Metric(
                label=f"ATR({self.params.atr_period})",
                value=round(atr_val, 4),
                format="price",
            ),
        }

        output = StrategyOutput(
            state="armed" if side else "scanning",
            state_label="Fade detectado" if side else "Esperando desviación",
            phases=phases,
            metrics=metrics,
            zones=[
                Zone(
                    id=f"zscore-band-{md.session.id}",
                    kind="band",
                    label=f"Banda ±{self.params.z}σ",
                    from_ts=last.t,
                    price_low=round(ma - self.params.z * sd, 4),
                    price_high=round(ma + self.params.z * sd, 4),
                    style={"color": "#a371f7", "opacity": 0.10, "line": "dashed"},
                    active=True,
                ),
                Zone(
                    id=f"zscore-mean-{md.session.id}",
                    kind="line",
                    label=f"MA({self.params.N})",
                    from_ts=last.t,
                    price_low=round(ma, 4),
                    price_high=round(ma, 4),
                    style={"color": "#a371f7", "opacity": 0.5},
                    active=True,
                ),
            ],
        )

        if side is None:
            return output

        distance = atr_val * self.params.stop_atr
        floor = self.params.stop_floor_frac * last.c if self.params.stop_floor_frac else 0
        distance = max(distance, floor)

        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.rr if side == "long" else last.c - distance * self.params.rr
        )

        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"z-score fade {z_score:.2f}",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(target_price, 4),
            strength=min(1.0, abs(z_score) / self.params.z),
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
        output.markers.append(
            Marker(
                id=f"marker-{_stamp(last.t)}",
                ts=last.t,
                price=last.c,
                kind="entry",
                side=side,
                label=f"Fade {side}",
            )
        )
        return output


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


# Import Marker
from .base import Marker  # noqa: E402