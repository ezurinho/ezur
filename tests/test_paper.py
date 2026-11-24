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


def test_el_informe_usa_el_contract_size_explicito(tmp_path):
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps({
            "instruments": {
                "primary": "BTC",
                "items": [{"symbol": "BTC", "tick_size": 0.01, "tick_value": 0.00002, "contract_size": 0.001}],
            }
        }),
        encoding="utf-8",
    )
    assert paper._profile_contract_size(profile) == 0.001


def test_el_informe_no_infiere_contract_size_si_falta(tmp_path):
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps({
            "instruments": {
                "primary": "BTC",
                "items": [{"symbol": "BTC", "tick_size": 0.01, "tick_value": 0.00002}],
            }
        }),
        encoding="utf-8",
    )
    assert paper._profile_contract_size(profile) is None


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


def test_avisa_si_la_curva_o_el_estado_no_cuadran():
    text = paper.render(SUMMARY, 25_000.0, "db", {"curve": 24_210.09, "state": 24_210.09})

    assert "NO cuadra con el libro" in text


def test_confirma_cuando_los_libros_cuadran():
    expected = 25_000.0 + SUMMARY["closed"]["pnl_net"]
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        {"curve": expected, "state": expected, "rows": 7},
    )

    assert "cuadra con el libro" in text
    assert "NO cuadra" not in text


def test_no_cuadra_si_la_curva_tiene_filas_de_mas():
    expected = 25_000.0 + SUMMARY["closed"]["pnl_net"]
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        {"curve": expected, "state": expected, "rows": 8},
    )

    assert "NO cuadra con el libro" in text
    assert "filas de curva: 8 para 7 operaciones cerradas" in text


def _trade(
    *,
    units: int = 300,
    entry: float = 60_000.0,
    opened: str = "2026-11-24T01:00:00+00:00",
    closed: str = "2026-11-24T01:30:00+00:00",
    pnl_net: float = -100.0,
):
    from datetime import datetime

    from server.models import TradeRecord

    return TradeRecord(
        symbol="BTC",
        side="long",
        units=units,
        entry_price=entry,
        exit_price=entry,
        opened_ts=datetime.fromisoformat(opened),
        closed_ts=datetime.fromisoformat(closed),
        pnl_net=pnl_net,
    )


def test_la_exposicion_mide_el_nocional_contra_el_capital():
    info = paper.exposure([_trade()], 25_000.0, contract_size=0.001)

    assert info["trades"] == 1
    assert info["max_notional"] == 18_000.0
    assert info["max_multiple"] == 0.72


def test_sin_escala_no_inventa_la_exposicion():
    info = paper.exposure([_trade()], 25_000.0)
    assert info["max_notional"] is None
    assert info["contract_size"] is None


def test_sin_operaciones_la_exposicion_queda_vacia():
    assert paper.exposure([], 25_000.0)["max_multiple"] is None


def test_marca_los_cierres_anteriores_a_la_apertura():
    broken = _trade(
        opened="2026-11-24T04:00:00+00:00",
        closed="2026-11-24T01:00:00+00:00",
        pnl_net=-27.9,
    )

    info = paper.impossible([_trade(pnl_net=-100.0), broken], 25_000.0)

    assert info["trades"] == 1
    assert info["pnl_net"] == -27.9
    assert info["equity_without"] == 24_900.0
    assert info["trades_without"] == 1


def test_el_pf_sin_las_imposibles_no_hereda_sus_ganancias():
    broken = _trade(
        opened="2026-11-24T04:00:00+00:00",
        closed="2026-11-24T01:00:00+00:00",
        pnl_net=-27.9,
    )

    info = paper.impossible(
        [_trade(pnl_net=150.0), _trade(pnl_net=-100.0), broken], 25_000.0
    )

    assert info["trades_without"] == 2
    assert info["pf_without"] == 1.5


def test_el_informe_enseña_exposicion_libro_roto_y_puerta():
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        exposure_info={
            "max_multiple": 0.72,
            "median_multiple": 0.7,
            "max_notional": 18_000.0,
        },
        anomalies={
            "trades": 2,
            "pnl_net": -27.91,
            "equity_without": 24_515.67,
            "pf_without": 0.245,
        },
        promotion={
            "passed": False,
            "reason": "pf con coste duplicado",
            "mode": "reduce",
            "size_factor": 0.25,
        },
    )

    assert "nocional máximo 18 000.00 (0.7× el capital)" in text
    assert "mediana 0.7×" in text
    assert "2 cierres anteriores a la apertura" in text
    assert "P&L -27.91 incluido" in text
    assert "equity sin ellas 24 515.67" in text
    assert "PF sin ellas 0.245" in text
    assert "puerta: no promovida (pf con coste duplicado) · modo reduce al 25 %" in text


def test_la_puerta_promovida_lo_dice():
    text = paper.render(SUMMARY, 25_000.0, "db", promotion={"passed": True})

    assert "puerta: promovida · riesgo completo" in text


def test_el_perfil_sin_puerta_no_enseña_estado(tmp_path):
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps({"risk": {"initial_capital": 25_000.0}}), encoding="utf-8"
    )

    assert paper.promotion_state(profile) is None


