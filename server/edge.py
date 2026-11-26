"""Guarda de ventaja contra coste.

La esperanza se mide fuera de muestra cuando la evidencia la trae; el coste
sale del mismo modelo de ejecución que usa el perfil. La esperanza del libro
ya viene **neta** de comisiones (`r_multiple = pnl_net / riesgo`), así que la
condición correcta es que sea positiva: si el neto supera cero, el bruto
supera el coste. Comparar el neto con el coste otra vez bloquearía una
estrategia rentable después de pagar el peaje. El coste se muestra para
comprobar que se midió con el mismo modelo. Sin medición no hay guarda: no se
inventa un número para bloquear.
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
        """True si hay coste medido y la esperanza neta es positiva.

        `expectancy_r` sale de `r_multiple`, que ya descuenta comisiones y
        slippage. Exigir además que supere `cost_r` restaría el peaje dos
        veces; el bruto se obtiene sumando el coste y es el que se compara
        con él en el detalle.
        """
        if self.expectancy_r is None or self.cost_r is None:
            return None
        return self.expectancy_r > 0.0

    def detail(self) -> str:
        frame = f" en {self.timeframe}" if self.timeframe else ""
        if self.expectancy_r is None or self.cost_r is None:
            return (
                f"sin medición de ventaja contra coste{frame}: "
                f"{self.reason or 'faltan cifras'}"
            )
        relation = "supera" if self.passes else "no supera"
        gross = self.expectancy_r + self.cost_r
        return (
            f"la esperanza neta{frame} ({self.scope}, "
            f"{self.expectancy_r:+.3f} R; bruta {gross:+.3f} R) {relation} "
            f"el coste por operación ({self.cost_r:.3f} R)"
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
