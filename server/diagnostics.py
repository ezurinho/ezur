"""Read-only diagnostics for the SQLite store.

Never creates tables, never writes, never takes a backup. Safe to run against a
live database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

TABLES = (
    "trades",
    "events",
    "equity",
    "kv",
    "backtests",
    "backtest_runs",
    "backtest_results",
    "backtest_ledger_outbox",
    "schema_migrations",
)


def _instant(value: Any) -> datetime | None:
    """Texto ISO a instante con zona.

    Comparar las fechas como cadenas miente en cuanto se mezclan `Z` y
    `+00:00`, o dos desfases distintos: `05:00+02:00` es anterior a
    `04:05+00:00` y como texto parece posterior. Se comparan instantes.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def _ledger_anomalies(connection: sqlite3.Connection, tables: set[str]) -> dict[str, Any]:
    """Filas que ningún veredicto debería haber producido.

    Una salida anterior a la entrada delata una barra vieja ejecutada sobre una
    posición viva; dos filas con el mismo signal_key son la misma operación
    contada dos veces. Se cuentan, no se corrigen: este comando es de lectura.
    """
    if "trades" not in tables:
        return {"impossible": [], "duplicate_signals": [], "without_signal_key": 0}
    impossible = []
    for row in connection.execute(
        "SELECT id, opened_ts, closed_ts FROM trades ORDER BY id"
    ):
        opened = _instant(row["opened_ts"])
        closed = _instant(row["closed_ts"])
        if opened is not None and closed is not None and closed < opened:
            impossible.append(dict(row))
    duplicate_signals = [
        dict(row)
        for row in connection.execute(
            """
            SELECT signal_key, COUNT(*) AS rows FROM trades
             WHERE signal_key <> ''
             GROUP BY signal_key HAVING COUNT(*) > 1
            """
        )
    ]
    without_signal_key = connection.execute(
        "SELECT COUNT(*) AS c FROM trades WHERE signal_key = ''"
    ).fetchone()["c"]
    return {
        "impossible": impossible,
        "duplicate_signals": duplicate_signals,
        "without_signal_key": without_signal_key,
    }


EQUITY_TOLERANCE = 0.01


def _kv_number(connection: sqlite3.Connection, key: str) -> float | None:
    row = connection.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    if row is None:
        return None
    try:
        return float(json.loads(row["value"]))
    except (TypeError, ValueError):
        return None


def _peak_reset(
    connection: sqlite3.Connection, tables: set[str]
) -> tuple[str, float] | None:
    """Último reinicio manual del pico: (cuándo, pico nuevo), si lo hay."""
    if "events" not in tables:
        return None
    row = connection.execute(
        "SELECT ts, meta FROM events WHERE category = 'risk' "
        "AND message LIKE 'pico reiniciado%' ORDER BY ts DESC, id DESC LIMIT 1"
    ).fetchone()
    if row is None:
        return None
    try:
        after = float((json.loads(row["meta"] or "{}") or {}).get("after"))
    except (TypeError, ValueError):
        return None
    return str(row["ts"]), after


