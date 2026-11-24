"""Versioned schema migrations.

Each migration is a list of statements applied once and recorded in
``schema_migrations``. Adding a version means appending to ``MIGRATIONS``;
never editing an already-applied entry.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

CURRENT_VERSION = 4

MIGRATIONS: dict[int, list[str]] = {
    1: [
        """
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            units INTEGER NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL NOT NULL,
            stop_price REAL,
            target_price REAL,
            opened_ts TEXT NOT NULL,
            closed_ts TEXT NOT NULL,
            pnl_gross REAL NOT NULL DEFAULT 0,
            fees REAL NOT NULL DEFAULT 0,
            pnl_net REAL NOT NULL DEFAULT 0,
            r_multiple REAL NOT NULL DEFAULT 0,
            exit_reason TEXT NOT NULL DEFAULT '',
            mode TEXT NOT NULL DEFAULT 'paper',
            signal_key TEXT NOT NULL DEFAULT '',
            diagnostics TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_trades_closed ON trades(closed_ts)",
        "CREATE INDEX IF NOT EXISTS idx_trades_mode ON trades(mode)",
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            level TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            meta TEXT NOT NULL DEFAULT '{}'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts)",
        """
        CREATE TABLE IF NOT EXISTS equity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            equity REAL NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS kv (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtests (
            run_id TEXT PRIMARY KEY,
            ts TEXT NOT NULL,
            payload TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtest_runs (
            run_id TEXT PRIMARY KEY,
            dataset_id TEXT NOT NULL,
            strategy_id TEXT NOT NULL,
            created_ts TEXT NOT NULL,
            label TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtest_results (
            run_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            FOREIGN KEY(run_id) REFERENCES backtest_runs(run_id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS backtest_ledger_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            error TEXT
        )
        """,
    ],
}


# v2: la misma operación cerrada no puede entrar dos veces. Un reinicio con
# backfill insertó una fila idéntica y el P&L del día se contó dos veces; el
# índice único es lo que garantiza el «una vez». La deduplicación va antes: el
# índice no se puede crear sobre una tabla con repetidos, y borrar sin dejar
# rastro de cuántas filas se tocaron sería otra forma de mentir.
MIGRATIONS[2] = [
    """
    CREATE TABLE IF NOT EXISTS trade_archive AS SELECT * FROM trades WHERE 0
    """,
    """
    INSERT INTO trade_archive
    SELECT * FROM trades
     WHERE id NOT IN (
        SELECT MIN(id) FROM trades
         GROUP BY mode, symbol, side, opened_ts, closed_ts,
                  entry_price, exit_price, units
     )
    """,
    """
    DELETE FROM trades
     WHERE id NOT IN (
        SELECT MIN(id) FROM trades
         GROUP BY mode, symbol, side, opened_ts, closed_ts,
                  entry_price, exit_price, units
     )
    """,
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_unique
         ON trades(mode, symbol, side, opened_ts, closed_ts,
                   entry_price, exit_price, units)""",
]

# v3: una señal se ejecuta una sola vez, aunque la posición se cierre dos veces
# (reinicio con posición restaurada, backfill fuera de orden). El índice por
# precios y horas no lo veía porque el segundo cierre cambia hora y precio; el
# signal_key sí es el mismo. Los cierres antiguos lo llevan vacío y quedan fuera
# del índice parcial.
MIGRATIONS[3] = [
    """
    INSERT INTO trade_archive
    SELECT * FROM trades
     WHERE signal_key <> ''
       AND id NOT IN (
        SELECT MIN(id) FROM trades
         WHERE signal_key <> ''
         GROUP BY mode, signal_key
     )
    """,
    """
    DELETE FROM trades
     WHERE signal_key <> ''
       AND id NOT IN (
        SELECT MIN(id) FROM trades
         WHERE signal_key <> ''
         GROUP BY mode, signal_key
     )
    """,
    """CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_signal
         ON trades(mode, signal_key)
      WHERE signal_key <> ''""",
]

# v4: el P&L neto tiene que poder reconstruirse desde sus componentes. El
# funding se guarda por operación (positivo = cobrado, negativo = pagado); las
# filas antiguas quedan a 0, que es el valor correcto para el histórico que no
# lo registró. No se inventa un cargo que el motor de papel no haya medido.
MIGRATIONS[4] = [
    "ALTER TABLE trades ADD COLUMN funding REAL NOT NULL DEFAULT 0",
]

DUPLICATE_QUERY = """
    SELECT COUNT(*) FROM trades
     WHERE id NOT IN (
        SELECT MIN(id) FROM trades
         GROUP BY mode, symbol, side, opened_ts, closed_ts,
                  entry_price, exit_price, units
     )
"""

DUPLICATE_SIGNAL_QUERY = """
    SELECT COUNT(*) FROM trades
     WHERE signal_key <> ''
       AND id NOT IN (
        SELECT MIN(id) FROM trades
         WHERE signal_key <> ''
         GROUP BY mode, signal_key
     )
"""


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_ts TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def applied_versions(conn: sqlite3.Connection) -> set[int]:
    _ensure_version_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row[0]) for row in rows}


def apply_migrations(conn: sqlite3.Connection) -> int:
    """Apply every pending migration. Idempotent."""
    _ensure_version_table(conn)
    done = applied_versions(conn)
    for version in sorted(MIGRATIONS):
        if version in done:
            continue
        removed = 0
        if version == 2:
            removed = int(conn.execute(DUPLICATE_QUERY).fetchone()[0] or 0)
        elif version == 3:
            removed = int(conn.execute(DUPLICATE_SIGNAL_QUERY).fetchone()[0] or 0)
        # SAVEPOINT y no BEGIN: funciona igual si el llamante ya tenía una
        # transacción abierta, y en este driver el DDL sólo entra en la transacción
        # cuando se abre una de forma explícita.
        savepoint = f"migration_{version}"
        conn.execute(f"SAVEPOINT {savepoint}")
        try:
            for statement in MIGRATIONS[version]:
                conn.execute(statement)
            if removed:
                conn.execute(
                    "INSERT INTO events (ts, level, category, message, meta) VALUES (?,?,?,?,?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        "warn",
                        "maintenance",
                        f"{removed} operación(es) duplicada(s) eliminadas al crear el índice único",
                        "{}",
                    ),
                )
            conn.execute(
                "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
            )
        except sqlite3.Error:
            # Media migración es peor que ninguna: la deduplicación sin su índice
            # dejaría la tabla limpia y sin protección, y el commit posterior la
            # consolidaría igual.
            conn.execute(f"ROLLBACK TO {savepoint}")
            conn.execute(f"RELEASE {savepoint}")
            raise
        conn.execute(f"RELEASE {savepoint}")
        conn.commit()
    return max(done | set(MIGRATIONS)) if MIGRATIONS else 0
