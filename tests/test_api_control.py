"""Control endpoints: the ones an operator actually presses."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app


@pytest.fixture
def pair(tmp_path):
    settings = Settings()
    settings.feed.replay_speed = 1000.0
    # Sin arranque automático el feed no rellena las órdenes entre el armado
    # de un test y la llamada al endpoint que se quiere medir.
    payload = settings.model_dump()
    payload["auto_start"] = False
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    app = create_app(
        config_path=config_path,
        db_path=tmp_path / "control.db",
        experiment_ledger=tmp_path / "ledger.jsonl",
    )
    client = TestClient(app)
    client.__enter__()
    yield client, app.state.engine
    client.__exit__(None, None, None)


def test_unknown_bot_action_is_404(pair):
    client, _ = pair
    assert client.post("/api/bot/teleport").status_code == 404


def test_start_pause_stop_cycle(pair):
    client, engine = pair
    assert client.post("/api/bot/start").json()["status"] == "running"
    assert client.post("/api/bot/pause").json()["status"] == "paused"
    assert client.post("/api/bot/stop").json()["status"] == "stopped"
    assert engine.state.status == "stopped"


def test_emergency_blocks_start_and_can_be_cleared(pair):
    client, engine = pair
    assert client.post("/api/emergency").json() == {"emergency": True}
    assert client.post("/api/bot/start").status_code == 409
    assert client.delete("/api/emergency").json() == {"emergency": False}
    assert client.post("/api/bot/start").json()["status"] == "running"
    assert engine.state.emergency is False


def test_close_position_without_a_position_is_a_no_op(pair):
    client, _ = pair
    assert client.post("/api/position/close").json() == {"closed": False}


def test_cancel_orders_leaves_no_pending_orders(pair):
    client, engine = pair
    assert client.post("/api/orders/cancel").json() == {"cancelled": False, "count": 0}
    assert engine.execution.pending_orders() == []
    assert client.get("/api/orders").json() == []


def test_cancel_orders_reports_the_real_count(pair):
    from server.models import RiskDecision
    from server.strategy.base import Signal
    from tests.conftest import NOW

    client, engine = pair
    signal = Signal(
        key="2026-01-15:long:1500",
        side="long",
        reason="test",
        ts=NOW,
        stop_price=99.5,
        target_price=102.25,
    )
    engine.execution.arm(
        RiskDecision(approved=True, code="approved", units=1, risk_per_unit=1.0),
        signal,
        "PRIMARY",
        100.0,
        NOW,
    )
    body = client.post("/api/orders/cancel").json()
    assert body == {"cancelled": True, "count": 1}
    assert engine.execution.pending_orders() == []


def test_config_reset_restores_defaults(pair):
    client, engine = pair
    client.put("/api/config", json={"patch": {"risk": {"max_trades_per_day": 9}}})
    assert client.get("/api/config").json()["risk"]["max_trades_per_day"] == 9
    reset = client.post("/api/config/reset").json()
    assert reset["risk"]["max_trades_per_day"] == Settings().risk.max_trades_per_day
    assert engine.settings.risk.max_trades_per_day == Settings().risk.max_trades_per_day


def test_trades_export_is_csv_with_a_header(pair):
    client, _ = pair
    response = client.get("/api/trades/export.csv")
    assert response.status_code == 200
    assert response.text == ""  # no trades yet, no fake header

    store = client.app.state.store
    from server.models import TradeRecord

    store.insert_trade(
        TradeRecord(
            symbol="PRIMARY",
            side="long",
            units=1,
            entry_price=100.0,
            exit_price=101.0,
            opened_ts="2026-11-20T14:30:00Z",
            closed_ts="2026-11-20T14:35:00Z",
            pnl_gross=1.0,
            pnl_net=0.9,
            fees=0.1,
            exit_reason="target",
            mode="paper",
            r_multiple=1.0,
        )
    )
    body = client.get("/api/trades/export.csv").text
    assert body.splitlines()[0].startswith("id,")
    assert "PRIMARY" in body


def test_trades_can_be_filtered_by_mode(pair):
    client, _ = pair
    assert client.get("/api/trades", params={"mode": "paper"}).json() == []


def test_datasets_endpoint_lists_csv_files(pair, tmp_path, monkeypatch):
    client, _ = pair
    data = tmp_path / "data"
    data.mkdir()
    (data / "bars.csv").write_text("ts,symbol\n", encoding="utf-8")
    # Los datasets viven en `data/` o donde diga EZUR_DATA_DIR, no junto al perfil.
    monkeypatch.setenv("EZUR_DATA_DIR", str(data))
    assert client.get("/api/datasets").json() == [(data / "bars.csv").as_posix()]


def test_websocket_sends_an_initial_snapshot(pair):
    client, _ = pair
    with client.websocket_connect("/api/ws") as ws:
        message = ws.receive_json()
        assert message["type"] == "snapshot"
        assert message["v"] == 1
        assert "strategy" in message["data"]


def _insert(client, side="long", closed="2026-11-20T15:00:00Z", mode="paper"):
    from datetime import datetime, timedelta

    from server.models import TradeRecord

    exit_ts = datetime.fromisoformat(closed.replace("Z", "+00:00"))
    client.app.state.store.insert_trade(
        TradeRecord(
            symbol="PRIMARY",
            side=side,
            units=1,
            entry_price=100.0,
            exit_price=101.0,
            opened_ts=exit_ts - timedelta(minutes=5),
            closed_ts=exit_ts,
            pnl_gross=1.0,
            pnl_net=0.9,
            fees=0.1,
            exit_reason="target",
            mode=mode,
            r_multiple=1.0,
        )
    )


def test_trades_can_be_filtered_by_side(pair):
    client, _ = pair
    _insert(client, side="long")
    _insert(client, side="short")
    assert len(client.get("/api/trades").json()) == 2
    assert len(client.get("/api/trades", params={"side": "short"}).json()) == 1


def test_trades_can_be_filtered_by_date_range(pair):
    client, _ = pair
    _insert(client, closed="2026-11-19T15:00:00Z")
    _insert(client, closed="2026-11-20T15:00:00Z")
    rows = client.get(
        "/api/trades",
        params={"start": "2026-11-20T00:00:00Z", "end": "2026-11-20T23:59:59Z"},
    ).json()
    assert len(rows) == 1
    assert rows[0]["closed_ts"].startswith("2026-11-20")


def test_csv_export_honours_the_filters(pair):
    client, _ = pair
    _insert(client, side="long")
    _insert(client, side="short")
    body = client.get("/api/trades/export.csv", params={"side": "long"}).text
    assert len(body.strip().splitlines()) == 2  # header + one row
