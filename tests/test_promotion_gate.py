"""La promoción es una puerta del arranque, no un informe que se ignora."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.backtest import (
    config_fingerprint,
    profile_fingerprint,
    research_fingerprint,
    risk_brakes,
)
from server.config import Settings
from server.engine import TradingEngine
from server.promotion import evaluate

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
    "metrics": {"trades": 169, "fees": 3802.5},
    "risk_budget": 250.0,
    "execution": {
        "commission_per_unit_side": 0.62,
        "tick_size": 0.25,
        "tick_value": 0.5,
    },
    "cost_per_trade_r": 0.09,
    "config_hash": config_fingerprint(Settings.model_validate(GATE_CONFIG)),
}
STRESS = {"split": {"out_of_sample": {"trades": 169, "profit_factor": 1.03}}}
CYCLE = {
    "pbo": {"pbo": 0.11},
    "dsr": {"dsr": 0.97},
    "universe": [{"timeframe": "1h"}],
}


def _write(path: Path, payload: dict) -> str:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


def _cycle_with_stress(pf: float) -> dict:
    survives = pf > 1.0
    return {
        **CYCLE,
        "stress": {
            "multiplier": 2.0,
            "method": "rerun",
            "selected": "fast5",
            "selected_survives": survives,
            "survivors": ["fast5"] if survives else [],
            "configs": [
                {
                    "name": "fast5",
                    "trades": 169,
                    "pf_net": pf,
                    "exp_r": 0.02 if survives else -0.02,
                    "survives": survives,
                }
            ],
        },
    }


def _stress_check(verdict: dict) -> dict:
    return next(
        check
        for check in verdict["checks"]
        if check["name"] == "pf_con_coste_duplicado"
    )


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
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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


def test_el_estres_sale_del_ciclo_sin_fichero_aparte():
    verdict = evaluate(
        EVIDENCE,
        None,
        _cycle_with_stress(1.03),
        {"id": "null", "version": "0.0.0"},
        config_hash=EVIDENCE["config_hash"],
        execution=EVIDENCE["execution"],
    )

    check = _stress_check(verdict)
    assert check["pass"] is True
    assert check["source"] == "ciclo"
    assert check["multiplier"] == 2.0
    assert verdict["passed"] is True


def test_el_ciclo_con_estres_insuficiente_no_promueve():
    verdict = evaluate(
        EVIDENCE,
        None,
        _cycle_with_stress(0.9),
        {"id": "null", "version": "0.0.0"},
        config_hash=EVIDENCE["config_hash"],
        execution=EVIDENCE["execution"],
    )

    check = _stress_check(verdict)
    assert check["pass"] is False
    assert check["source"] == "ciclo"
    assert "coste duplicado (ciclo)" in check["reason"]
    assert verdict["passed"] is False


def test_el_fichero_de_estres_sigue_siendo_el_fallback():
    verdict = evaluate(
        EVIDENCE,
        STRESS,
        CYCLE,
        {"id": "null", "version": "0.0.0"},
        config_hash=EVIDENCE["config_hash"],
        execution=EVIDENCE["execution"],
    )

    check = _stress_check(verdict)
    assert check["pass"] is True
    assert check["source"] == "fichero"


def test_la_puerta_apagada_no_bloquea_nada(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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
        effective = client.get("/api/status").json()["data"]["risk"]["limits"]["risk_per_trade_pct"]
        configured = client.get("/api/config").json()["risk"]["risk_per_trade_pct"]
        events = client.get("/api/events?limit=20").json()
        promotion_events = [
            event["message"] for event in events if event.get("category") == "promotion"
        ]

    assert status == "running"
    assert started == [True]
    assert effective == 0.25
    assert configured == 1.0
    assert app.state.settings.risk.risk_per_trade_pct == 0.25
    assert app.state.configured_settings.risk.risk_per_trade_pct == 1.0
    # El motor tiene que nacer con la copia efectiva: si el RiskManager se
    # construye antes de la reducción, el snapshot miente y el tamaño real
    # sigue siendo el configurado.
    assert app.state.engine.risk.config.risk_per_trade_pct == 0.25
    assert app.state.engine.builder.settings.risk.risk_per_trade_pct == 0.25
    # El evento debe contar 1,00 -> 0,25, no 0,25 -> 0,06: si se redacta
    # después de mutar la configuración, el diagnóstico confunde la causa.
    assert any("riesgo 1.00 % -> 0.25 %" in message for message in promotion_events)


def test_guardar_config_no_compone_la_reduccion_por_promocion(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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
        db_path=tmp_path / "reduced-save.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        assert client.get("/api/config").json()["risk"]["risk_per_trade_pct"] == 1.0
        first = client.put("/api/config", json={"patch": {"risk": {"max_trades_per_day": 4}}})
        assert first.status_code == 200
        assert first.json()["risk"]["risk_per_trade_pct"] == 1.0
        assert client.get("/api/status").json()["data"]["risk"]["limits"]["risk_per_trade_pct"] == 0.25

        saved = json.loads(config.read_text(encoding="utf-8"))
        assert saved["risk"]["risk_per_trade_pct"] == 1.0
        assert saved["risk"]["max_trades_per_day"] == 4

        # Un segundo guardado tampoco puede convertir 0,25 en el nuevo 1,0.
        second = client.put("/api/config", json={"patch": {"risk": {"max_trades_per_day": 5}}})
        assert second.status_code == 200
        saved = json.loads(config.read_text(encoding="utf-8"))
        assert saved["risk"]["risk_per_trade_pct"] == 1.0
        assert client.get("/api/status").json()["data"]["risk"]["limits"]["risk_per_trade_pct"] == 0.25


def test_cambiar_el_riesgo_configurado_reduce_sobre_el_nuevo_valor(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: asyncio.sleep(0, result=started.append(True)))

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
        db_path=tmp_path / "risk-reduce.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        response = client.put(
            "/api/config",
            json={"patch": {"risk": {"risk_per_trade_pct": 2.0}}},
        )
        assert response.status_code == 200
        assert response.json()["risk"]["risk_per_trade_pct"] == 2.0
        status = client.get("/api/status").json()["data"]["risk"]["limits"]["risk_per_trade_pct"]

    saved = json.loads(config.read_text(encoding="utf-8"))
    assert saved["risk"]["risk_per_trade_pct"] == 2.0
    assert status == 0.5
    assert app.state.engine.risk.config.risk_per_trade_pct == 0.5


# --- huella de investigación vs huella del perfil ---------------------------


def test_ajustar_un_freno_no_cambia_la_huella_de_investigacion():
    base = Settings.model_validate(GATE_CONFIG)
    apretado = Settings.model_validate(
        {
            **GATE_CONFIG,
            "risk": {"max_drawdown_pct": 2.5, "max_trades_per_day": 4},
        }
    )

    assert research_fingerprint(base) == research_fingerprint(apretado)
    assert profile_fingerprint(base) != profile_fingerprint(apretado)


def test_la_puerta_exige_la_investigacion_y_deja_escritos_los_frenos():
    settings = Settings.model_validate(
        {
            **GATE_CONFIG,
            "risk": {"max_drawdown_pct": 2.5, "max_trades_per_day": 4},
        }
    )
    medido = {"max_drawdown_pct": 5.0, "max_trades_per_day": 8}
    eviden = {
        **EVIDENCE,
        # La huella vieja ya no manda: si la investigación coincide, el ajuste
        # de frenos no invalida la evidencia.
        "config_hash": "0" * 16,
        "research_hash": research_fingerprint(settings),
        "profile_hash": "f" * 16,
        "brakes": medido,
    }

    verdict = evaluate(
        eviden,
        None,
        _cycle_with_stress(1.03),
        {"id": "null", "version": "0.0.0"},
        config_hash=config_fingerprint(settings),
        execution=EVIDENCE["execution"],
        research_hash=research_fingerprint(settings),
        profile_hash=profile_fingerprint(settings),
        brakes=risk_brakes(settings),
    )

    check = next(
        item
        for item in verdict["checks"]
        if item["name"] == "evidencia_de_la_configuracion"
    )
    assert check["pass"] is True
    assert verdict["source"]["brakes"] == medido
    assert verdict["source"]["profile_hash"] == "f" * 16
    assert verdict["source"]["brakes_current"]["max_drawdown_pct"] == 2.5


def test_la_evidencia_vieja_sigue_comparando_la_huella_completa():
    settings = Settings.model_validate(GATE_CONFIG)

    verdict = evaluate(
        EVIDENCE,
        None,
        _cycle_with_stress(1.03),
        {"id": "null", "version": "0.0.0"},
        config_hash="0" * 16,
        execution=EVIDENCE["execution"],
        research_hash=research_fingerprint(settings),
        profile_hash=profile_fingerprint(settings),
        brakes=risk_brakes(settings),
    )

    check = next(
        item
        for item in verdict["checks"]
        if item["name"] == "evidencia_de_la_configuracion"
    )
    assert check["pass"] is False
    assert "anterior a la separación" in check["reason"]
