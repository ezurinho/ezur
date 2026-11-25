"""ORB (Opening Range Breakout) strategy.

Hypothesis: the first N bars of a session define a range; a breakout of that
range in the session's early hours carries directional momentum. The stop is
placed at the opposite edge of the range (or a fraction of ATR), target at R.
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


class ORBParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range_bars: int = Field(default=12, ge=1, le=120, description="Barras del rango de apertura")
    sessions: list[str] = Field(
        default_factory=lambda: ["13:30", "20:00"],
        description="UTC session starts as HH:MM (e.g. NY open, Asia open)",
    )
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    stop_atr: float = Field(default=1.0, gt=0, le=10, description="Stop en múltiplos de ATR")
    rr: float = Field(default=2.0, gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    stop_floor_frac: float = Field(
        default=0.0, ge=0, le=0.2, description="Suelo del stop como fracción del precio"
    )

    @model_validator(mode="after")
    def _validate_sessions(self) -> "ORBParams":
        for s in self.sessions:
            if not (len(s) == 5 and s[2] == ":" and s[:2].isdigit() and s[3:].isdigit()):
                raise ValueError(f"session '{s}' must be HH:MM")
            hh, mm = int(s[:2]), int(s[3:])
            if not (0 <= hh <= 23 and 0 <= mm <= 59):
                raise ValueError(f"session '{s}' invalid hour/minute")
        return self


class ORBStrategy(BaseStrategy):
    id = "orb"
    name = "Opening Range Breakout (sin validar)"
    version = "0.1.0"
    params_model = ORBParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = ORBParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.range_bars, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=True)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        bars = md.bars.get(md.primary, [])
        needed = max(self.params.range_bars, self.params.atr_period) + 2
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

        # Current session info
        session = md.session
        template = md.params.get("session_template") if hasattr(md, "params") else None
        # For now, use a simple approach: check if we're in the first N bars of the session
        # In a real implementation, this would use session timing

        closes = [bar.c for bar in bars]
        highs = [bar.h for bar in bars]
        lows = [bar.l for bar in bars]
        atr_val = atr(bars, self.params.atr_period)

        if atr_val is None or atr_val <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        # Simple ORB: track the first N bars of each session
        # This is a simplified version; the full runner uses timestamps
        range_n = self.params.range_bars
        if len(bars) < range_n + 1:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        # Get range from first N bars of the most recent session
        # (In production, use actual session boundaries from md.session)
        range_start = len(bars) - range_n - 1
        range_high = max(highs[range_start:range_start + range_n])
        range_low = min(lows[range_start:range_start + range_n])

        last = bars[-1]
        broke_up = last.c > range_high
        broke_down = last.c < range_low
        side = "long" if broke_up else "short" if broke_down else None

        phases.append(
            Phase(
                key="range",
                label="Rango de apertura",
                status="done",
                ts=last.t,
                detail=f"{range_low:.2f} – {range_high:.2f}",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Breakout",
                status="active" if side else "pending",
                ts=last.t,
                detail=side or "sin ruptura",
            )
        )

        position_in_range = (
            (last.c - range_low) / (range_high - range_low) if range_high > range_low else 0.5
        )
        metrics = {
            "range_high": Metric(label="Alto del rango", value=round(range_high, 4), format="price"),
            "range_low": Metric(label="Bajo del rango", value=round(range_low, 4), format="price"),
            "atr": Metric(
                label=f"ATR({self.params.atr_period})",
                value=round(atr_val, 4),
                format="price",
            ),
            "position": Metric(
                label="Posición en el rango",
                value=round(max(0.0, min(1.0, position_in_range)) * 100, 2),
                format="pct",
                tone="good" if position_in_range > 0.8 else "bad" if position_in_range < 0.2 else "neutral",
            ),
        }

        output = StrategyOutput(
            state="armed" if side else "scanning",
            state_label="Breakout detectado" if side else "Esperando breakout",
            phases=phases,
            metrics=metrics,
            zones=[
                Zone(
                    id=f"orb-range-{session.id}",
                    kind="band",
                    label="Rango ORB",
                    from_ts=last.t,
                    price_low=round(range_low, 4),
                    price_high=round(range_high, 4),
                    style={"color": "#8b949e", "opacity": 0.10, "line": "dashed"},
                    active=True,
                )
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
            key=f"{session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"ORB breakout rango {range_n}",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(target_price, 4),
            strength=min(1.0, abs(last.c - (range_high if broke_up else range_low)) / atr_val),
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
                label=f"ORB {side}",
            )
        )
        return output


def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


# Need to import Marker
from .base import Marker  # noqa: E402