"""La cuenta de papel tiene que poder leerse aunque el bot esté parado."""
from __future__ import annotations

import json
from pathlib import Path

from server import paper

SUMMARY = {
    "closed": {
        "trades": 7,
        "wins": 1,
        "losses": 6,
        "win_rate": 0.142857,
        "profit_factor": 0.14047,
        "expectancy_r": -1.01586,
        "pnl_net": -643.59048,
        "fees": 205.8,
        "best_trade": 105.18,
        "worst_trade": -146.32,
        "max_loss_streak": 5,
    }
}


def test_el_resumen_dice_si_gana_o_pierde():
    text = paper.render(SUMMARY, 25_000.0, "db")

    assert "resultado -643.59" in text
    assert "equity 24 356.41" in text
    assert "factor de beneficio 0.14" in text
    assert "comisiones 205.80 (47 % del bruto)" in text
    assert "acierto 14.3 %" in text


def test_sin_operaciones_no_inventa_cifras():
    text = paper.render({"closed": {"trades": 0}}, 25_000.0, "db")

    assert "sin operaciones cerradas" in text
    assert "factor de beneficio" not in text


def test_sin_base_avisa_y_sale_con_error(tmp_path, capsys):
    code = paper.main(["--db", str(tmp_path / "nada.db")])

    assert code == 1
    assert "no hay base" in capsys.readouterr().out


def test_el_perfil_aporta_su_capital(tmp_path):
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps({"risk": {"initial_capital": 100_000.0}}), encoding="utf-8"
    )

    db, capital = paper._profile_defaults(profile)

    assert db == profile / "terminal.db"
    assert capital == 100_000.0


def test_una_base_sin_operaciones_se_lee_sin_romperse(tmp_path, capsys):
    import sqlite3

    db = tmp_path / "vacia.db"
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT, side TEXT, units REAL,"
        " entry_price REAL, exit_price REAL, opened_ts TEXT, closed_ts TEXT,"
        " fees REAL, pnl_net REAL, pnl_gross REAL, r_multiple REAL, mode TEXT,"
        " ambiguous INTEGER DEFAULT 0)"
    )
    conn.commit()
    conn.close()

    code = paper.main(["--db", str(db), "--json"])

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["summary"]["closed"]["trades"] == 0
