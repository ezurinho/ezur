"""Auditoría de fills contra las velas de 1 minuto que los contuvieron.

Un fill es imposible cuando su precio queda fuera del rango ``low..high`` de la
vela de 1 m que contiene su timestamp, más la tolerancia declarada para el
slippage del modelo. La tolerancia importa: el motor desplaza el fill hasta
``max_slippage_ticks``; contar eso como imposible sería auditar el modelo, no
los datos.

El audit no corrige nada. Cuenta los fills imposibles, elimina las operaciones
que contienen alguno y compara el PF antes y después para que la caída sea
visible.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from .models import Bar, TradeRecord
from .stats import compute_stats

CandleKey = tuple[str, datetime]


def _minute(stamp: datetime) -> datetime:
    """Minuto UTC que contiene el instante, sin segundos ni microsegundos."""
    value = stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


def _parse_ts(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    stamp = datetime.fromisoformat(text)
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def needed_candles(trades: Iterable[TradeRecord]) -> set[CandleKey]:
    """Claves (símbolo, minuto) que necesitan los dos fills de cada operación."""
    keys: set[CandleKey] = set()
    for trade in trades:
        keys.add((trade.symbol, _minute(trade.opened_ts)))
        keys.add((trade.symbol, _minute(trade.closed_ts)))
    return keys


def load_candles(
    path: str | Path,
    keys: Iterable[CandleKey] | None = None,
) -> dict[CandleKey, Bar]:
    """Carga velas de 1 m, opcionalmente solo las claves que se van a auditar.

    Filtrar durante la lectura evita mantener en memoria un CSV de un millón de
    velas cuando la corrida solo tiene cientos de fills. El timestamp se
    normaliza al minuto: la vela que contiene el fill es la que manda.
    """
    target = Path(path)
    wanted = set(keys) if keys is not None else None
    if wanted is not None and not wanted:
        return {}

    candles: dict[CandleKey, Bar] = {}
    with target.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = {"ts", "symbol", "o", "h", "l", "c"} - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"faltan columnas en {target}: {sorted(missing)}")
        for line, row in enumerate(reader, start=2):
            symbol = row["symbol"]
            stamp = _minute(_parse_ts(row["ts"]))
            key = (symbol, stamp)
            if wanted is not None and key not in wanted:
                continue
            try:
                low = float(row["l"])
                high = float(row["h"])
                bar = Bar(
                    t=stamp,
                    o=float(row["o"]),
                    h=high,
                    l=low,
                    c=float(row["c"]),
                    v=float(row.get("v") or 0.0),
                )
            except (TypeError, ValueError) as error:
                raise ValueError(f"vela inválida en {target}:{line}") from error
            if low > high:
                raise ValueError(f"vela inválida en {target}:{line}: low > high")
            candles[key] = bar
            if wanted is not None and len(candles) == len(wanted):
                break
    return candles


def _overshoot(price: float, low: float, high: float, tick_size: float) -> float:
    if price < low:
        return (low - price) / tick_size
    if price > high:
        return (price - high) / tick_size
    return 0.0


def audit_fills(
    trades: Iterable[TradeRecord],
    candles: Mapping[CandleKey, Bar],
    *,
    tick_size: float = 0.01,
    tolerance_ticks: float = 0.0,
) -> dict[str, object]:
    """Compara cada entrada y salida con su vela de 1 m.

    ``tolerance_ticks`` es el margen que el modelo de ejecución puede desplazar
    el precio (el ``max_slippage_ticks`` del perfil). Un fill fuera del OHLC
    pero dentro de ese margen se cuenta como ``tolerated``; uno fuera del margen
    es ``impossible`` y arrastra su operación fuera del PF auditado.
    """
    if tick_size <= 0:
        raise ValueError("tick_size debe ser positivo")
    if tolerance_ticks < 0:
        raise ValueError("tolerance_ticks no puede ser negativo")

    records = list(trades)
    tolerance = tolerance_ticks * tick_size
    impossible_trades: set[int] = set()
    details: list[dict[str, object]] = []
    checked = missing = outside = tolerated = impossible = 0
    impossible_entry = impossible_exit = 0

    for index, trade in enumerate(records):
        legs = (
            ("entry", trade.opened_ts, trade.entry_price),
            ("exit", trade.closed_ts, trade.exit_price),
        )
        for leg, when, price in legs:
            key = (trade.symbol, _minute(when))
            bar = candles.get(key)
            base = {
                "trade": index,
                "leg": leg,
                "symbol": trade.symbol,
                "ts": _minute(when).isoformat(),
                "price": price,
            }
            if bar is None:
                missing += 1
                details.append({**base, "status": "missing", "low": None, "high": None})
                continue

            checked += 1
            overshoot = _overshoot(price, bar.l, bar.h, tick_size)
            if overshoot == 0:
                continue
            outside += 1
            if price < bar.l - tolerance or price > bar.h + tolerance:
                impossible += 1
                impossible_trades.add(index)
                if leg == "entry":
                    impossible_entry += 1
                else:
                    impossible_exit += 1
                status = "impossible"
            else:
                tolerated += 1
                status = "tolerated"
            details.append(
                {
                    **base,
                    "status": status,
                    "low": bar.l,
                    "high": bar.h,
                    "overshoot_ticks": round(overshoot, 6),
                }
            )

    kept = [
        trade for index, trade in enumerate(records) if index not in impossible_trades
    ]
    before = compute_stats(records)
    after = compute_stats(kept)
    pf_before = float(before["profit_factor"])
    pf_after = float(after["profit_factor"])
    pf_drop = pf_before - pf_after
    return {
        "trades": len(records),
        "trades_kept": len(kept),
        "trades_removed": len(impossible_trades),
        "trades_with_impossible": len(impossible_trades),
        "fills": len(records) * 2,
        "checked_fills": checked,
        "missing_fills": missing,
        "outside_ohlc_fills": outside,
        "tolerated_fills": tolerated,
        "impossible_fills": impossible,
        "impossible_entry_fills": impossible_entry,
        "impossible_exit_fills": impossible_exit,
        "tick_size": tick_size,
        "tolerance_ticks": tolerance_ticks,
        "pf_before": pf_before,
        "pf_after": pf_after,
        "pf_drop": pf_drop,
        "pf_drop_pct": (pf_drop / pf_before * 100.0) if pf_before else 0.0,
        "pnl_before": float(before["pnl_net"]),
        "pnl_after": float(after["pnl_net"]),
        "pnl_removed": float(before["pnl_net"]) - float(after["pnl_net"]),
        "details": details,
    }
