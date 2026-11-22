"""SQLite store in WAL mode.

The interface is intentionally narrow so a PostgreSQL implementation can replace
this module without touching callers.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .migrations import CURRENT_VERSION, apply_migrations
from .models import TradeRecord

EVENTS_RETENTION = 5000
SCHEMA_VERSION = CURRENT_VERSION


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class Store:
    def __init__(self, db_path: str | Path = "data/terminal.db") -> None:
        path = Path(db_path)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(self.conn)

    def close(self) -> None:
        self.conn.close()

    # --- schema -----------------------------------------------------------
    def schema_version(self) -> int:
        row = self.conn.execute(
            "SELECT MAX(version) AS v FROM schema_migrations"
        ).fetchone()
        return int(row["v"] or 0)

    def tables(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row["name"] for row in rows}

    # --- trades -----------------------------------------------------------
    def insert_trade(self, trade: TradeRecord) -> int:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO trades (
                    symbol, side, units, entry_price, exit_price, stop_price,
                    target_price, opened_ts, closed_ts, pnl_gross, fees,
                    pnl_net, r_multiple, exit_reason, mode, signal_key,
                    diagnostics
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    trade.symbol,
                    trade.side,
                    trade.units,
                    trade.entry_price,
                    trade.exit_price,
                    trade.stop_price,
                    trade.target_price,
                    _iso(trade.opened_ts),
                    _iso(trade.closed_ts),
                    trade.pnl_gross,
                    trade.fees,
                    trade.pnl_net,
                    trade.r_multiple,
                    trade.exit_reason,
                    trade.mode,
                    trade.signal_key,
                    json.dumps(trade.diagnostics),
                ),
            )
        return int(cur.lastrowid or 0)

    def list_trades(
        self, limit: int = 100, offset: int = 0, mode: str | None = None
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM trades"
        params: list[Any] = []
        if mode:
            query += " WHERE mode = ?"
            params.append(mode)
        query += " ORDER BY closed_ts DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in self.conn.execute(query, params)]

    def all_trades(self, limit: int = 1_000_000) -> list[TradeRecord]:
        return [
            TradeRecord.model_validate(row_to_trade(row))
            for row in reversed(self.list_trades(limit=limit))
        ]

    def count_trades(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS c FROM trades").fetchone()["c"])

    # --- events -----------------------------------------------------------
    def insert_event(
        self,
        level: str,
        category: str,
        message: str,
        meta: dict[str, Any] | None = None,
        ts: datetime | None = None,
    ) -> int:
        stamp = _iso(ts or datetime.now(timezone.utc))
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO events (ts, level, category, message, meta) VALUES (?,?,?,?,?)",
                (stamp, level, category, message, json.dumps(meta or {})),
            )
            self.conn.execute(
                """
                DELETE FROM events WHERE id NOT IN (
                    SELECT id FROM events ORDER BY id DESC LIMIT ?
                )
                """,
                (EVENTS_RETENTION,),
            )
        return int(cur.lastrowid or 0)

    def list_events(self, limit: int = 200, level: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM events"
        params: list[Any] = []
        if level:
            query += " WHERE level = ?"
            params.append(level)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        return [dict(row) for row in self.conn.execute(query, params)]

    def count_events(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) AS c FROM events").fetchone()["c"])

    # --- equity -----------------------------------------------------------
    def append_equity(self, equity: float, ts: datetime | None = None) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO equity (ts, equity) VALUES (?, ?)",
                (_iso(ts or datetime.now(timezone.utc)), equity),
            )

    def equity_curve(self, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT ts, equity FROM equity ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in reversed(rows)]

    # --- key/value --------------------------------------------------------
    def kv_get(self, key: str) -> Any:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None

    def kv_set(self, key: str, value: Any) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, json.dumps(value, default=str)),
            )

    def kv_delete(self, key: str) -> None:
        with self.conn:
            self.conn.execute("DELETE FROM kv WHERE key = ?", (key,))

    # --- backtests --------------------------------------------------------
    def save_backtest(self, run_id: str, payload: dict[str, Any]) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT INTO backtests (run_id, ts, payload) VALUES (?,?,?) "
                "ON CONFLICT(run_id) DO UPDATE SET payload = excluded.payload",
                (run_id, _iso(datetime.now(timezone.utc)), json.dumps(payload, default=str)),
            )

    def get_backtest(self, run_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT payload FROM backtests WHERE run_id = ?", (run_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_backtest_runs(self, cursor: str | None = None, limit: int = 25) -> dict[str, Any]:
        query = "SELECT run_id, ts FROM backtests"
        params: list[Any] = []
        if cursor:
            query += " WHERE run_id < ?"
            params.append(cursor)
        query += " ORDER BY run_id DESC LIMIT ?"
        params.append(limit + 1)
        rows = [dict(row) for row in self.conn.execute(query, params)]
        has_more = len(rows) > limit
        rows = rows[:limit]
        return {
            "runs": rows,
            "has_more": has_more,
            "next_cursor": rows[-1]["run_id"] if has_more and rows else None,
        }

    # --- maintenance ------------------------------------------------------
    def stats_counts(self) -> dict[str, int]:
        return {
            "trades": int(self.conn.execute("SELECT COUNT(*) c FROM trades").fetchone()["c"]),
            "equity": int(self.conn.execute("SELECT COUNT(*) c FROM equity").fetchone()["c"]),
            "events": int(self.conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]),
            "backtests": int(self.conn.execute("SELECT COUNT(*) c FROM backtests").fetchone()["c"]),
        }

    def reset_stats(self, *, include_backtests: bool = False) -> dict[str, int]:
        """Delete operational history. Backtests are preserved by default."""
        before = self.stats_counts()
        with self.conn:
            self.conn.execute("DELETE FROM trades")
            self.conn.execute("DELETE FROM equity")
            self.conn.execute("DELETE FROM events")
            if include_backtests:
                self.conn.execute("DELETE FROM backtest_results")
                self.conn.execute("DELETE FROM backtest_runs")
                self.conn.execute("DELETE FROM backtests")
        after = self.stats_counts()
        return {key: before[key] - after[key] for key in before}

    def executemany(self, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
        with self.conn:
            self.conn.executemany(sql, rows)


def row_to_trade(row: dict[str, Any]) -> dict[str, Any]:
    """Map a stored row back to the TradeRecord shape."""
    return {
        "symbol": row["symbol"],
        "side": row["side"],
        "units": row["units"],
        "entry_price": row["entry_price"],
        "exit_price": row["exit_price"],
        "stop_price": row["stop_price"],
        "target_price": row["target_price"],
        "opened_ts": row["opened_ts"],
        "closed_ts": row["closed_ts"],
        "pnl_gross": row["pnl_gross"],
        "fees": row["fees"],
        "pnl_net": row["pnl_net"],
        "r_multiple": row["r_multiple"],
        "exit_reason": row["exit_reason"],
        "mode": row["mode"],
        "signal_key": row["signal_key"],
        "diagnostics": json.loads(row["diagnostics"] or "{}"),
    }
