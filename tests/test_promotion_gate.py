"""La promoción es una puerta del arranque, no un informe que se ignora."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.backtest import config_fingerprint
from server.config import Settings
from server.engine import TradingEngine

GATE_CONFIG = {
    "auto_start": True,
    "feed": {"provider": "simulated"},
    "promotion": {
        "required": True,
        "evidence": "",
        "stress_evidence": "",
        "cycle": "",
    },
}
EVIDENCE = {
    "strategy": {"id": "null", "version": "0.0.0"},
    "dataset": "data/BTC_1h_binance.csv",
    "split": {"out_of_sample": {"trades": 169, "profit_factor": 1.12}},
    "cost_per_trade_r": 0.09,
    "config_hash": config_fingerprint(Settings.model_validate(GATE_CONFIG)),
}
STRESS = {"split": {"out_of_sample": {"trades": 169, "profit_factor": 1.03}}}
CYCLE = {"pbo": {"pbo": 0.11}, "universe": [{"timeframe": "1h"}]}


def _write(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _boot(tmp_path: Path, promotion: dict) -> tuple[TestClient, list[bool]]:
    config = tmp_path / "config.json"
    config.write_text(
        json.dumps(
            {"auto_start": True, "feed": {"provider": "simulated"}, "promotion": promotion}
        ),
        encoding="utf-8",
    )
    started: list[bool] = []
    return config, started


def test_sin_promocion_el_motor_no_arranca_solo(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    config, _ = _boot(
        tmp_path,
        {"required": True, "evidence": str(tmp_path / "no-existe.json")},
    )
    app = server_main.create_app(
        config_path=config,
        db_path=tmp_path / "gate.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status in {"idle", "stopped"}
    assert started == []


def test_con_la_evidencia_completa_arranca(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    config, _ = _boot(
        tmp_path,
        {
            "required": True,
            "evidence": _write(tmp_path / "bt.json", EVIDENCE),
            "stress_evidence": _write(tmp_path / "bt2x.json", STRESS),
            "cycle": _write(tmp_path / "ciclo.json", CYCLE),
        },
    )
    app = server_main.create_app(
        config_path=config,
        db_path=tmp_path / "pass.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status == "running"
    assert started == [True]


def test_la_evidencia_de_otra_estrategia_no_promueve(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    otra = {**EVIDENCE, "strategy": {"id": "donchian", "version": "0.1.0"}}
    config, _ = _boot(
        tmp_path,
        {
            "required": True,
            "evidence": _write(tmp_path / "bt-otra.json", otra),
            "stress_evidence": _write(tmp_path / "bt2x.json", STRESS),
            "cycle": _write(tmp_path / "ciclo.json", CYCLE),
        },
    )
    app = server_main.create_app(
        config_path=config,
        db_path=tmp_path / "ajena.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status in {"idle", "stopped"}
    assert started == []


def test_la_evidencia_de_otra_configuracion_no_promueve(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    ajena = {**EVIDENCE, "config_hash": "0" * 16}
    config, _ = _boot(
        tmp_path,
        {
            "required": True,
            "evidence": _write(tmp_path / "bt-ajena.json", ajena),
            "stress_evidence": _write(tmp_path / "bt2x.json", STRESS),
            "cycle": _write(tmp_path / "ciclo.json", CYCLE),
        },
    )
    app = server_main.create_app(
        config_path=config,
        db_path=tmp_path / "hash.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status in {"idle", "stopped"}
    assert started == []


def test_la_puerta_apagada_no_bloquea_nada(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    config, _ = _boot(tmp_path, {"required": False})
    app = server_main.create_app(
        config_path=config,
        db_path=tmp_path / "off.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status == "running"
    assert started == [True]


def test_sin_promocion_en_modo_reduce_arranca_a_menor_tamano(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    config, _ = _boot(
        tmp_path,
        {
            "required": True,
            "mode": "reduce",
            "size_factor": 0.25,
            "evidence": str(tmp_path / "no-existe.json"),
        },
    )
    app = server_main.create_app(
        config_path=config,
        db_path=tmp_path / "reduced.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status == "running"
    assert started == [True]
    assert app.state.settings.risk.risk_per_trade_pct == 0.25
