"""La promoción es una puerta del arranque, no un informe que se ignora."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.engine import TradingEngine

EVIDENCE = {
    "split": {"out_of_sample": {"trades": 169, "profit_factor": 1.12}},
    "cost_per_trade_r": 0.09,
}
STRESS = {"split": {"out_of_sample": {"trades": 169, "profit_factor": 1.03}}}
CYCLE = {"pbo": {"pbo": 0.11}}


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
