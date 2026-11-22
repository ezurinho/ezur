"""Donchian breakout. Second plugin, written only against the strategy contract.

It exists to prove the point of the base repository: a completely different idea
(breakout of a price channel, no moving-average crossover) plugs in by adding one
file and one registry line, with zero changes to the engine, the snapshot, the
API or the UI.

**Not validated.** It is expected to lose money on synthetic random data, exactly
like the reference strategy. Its verdict belongs in the experiment ledger, not in
a pitch.
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
from .indicators import atr, highest, lowest


class DonchianParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: int = Field(default=20, ge=5, le=300, description="Velas del canal")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    stop_atr: float = Field(default=1.2, gt=0, le=10, description="Stop en múltiplos de ATR")
    rr: float = Field(default=2.0, gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    buffer_ticks: float = Field(
        default=0.0, ge=0, le=20, description="Margen extra sobre el extremo del canal"
    )


class DonchianStrategy(BaseStrategy):
    id = "donchian"
    name = "Ruptura de canal Donchian (sin validar)"
    version = "0.1.0"
    params_model = DonchianParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = DonchianParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.channel, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars.get(md.primary, [])
        needed = max(self.params.channel, self.params.atr_period) + 2
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
        history = bars[:-1]  # the channel must not contain the bar being tested
        upper = highest(history, self.params.channel)
        lower = lowest(history, self.params.channel)
        volatility = atr(bars, self.params.atr_period)
        if upper is None or lower is None or volatility is None or volatility <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        buffer = self.params.buffer_ticks * 0.25
        broke_up = last.c > upper + buffer
        broke_down = last.c < lower - buffer
        side = "long" if broke_up else "short" if broke_down else None

        phases.append(
            Phase(
                key="channel",
                label="Canal",
                status="done",
                ts=last.t,
                detail=f"{lower:.2f} – {upper:.2f}",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Ruptura",
                status="active" if side else "pending",
                ts=last.t,
                detail=side or "sin ruptura",
            )
        )

        position_in_channel = (last.c - lower) / (upper - lower) if upper > lower else 0.5
        metrics = {
            "upper": Metric(label="Banda superior", value=round(upper, 4), format="price"),
            "lower": Metric(label="Banda inferior", value=round(lower, 4), format="price"),
            "atr": Metric(
                label=f"ATR({self.params.atr_period})",
                value=round(volatility, 4),
                format="price",
            ),
            "position": Metric(
                label="Posición en el canal",
                value=round(max(0.0, min(1.0, position_in_channel)) * 100, 2),
                format="pct",
                tone="good" if position_in_channel > 0.8 else "bad" if position_in_channel < 0.2 else "neutral",
            ),
        }

        output = StrategyOutput(
            state="armed" if side else "scanning",
            state_label="Ruptura detectada" if side else "Esperando ruptura",
            phases=phases,
            metrics=metrics,
            zones=[
                Zone(
                    id=f"channel-{md.session.id}",
                    kind="band",
                    label="Canal Donchian",
                    from_ts=last.t,
                    price_low=round(lower, 4),
                    price_high=round(upper, 4),
                    style={"color": "#8b949e", "opacity": 0.10, "line": "dashed"},
                    active=True,
                )
            ],
        )
        if side is None:
            return output

        distance = volatility * self.params.stop_atr
        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.rr
            if side == "long"
            else last.c - distance * self.params.rr
        )
        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"ruptura canal {self.params.channel}",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(target_price, 4),
            strength=min(1.0, abs(last.c - (upper if broke_up else lower)) / volatility),
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
                label=f"Ruptura {side}",
            )
        )
        return output


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")
