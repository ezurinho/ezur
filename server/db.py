"""SQLite store in WAL mode.

The interface is intentionally narrow so a PostgreSQL implementation can replace
this module without touching callers.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .migrations import CURRENT_VERSION, apply_migrations
from .models import TradeRecord

EVENTS_RETENTION = 5000
SCHEMA_VERSION = CURRENT_VERSION


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class _LockedConnection:
    """One SQLite connection, serialised across threads.

    `sqlite3` with `check_same_thread=False` lets any thread call `commit`, and
    the engine (event loop) and a request handler can both be inside
    `with self.conn:` at the same time — which surfaces as
    «cannot commit - no transaction is active». A re-entrant lock is the least
    invasive truthful fix: writes are serialised, reads stay untouched.
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        self._lock = threading.RLock()

    def execute(self, *args: Any, **kwargs: Any):
        with self._lock:
            return self._conn.execute(*args, **kwargs)

    def executemany(self, *args: Any, **kwargs: Any):
        with self._lock:
            return self._conn.executemany(*args, **kwargs)

    def commit(self) -> None:
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        with self._lock:
            self._conn.rollback()

    def __enter__(self):
        self._lock.acquire()
        self._conn.__enter__()
        return self._conn

    def __exit__(self, *exc: Any):
        try:
            return self._conn.__exit__(*exc)
        finally:
            self._lock.release()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._conn, item)

    def __setattr__(self, item: str, value: Any) -> None:
        # `row_factory` and `text_factory` are attributes of the real connection;
        # setting them on the proxy would silently keep returning tuples.
        if item in {"_conn", "_lock"}:
            object.__setattr__(self, item, value)
        else:
            setattr(self._conn, item, value)


