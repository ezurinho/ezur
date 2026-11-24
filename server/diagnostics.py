"""Read-only diagnostics for the SQLite store.

Never creates tables, never writes, never takes a backup. Safe to run against a
live database.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
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


def _ledger_anomalies(connection: sqlite3.Connection, tables: set[str]) -> dict[str, Any]:
    """Filas que ningún veredicto debería haber producido.

    Una salida anterior a la entrada delata una barra vieja ejecutada sobre una
    posición viva; dos filas con el mismo signal_key son la misma operación
    contada dos veces. Se cuentan, no se corrigen: este comando es de lectura.
    """
    if "trades" not in tables:
        return {"impossible": [], "duplicate_signals": [], "without_signal_key": 0}
    impossible = [
        dict(row)
        for row in connection.execute(
            "SELECT id, opened_ts, closed_ts FROM trades WHERE closed_ts < opened_ts ORDER BY id"
        )
    ]
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


def diagnose(db_path: str | Path) -> dict[str, Any]:
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
            "size_bytes": path.stat().st_size,
            "wal_bytes": path.with_suffix(path.suffix + "-wal").stat().st_size
            if path.with_suffix(path.suffix + "-wal").exists()
            else 0,
        }
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnóstico de solo lectura")
    parser.add_argument("--db", default="data/terminal.db")
    args = parser.parse_args()
    print(json.dumps(diagnose(args.db), indent=2))


if __name__ == "__main__":
    main()