def test_la_puerta_del_perfil_se_evalua(tmp_path):
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps(
            {
                "promotion": {
                    "required": True,
                    "mode": "reduce",
                    "size_factor": 0.25,
                    "evidence": None,
                    "stress_evidence": None,
                    "cycle": None,
                }
            }
        ),
        encoding="utf-8",
    )

    state = paper.promotion_state(profile)

    assert state is not None
    assert state["passed"] is False
    assert state["mode"] == "reduce"
    assert state["size_factor"] == 0.25


def test_el_informe_dice_el_estado_del_bot():
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        health={
            "drawdown_pct": 1.96,
            "halt_at_pct": 10.0,
            "halted": False,
            "heartbeat_s": 4.0,
            "emergency": False,
        },
    )

    assert "estado: drawdown 1.96 % · parada dura al 10.00 % · latido hace 4 s" in text


def test_el_informe_avisa_de_parada_dura_y_emergencia():
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        health={
            "drawdown_pct": 12.0,
            "halt_at_pct": 10.0,
            "halted": True,
            "heartbeat_s": 400.0,
            "emergency": True,
        },
    )

    assert "parada dura al 10.00 % ACTIVA" in text
    assert "emergencia activa" in text


def test_sin_latido_lo_dice():
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        health={
            "drawdown_pct": 1.0,
            "halt_at_pct": None,
            "halted": False,
            "heartbeat_s": None,
            "emergency": False,
        },
    )

    assert "sin latido" in text


def test_health_state_lee_el_perfil_y_el_libro(tmp_path):
    profile = tmp_path / "perfil"
    profile.mkdir()
    (profile / "config.json").write_text(
        json.dumps(
            {
                "risk": {
                    "soft_brakes": True,
                    "max_drawdown_pct": 5.0,
                    "soft_brake_halt_multiple": 2.0,
                    "max_daily_loss_pct": 3.0,
                    "max_trades_per_day": 3,
                }
            }
        ),
        encoding="utf-8",
    )

    state = paper.health_state(
        profile,
        25_000.0,
        -3_000.0,
        {"peak": 25_000.0, "heartbeat": "2026-11-24T00:00:00+00:00", "emergency": False},
    )

    assert state["drawdown_pct"] == 12.0
    assert state["halt_at_pct"] == 10.0
    assert state["halted"] is True
    assert state["heartbeat_s"] is not None
    assert state["daily_loss_limit"] == -750.0
    assert state["max_daily_trades"] == 3


def test_books_lee_pico_latido_y_emergencia(tmp_path):
    from server.db import Store

    db = tmp_path / "terminal.db"
    store = Store(db)
    store.kv_set("peak_equity", 25_000.0)
    store.kv_set("heartbeat", "2026-11-24T00:00:00+00:00")
    store.kv_set("emergency", False)
    store.kv_set("day_stats", {"trades": 3, "pnl": 153.9, "consecutive_losses": 0})
    store.kv_set("session_id", "2026-11-24:CRYPTO24")
    store.close()

    stored = paper.books(db)

    assert stored["peak"] == 25_000.0
    assert stored["heartbeat"] == "2026-11-24T00:00:00+00:00"
    assert stored["emergency"] is False
    assert stored["day"]["trades"] == 3
    assert stored["session"] == "2026-11-24:CRYPTO24"


def test_el_informe_muestra_el_dia_de_la_sesion():
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        books_state={
            "day": {"trades": 3, "pnl": 153.8954522, "consecutive_losses": 0},
            "session": "2026-11-24:CRYPTO24",
        },
    )

    assert "día: 3 ops · P&L 153.90 · racha 0 · sesión 2026-11-24:CRYPTO24" in text

def test_el_dia_ensena_los_topes_del_perfil():
    text = paper.render(
        SUMMARY,
        25_000.0,
        "db",
        books_state={
            "day": {"trades": 3, "pnl": 153.8954522, "consecutive_losses": 0},
            "session": "2026-11-24:CRYPTO24",
        },
        health={"drawdown_pct": 1.96, "daily_loss_limit": -750.0, "max_daily_trades": 3},
    )

    assert "día: 3/3 ops · P&L 153.90 de -750.00 · racha 0" in text


def test_strict_marca_parada_y_latido_viejo():
    assert paper.alarms(
        {"halted": True, "emergency": False, "heartbeat_s": 3.0}, None, {}
    ) == ["parada dura"]
    assert paper.alarms(
        {"halted": False, "emergency": False, "heartbeat_s": 3_600.0}, None, {}
    ) == ["latido viejo"]


def test_strict_no_marca_una_puerta_que_solo_frena():
    assert paper.alarms(
        {"halted": False, "emergency": False, "heartbeat_s": 30.0},
        {"passed": False, "mode": "reduce"},
        {},
    ) == []
    assert paper.alarms(
        {"halted": False, "emergency": False, "heartbeat_s": 30.0},
        {"passed": False, "mode": "block"},
        {},
    ) == ["sin promoción"]
