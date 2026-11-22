"""Null strategy: the placeholder that keeps the skeleton runnable.

It emits no signal, no phase and no metric. Everything downstream must work
with this output, which is exactly the point: the infrastructure cannot rely
on any strategy content.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from .base import BaseStrategy, MarketData, StrategyOutput, Warmup


class NullParams(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NullStrategy(BaseStrategy):
    id = "null"
    name = "Estrategia pendiente"
    version = "0.0.0"
    params_model = NullParams

    def warmup_requirements(self) -> Warmup:
        return Warmup(bars={}, session_ready=False)

    def evaluate(self, md: MarketData) -> StrategyOutput:
        return StrategyOutput(state="disabled", state_label="Sin estrategia")
