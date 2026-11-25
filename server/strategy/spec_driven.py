"""Spec-driven strategy implementations.

These strategies implement the exact rules defined in the runner (motor-ia-estrategias-btc)
using the parameter names from the strategy_spec schema. They plug into the ezur engine
via the standard BaseStrategy contract.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


# --------------------------------------------------------------------------- #
# Donchian Breakout (spec-driven)
# --------------------------------------------------------------------------- #

class DonchianBreakoutParams(BaseModel):
    """Parameters matching strategy_spec schema for donchian_breakout rule."""
    model_config = ConfigDict(extra="forbid")

    N: int = Field(ge=2, le=300, description="Velas del canal")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    atr_k: float = Field(gt=0, le=10, description="Stop en múltiplos de ATR")
    tp_r: float = Field(gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    stop_floor_frac: float = Field(default=0.0, ge=0, le=0.2, description="Suelo del stop como fracción del precio")


class DonchianBreakoutStrategy(BaseStrategy):
    id = "donchian_breakout"
    name = "Donchian Breakout (spec-driven)"
    version = "1.0.0"
    params_model = DonchianBreakoutParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = DonchianBreakoutParams.model_validate(params or {})

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

        last = bars[-1]
        history = bars[:-1]  # channel must not contain the bar being tested
        upper = highest(history, self.params.N)
        lower = lowest(history, self.params.N)
        volatility = atr(bars, self.params.atr_period)
        if upper is None or lower is None or volatility is None or volatility <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        broke_up = last.c > upper
        broke_down = last.c < lower
        side = "long" if broke_up else "short" if broke_down else None

        phases.append(
            Phase(
                key="channel",
                label="Canal Donchian",
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
                    label=f"Canal Donchian({self.params.N})",
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

        distance = volatility * self.params.atr_k
        floor = self.params.stop_floor_frac * last.c if self.params.stop_floor_frac else 0
        distance = max(distance, floor)

        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.tp_r if side == "long" else last.c - distance * self.params.tp_r
        )

        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"ruptura canal {self.params.N}",
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


# --------------------------------------------------------------------------- #
# EMA State (spec-driven)
# --------------------------------------------------------------------------- #

class EMAStateParams(BaseModel):
    """Parameters matching strategy_spec schema for ema_state rule."""
    model_config = ConfigDict(extra="forbid")

    fast: int = Field(ge=2, le=200, description="EMA rápida")
    slow: int = Field(ge=3, le=500, description="EMA lenta")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    atr_k: float = Field(gt=0, le=10, description="Stop en múltiplos de ATR")
    tp_r: float = Field(gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    stop_floor_frac: float = Field(default=0.0, ge=0, le=0.2, description="Suelo del stop como fracción del precio")

    @model_validator(mode="after")
    def _ordered(self) -> "EMAStateParams":
        if self.slow <= self.fast:
            raise ValueError("slow must be greater than fast")
        return self


class EMAStateStrategy(BaseStrategy):
    id = "ema_state"
    name = "EMA State (spec-driven)"
    version = "1.0.0"
    params_model = EMAStateParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = EMAStateParams.model_validate(params or {})

    def warmup_requirements(self) -> Warmup:
        needed = max(self.params.slow, self.params.atr_period) + 2
        return Warmup(bars={"*": needed}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        from .indicators import ema
        bars = md.bars.get(md.primary, [])
        needed = max(self.params.slow, self.params.atr_period) + 2
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
        fast_ema = ema(closes, self.params.fast)
        slow_ema = ema(closes, self.params.slow)
        volatility = atr(bars, self.params.atr_period)
        if fast_ema is None or slow_ema is None or volatility is None or volatility <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        prev_fast = ema(closes[:-1], self.params.fast)
        prev_slow = ema(closes[:-1], self.params.slow)
        crossed_up = prev_fast is not None and prev_slow is not None and prev_fast <= prev_slow and fast_ema > slow_ema
        crossed_down = prev_fast is not None and prev_slow is not None and prev_fast >= prev_slow and fast_ema < slow_ema

        last = bars[-1]
        side = "long" if crossed_up else "short" if crossed_down else None

        phases.append(
            Phase(
                key="emas",
                label="EMAs",
                status="done",
                ts=last.t,
                detail=f"fast={fast_ema:.2f} slow={slow_ema:.2f}",
            )
        )
        phases.append(
            Phase(
                key="trigger",
                label="Cruce EMA",
                status="active" if side else "pending",
                ts=last.t,
                detail=side or "sin cruce",
            )
        )

        metrics = {
            "fast": Metric(label=f"EMA({self.params.fast})", value=round(fast_ema, 4), format="price"),
            "slow": Metric(label=f"EMA({self.params.slow})", value=round(slow_ema, 4), format="price"),
            "atr": Metric(
                label=f"ATR({self.params.atr_period})",
                value=round(volatility, 4),
                format="price",
            ),
            "spread": Metric(
                label="Separación",
                value=round(fast_ema - slow_ema, 4),
                format="price",
                tone="good" if fast_ema > slow_ema else "bad" if fast_ema < slow_ema else "neutral",
            ),
        }

        output = StrategyOutput(
            state="armed" if side else "scanning",
            state_label="Cruce EMA" if side else "Esperando cruce",
            phases=phases,
            metrics=metrics,
            zones=[
                Zone(
                    id=f"ema-spread-{md.session.id}",
                    kind="band",
                    label=f"EMA{self.params.fast}-EMA{self.params.slow}",
                    from_ts=last.t,
                    price_low=min(fast_ema, slow_ema),
                    price_high=max(fast_ema, slow_ema),
                    style={"color": "#58a6ff", "opacity": 0.10},
                    active=True,
                )
            ],
        )
        if side is None:
            return output

        distance = volatility * self.params.atr_k
        floor = self.params.stop_floor_frac * last.c if self.params.stop_floor_frac else 0
        distance = max(distance, floor)

        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.tp_r if side == "long" else last.c - distance * self.params.tp_r
        )

        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
            side=side,
            reason=f"cruce EMA{self.params.fast}/EMA{self.params.slow}",
            ts=last.t,
            stop_price=round(stop_price, 4),
            target_price=round(target_price, 4),
            strength=min(1.0, abs(fast_ema - slow_ema) / volatility) if volatility else None,
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
                label=f"EMA {side}",
            )
        )
        return output


# --------------------------------------------------------------------------- #
# Z-Score Fade (spec-driven)
# --------------------------------------------------------------------------- #

class ZScoreFadeParams(BaseModel):
    """Parameters matching strategy_spec schema for zscore_fade rule."""
    model_config = ConfigDict(extra="forbid")

    N: int = Field(ge=5, le=500, description="Ventana para media/desviación")
    z: float = Field(default=2.0, gt=0, le=5, description="Umbral de z-score")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    atr_k: float = Field(default=1.0, gt=0, le=10, description="Stop en múltiplos de ATR")
    tp_r: float = Field(default=2.0, gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    stop_floor_frac: float = Field(default=0.0, ge=0, le=0.2, description="Suelo del stop")


class ZScoreFadeStrategy(BaseStrategy):
    id = "zscore_fade"
    name = "Z-Score Fade (spec-driven)"
    version = "1.0.0"
    params_model = ZScoreFadeParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = ZScoreFadeParams.model_validate(params or {})

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
            "threshold": Metric(label=f"Umbral z={self.params.z}", value=self.params.z, format="number"),
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

        distance = atr_val * self.params.atr_k
        floor = self.params.stop_floor_frac * last.c if self.params.stop_floor_frac else 0
        distance = max(distance, floor)

        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.tp_r if side == "long" else last.c - distance * self.params.tp_r
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


# --------------------------------------------------------------------------- #
# ORB Session (spec-driven)
# --------------------------------------------------------------------------- #

class ORBSessionParams(BaseModel):
    """Parameters matching strategy_spec schema for orb_session rule."""
    model_config = ConfigDict(extra="forbid")

    range_bars: int = Field(ge=1, le=120, description="Barras del rango de apertura")
    atr_period: int = Field(default=14, ge=2, le=200, description="Periodo del ATR")
    atr_k: float = Field(default=1.0, gt=0, le=10, description="Stop en múltiplos de ATR")
    tp_r: float = Field(default=2.0, gt=0, le=10, description="Objetivo en múltiplos del riesgo")
    stop_floor_frac: float = Field(default=0.0, ge=0, le=0.2, description="Suelo del stop como fracción del precio")


class ORBSessionStrategy(BaseStrategy):
    id = "orb_session"
    name = "Opening Range Breakout (spec-driven)"
    version = "1.0.0"
    params_model = ORBSessionParams

    def __init__(self, params: dict | None = None) -> None:
        self.params = ORBSessionParams.model_validate(params or {})

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

        closes = [bar.c for bar in bars]
        highs = [bar.h for bar in bars]
        lows = [bar.l for bar in bars]
        atr_val = atr(bars, self.params.atr_period)

        if atr_val is None or atr_val <= 0:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

        range_n = self.params.range_bars
        if len(bars) < range_n + 1:
            return StrategyOutput(state="warmup", state_label="Calentando", phases=phases)

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
                    id=f"orb-range-{md.session.id}",
                    kind="band",
                    label=f"Rango ORB({range_n})",
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

        distance = atr_val * self.params.atr_k
        floor = self.params.stop_floor_frac * last.c if self.params.stop_floor_frac else 0
        distance = max(distance, floor)

        stop_price = last.c - distance if side == "long" else last.c + distance
        target_price = (
            last.c + distance * self.params.tp_r if side == "long" else last.c - distance * self.params.tp_r
        )

        output.signal = Signal(
            key=f"{md.session.id}:{side}:{_stamp(last.t)}",
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


# --------------------------------------------------------------------------- #
# Helper
# --------------------------------------------------------------------------- #

def _stamp(value: datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%S")


# Import Marker
from .base import Marker  # noqa: E402