from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server import holdout
from server.confirmatory import canonical_hash, file_hash
from server.config import Settings
from server.holdout import HOLDOUT_END, HOLDOUT_START
from server.main import create_app
from server.market import synthetic
from server.simulation import session_start_utc
from server.strategy.null_strategy import NullStrategy


def _dataset(path: Path, settings: Settings, *, bars: int = 60) -> Path:
    day = date(2026, 12, 1)
    symbols = settings.instruments.symbols
    series = {
        symbol: synthetic.generate_session(
            day.isoformat(),
            symbol,
            start=session_start_utc(settings, day),
            bars=bars,
        )
        for symbol in symbols
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        for index in range(bars):
            for symbol in symbols:
                bar = series[symbol][index]
                writer.writerow(
                    [bar.t.isoformat(), symbol, bar.o, bar.h, bar.l, bar.c, bar.v]
                )
    return path


@pytest.fixture
def holdout_api(tmp_path, monkeypatch):
    settings = Settings()
    settings.strategy.id = "null"
    config = tmp_path / "config.json"
    config.write_text(settings.model_dump_json(), encoding="utf-8")
    app = create_app(
        config_path=config,
        db_path=tmp_path / "holdout.db",
        experiment_ledger=tmp_path / "experiments.jsonl",
    )
    monkeypatch.setenv(holdout.SEAL_ENV, "1")
    monkeypatch.setattr(holdout, "PREREG_FILE", tmp_path / "PREREGISTRO.sha256")
    monkeypatch.setattr(holdout, "LOCK_FILE", tmp_path / "lock.json")
    monkeypatch.setattr(holdout, "EVENTS_FILE", tmp_path / "events.jsonl")
    monkeypatch.setattr(holdout, "ATTESTATION_DIR", tmp_path / "attestations")
    holdout.PREREG_FILE.write_text("a" * 64, encoding="utf-8")
    path = _dataset(tmp_path / "holdout.csv", settings)
    return app, path, settings, tmp_path


def _seal(path: Path, settings: Settings) -> None:
    from server.strategy.null_strategy import NullStrategy

    holdout.seal_run(path, settings, NullStrategy())


def test_el_endpoint_de_estado_es_solo_lectura(holdout_api):
    app, path, settings, _ = holdout_api
    _seal(path, settings)
    with TestClient(app) as client:
        before = client.get("/api/holdout/status").json()
        after = client.get("/api/holdout/status").json()
        unseal = client.post("/api/holdout/unseal")

    assert before["state"] == "READY"
    assert after["state"] == "READY"
    assert before["promotion_blocked"] is True
    assert unseal.status_code in {404, 405}


def test_backtest_sellado_devuelve_codigo_e_incidente_sin_guardar(holdout_api, monkeypatch):
    app, path, settings, _ = holdout_api
    monkeypatch.delenv(holdout.SEAL_ENV, raising=False)
    with TestClient(app) as client:
        response = client.post(
            "/api/backtest/run",
            json={"dataset_path": str(path), "stress": False},
        )
        ledger = client.get("/api/experiments").json()

    body = response.json()
    assert response.status_code == 409
    assert body["code"] == "HO-001"
    assert body["state"] == "SEALED"
    assert "holdout" in body["detail"]
    assert ledger["summary"]["experiments"] == 0


def test_una_corrida_autorizada_consume_una_sola_vez(holdout_api):
    app, path, settings, tmp_path = holdout_api
    _seal(path, settings)
    with TestClient(app) as client:
        first = client.post(
            "/api/backtest/run",
            json={"dataset_path": str(path), "stress": True},
        )
        second = client.post(
            "/api/backtest/run",
            json={"dataset_path": str(path), "stress": False},
        )
        ledger = client.get("/api/experiments").json()
        state = client.get("/api/holdout/status").json()

    assert first.status_code == 200
    first_payload = first.json()
    assert first_payload["holdout"]["state"] == "CONSUMED"
    assert first_payload["diagnostics"]["holdout"]["state"] == "CONSUMED"
    assert first_payload["experiment_id"]
    assert first_payload["holdout"]["evidence_sha256"]
    assert holdout.attestation_for(first_payload["holdout"]["permit_id"])

    assert second.status_code == 409
    assert second.json()["code"] == "HO-005"
    assert ledger["summary"]["experiments"] == 1
    assert state["state"] == "CONSUMED"
    assert state["promotion_blocked"] is False
    assert (tmp_path / "events.jsonl").is_file()

    verified = holdout.verify_consumed(
        first_payload,
        dataset_id=first_payload["dataset_id"],
        study_hash=canonical_hash(holdout.holdout_config(settings)),
        strategy_hash=canonical_hash(holdout.strategy_payload(NullStrategy())),
    )
    assert verified["ok"] is True, verified["reasons"]


def test_validate_no_expone_el_tramo_sellado(holdout_api):
    app, path, settings, _ = holdout_api
    with TestClient(app) as client:
        response = client.post("/api/data/validate", json={"path": str(path)})

    assert response.status_code == 409
    assert response.json()["code"] == "HO-001"


def test_compare_rechaza_el_holdout_antes_de_ejecutar(holdout_api):
    app, path, settings, _ = holdout_api
    _seal(path, settings)
    with TestClient(app) as client:
        response = client.post(
            "/api/backtest/compare",
            json={"dataset_path": str(path), "strategies": ["null"]},
        )

    assert response.status_code == 409
    assert response.json()["code"] == "HO-009"


def test_el_holdout_no_se_expone_por_el_estado(holdout_api):
    app, path, settings, _ = holdout_api
    _seal(path, settings)
    with TestClient(app) as client:
        body = client.get("/api/holdout/status").json()

    assert "dataset" not in body
    assert "prereg" not in body
    assert "permit" in body
    assert body["permit"] is None
    assert file_hash(path)
    assert HOLDOUT_START.date().isoformat() in body["window"]
    assert HOLDOUT_END.date().isoformat() in body["window"]
