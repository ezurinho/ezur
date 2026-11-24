"""Una migración que falla a mitad no puede dejar trabajo a medias."""

from __future__ import annotations

import sqlite3

import pytest

from server import migrations


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row[0] for row in rows}


def test_a_failed_migration_leaves_nothing_behind(tmp_path, monkeypatch):
    conn = sqlite3.connect(tmp_path / "half.db")
    try:
        migrations.apply_migrations(conn)

        monkeypatch.setitem(
            migrations.MIGRATIONS,
            99,
            [
                "CREATE TABLE half_done (id INTEGER)",
                "INSERT INTO tabla_que_no_existe VALUES (1)",
            ],
        )

        with pytest.raises(sqlite3.Error):
            migrations.apply_migrations(conn)

        assert "half_done" not in _tables(conn)
        assert 99 not in migrations.applied_versions(conn)
        # Y la base sigue usable: no queda una transacción abierta.
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 0
    finally:
        conn.close()


def test_signal_deduplication_archives_instead_of_erasing(tmp_path):
    conn = sqlite3.connect(tmp_path / "legacy.db")
    try:
        for statement in migrations.MIGRATIONS[1]:
            conn.execute(statement)
        rows = [
            ("PRIMARY", "long", 1, 100.0, 99.0, 99.5, 101.0,
             "2026-01-01T10:00:00+00:00", "2026-01-01T10:01:00+00:00",
             -1.0, 0.0, -1.0, -1.0, "stop", "paper", "same-signal"),
            ("PRIMARY", "long", 1, 100.0, 98.0, 99.5, 101.0,
             "2026-01-01T10:00:00+00:00", "2026-01-01T10:02:00+00:00",
             -2.0, 0.0, -2.0, -2.0, "stop", "paper", "same-signal"),
        ]
        conn.executemany(
            """INSERT INTO trades(symbol, side, units, entry_price, exit_price,
               stop_price, target_price, opened_ts, closed_ts, pnl_gross, fees,
               pnl_net, r_multiple, exit_reason, mode, signal_key)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        migrations.apply_migrations(conn)
        assert conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0] == 1
        archived = conn.execute("SELECT exit_price, signal_key FROM trade_archive").fetchall()
        assert archived == [(98.0, "same-signal")]
    finally:
        conn.close()
