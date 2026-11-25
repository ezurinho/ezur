"""Guarda de ventaja contra coste.

La esperanza se mide fuera de muestra cuando la evidencia la trae; el coste
sale del mismo modelo de ejecución que usa el perfil. Si la esperanza no
supera el coste por operación, operar es pagar por una ventaja que no existe:
el motor no abre y el panel enseña las dos cifras. Sin medición no hay guarda:
no se inventa un número para bloquear.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings
from .promotion import cost_per_trade_r, execution_model


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


@dataclass(frozen=True)
class EdgeGuard:
    expectancy_r: float | None
    cost_r: float | None
    timeframe: str | None
    scope: str
    reason: str | None = None

    @property
    def passes(self) -> bool | None:
        """True solo si hay las dos cifras y la esperanza supera el coste."""
        if self.expectancy_r is None or self.cost_r is None:
            return None
        return self.expectancy_r > self.cost_r

    def detail(self) -> str:
        frame = f" en {self.timeframe}" if self.timeframe else ""
        if self.expectancy_r is None or self.cost_r is None:
            return (
                f"sin medición de ventaja contra coste{frame}: "
                f"{self.reason or 'faltan cifras'}"
            )
        relation = "supera" if self.passes else "no supera"
        return (
            f"la esperanza medida{frame} ({self.scope}, "
            f"{self.expectancy_r:+.3f} R) {relation} el coste por operación "
            f"({self.cost_r:.3f} R)"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "expectancy_r": self.expectancy_r,
            "cost_r": self.cost_r,
            "timeframe": self.timeframe,
            "scope": self.scope,
            "passes": self.passes,
            "reason": self.reason,
            "detail": self.detail(),
        }


def measure(evidence: dict[str, Any] | None, settings: Settings) -> EdgeGuard:
    """Compara la esperanza medida con el coste por operación del perfil."""
    timeframe = settings.strategy.timeframe_signal or settings.strategy.timeframe
    if not evidence:
        return EdgeGuard(
            None, None, timeframe, "sin evidencia", "no hay evidencia de promoción"
        )
    split = evidence.get("split") or {}
    out_of_sample = split.get("out_of_sample") or {}
    expectancy = _number(out_of_sample.get("expectancy_r"))
    scope = "fuera de muestra"
    if expectancy is None:
        expectancy = _number((evidence.get("metrics") or {}).get("expectancy_r"))
        scope = "global"
    cost, reason = cost_per_trade_r(evidence, execution_model(settings))
    if expectancy is None:
        reason = reason or "la evidencia no mide esperanza"
    return EdgeGuard(expectancy, cost, timeframe, scope, reason or None)


def measure_path(path: str | Path | None, settings: Settings) -> EdgeGuard | None:
    """Igual que `measure`, leyendo la evidencia de disco; sin fichero, no hay guarda."""
    if not path:
        return None
    target = Path(path)
    if not target.is_file():
        return None
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(document, dict):
        return None
    return measure(document, settings)
