from __future__ import annotations

from server.schemas import SnapshotData

EXPECTED_PATHS = [
    "/api/health",
    "/api/status",
    "/api/config",
    "/api/bot/{action}",
    "/api/position/close",
    "/api/orders/cancel",
    "/api/orders",
    "/api/emergency",
    "/api/trades",
    "/api/trades/export.csv",
    "/api/events",
    "/api/stats",
    "/api/validation",
    "/api/chart/history",
    "/api/strategy/schema",
    "/api/data/validate",
    "/api/datasets",
    "/api/backtest/run",
    "/api/experiments",
        "/api/funnel",
    "/api/stats/reset/preview",
    "/api/stats/reset",
    "/api/backtest/runs",
]


def test_health_returns_ok(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_liveness_health_returns_ok(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "ezur"}


def test_openapi_exposes_all_groups(client):
    paths = client.get("/openapi.json").json()["paths"]
    missing = [path for path in EXPECTED_PATHS if path not in paths]
    assert missing == []


def test_status_returns_valid_snapshot(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["type"] == "snapshot"
    assert payload["v"] == 1
    SnapshotData.model_validate(payload["data"])
    assert isinstance(payload["data"]["rejections"], dict)


def test_config_put_rejects_invalid(client):
    response = client.put("/api/config", json={"patch": {"risk": {"risk_per_trade_pct": 150}}})
    assert response.status_code == 422


def test_config_put_applies_partial_patch(client):
    response = client.put("/api/config", json={"patch": {"risk": {"max_trades_per_day": 4}}})
    assert response.status_code == 200
    assert response.json()["risk"]["max_trades_per_day"] == 4


def test_strategy_schema_is_served(client):
    response = client.get("/api/strategy/schema")
    assert response.status_code == 200
    payload = response.json()
    assert "null" in payload["available"]
    assert payload["params_schema"]["type"] == "object"


def test_emergency_toggles(client):
    assert client.post("/api/emergency").json()["emergency"] is True
    assert client.get("/api/status").json()["data"]["risk"]["blocked"] is True
    assert client.delete("/api/emergency").json()["emergency"] is False


def test_unknown_bot_action_is_404(client):
    assert client.post("/api/bot/teleport").status_code == 404


def test_ws_sends_snapshot_on_connect(client):
    with client.websocket_connect("/api/ws") as websocket:
        message = websocket.receive_json()
        assert message["type"] == "snapshot"
        assert message["v"] == 1
        SnapshotData.model_validate(message["data"])


def test_ws_snapshot_has_no_strategy_specific_keys(client):
    with client.websocket_connect("/api/ws") as websocket:
        data = websocket.receive_json()["data"]
    assert set(data["strategy"]) == {
        "id",
        "name",
        "version",
        "timeframe",
        "state",
        "state_label",
        "phases",
        "metrics",
        "signal",
        "rejection",
        "rejections",
    }
    assert data["strategy"]["phases"] == []
    assert data["strategy"]["metrics"] == {}
    # El marco es del motor (agrupa el feed de 1 m), no un parámetro del plugin.
    assert data["strategy"]["timeframe"] == "1m"


def test_validation_reports_inconclusive_without_trades(client):
    payload = client.get("/api/validation").json()
    assert payload["verdict"] == "RECHAZADA"
    assert "G4" in payload["failed"]
    assert "H1-H5" in payload["not_measured"]


def test_empty_stats_and_events(client):
    assert client.get("/api/stats").json()["closed"]["trades"] == 0
    assert client.get("/api/events").json() == []
    assert client.get("/api/trades").json() == []


def test_stats_reset_preview_and_apply(client):
    preview = client.get("/api/stats/reset/preview")
    assert preview.status_code == 200
    assert "would_delete" in preview.json()

    applied = client.post("/api/stats/reset", json={"include_backtests": False})
    assert applied.status_code == 200
    assert "deleted" in applied.json()


def test_stats_reset_refuses_a_running_engine(client):
    engine = client.app.state.engine
    engine.start()
    response = client.post("/api/stats/reset", json={"include_backtests": False})
    assert response.status_code == 409
    engine.stop()


def test_chart_history_rejects_unknown_timeframe(client):
    response = client.get("/api/chart/history", params={"tf": "7m"})
    assert response.status_code == 422


def test_chart_history_accepts_the_documented_enums(client):
    for timeframe in ("1m", "5m", "15m", "30m"):
        response = client.get("/api/chart/history", params={"tf": timeframe})
        assert response.status_code == 200
        assert response.json()["timeframe"] == timeframe


def test_strategy_schema_reports_the_live_strategy(client):
    payload = client.get("/api/strategy/schema").json()
    config = client.get("/api/config").json()
    assert payload["active"] == config["strategy"]["id"]
    assert payload["id"] == payload["active"]
    assert set(payload["available"]) >= {"null", "reference", "donchian", "fade"}


def test_strategy_schema_can_target_another_plugin(client):
    payload = client.get("/api/strategy/schema", params={"strategy_id": "fade"}).json()
    assert payload["id"] == "fade"
    assert "sigma" in payload["params_schema"]["properties"]


def test_strategy_schema_unknown_id_is_404(client):
    assert client.get("/api/strategy/schema", params={"strategy_id": "nope"}).status_code == 404


def test_health_reports_the_engine_heartbeat(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["engine"]["status"] in {"idle", "stopped", "running"}
    assert "last_bar_age_s" in body["engine"]
    assert body["engine"]["mode"] in {"paper", "live", "backtest"}
