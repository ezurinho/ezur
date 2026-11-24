from __future__ import annotations

import pytest
from fastapi import WebSocketDisconnect


def test_cross_site_http_is_rejected(client):
    response = client.get("/api/status", headers={"origin": "https://evil.example"})
    assert response.status_code == 403


def test_untrusted_host_is_rejected(client):
    response = client.get("/api/status", headers={"host": "evil.example"})
    assert response.status_code == 403


def test_same_origin_request_still_works(client):
    response = client.get(
        "/api/status",
        headers={"host": "127.0.0.1:8765", "origin": "http://127.0.0.1:8765"},
    )
    assert response.status_code == 200


def test_cross_site_websocket_is_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/ws", headers={"origin": "https://evil.example"}):
            pass


def test_snapshot_does_not_leak_the_alert_webhook(client):
    engine = client.app.state.engine
    engine.settings.alerts.webhook_url = "https://example.invalid/secret"
    snapshot = client.get("/api/status").json()["data"]
    assert snapshot["settings"]["alerts"]["webhook_url"] == "••••••"
    assert client.get("/api/config").json()["alerts"]["webhook_url"].endswith("/secret")
