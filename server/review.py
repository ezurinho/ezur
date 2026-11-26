"""Vista comparativa 2025 del perfil 15m.

Las filas del perfil y de coste ×2 salen de los artefactos de la review tal
cual. BTC no tiene artefacto propio: la review solo guardó su cifra en el
documento, así que aquí se reproduce desde el CSV que declara el artefacto,
filtrando su ventana. El DD del benchmark usa cierres diarios UTC, que es la
convención del −32,02 % documentado; el retorno va de la apertura inicial al
cierre final.
"""

from __future__ import annotations

import csv
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

PROFILE_ARTIFACT = "data/research/promotion/profile-15m-2025.json"
COST2X_ARTIFACT = "data/research/promotion/profile-15m-2025-cost2x.json"
REVIEW_INITIAL_CAPITAL = 25_000.0
CAPITAL_SOURCE = "capital inicial del perfil en la review (25.000 $)"


class ReviewUnavailable(RuntimeError):
    """Faltan datos de la review; no se rellena el hueco con una estimación."""


def _number(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _read_json(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ReviewUnavailable(f"falta el artefacto {relative}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ReviewUnavailable(f"no se pudo leer {relative}: {error}") from error
    if not isinstance(payload, dict):
        raise ReviewUnavailable(f"{relative} no contiene un objeto JSON")
    return payload


def _utc_day(value: Any, field: str) -> datetime:
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise ReviewUnavailable(f"ventana inválida: {field}={value!r}") from error
    return datetime(parsed.year, parsed.month, parsed.day, tzinfo=timezone.utc)


def _timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ReviewUnavailable(f"timestamp inválido en el dataset: {value!r}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_bars(
    root: Path,
    dataset: str,
    start: datetime,
    end: datetime,
) -> list[tuple[datetime, float, float, float, float]]:
    path = Path(dataset)
    if not path.is_absolute():
        path = root / path
    try:
        handle = path.open(newline="", encoding="utf-8")
    except FileNotFoundError as error:
        raise ReviewUnavailable(f"falta el dataset {dataset}") from error
    except OSError as error:
        raise ReviewUnavailable(f"no se pudo abrir {dataset}: {error}") from error

    bars: list[tuple[datetime, float, float, float, float]] = []
    try:
        with handle:
            reader = csv.DictReader(handle)
            required = {"ts", "o", "h", "l", "c"}
            if reader.fieldnames is None or not required.issubset(reader.fieldnames):
                raise ReviewUnavailable(f"{dataset} no tiene columnas {sorted(required)}")
            for row in reader:
                try:
                    ts = _timestamp(row["ts"])
                    if ts < start or ts >= end:
                        continue
                    bars.append(
                        (
                            ts,
                            float(row["o"]),
                            float(row["h"]),
                            float(row["l"]),
                            float(row["c"]),
                        )
                    )
                except (KeyError, TypeError, ValueError) as error:
                    raise ReviewUnavailable(f"vela inválida en {dataset}: {error}") from error
    except OSError as error:
        raise ReviewUnavailable(f"no se pudo leer {dataset}: {error}") from error

    if not bars:
        raise ReviewUnavailable(
            f"{dataset} no tiene velas en la ventana {start.date()} → {end.date()}"
        )
    bars.sort(key=lambda bar: bar[0])
    return bars


def _benchmark(
    root: Path,
    artifact: dict[str, Any],
    window: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    dataset = artifact.get("dataset")
    if not isinstance(dataset, str) or not dataset:
        raise ReviewUnavailable("el artefacto del perfil no declara dataset")

    start = _utc_day(window.get("from"), "from")
    end = _utc_day(window.get("to"), "to")
    bars = _read_bars(root, dataset, start, end)

    first_ts, first_open = bars[0][0], bars[0][1]
    last_ts, last_close = bars[-1][0], bars[-1][4]
    daily_closes: dict[date, float] = {}
    for ts, _, _, _, close in bars:
        daily_closes[ts.date()] = close

    closes = [daily_closes[day] for day in sorted(daily_closes)]
    peak = closes[0]
    drawdown = 0.0
    for close in closes:
        if close > peak:
            peak = close
        drawdown = min(drawdown, close / peak - 1)

    return_pct = last_close / first_open - 1 if first_open else None
    edited_ts = first_ts.isoformat().replace("+00:00", "Z")
    benchmark = {
        "method": (
            "apertura de la primera vela → cierre de la última; "
            "DD máximo sobre cierres diarios UTC"
        ),
        "dataset": dataset,
        "first_ts": edited_ts,
        "last_ts": last_ts.isoformat().replace("+00:00", "Z"),
        "first_open": first_open,
        "last_close": last_close,
        "bars": len(bars),
        "daily_closes": len(closes),
        "return_pct": return_pct,
        "drawdown_pct": drawdown,
    }
    row = {
        "id": "btc_bh",
        "label": "BTC buy-and-hold",
        "source": f"{dataset} · cierres diarios",
        "trades": None,
        "pnl_usd": None,
        "return_pct": return_pct,
        "profit_factor": None,
        "fees": None,
        "drawdown_usd": None,
        "drawdown_pct": drawdown,
        "open_position": {
            "kind": "spot",
            "side": "spot",
            "units": None,
            "entry_price": first_open,
            "stop_price": None,
            "target_price": None,
            "opened_ts": edited_ts,
            "entry_fees": None,
        },
        "note": "apertura → cierre · DD diario",
    }
    return benchmark, row


def _open_position(artifact: dict[str, Any]) -> dict[str, Any] | None:
    diagnostics = artifact.get("diagnostics")
    position = diagnostics.get("open_position") if isinstance(diagnostics, dict) else None
    if not isinstance(position, dict):
        return None
    opened_ts = position.get("opened_ts")
    side = position.get("side")
    return {
        "kind": "trade",
        "side": side if isinstance(side, str) else "unknown",
        "units": _number(position, "units"),
        "entry_price": _number(position, "entry_price"),
        "stop_price": _number(position, "stop_price"),
        "target_price": _number(position, "target_price"),
        "opened_ts": opened_ts if isinstance(opened_ts, str) else None,
        "entry_fees": _number(position, "entry_fees"),
    }


def _strategy_row(
    artifact: dict[str, Any],
    *,
    ident: str,
    label: str,
    source: str,
    initial_capital: float,
) -> dict[str, Any]:
    metrics = artifact.get("metrics")
    if not isinstance(metrics, dict):
        raise ReviewUnavailable(f"{source} no tiene metrics")

    pnl = _number(metrics, "pnl_net")
    drawdown = _number(metrics, "max_drawdown")
    trades = _number(metrics, "trades")
    return {
        "id": ident,
        "label": label,
        "source": source,
        "trades": int(trades) if trades is not None else None,
        "pnl_usd": pnl,
        "return_pct": pnl / initial_capital if pnl is not None else None,
        "profit_factor": _number(metrics, "profit_factor"),
        "fees": _number(metrics, "fees"),
        "drawdown_usd": drawdown,
        "drawdown_pct": -drawdown / initial_capital if drawdown is not None else None,
        "open_position": _open_position(artifact),
        "note": None,
    }


def review_2025(
    repo_root: Path | str | None = None,
    *,
    initial_capital: float = REVIEW_INITIAL_CAPITAL,
) -> dict[str, Any]:
    """Devuelve la comparación 2025 sin recalcular las operaciones de la review."""

    if not isinstance(initial_capital, (int, float)) or initial_capital <= 0:
        raise ValueError("initial_capital debe ser positivo")

    root = Path(repo_root) if repo_root is not None else Path(__file__).resolve().parents[1]
    profile = _read_json(root, PROFILE_ARTIFACT)
    cost2x = _read_json(root, COST2X_ARTIFACT)

    window = profile.get("window")
    if not isinstance(window, dict):
        raise ReviewUnavailable("el artefacto del perfil no declara ventana")
    if cost2x.get("window") != window:
        raise ReviewUnavailable("perfil y coste ×2 no cubren la misma ventana")
    if cost2x.get("dataset") != profile.get("dataset"):
        raise ReviewUnavailable("perfil y coste ×2 no usan el mismo dataset")

    benchmark, benchmark_row = _benchmark(root, profile, window)
    rows = [
        _strategy_row(
            profile,
            ident="profile",
            label="Perfil 15m",
            source=PROFILE_ARTIFACT,
            initial_capital=float(initial_capital),
        ),
        _strategy_row(
            cost2x,
            ident="cost2x",
            label="Perfil · coste ×2",
            source=COST2X_ARTIFACT,
            initial_capital=float(initial_capital),
        ),
        benchmark_row,
    ]
    return {
        "window": {"from": str(window.get("from")), "to": str(window.get("to"))},
        "dataset": profile.get("dataset"),
        "config_hash": profile.get("config_hash"),
        "cost2x_config_hash": cost2x.get("config_hash"),
        "initial_capital": float(initial_capital),
        "capital_source": CAPITAL_SOURCE,
        "benchmark": benchmark,
        "note": (
            "El P&L y el DD del perfil y de coste ×2 solo incluyen operaciones cerradas; "
            "la posición abierta no está marcada a mercado."
        ),
        "rows": rows,
    }