def _books(
    connection: sqlite3.Connection,
    tables: set[str],
    capital: float,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Las tres copias de la verdad, comparadas: libro, curva y `kv`.

    El libro manda. La curva y el estado se escriben desde memoria, y cuando esa
    memoria sumó un cierre dos veces el panel enseñó 24.210,09 frente a
    24.356,41 del libro. Este bloque dice cuál de las copias se desvió y por
    cuánto, sin arreglar nada.
    """
    if not {"trades", "equity", "kv"} <= tables:
        return {"checked": False, "reason": "faltan tablas", "differences": {}}
    trades = int(connection.execute("SELECT COUNT(*) AS c FROM trades").fetchone()["c"])
    total_row = connection.execute(
        "SELECT COALESCE(SUM(pnl_net), 0) AS total FROM trades"
    ).fetchone()
    rows = int(connection.execute("SELECT COUNT(*) AS c FROM equity").fetchone()["c"])
    last = connection.execute("SELECT ts, equity FROM equity ORDER BY ts DESC LIMIT 1").fetchone()
    # Un reinicio manual del pico es legítimo: desde ahí se mide el drawdown, no
    # desde el máximo histórico de la curva. Si no se tiene en cuenta, la
    # auditoría señalaría como desviación una decisión deliberada.
    reset = _peak_reset(connection, tables)
    if reset is not None:
        reset_at, base = reset
        high_row = connection.execute(
            "SELECT MAX(equity) AS high FROM equity WHERE ts >= ?", (reset_at,)
        ).fetchone()
    else:
        reset_at = None
        base = float(capital)
        high_row = connection.execute("SELECT MAX(equity) AS high FROM equity").fetchone()
    total = float(total_row["total"] or 0.0)
    high = float(high_row["high"]) if high_row and high_row["high"] is not None else None
    book = float(capital) + total
    state = _kv_number(connection, "equity")
    peak_state = _kv_number(connection, "peak_equity")
    curve = float(last["equity"]) if last else None
    peak_expected = max(base, high) if high is not None else base

    # La parada dura del riesgo deja el bot sin operar para siempre: sin
    # operaciones la equity no vuelve al pico. Si está activa, el informe tiene
    # que decirlo, no dejar que se descubra por la ausencia de operaciones.
    drawdown_pct = (
        (peak_state - book) / peak_state * 100
        if peak_state and peak_state > 0
        else 0.0
    )
    halt_at = None
    if limits and limits.get("soft_brakes") and limits.get("max_drawdown_pct"):
        halt_at = round(
            float(limits["max_drawdown_pct"]) * float(limits.get("halt_multiple") or 1),
            4,
        )
    halted = bool(halt_at is not None and drawdown_pct >= halt_at)

    differences: dict[str, float | int] = {}
    if state is not None and abs(state - book) > EQUITY_TOLERANCE:
        differences["state_vs_book"] = round(state - book, 8)
    if curve is not None and abs(curve - book) > EQUITY_TOLERANCE:
        differences["curve_vs_book"] = round(curve - book, 8)
    if peak_state is not None and abs(peak_state - peak_expected) > EQUITY_TOLERANCE:
        differences["peak_vs_curve"] = round(peak_state - peak_expected, 8)
    if rows != trades:
        differences["rows_vs_trades"] = rows - trades

    return {
        "checked": True,
        "capital": float(capital),
        "trades": trades,
        "curve_rows": rows,
        "book_equity": round(book, 8),
        "state_equity": state,
        "curve_equity": curve,
        "peak_equity": peak_state,
        "peak_expected": round(peak_expected, 8),
        "peak_reset_at": reset_at,
        "differences": differences,
        "consistent": not differences,
        "drawdown_pct": drawdown_pct,
        "halt_at_pct": halt_at,
        "halted": halted,
    }


def diagnose(
    db_path: str | Path,
    capital: float = 25_000.0,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists():
        return {"path": str(path), "exists": False, "errors": ["database not found"]}

    uri = f"file:{path.as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {
            row["name"]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        counts: dict[str, int] = {}
        for table in TABLES:
            if table not in tables:
                counts[table] = -1
                continue
            counts[table] = connection.execute(
                f"SELECT COUNT(*) AS c FROM {table}"
            ).fetchone()["c"]

        version_row = (
            connection.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
            if "schema_migrations" in tables
            else None
        )
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        journal = connection.execute("PRAGMA journal_mode").fetchone()[0]

        return {
            "path": str(path),
            "exists": True,
            "schema_version": int(version_row["v"]) if version_row and version_row["v"] else 0,
            "journal_mode": str(journal).lower(),
            "integrity": integrity,
            "tables": counts,
            "missing_tables": sorted(table for table, count in counts.items() if count < 0),
            "ledger": _ledger_anomalies(connection, tables),
            "books": _books(connection, tables, capital, limits),
            "size_bytes": path.stat().st_size,
            "wal_bytes": path.with_suffix(path.suffix + "-wal").stat().st_size
            if path.with_suffix(path.suffix + "-wal").exists()
            else 0,
        }
    finally:
        connection.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de solo lectura")
    parser.add_argument("--db", default="data/terminal.db")
    parser.add_argument(
        "--capital", type=float, default=25_000.0, help="capital inicial del libro"
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="carpeta del perfil: toma capital y tope de drawdown de su config",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="sale con 1 si hay desviaciones, filas imposibles o parada dura",
    )
    args = parser.parse_args(argv)

    capital = args.capital
    limits = None
    if args.profile:
        config = Path(args.profile) / "config.json"
        try:
            document = json.loads(config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            document = {}
        risk = document.get("risk") or {}
        capital = float(risk.get("initial_capital") or capital)
        limits = {
            "max_drawdown_pct": float(risk.get("max_drawdown_pct") or 0.0),
            "halt_multiple": float(risk.get("soft_brake_halt_multiple") or 1.0),
            "soft_brakes": bool(risk.get("soft_brakes")),
        }
    report = diagnose(args.db, capital, limits)
    print(json.dumps(report, indent=2))
    if not args.strict:
        return 0

    problems: list[str] = []
    if not report.get("exists"):
        problems.append("sin base")
    if report.get("integrity") != "ok":
        problems.append("integridad")
    if report.get("missing_tables"):
        problems.append("faltan tablas")
    if (report.get("ledger") or {}).get("impossible"):
        problems.append("filas imposibles")
    books = report.get("books") or {}
    if books.get("checked") and not books.get("consistent"):
        problems.append("libros descuadrados")
    if books.get("halted"):
        problems.append("parada dura")
    if problems:
        print("revisar: " + ", ".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
