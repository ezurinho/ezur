"""El reconstruir de equity: curva, estado y copia de seguridad."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
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


def _latido(db: Path, cuando: datetime) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES ('heartbeat', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(cuando.isoformat()),),
        )
        conn.commit()
    finally:
        conn.close()


def test_no_reescribe_con_el_motor_vivo(tmp_path, capsys):
    from datetime import datetime, timezone

    db = _db(tmp_path)
    _latido(db, datetime.now(timezone.utc))

    code = equity.main(["--db", str(db), "--apply"])

    assert code == 2
    assert "motor está vivo" in capsys.readouterr().out


def test_force_reescribe_aunque_el_motor_este_vivo(tmp_path):
    from datetime import datetime, timezone

    db = _db(tmp_path)
    _latido(db, datetime.now(timezone.utc))

    code = equity.main(["--db", str(db), "--apply", "--force"])

    assert code == 0


def test_un_latido_viejo_no_bloquea(tmp_path):
    from datetime import datetime, timedelta, timezone

    db = _db(tmp_path)
    _latido(db, datetime.now(timezone.utc) - timedelta(hours=1))

    assert equity.engine_alive(db) is False


def test_el_reconstruir_arregla_tambien_el_pico(tmp_path):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES ('peak_equity', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(1.0),),
        )
        conn.commit()
    finally:
        conn.close()

    equity.apply(db, 25000.0, backup_dir=tmp_path / "copias")

    assert equity.current(db)["kv_peak"] == pytest.approx(25000.0)


def test_el_pico_reconstruido_recoge_la_curva(tmp_path):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO trades "
            "(symbol, side, units, entry_price, exit_price, opened_ts, closed_ts, signal_key, pnl_net) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "BTC",
                "long",
                1,
                100.0,
                103.0,
                "2026-11-23T09:00:00+00:00",
                "2026-11-23T09:30:00+00:00",
                "alta",
                300.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    equity.apply(db, 25000.0, backup_dir=tmp_path / "copias")

    # 25.000 - 133,09 + 105,18 - 146,32 + 300 = 25.125,77
    assert equity.current(db)["kv_peak"] == pytest.approx(25_125.77)

def test_reset_peak_pone_el_pico_en_la_equity_del_libro(tmp_path):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES ('peak_equity', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(30_000.0),),
        )
        conn.commit()
    finally:
        conn.close()

    result = equity.reset_peak(db, 25_000.0, backup_dir=tmp_path / "copias")

    assert result["before"] == pytest.approx(30_000.0)
    assert result["after"] == pytest.approx(24_825.77)
    assert Path(result["backup"]).is_file()
    assert equity.current(db)["kv_peak"] == pytest.approx(24_825.77)

    conn = sqlite3.connect(db)
    try:
        message = conn.execute(
            "SELECT message FROM events WHERE category = 'risk' ORDER BY id DESC LIMIT 1"
        ).fetchone()[0]
    finally:
        conn.close()
    assert "pico reiniciado" in message


def test_reset_peak_se_niega_con_el_motor_vivo(tmp_path, capsys):
    from datetime import datetime, timezone

    db = _db(tmp_path)
    _latido(db, datetime.now(timezone.utc))

    assert equity.main(["--db", str(db), "--reset-peak"]) == 2
    assert "motor está vivo" in capsys.readouterr().out


def test_reset_peak_por_cli_deja_el_pico_y_la_copia(tmp_path, capsys):
    db = _db(tmp_path)

    assert equity.main(["--db", str(db), "--reset-peak", "--capital", "25000"]) == 0

    out = capsys.readouterr().out
    assert "pico reiniciado" in out
    assert "copia:" in out
    assert equity.current(db)["kv_peak"] == pytest.approx(24_825.77)

def test_apply_no_baja_un_pico_mas_alto_que_la_curva(tmp_path):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES ('peak_equity', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(30_000.0),),
        )
        conn.commit()
    finally:
        conn.close()

    equity.apply(db, 25_000.0, backup_dir=tmp_path / "copias")

    assert equity.current(db)["kv_peak"] == pytest.approx(30_000.0)


def test_el_reporte_avisa_si_conserva_un_pico_mas_alto(tmp_path, capsys):
    db = _db(tmp_path)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO kv (key, value) VALUES ('peak_equity', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (json.dumps(30_000.0),),
        )
        conn.commit()
    finally:
        conn.close()

    assert equity.main(["--db", str(db)]) == 0

    out = capsys.readouterr().out
    assert "pico conservado en 30000.0" in out
    assert "--reset-peak" in out

def test_load_trades_ordena_por_instante_no_por_texto(tmp_path):
    db = tmp_path / "desfases.db"
    conn = sqlite3.connect(db)
    try:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO trades "
            "(symbol, side, units, entry_price, exit_price, opened_ts, closed_ts, signal_key, pnl_net) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "BTC",
                "long",
                1,
                100.0,
                101.0,
                "2026-11-24T08:00:00-05:00",
                "2026-11-24T09:00:00-05:00",
                "tarde",
                100.0,
            ),
        )
        conn.execute(
            "INSERT INTO trades "
            "(symbol, side, units, entry_price, exit_price, opened_ts, closed_ts, signal_key, pnl_net) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "BTC",
                "long",
                1,
                100.0,
                100.5,
                "2026-11-24T12:00:00+00:00",
                "2026-11-24T13:00:00+00:00",
                "temprana",
                50.0,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    loaded = equity.load_trades(db)

    # 13:00Z ocurre antes que 09:00-05:00 (14:00Z), aunque como texto vaya después.
    assert [trade["pnl_net"] for trade in loaded] == [50.0, 100.0]


def _funded_db(tmp_path: Path, stored_net: float = 85.0) -> Path:
    db = tmp_path / "funded.db"
    conn = sqlite3.connect(db)
    try:
        apply_migrations(conn)
        conn.execute(
            "INSERT INTO trades "
            "(symbol, side, units, entry_price, exit_price, opened_ts, closed_ts, "
            " signal_key, pnl_gross, fees, funding, pnl_net) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "BTC",
                "long",
                1,
                100.0,
                101.0,
                "2026-11-23T01:00:00+00:00",
                "2026-11-23T01:03:00+00:00",
                "funding",
                100.0,
                10.0,
                -5.0,
                stored_net,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db


def test_la_equity_usa_gross_fees_y_funding(tmp_path):
    planned = equity.plan(_funded_db(tmp_path), 25_000.0)

    assert planned["gross"] == pytest.approx(100.0)
    assert planned["fees"] == pytest.approx(10.0)
    assert planned["funding"] == pytest.approx(-5.0)
    assert planned["net"] == pytest.approx(85.0)
    assert planned["last_equity"] == pytest.approx(25_085.0)


def test_apply_corrige_el_pnl_net_derivado(tmp_path):
    db = _funded_db(tmp_path, stored_net=999.0)

    equity.apply(db, 25_000.0, backup_dir=tmp_path / "copias")

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT pnl_net FROM trades").fetchone()[0] == pytest.approx(85.0)
    finally:
        conn.close()
    assert equity.audit(db, 25_000.0)["ok"] is True
    assert equity.current(db)["last_equity"] == pytest.approx(25_085.0)


def test_audit_detecta_una_curva_con_filas_de_mas(tmp_path):
    db = _db(tmp_path)
    equity.apply(db, 25_000.0, backup_dir=tmp_path / "copias")
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT INTO equity (ts, equity) VALUES (?, ?)",
            ("2026-11-23T09:00:00+00:00", 24_825.77),
        )
        conn.commit()
    finally:
        conn.close()

    result = equity.audit(db, 25_000.0)

    assert result["ok"] is False
    assert "curve_rows" in result["issues"]
    assert result["differences"]["curve_rows"] == 1


def test_audit_exige_que_la_curva_empiece_en_la_primera_operacion(tmp_path):
    db = _db(tmp_path)

    result = equity.audit(db, 25_000.0)

    assert result["ok"] is False
    assert "curve_timestamp" in result["issues"]
    assert any(key.startswith("curve_ts_") for key in result["differences"])


def test_el_arranque_se_bloquea_si_la_curva_no_cuadra(tmp_path):
    from server.config import Settings
    from server.db import Store
    from server.engine import TradingEngine

    db = _db(tmp_path)
    store = Store(db)
    try:
        engine = TradingEngine(Settings(), store, feed=None)
        with pytest.raises(RuntimeError, match="equity no cuadra"):
            engine.start()
        assert engine.state.block_reason == "equity_mismatch"
        assert engine.state.status == "error"
    finally:
        store.close()


def test_el_arranque_pasa_despues_de_reconstruir(tmp_path):
    from server.config import Settings
    from server.db import Store
    from server.engine import TradingEngine

    db = _db(tmp_path)
    equity.apply(db, 25_000.0, backup_dir=tmp_path / "copias")
    store = Store(db)
    try:
        engine = TradingEngine(Settings(), store, feed=None)
        engine.start()
        assert engine.state.status == "running"
        assert engine.state.block_reason is None
    finally:
        store.close()
