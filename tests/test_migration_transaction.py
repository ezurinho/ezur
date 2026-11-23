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