class Store:
    def __init__(self, db_path: str | Path = "data/terminal.db") -> None:
        path = Path(db_path)
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.conn = _LockedConnection(
            sqlite3.connect(str(path), check_same_thread=False, timeout=10.0)
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        apply_migrations(self.conn)

    def close(self) -> None:
        self.conn.close()

    def backup(self, target: str | Path) -> Path:
        """Copia consistente con SQLite online backup, incluyendo el WAL."""
        path = Path(target)
        if path.resolve() == self.path.resolve():
            raise ValueError("backup target must differ from the live database")
        path.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(str(path))
        try:
            self.conn.backup(destination)
        finally:
            destination.close()
        return path

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
        return self.insert_trade_once(trade)[0]

    def insert_trade_once(self, trade: TradeRecord) -> tuple[int, bool]:
        """Inserta la operación y dice si era nueva.

        Una operación cerrada es única: mismo modo, mismo instrumento, mismas
        horas y mismos precios. Un reinicio con backfill volvió a insertar una
        fila idéntica y el P&L del día se contó dos veces. El segundo valor
        importa: quien lleva la equity en memoria necesita saber si esta
        operación ya se contabilizó antes de volver a sumarla.

        Una salida anterior a la entrada no es una operación: es la huella de
        una barra vieja ejecutándose sobre una posición viva. Se rechaza en voz
        alta en vez de guardar un número que ninguna pantalla puede explicar.
        """
        if trade.closed_ts < trade.opened_ts:
            raise ValueError(
                "operación imposible: cierra "
                f"{_iso(trade.closed_ts)} antes de abrir {_iso(trade.opened_ts)}"
            )
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO trades (
                    symbol, side, units, entry_price, exit_price, stop_price,
                    target_price, opened_ts, closed_ts, pnl_gross, fees,
                    funding, pnl_net, r_multiple, exit_reason, mode, signal_key,
                    diagnostics
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT DO NOTHING
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
                    trade.funding,
                    trade.pnl_net,
                    trade.r_multiple,
                    trade.exit_reason,
                    trade.mode,
                    trade.signal_key,
                    json.dumps(trade.diagnostics),
                ),
            )
        if cur.rowcount > 0:
            return int(cur.lastrowid or 0), True
        existing = self._find_trade(trade)
        return (int(existing["id"]) if existing else 0), False

    def _find_trade(self, trade: TradeRecord) -> sqlite3.Row | None:
        row = self.conn.execute(
            """
            SELECT id FROM trades
             WHERE mode=? AND symbol=? AND side=? AND opened_ts=? AND closed_ts=?
               AND entry_price=? AND exit_price=? AND units=?
            """,
            (
                trade.mode,
                trade.symbol,
                trade.side,
                _iso(trade.opened_ts),
                _iso(trade.closed_ts),
                trade.entry_price,
                trade.exit_price,
                trade.units,
            ),
        ).fetchone()
        if row is not None or not trade.signal_key:
            return row
        # La misma señal puede volver a cerrarse con otra barra (posición
        # restaurada). No es la misma fila, pero sí la misma operación: se
        # devuelve la que ya está para que el llamante no la sume otra vez.
        return self.conn.execute(
            "SELECT id FROM trades WHERE mode=? AND signal_key=? LIMIT 1",
            (trade.mode, trade.signal_key),
        ).fetchone()

    def list_trades(
        self,
        limit: int = 100,
        offset: int = 0,
        mode: str | None = None,
        side: str | None = None,
        start: str | datetime | None = None,
        end: str | datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Most recent first, with optional filters on mode, side and date range."""
        clauses: list[str] = []
        params: list[Any] = []
        if mode:
            clauses.append("mode = ?")
            params.append(mode)
        if side:
            clauses.append("side = ?")
            params.append(side)
        if start is not None:
            clauses.append("closed_ts >= ?")
            params.append(_iso(start) if isinstance(start, datetime) else start)
        if end is not None:
            clauses.append("closed_ts <= ?")
            params.append(_iso(end) if isinstance(end, datetime) else end)
        query = "SELECT * FROM trades"
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY closed_ts DESC, id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        return [dict(row) for row in self.conn.execute(query, params)]

    def all_trades(
        self, limit: int = 1_000_000, mode: str | None = None
    ) -> list[TradeRecord]:
        return [
            TradeRecord.model_validate(row_to_trade(row))
            for row in reversed(self.list_trades(limit=limit, mode=mode))
        ]

    def realized_pnl(self, mode: str | None = None) -> float:
        query = "SELECT COALESCE(SUM(pnl_net), 0) AS total FROM trades"
        params: tuple[Any, ...] = ()
        if mode is not None:
            query += " WHERE mode = ?"
            params = (mode,)
        row = self.conn.execute(query, params).fetchone()
        return float(row["total"] or 0.0)

    def count_trades(self, mode: str | None = None) -> int:
        query = "SELECT COUNT(*) AS c FROM trades"
        params: tuple[Any, ...] = ()
        if mode is not None:
            query += " WHERE mode = ?"
            params = (mode,)
        return int(self.conn.execute(query, params).fetchone()["c"])

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
            # La retención se corta por id, no con un NOT IN sobre toda la
            # tabla: esa subconsulta se recorre entera en cada evento y en un
            # backtest son miles de eventos (16 s de 35 s de una corrida).
            cutoff = self.conn.execute(
                "SELECT id FROM events ORDER BY id DESC LIMIT 1 OFFSET ?",
                (EVENTS_RETENTION - 1,),
            ).fetchone()
            if cutoff is not None:
                self.conn.execute("DELETE FROM events WHERE id < ?", (cutoff[0],))
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
        # `run_id` es aleatorio desde que identifica la ejecución, así que el
        # orden cronológico va por `rowid` (la fila se inserta al terminar la
        # corrida). El cursor sigue siendo el run_id, que el cliente trata como
        # opaco: se traduce a su rowid para no comparar identificadores
        # aleatorios, que repetía o saltaba corridas entre páginas.
        query = "SELECT rowid AS seq, run_id, ts, payload FROM backtests"
        params: list[Any] = []
        if cursor:
            anchor = self.conn.execute(
                "SELECT rowid FROM backtests WHERE run_id = ?", (cursor,)
            ).fetchone()
            if anchor is None:
                return {"runs": [], "has_more": False, "next_cursor": None}
            query += " WHERE rowid < ?"
            params.append(anchor["rowid"])
        query += " ORDER BY rowid DESC LIMIT ?"
        params.append(limit + 1)
        raw = [dict(row) for row in self.conn.execute(query, params)]
        has_more = len(raw) > limit
        raw = raw[:limit]
        runs: list[dict[str, Any]] = []
        for row in raw:
            try:
                payload = json.loads(row["payload"])
            except (TypeError, ValueError):
                payload = {}
            runs.append(
                {
                    "run_id": row["run_id"],
                    "ts": row["ts"],
                    "strategy_id": payload.get("strategy_id"),
                    "strategy_version": payload.get("strategy_version"),
                    "dataset_id": payload.get("dataset_id"),
                    "run_group": payload.get("run_group"),
                    "trades": len(payload.get("trades", [])),
                }
            )
        return {
            "runs": runs,
            "has_more": has_more,
            "next_cursor": runs[-1]["run_id"] if has_more and runs else None,
        }

    # --- maintenance ------------------------------------------------------
    def stats_counts(self) -> dict[str, int]:
        return {
            "trades": int(self.conn.execute("SELECT COUNT(*) c FROM trades").fetchone()["c"]),
            "equity": int(self.conn.execute("SELECT COUNT(*) c FROM equity").fetchone()["c"]),
            "events": int(self.conn.execute("SELECT COUNT(*) c FROM events").fetchone()["c"]),
            "backtests": int(self.conn.execute("SELECT COUNT(*) c FROM backtests").fetchone()["c"]),
        }

    def reset_stats(self, *, include_backtests: bool = False, mode: str | None = None) -> dict[str, int]:
        """Delete operational history. Backtests are preserved by default.

        También se borra el estado operativo de `kv`: si sobrevive, el próximo
        arranque restaura una posición que ya no está en el libro o mide el
        drawdown contra un pico de una cuenta que ya no existe. `emergency` se
        conserva: es un interruptor manual, no historial.
        """
        before = self.stats_counts()
        with self.conn:
            if include_backtests:
                self.conn.execute("DELETE FROM trades")
            elif mode is not None:
                self.conn.execute("DELETE FROM trades WHERE mode = ?", (mode,))
            else:
                self.conn.execute("DELETE FROM trades")
            self.conn.execute("DELETE FROM equity")
            self.conn.execute("DELETE FROM events")
            self.conn.execute(
                "DELETE FROM kv WHERE key IN ('equity', 'peak_equity', 'day_stats', "
                "'session_id', 'last_exit_ts', 'position', 'heartbeat')"
            )
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
        "funding": row.get("funding", 0.0),
        "pnl_net": row["pnl_net"],
        "r_multiple": row["r_multiple"],
        "exit_reason": row["exit_reason"],
        "mode": row["mode"],
        "signal_key": row["signal_key"],
        "diagnostics": json.loads(row["diagnostics"] or "{}"),
    }
