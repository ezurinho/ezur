"""El reconstruir de equity: curva, estado y copia de seguridad."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from server import equity
from server.migrations import apply_migrations


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "terminal.db"
    conn = sqlite3.connect(path)
    try:
        apply_migrations(conn)
        conn.executemany(
            "INSERT INTO trades "
            "(symbol, side, units, entry_price, exit_price, opened_ts, closed_ts, signal_key, pnl_net) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            [
                ("BTC", "long", 1, 100.0, 99.0, "2026-11-23T01:00:00+00:00", "2026-11-23T01:03:00+00:00", "a", -133.09),
                ("BTC", "long", 1, 100.0, 101.0, "2026-11-23T03:00:00+00:00", "2026-11-23T01:57:00+00:00", "b", 105.18),
                ("BTC", "long", 1, 100.0, 99.0, "2026-11-23T04:00:00+00:00", "2026-11-23T02:27:00+00:00", "c", -146.32),
            ],
        )
        conn.executemany(
            "INSERT INTO equity (ts, equity) VALUES (?,?)",
            [
                ("2026-11-23T01:03:00+00:00", 24866.91),
                ("2026-11-23T02:27:00+00:00", 24720.59),
                ("2026-11-23T09:00:00+00:00", 24574.27),  # punto fantasma
            ],
        )
        conn.execute("INSERT INTO kv (key, value) VALUES ('equity', ?)", (json.dumps(24574.27),))
        conn.commit()
    finally:
        conn.close()
    return path


def test_la_curva_acumula_en_orden_de_cierre(tmp_path):
    planned = equity.plan(_db(tmp_path), 25000.0)

    assert [p["equity"] for p in planned["curve"]] == pytest.approx(
        [24866.91, 24972.09, 24825.77]
    )
    assert planned["last_equity"] == pytest.approx(24825.77)


def test_el_dia_se_recalcula_con_las_operaciones_reales(tmp_path):
    stats = equity.day_stats(
        [
            {"closed_ts": "2026-11-22T20:00:00+00:00", "pnl_net": -10.0},
            {"closed_ts": "2026-11-23T01:03:00+00:00", "pnl_net": -133.09},
            {"closed_ts": "2026-11-23T01:57:00+00:00", "pnl_net": 105.18},
            {"closed_ts": "2026-11-23T02:27:00+00:00", "pnl_net": -146.32},
        ]
    )

    assert stats == {
        "trades": 3,
        "wins": 1,
        "losses": 2,
        "pnl": pytest.approx(-174.23),
        "consecutive_losses": 1,
    }


def test_apply_deja_curva_y_estado_en_la_misma_cifra(tmp_path):
    db = _db(tmp_path)

    backup = equity.apply(db, 25000.0, backup_dir=tmp_path / "copias")

    assert backup.is_file()
    after = equity.current(db)
    assert after["rows"] == 3
    assert after["last_equity"] == pytest.approx(24825.77)
    assert after["kv_equity"] == pytest.approx(24825.77)
    assert after["kv_day_stats"]["trades"] == 3


def test_apply_es_idempotente(tmp_path):
    db = _db(tmp_path)
    equity.apply(db, 25000.0, backup_dir=tmp_path / "copias")
    first = equity.current(db)
    equity.apply(db, 25000.0, backup_dir=tmp_path / "copias")
    second = equity.current(db)

    assert first == second


def test_el_modo_seco_no_escribe(tmp_path):
    db = _db(tmp_path)
    before = equity.current(db)

    assert equity.main(["--db", str(db), "--capital", "25000"]) == 0

    assert equity.current(db) == before
