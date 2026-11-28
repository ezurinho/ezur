"""Candado del holdout, aplicado al runner y no solo a los scripts de research.

El tramo 2026-12-01/2027-05-31 es evidencia de una sola vez. Un backtest que
lo toque sin pre-registro ni sello reproducible debe fallar antes de ejecutar
el motor, no después de mirar el resultado.

El sello usa las mismas piezas que `confirmatory.seal_holdout`: hash del CSV,
de la identidad de la estrategia y de la configuración que define el estudio.
La configuración sellada excluye `execution` a propósito: el estrés de costes
duplica comisiones y slippage, y debe poder correr sobre el mismo holdout sin
considerarse otro estudio.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .confirmatory import seal_holdout, verify_seal

HOLDOUT_START = datetime(2026, 12, 1, tzinfo=timezone.utc)
# El final documentado es inclusivo (23:59:59); para comparar ventanas
# semiaabiertas se usa el comienzo del día siguiente.
HOLDOUT_END = datetime(2027, 5, 31, 23, 59, 59, tzinfo=timezone.utc)
HOLDOUT_END_EXCLUSIVE = datetime(2027, 6, 1, tzinfo=timezone.utc)
SEAL_ENV = "EZUR_HOLDOUT_UNSEAL"

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "holdout"
PREREG_FILE = DATA_DIR / "PREREGISTRO.sha256"
LOCK_FILE = DATA_DIR / "lock.json"

_ONE_MICROSECOND = timedelta(microseconds=1)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HoldoutSealed(RuntimeError):
    """Se intentó usar el holdout sin autorización registrada."""


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def effective_window(
    dataset_first: datetime | None,
    dataset_last: datetime | None,
    *,
    start: datetime | None,
    end: datetime | None,
) -> tuple[datetime, datetime] | None:
    """Intersección real entre el CSV y la ventana pedida (fin exclusivo)."""
    if dataset_first is None or dataset_last is None:
        return None
    first = _aware(dataset_first)
    last = _aware(dataset_last)
    if start is not None:
        first = max(first, _aware(start))
    if end is not None:
        last = min(last, _aware(end) - _ONE_MICROSECOND)
    return (first, last) if first <= last else None


def overlaps_holdout(first: datetime, last: datetime) -> bool:
    return first < HOLDOUT_END_EXCLUSIVE and last >= HOLDOUT_START


def holdout_config(settings) -> dict[str, Any]:
    """Parte del perfil que no puede cambiar entre el sello y la corrida.

    `execution` queda fuera porque el test de costes duplicados es una
    sensibilidad del mismo estudio, no un estudio nuevo. `risk` sí entra: un
    cambio de riesgo cambia qué operaciones sobreviven al holdout.
    """
    payload = settings.model_dump(mode="json")
    return {
        "strategy": payload["strategy"],
        "instruments": payload["instruments"],
        "risk": payload["risk"],
    }


def strategy_payload(strategy) -> dict[str, Any]:
    params = getattr(strategy, "params", None)
    if hasattr(params, "model_dump"):
        params = params.model_dump(mode="json")
    return {
        "id": getattr(strategy, "id", ""),
        "version": getattr(strategy, "version", ""),
        "params": params,
    }


def _check_pre_registration() -> None:
    if os.environ.get(SEAL_ENV) != "1":
        raise HoldoutSealed(
            f"el holdout {HOLDOUT_START.date()}/{HOLDOUT_END.date()} está sellado; "
            f"define {SEAL_ENV}=1 y un pre-registro firmado para abrirlo"
        )
    if not PREREG_FILE.is_file():
        raise HoldoutSealed(
            f"{SEAL_ENV}=1 pero falta {PREREG_FILE}: sin pre-registro firmado no se abre"
        )
    digest = PREREG_FILE.read_text(encoding="utf-8").strip().lower()
    if not _SHA256.fullmatch(digest):
        raise HoldoutSealed(
            f"{PREREG_FILE} no contiene un SHA-256 válido; el pre-registro no es verificable"
        )


def guard_window(
    dataset_first: datetime | None,
    dataset_last: datetime | None,
    *,
    start: datetime | None,
    end: datetime | None,
    dataset_path: str | Path,
    config: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    """Autoriza o aborta el tramo solicitado. Devuelve la traza para el informe."""
    window = effective_window(dataset_first, dataset_last, start=start, end=end)
    if window is None:
        return {"overlaps": False, "authorized": False, "window": None}
    first, last = window
    trace = {
        "overlaps": True,
        "authorized": False,
        "window": [first.isoformat(), last.isoformat()],
    }
    if not overlaps_holdout(first, last):
        trace["overlaps"] = False
        return trace

    _check_pre_registration()
    verdict = verify_seal(
        LOCK_FILE,
        dataset_path=dataset_path,
        config=config,
        strategy=strategy,
    )
    if not verdict["ok"]:
        reasons = "; ".join(verdict["reasons"]) or "sello ausente o inválido"
        raise HoldoutSealed(
            f"el tramo {HOLDOUT_START.date()}/{HOLDOUT_END.date()} no tiene un sello "
            f"válido en {LOCK_FILE}: {reasons}"
        )
    trace["authorized"] = True
    trace["sealed_ts"] = verdict.get("sealed_ts")
    return trace


def seal_run(
    dataset_path: str | Path,
    settings,
    strategy,
    *,
    protocol: str = "holdout 2026-12-01/2027-05-31",
) -> dict[str, Any]:
    """Crea el sello único para este dataset, perfil y estrategia."""
    return seal_holdout(
        LOCK_FILE,
        dataset_path=dataset_path,
        config=holdout_config(settings),
        strategy=strategy_payload(strategy),
        protocol=protocol,
    )
