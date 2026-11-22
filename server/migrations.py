"""Versioned schema migrations.

Each migration is a list of statements applied once and recorded in
``schema_migrations``. Adding a version means appending to ``MIGRATIONS``;
never editing an already-applied entry.
"""

from __future__ import annotations

import sqlite3

CURRENT_VERSION = 1

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
        for statement in MIGRATIONS[version]:
            conn.execute(statement)
        conn.execute(
            "INSERT INTO schema_migrations (version) VALUES (?)", (version,)
        )
        conn.commit()
    return max(done | set(MIGRATIONS)) if MIGRATIONS else 0
