"""Readiness del motor: latido y frescura del feed.

`/health` es liveness del proceso: prueba que FastAPI responde. `/ready` mira
lo que de verdad importa para operar: motor en marcha, heartbeat reciente y
última vela dentro del límite.

Un motor parado no está listo, pero el watchdog **no** debe reiniciarlo: la
parada puede ser deliberada. Por eso el payload dice `engine.status` y el
watchdog solo cuenta fallo cuando el estado es `running`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

# Dos barras de 15 m: un latido más viejo significa que el bucle dejó de correr.
HEARTBEAT_MAX_S = 1800.0
FEED_MAX_S = 1800.0


def _stamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _age(stamp: datetime | None, now: datetime) -> float | None:
    if stamp is None:
        return None
    aware = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)
    return max(0.0, (now - aware).total_seconds())


def assess(
    engine: Any,
    store: Any,
    *,
    now: datetime | None = None,
    heartbeat_max_s: float = HEARTBEAT_MAX_S,
    feed_max_s: float = FEED_MAX_S,
) -> dict[str, Any]:
    """Devuelve el estado de readiness sin tocar el motor."""
    moment = now or datetime.now(timezone.utc)
    status = getattr(getattr(engine, "state", None), "status", None)
    reasons: list[str] = []

    heartbeat_age = _age(_stamp(store.kv_get("heartbeat")), moment)
    last_bar_age = _age(
        _stamp(getattr(getattr(engine, "state", None), "last_bar_ts", None)), moment
    )

    if status != "running":
        reasons.append(f"engine_{status or 'unknown'}")
    if heartbeat_age is None:
        reasons.append("heartbeat_missing")
    elif heartbeat_age > heartbeat_max_s:
        reasons.append("heartbeat_stale")
    # Al arrancar todavía no hay vela, pero el heartbeat ya existe: no se
    # declara caído el feed por la primera vela que aún no llegó.
    if last_bar_age is not None and last_bar_age > feed_max_s:
        reasons.append("feed_stale")

    return {
        "ready": not reasons,
        "engine": {
            "status": status,
            "mode": getattr(engine, "mode", None),
        },
        "heartbeat_age_s": None if heartbeat_age is None else round(heartbeat_age, 1),
        "last_bar_age_s": None if last_bar_age is None else round(last_bar_age, 1),
        "reasons": reasons,
        "limits_s": {"heartbeat": heartbeat_max_s, "feed": feed_max_s},
    }
