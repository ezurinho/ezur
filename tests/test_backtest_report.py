"""Lo que hace legible una corrida: rechazos, reparto IS/OOS y JSON reproducible."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from server.backtest import main, partition_by_split, run_backtest
from server.strategy.null_strategy import NullStrategy


@dataclass
class _FakeTrade:
    closed_ts: datetime


def test_partition_by_split_corta_por_cierre():
    start = datetime(2026, 1, 15, tzinfo=timezone.utc)
    trades = [_FakeTrade(start + timedelta(days=day)) for day in range(4)]
    cut = start + timedelta(days=2)

    inside, outside = partition_by_split(trades, cut)

    assert [trade.closed_ts for trade in inside] == [start, start + timedelta(days=1)]
    assert [trade.closed_ts for trade in outside] == [
        start + timedelta(days=2),
        start + timedelta(days=3),
    ]


def test_partition_by_split_sin_datos_en_un_lado():
    start = datetime(2026, 1, 15, tzinfo=timezone.utc)
    trades = [_FakeTrade(start)]
    inside, outside = partition_by_split(trades, start + timedelta(days=1))
    assert inside and not outside


def test_el_backtest_expone_los_rechazos(settings, dataset_path):
    result = run_backtest(settings, dataset_path, NullStrategy())
    assert isinstance(result.diagnostics["rejections"], dict)


def test_los_rechazos_se_acumulan_entre_sesiones(engine, settings):
    """`_rejections` se vacía cada sesión; el total de la corrida no."""
    from server.timeutil import now_utc, session_for

    when = now_utc()
    engine._note_rejection("stop_too_wide", "stop fuera de límite", when)
    engine._note_rejection("stop_too_wide", "stop fuera de límite", when)
    template = settings.instruments.template_for(settings.instruments.primary)
    engine._on_new_session(session_for(when, template))
    engine._note_rejection("stop_too_wide", "stop fuera de límite", when)
    engine._note_rejection("max_drawdown_reached", "drawdown", when)

    assert engine.rejection_totals() == {
        "stop_too_wide": 3,
        "max_drawdown_reached": 1,
    }


def test_el_cli_escribe_json_con_metricas_y_coste(settings, dataset_path, tmp_path, monkeypatch):
    target = tmp_path / "run.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "backtest",
            "--dataset",
            str(dataset_path),
            "--strategy",
            "reference",
            "--out",
            str(target),
            "--split",
            "2026-01-15T14:45:00+00:00",
        ],
    )

    main()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["strategy"]["id"] == "reference"
    assert payload["metrics"]["trades"] == 0 or payload["metrics"]["trades"] >= 0
    assert set(payload["split"]) == {"at", "in_sample", "out_of_sample"}
    assert "cost_per_trade_r" in payload
    assert isinstance(payload["diagnostics"]["rejections"], dict)


def test_el_coste_del_json_se_mide_en_el_fuera_de_muestra(
    settings, tmp_path, synthetic_csv, monkeypatch
):
    target = tmp_path / "split.json"
    path = synthetic_csv(tmp_path / "split.csv")
    monkeypatch.setattr(
        "sys.argv",
        [
            "backtest",
            "--dataset",
            str(path),
            "--strategy",
            "reference",
            "--split",
            "2026-01-15T15:30:00+00:00",
            "--out",
            str(target),
        ],
    )

    main()

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["cost_scope"] == "out_of_sample"
    assert payload["cost_trades"] == payload["split"]["out_of_sample"]["trades"]
    assert 0 < payload["cost_trades"] < payload["metrics"]["trades"]
    assert payload["cost_per_trade_r"] == pytest.approx(
        payload["cost_per_trade_r_weighted"]
    )


def test_el_cli_mide_g8_y_g2_igual_que_la_api(
    settings, tmp_path, synthetic_csv, monkeypatch
):
    """El CLI no puede declarar INCONCLUSO por puertas que la API sí mide."""
    target = tmp_path / "gates.json"
    path = synthetic_csv(tmp_path / "gates.csv", bars=120)
    monkeypatch.setattr(
        "sys.argv",
        [
            "backtest",
            "--dataset",
            str(path),
            "--strategy",
            "reference",
            "--gates",
            "--out",
            str(target),
        ],
    )

    main()

    payload = json.loads(target.read_text(encoding="utf-8"))
    outcomes = {item["id"]: item["status"] for item in payload["gates"]["outcomes"]}
    assert outcomes["G8"] != "not_measured"
    assert outcomes["G2"] in {"pass", "fail"}
    assert "G8" not in payload["gates"]["not_measured"]
    assert "G2" not in payload["gates"]["not_measured"]


def test_el_informe_declara_la_curva_marcada_a_mercado(settings, dataset_path):
    # El motor anota equity + P&L no realizado en cada vela con posicion. Si el
    # informe dijera lo contrario, el drawdown de una posicion abierta se leeria
    # como si la cuenta solo existiera en los cierres.
    result = run_backtest(settings, dataset_path, NullStrategy())
    assert result.diagnostics["marked_to_market"] is True
