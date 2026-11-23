"""Alertas fuera de banda: la cola no bloquea, las caídas se cuentan."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.alerts import Alert, WebhookNotifier, build_notifier
from server.config import AlertsConfig, Settings
from server.db import Store
from server.engine import TradingEngine
from server.main import create_app
from server.market.feed import SimulatedFeed
from server.strategy.null_strategy import NullStrategy


class Capture:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[dict] = []
        self.fail_times = fail_times
        self.attempts = 0

    def __call__(self, payload: dict) -> None:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise OSError("webhook caído")
        self.sent.append(payload)


def _notifier(transport, **kwargs) -> WebhookNotifier:
    options = {
        "min_level": "warn",
        "dedupe_window_s": 0.0,
        "retry_backoff_s": 0.0,
        "max_retries": 1,
        "transport": transport,
    }
    options.update(kwargs)
    return WebhookNotifier("http://example.test/hook", **options)


def _drain(notifier: WebhookNotifier, timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while notifier.stats["queued"] > notifier.stats["sent"] + notifier.stats["failed"]:
        if time.monotonic() > deadline:
            break
        time.sleep(0.01)


def test_disabled_notifier_never_starts_a_thread():
    notifier = WebhookNotifier(None)
    assert notifier.enabled is False
    assert notifier.enqueue("error", "risk", "parada") is False
    assert notifier._thread is None


def test_only_levels_at_or_above_the_threshold_are_queued():
    capture = Capture()
    notifier = _notifier(capture)
    try:
        assert notifier.enqueue("info", "engine", "motor iniciado") is False
        assert notifier.stats["filtered"] == 1
        assert notifier.enqueue("warn", "risk", "parada de emergencia activada") is True
        _drain(notifier)
        assert [item["message"] for item in capture.sent] == [
            "parada de emergencia activada"
        ]
    finally:
        notifier.close()


def test_payload_has_a_stable_shape():
    alert = Alert("warn", "risk", "límite alcanzado", {"daily_trades": 3})
    payload = alert.payload()
    assert set(payload) == {"source", "level", "category", "message", "meta", "ts"}
    assert payload["source"] == "ezur"
    assert payload["meta"]["daily_trades"] == 3


def test_identical_messages_are_sent_once_inside_the_window():
    capture = Capture()
    notifier = _notifier(capture, dedupe_window_s=60.0)
    try:
        for _ in range(5):
            notifier.enqueue("warn", "risk", "bloqueado: max_trades_reached")
        _drain(notifier)
        assert len(capture.sent) == 1
        assert notifier.stats["deduped"] == 4
    finally:
        notifier.close()


def test_dedupe_window_expires():
    capture = Capture()
    now = [0.0]
    notifier = _notifier(capture, dedupe_window_s=10.0, clock=lambda: now[0])
    try:
        notifier.enqueue("warn", "risk", "repetido")
        now[0] = 11.0
        notifier.enqueue("warn", "risk", "repetido")
        _drain(notifier)
        assert len(capture.sent) == 2
    finally:
        notifier.close()


def test_failures_are_counted_not_raised():
    capture = Capture(fail_times=10)
    failures: list[str] = []
    notifier = _notifier(capture, on_failure=failures.append, max_retries=2)
    try:
        notifier.enqueue("error", "execution", "orden rechazada")
        _drain(notifier)
        assert notifier.stats["failed"] == 1
        assert notifier.stats["sent"] == 0
        assert failures and "no entregada" in failures[-1]
        assert capture.attempts == 2
    finally:
        notifier.close()


def test_retry_succeeds_on_the_second_attempt():
    capture = Capture(fail_times=1)
    notifier = _notifier(capture, max_retries=3)
    try:
        notifier.enqueue("error", "execution", "reintento")
        _drain(notifier)
        assert notifier.stats["sent"] == 1
        assert notifier.stats["failed"] == 0
    finally:
        notifier.close()


def test_full_queue_drops_and_counts():
    capture = Capture()
    notifier = _notifier(capture, queue_size=1)
    # No worker: the queue is a plain buffer, so the second alert has nowhere to go.
    notifier._start = lambda: None  # type: ignore[method-assign]
    notifier._queue.put_nowait(Alert("warn", "x", "ocupa la cola"))
    assert notifier.enqueue("warn", "y", "no cabe") is False
    assert notifier.stats["dropped"] == 1


def test_close_counts_pending_alerts_as_dropped():
    notifier = _notifier(Capture())
    notifier._queue.put_nowait(Alert("warn", "x", "pendiente"))
    notifier.close()
    assert notifier.stats["dropped"] == 1


def test_snapshot_reports_the_configuration_and_counters():
    notifier = _notifier(Capture())
    info = notifier.snapshot()
    assert info["enabled"] is True
    assert info["url_configured"] is True
    assert info["min_level"] == "warn"
    assert info["queued"] == 0


def test_invalid_min_level_is_rejected():
    with pytest.raises(ValueError):
        WebhookNotifier("http://example.test", min_level="loud")


# --- wiring ---------------------------------------------------------------
def test_build_notifier_honours_the_config_and_the_env_override():
    assert build_notifier(AlertsConfig()) is None
    assert build_notifier(AlertsConfig(enabled=True)) is None
    from_config = build_notifier(AlertsConfig(enabled=True, webhook_url="http://a.test"))
    assert from_config is not None and from_config.url == "http://a.test"
    from_env = build_notifier(AlertsConfig(), url_override="http://b.test")
    assert from_env is not None and from_env.url == "http://b.test"


def test_engine_forwarded_events_reach_the_notifier(tmp_path: Path):
    capture = Capture()
    notifier = _notifier(capture)
    store = Store(tmp_path / "alerts.db")
    engine = TradingEngine(
        Settings(),
        store,
        feed=SimulatedFeed("2026-01-05", ["AAA"]),
        strategy=NullStrategy(),
        notifier=notifier,
    )
    try:
        engine._event("debug", "engine", "ruido")
        engine.emergency_on()
        _drain(notifier)
        assert [item["category"] for item in capture.sent] == ["risk"]
        assert "emergencia" in capture.sent[0]["message"]
    finally:
        notifier.close()
        store.close()


def test_alerts_endpoint_says_off_and_explains_why(tmp_path: Path):
    app = create_app(config_path=tmp_path / "config.json", db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        body = client.get("/api/alerts").json()
    assert body["enabled"] is False
    assert body["config_enabled"] is False
    assert "webhook" in body["reason"]


def test_alerts_endpoint_reports_counters_when_configured(tmp_path: Path):
    config = tmp_path / "config.json"
    settings = Settings()
    settings.alerts = AlertsConfig(
        enabled=True, webhook_url="http://example.test/hook", min_level="error"
    )
    config.write_text(settings.model_dump_json(), encoding="utf-8")
    app = create_app(config_path=config, db_path=tmp_path / "t.db")
    app.state.notifier = _notifier(Capture())
    with TestClient(app) as client:
        body = client.get("/api/alerts").json()
    assert body["enabled"] is True
    assert body["url_configured"] is True


def test_webhook_posts_json_over_a_real_socket():
    """One loopback round trip: the payload really is JSON on the wire."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    received: list[dict] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802 - nombre impuesto por http.server
            length = int(self.headers["Content-Length"])
            received.append(json.loads(self.rfile.read(length).decode("utf-8")))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    notifier = WebhookNotifier(
        f"http://127.0.0.1:{server.server_address[1]}/hook", dedupe_window_s=0.0
    )
    try:
        notifier.enqueue("error", "risk", "parada de emergencia activada", {"mode": "paper"})
        _drain(notifier)
        assert notifier.stats["sent"] == 1
        assert received[0]["message"] == "parada de emergencia activada"
        assert received[0]["meta"]["mode"] == "paper"
    finally:
        notifier.close()
        server.shutdown()
        server.server_close()


