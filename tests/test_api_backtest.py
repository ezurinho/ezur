from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app
from server.market import synthetic
from server.simulation import session_start_utc


def _dataset(
    path: Path,
    settings: Settings,
    symbols: list[str],
    bars: int = 120,
    days: list[date] | None = None,
) -> Path:
    sessions = days or [date(2026, 11, 20)]
    series = {
        day: {
            symbol: synthetic.generate_session(
                day.isoformat(),
                symbol,
                start=session_start_utc(settings, day),
                bars=bars,
            )
            for symbol in symbols
        }
        for day in sessions
    }
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        for day in sessions:
            for index in range(bars):
                for symbol in symbols:
                    bar = series[day][symbol][index]
                    writer.writerow(
                        [bar.t.isoformat(), symbol, bar.o, bar.h, bar.l, bar.c, bar.v]
                    )
    return path


@pytest.fixture
def app_client(tmp_path):
    settings = Settings()
    settings.strategy.id = "reference"
    settings.instruments.items = [
        type(settings.instruments.items[0])(symbol="PRIMARY", role="primary"),
        type(settings.instruments.items[0])(symbol="CTX_A", role="context"),
    ]
    config_path = tmp_path / "config.json"
    config_path.write_text(settings.model_dump_json(), encoding="utf-8")
    app = create_app(
        config_path=config_path,
        db_path=tmp_path / "api.db",
        experiment_ledger=tmp_path / "experiments.jsonl",
    )
    with TestClient(app) as client:
        yield client, tmp_path, settings


def test_validate_reports_misalignment(app_client):
    client, tmp_path, settings = app_client
    path = tmp_path / "half.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        stamp = session_start_utc(settings, date(2026, 11, 20)).isoformat()
        writer.writerow([stamp, "PRIMARY", 100, 101, 99, 100.5, 10])

    report = client.post("/api/data/validate", json={"path": str(path)}).json()
    assert report["ok"] is False
    assert any(issue["code"] == "empty_symbol" for issue in report["errors"])


def test_backtest_run_records_an_experiment(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"])

    response = client.post("/api/backtest/run", json={"dataset_path": str(path)})
    assert response.status_code == 200
    payload = response.json()
    assert payload["trades"] > 0
    assert payload["verdict"] == "RECHAZADA"
    assert len(payload["dataset_id"]) == 64
    # Con cero operaciones hace falta saber si la regla no disparó o si el
    # riesgo las descartó: el diagnóstico viaja con la corrida.
    assert isinstance(payload["diagnostics"]["rejections"], dict)

    ledger = client.get("/api/experiments").json()
    assert ledger["summary"]["experiments"] == 1
    assert ledger["entries"][0]["experiment_id"] == payload["experiment_id"]
    assert ledger["entries"][0]["strategy"]["id"] == "reference"


def test_backtest_rejects_invalid_dataset(app_client):
    client, tmp_path, _ = app_client
    broken = tmp_path / "broken.csv"
    broken.write_text("ts,symbol\n", encoding="utf-8")
    response = client.post("/api/backtest/run", json={"dataset_path": str(broken)})
    assert response.status_code == 422
    assert "invalid dataset" in response.json()["detail"]


def test_backtest_runs_endpoint_lists_saved_runs(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=60)
    client.post("/api/backtest/run", json={"dataset_path": str(path), "save": True})

    listing = client.get("/api/backtest/runs").json()
    assert len(listing["runs"]) == 1
    assert listing["has_more"] is False


def test_dataset_validation_accepts_aligned_multi_symbol_file(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=30)
    report = client.post("/api/data/validate", json={"path": str(path)}).json()
    assert report["ok"] is True
    assert report["symbols"] == ["PRIMARY", "CTX_A"]
    assert report["sessions"] == 1


def test_backtest_run_measures_g8_and_g2(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"])

    payload = client.post("/api/backtest/run", json={"dataset_path": str(path)}).json()
    outcomes = {item["id"]: item["status"] for item in payload["validation"]["outcomes"]}
    assert outcomes["G8"] != "not_measured"
    assert outcomes["G2"] == "pass"
    assert "G2" not in payload["validation"]["not_measured"]


def test_backtest_run_can_skip_the_stress_runs(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"])

    payload = client.post(
        "/api/backtest/run", json={"dataset_path": str(path), "stress": False}
    ).json()
    outcomes = {item["id"]: item["status"] for item in payload["validation"]["outcomes"]}
    assert outcomes["G8"] == "not_measured"


def test_backtest_run_honours_the_requested_window(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(
        tmp_path / "two_days.csv",
        settings,
        ["PRIMARY", "CTX_A"],
        days=[date(2026, 11, 19), date(2026, 11, 20)],
    )

    full = client.post(
        "/api/backtest/run", json={"dataset_path": str(path), "stress": False}
    ).json()
    limited = client.post(
        "/api/backtest/run",
        json={
            "dataset_path": str(path),
            "stress": False,
            "start": "2026-11-20",
            "end": "2026-11-21",
        },
    ).json()

    assert full["trades"] > 0
    assert 0 < limited["trades"] < full["trades"]


def test_backtest_run_rejects_an_empty_window(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"])

    response = client.post(
        "/api/backtest/run",
        json={
            "dataset_path": str(path),
            "start": "2026-11-21",
            "end": "2026-11-20",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "start debe ser anterior a end"


def test_backtest_uses_the_saved_profile_not_the_reduced_effective_copy(app_client):
    client, tmp_path, settings = app_client
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"])
    configured = client.app.state.configured_settings
    client.app.state.engine.settings.risk.risk_per_trade_pct = (
        configured.risk.risk_per_trade_pct / 2
    )

    payload = client.post(
        "/api/backtest/run", json={"dataset_path": str(path), "stress": False}
    ).json()

    from server.backtest import config_fingerprint

    assert payload["config_hash"] == config_fingerprint(configured)
