"""Arranque automático: el motor no espera a que alguien pulse «empezar»."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from server import main as server_main
from server.config import Settings, load_settings
from server.engine import TradingEngine


def _config(tmp_path: Path, auto_start: bool) -> Path:
    payload = json.loads(Path("profiles/okx/config.json").read_text(encoding="utf-8"))
    payload["auto_start"] = auto_start
    payload["feed"]["provider"] = "simulated"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_auto_start_defaults_to_on():
    assert Settings().auto_start is True


def test_auto_start_is_read_from_the_profile(tmp_path):
    assert load_settings(_config(tmp_path, True)).auto_start is True
    assert load_settings(_config(tmp_path, False)).auto_start is False


def test_boot_starts_the_engine_without_a_human(tmp_path, monkeypatch):
    """El lifespan arranca el motor; se espía la llamada en vez de esperar ticks."""
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    app = server_main.create_app(
        config_path=_config(tmp_path, True),
        db_path=tmp_path / "auto.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        assert client.get("/api/status").json()["data"]["status"] == "running"
    assert started == [True]


def test_auto_start_off_leaves_it_waiting_for_orders(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))

    app = server_main.create_app(
        config_path=_config(tmp_path, False),
        db_path=tmp_path / "idle.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        assert client.get("/api/status").json()["data"]["status"] in {"idle", "stopped"}
    assert started == []

def test_un_perfil_ilegible_no_arranca_solo(tmp_path, monkeypatch):
    started: list[bool] = []
    monkeypatch.setattr(TradingEngine, "start_task", lambda self: started.append(True))
    bad = tmp_path / "config.json"
    bad.write_text("{esto no es json", encoding="utf-8")
    db = tmp_path / "roto.db"

    app = server_main.create_app(
        config_path=bad,
        db_path=db,
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    with TestClient(app) as client:
        status = client.get("/api/status").json()["data"]["status"]

    assert status in {"idle", "stopped"}
    assert started == []
    assert (tmp_path / "config.json.broken").exists()

    from server.db import Store

    store = Store(db)
    try:
        events = store.list_events()
    finally:
        store.close()
    assert any("config inválida" in event["message"] for event in events)