def test_send_now_delivers_on_the_calling_thread():
    capture = Capture()
    notifier = _notifier(capture)

    result = notifier.send_now("warn", "test", "prueba desde la UI")

    assert result["sent"] is True
    assert result["reason"] is None
    assert capture.sent[0]["category"] == "test"
    assert result["stats"]["sent"] == 1
    notifier.close()


def test_send_now_reports_failure_instead_of_lying():
    capture = Capture(fail_times=5)
    notifier = _notifier(capture, max_retries=1)

    result = notifier.send_now("warn", "test", "prueba")

    assert result["sent"] is False
    assert "webhook" in result["reason"]
    assert result["stats"]["failed"] == 1
    notifier.close()


def test_send_now_bypasses_min_level_but_not_the_switch():
    capture = Capture()
    notifier = _notifier(capture, min_level="warn")
    assert notifier.send_now("info", "test", "info explícita")["sent"] is True

    disabled = WebhookNotifier(None, transport=capture, dedupe_window_s=0.0)
    result = disabled.send_now("warn", "test", "sin webhook")
    assert result["sent"] is False
    assert "desactivadas" in result["reason"]
    notifier.close()


def test_alerts_test_endpoint_without_webhook_is_explicit(tmp_path: Path):
    app = create_app(
        config_path=tmp_path / "config.json",
        db_path=tmp_path / "alerts.db",
    )
    with TestClient(app) as client:
        body = client.post("/api/alerts/test").json()

    assert body["sent"] is False
    assert "desactivadas" in body["reason"]
    assert body["config_enabled"] is False


def test_alerts_test_endpoint_delivers_when_configured(tmp_path: Path, monkeypatch):
    capture = Capture()
    config = tmp_path / "config.json"
    config.write_text(
        Settings(
            auto_start=False,
            alerts=AlertsConfig(enabled=True, webhook_url="http://example.test/hook"),
        ).model_dump_json(),
        encoding="utf-8",
    )
    fake = _notifier(capture)
    monkeypatch.setattr("server.main.build_notifier", lambda *args, **kwargs: fake)
    app = create_app(config_path=config, db_path=tmp_path / "alerts.db")

    with TestClient(app) as client:
        body = client.post("/api/alerts/test").json()

    assert body["sent"] is True
    assert capture.sent[0]["source"] == "ezur"


def test_enabling_alerts_via_config_rebuilds_the_notifier(tmp_path: Path, monkeypatch):
    capture = Capture()
    fake = _notifier(capture)
    calls: list[object] = []

    def builder(config, **kwargs):
        calls.append(config)
        return fake

    monkeypatch.setattr("server.alerts.build_notifier", builder)
    app = create_app(
        config_path=tmp_path / "config.json",
        db_path=tmp_path / "config-alerts.db",
    )
    with TestClient(app) as client:
        before = client.get("/api/alerts").json()
        assert before["enabled"] is False

        client.put(
            "/api/config",
            json={
                "patch": {
                    "alerts": {
                        "enabled": True,
                        "webhook_url": "http://example.test/hook",
                        "min_level": "warn",
                    }
                }
            },
        )
        after = client.get("/api/alerts").json()
        assert after["enabled"] is True

        sent = client.post("/api/alerts/test").json()
        assert sent["sent"] is True

    assert calls  # el cambio reconstruyó el notifier
    assert capture.sent[0]["category"] == "test"
