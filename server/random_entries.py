"""Random-entry benchmark for a candidate's trade log.

The question this answers is narrow: given the same stop distance, target,
size, number of trades and entry filters, would random entries have produced a
better profit factor? It is a null model for the entries, not a new strategy.

Each random trade reuses one actual trade as a template (stop distance, target
distance and units), chooses a random side and a random eligible bar, and is
walked forward over the same signal-timeframe OHLC bars with stop-first
priority. Entry is the next bar open, as in the engine. The filters mirrored
here are the entry filters that do not depend on the equity path: session
window, max trades per day, one concurrent position, cooldown, and stop/unit
caps. Account-level brakes are intentionally not simulated; they depend on the
sequence of results and would make the comparison a different experiment.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

REQUIRED_TRADE_COLUMNS = {
    "opened_ts",
    "entry_price",
    "stop_price",
    "target_price",
    "units",
    "fees",
    "pnl_net",
    "side",
}


def _pf(values: np.ndarray) -> float | None:
    values = np.asarray(values, dtype=float)
    gains = float(values[values > 0].sum())
    losses = float(-values[values < 0].sum())
    if losses <= 0:
        return math.inf if gains > 0 else None
    return gains / losses


def _clean(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(float(value), 4)


def _session_minutes(stamp: pd.Timestamp, start: str, end: str) -> bool:
    def parsed(value: str) -> int:
        hour, _, minute = value.partition(":")
        return int(hour) * 60 + int(minute)

    current = stamp.hour * 60 + stamp.minute
    return parsed(start) <= current <= parsed(end)


def _bar_frame(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("las velas del benchmark necesitan índice temporal")
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame[["o", "h", "l", "c"]].dropna().sort_index()


def _templates(trades: pd.DataFrame) -> list[dict[str, float]]:
    templates: list[dict[str, float]] = []
    for row in trades.itertuples(index=False):
        entry = float(row.entry_price)
        stop = float(row.stop_price)
        target = float(row.target_price)
        units = int(row.units)
        stop_distance = abs(entry - stop)
        target_distance = abs(target - entry)
        if stop_distance <= 0 or target_distance <= 0 or units <= 0:
            continue
        templates.append(
            {
                "stop_distance": stop_distance,
                "target_distance": target_distance,
                "units": units,
                "fees": float(row.fees),
            }
        )
    return templates


def _simulate(
    bars: pd.DataFrame,
    entry_idx: int,
    side: int,
    stop: float,
    target: float,
    time_stop_bars: int,
) -> tuple[int, float, str] | None:
    opens = bars["o"].to_numpy(dtype=float)
    highs = bars["h"].to_numpy(dtype=float)
    lows = bars["l"].to_numpy(dtype=float)
    closes = bars["c"].to_numpy(dtype=float)
    last = min(len(bars) - 1, entry_idx + max(1, time_stop_bars) - 1)
    for index in range(entry_idx, last + 1):
        open_, high, low, _close = (
            opens[index],
            highs[index],
            lows[index],
            closes[index],
        )
        if side > 0:
            if open_ <= stop:
                return index, open_, "stop_gap"
            if open_ >= target:
                return index, open_, "target_gap"
            # Stop first, like the engine's intrabar priority.
            if low <= stop:
                return index, stop, "stop"
            if high >= target:
                return index, target, "target"
        else:
            if open_ >= stop:
                return index, open_, "stop_gap"
            if open_ <= target:
                return index, open_, "target_gap"
            if high >= stop:
                return index, stop, "stop"
            if low <= target:
                return index, target, "target"
    return last, closes[last], "time"


def _scheduled_starts(
    rng: np.random.Generator,
    count: int,
    total_bars: int,
    warmup_bars: int,
    min_gap_bars: int,
) -> np.ndarray | None:
    """Random starts with enough separation to keep one position at a time."""
    first = max(0, warmup_bars)
    gap = max(1, min_gap_bars)
    span = (total_bars - 2) - first
    if count < 1 or span < (count - 1) * gap:
        return None
    slack = span - (count - 1) * gap
    extras = np.floor(rng.dirichlet(np.ones(count)) * slack).astype(np.int64)
    starts = first + np.arange(count, dtype=np.int64) * gap + np.cumsum(extras)
    if int(starts[-1]) > total_bars - 2:
        return None
    return starts


def random_entry_benchmark(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    *,
    config: str = "",
    iterations: int = 200,
    seed: int = 7,
    time_stop_bars: int = 240,
    warmup_bars: int = 0,
    min_gap_bars: int = 0,
    max_trades_per_day: int = 4,
    cooldown_minutes: int = 2,
    trade_window_start: str = "00:00",
    trade_window_end: str = "23:59",
    max_units_per_trade: int = 300,
    max_stop_ticks: int = 400_000,
    min_stop_ticks: int = 0,
    max_cost_r: float | None = None,
    tick_size: float = 0.01,
    fee_taker_bps: float = 5.0,
    half_spread_bps: float = 0.07,
    commission_per_unit_side: float = 0.0,
) -> dict[str, Any]:
    """Compare actual PF with a random-entry distribution.

    The actual trade log supplies the distribution of stop distances, target
    distances and sizes. Every iteration draws a new random entry time and side
    for each template, keeping the number of accepted trades equal to the
    actual count whenever the filtered pool has enough room. The result is
    descriptive: it says where the observed PF sits inside that null, not
    whether a different strategy would pass.
    """
    if iterations < 1:
        return {"available": False, "reason": "iterations debe ser >= 1"}
    missing = sorted(REQUIRED_TRADE_COLUMNS - set(trades.columns))
    if missing:
        return {
            "available": False,
            "reason": "faltan columnas para el benchmark: " + ", ".join(missing),
        }
    if trades.empty:
        return {"available": False, "reason": "sin operaciones para comparar"}
    try:
        frame = _bar_frame(bars)
    except (KeyError, ValueError) as error:
        return {"available": False, "reason": str(error)}
    if len(frame) < 2:
        return {"available": False, "reason": "velas insuficientes"}

    templates = _templates(trades)
    if len(templates) != len(trades):
        return {
            "available": False,
            "reason": "hay operaciones con stop, objetivo o tamaño inválidos",
        }

    actual_pf = _pf(trades["pnl_net"].to_numpy(dtype=float))
    if actual_pf is None:
        return {"available": False, "reason": "PF real no calculable"}

    rng = np.random.default_rng(seed)
    opens = frame["o"].to_numpy(dtype=float)
    stamps = frame.index
    timestamps = [pd.Timestamp(stamp) for stamp in stamps]
    n_trades = len(templates)
    stop_tick = float(tick_size) if tick_size > 0 else 0.0
    fee_rate = (fee_taker_bps + half_spread_bps) / 10_000.0
    stop_floor = min_stop_ticks * stop_tick
    stop_ceiling = max_stop_ticks * stop_tick
    pfs: list[float] = []
    random_trade_counts: list[int] = []
    reasons: list[str] = []
    if n_trades >= len(frame) - max(0, int(warmup_bars)):
        return {
            "available": False,
            "reason": "no hay suficientes barras para el número de operaciones",
            "actual_pf": _clean(actual_pf),
            "trades": n_trades,
        }

    # La regla de una sola posición impide sortear las N entradas de forma
    # independiente: con operaciones de hasta 240 velas, muchas caerían dentro
    # de la anterior. Se sortea un calendario con separación mínima (time stop)
    # y holgura aleatoria; así el número de operaciones es exactamente el real y
    # ningún solape se cuela como si hubiera pasado los filtros.
    gap = max(1, int(min_gap_bars), int(time_stop_bars))
    rounds = 20
    for _ in range(iterations):
        values: list[float] | None = None
        invalid_reason = ""
        for _round in range(rounds):
            starts = _scheduled_starts(
                rng, n_trades, len(frame), max(0, int(warmup_bars)), gap
            )
            if starts is None:
                invalid_reason = "sin hueco para el calendario"
                break
            order = list(range(n_trades))
            rng.shuffle(order)
            day_counts: dict[Any, int] = {}
            last_exit_idx = -1
            last_exit_ts: pd.Timestamp | None = None
            accepted: list[float] = []
            valid = True
            for position, start_value in enumerate(starts):
                start = int(start_value)
                entry_idx = start + 1
                stamp = timestamps[entry_idx]
                if start < last_exit_idx:
                    invalid_reason = "solape"
                    valid = False
                    break
                if not _session_minutes(stamp, trade_window_start, trade_window_end):
                    invalid_reason = "ventana"
                    valid = False
                    break
                if day_counts.get(stamp.date(), 0) >= max_trades_per_day:
                    invalid_reason = "cupo diario"
                    valid = False
                    break
                if last_exit_ts is not None:
                    elapsed = (stamp - last_exit_ts).total_seconds() / 60.0
                    if elapsed < cooldown_minutes:
                        invalid_reason = "cooldown"
                        valid = False
                        break
                template = templates[order[position]]
                stop_distance = template["stop_distance"]
                target_distance = template["target_distance"]
                units = int(template["units"])
                if units > max_units_per_trade:
                    invalid_reason = "unidades"
                    valid = False
                    break
                if stop_tick and not (stop_floor <= stop_distance <= stop_ceiling):
                    invalid_reason = "stop"
                    valid = False
                    break
                side = 1 if rng.random() < 0.5 else -1
                entry = float(opens[entry_idx])
                if max_cost_r is not None and max_cost_r > 0:
                    risk_budget = stop_distance * units
                    estimated_fees = (
                        2.0 * entry * units * fee_rate
                        + 2.0 * commission_per_unit_side * units
                    )
                    if risk_budget <= 0 or estimated_fees / risk_budget > max_cost_r:
                        invalid_reason = "coste"
                        valid = False
                        break
                stop = entry - side * stop_distance
                target = entry + side * target_distance
                simulated = _simulate(
                    frame, entry_idx, side, stop, target, time_stop_bars
                )
                if simulated is None:
                    invalid_reason = "sin salida"
                    valid = False
                    break
                exit_idx, exit_price, _exit_reason = simulated
                if exit_idx >= len(frame):
                    invalid_reason = "fin del dataset"
                    valid = False
                    break
                gross = (exit_price - entry) * side * units
                fees = (
                    (entry + exit_price) * units * fee_rate
                    + 2.0 * commission_per_unit_side * units
                )
                accepted.append(gross - fees)
                day_counts[stamp.date()] = day_counts.get(stamp.date(), 0) + 1
                last_exit_idx = exit_idx
                last_exit_ts = timestamps[exit_idx]
            if valid and len(accepted) == n_trades:
                values = accepted
                break
        if values is None:
            reasons.append(
                f"una iteración no pudo colocar {n_trades} operaciones"
                + (f" ({invalid_reason})" if invalid_reason else "")
            )
            continue
        value = _pf(np.asarray(values, dtype=float))
        if value is not None:
            pfs.append(value)
            random_trade_counts.append(len(values))

    if not pfs:
        return {
            "available": False,
            "reason": reasons[0] if reasons else "no se pudo completar ninguna iteración",
            "actual_pf": _clean(actual_pf),
            "trades": int(len(trades)),
        }

    values = np.asarray(pfs, dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return {
            "available": False,
            "reason": "las iteraciones no produjeron un PF finito",
            "actual_pf": _clean(actual_pf),
            "trades": int(len(trades)),
        }
    at_least = int((finite >= actual_pf).sum())
    return {
        "available": True,
        "method": (
            "Monte Carlo de entradas aleatorias: una plantilla real por operación "
            "(stop, objetivo y unidades), lado y barra aleatorios, salida por la "
            "misma regla de stop/objetivo/tiempo, filtros de entrada replicados"
        ),
        "config": config,
        "seed": int(seed),
        "iterations": int(iterations),
        "trades": int(len(trades)),
        "iterations_completed": int(finite.size),
        "random_trades": int(random_trade_counts[0]),
        "actual_pf": _clean(actual_pf),
        "random_pf_median": _clean(float(np.median(finite))),
        "random_pf_p05": _clean(float(np.percentile(finite, 5))),
        "random_pf_p95": _clean(float(np.percentile(finite, 95))),
        "random_pf_min": _clean(float(finite.min())),
        "random_pf_max": _clean(float(finite.max())),
        "share_random_ge_actual": round(at_least / finite.size, 4),
        "percentile": round(1.0 - at_least / finite.size, 4),
        "p_value": round((at_least + 1.0) / (finite.size + 1.0), 4),
        "same": {
            "trades": True,
            "stop": "distancia de stop de cada operación real",
            "target": "distancia de objetivo de cada operación real",
            "units": "unidades de cada operación real",
            "filters": [
                "ventana de entrada",
                "máximo de operaciones por día",
                "una posición concurrente",
                "cooldown entre operaciones",
                "tope máximo y mínimo de stop",
                "tope de unidades",
                "tope de coste por operación en R",
            ],
        },
        "caveat": (
            "No reproduce frenos de cuenta (drawdown, rachas, frenos suaves): "
            "dependen de la secuencia y convertirían la prueba en otro experimento."
        ),
    }
