"""Readiness: motor en marcha, latido y feed frescos, sin reiniciar paradas."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from server.readiness import assess

NOW = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)


class FakeStore:
    def __init__(self, heartbeat: datetime | None) -> None:
        self.heartbeat = heartbeat

    def kv_get(self, key: str) -> datetime | None:
        return self.heartbeat if key == "heartbeat" else None


def fake_engine(status: str = "running", last_bar: datetime | None = None):
    return SimpleNamespace(
        state=SimpleNamespace(status=status, last_bar_ts=last_bar),
        mode="paper",
    )


def test_running_con_latido_y_vela_frescos_esta_listo():
    result = assess(
        fake_engine(last_bar=NOW - timedelta(minutes=2)),
        FakeStore(NOW - timedelta(seconds=20)),
        now=NOW,
    )

    assert result["ready"] is True
    assert result["reasons"] == []
    assert result["heartbeat_age_s"] == 20.0
    assert result["last_bar_age_s"] == 120.0


def test_un_latido_viejo_no_esta_listo():
    result = assess(
        fake_engine(last_bar=NOW - timedelta(minutes=2)),
        FakeStore(NOW - timedelta(hours=2)),
        now=NOW,
    )

    assert result["ready"] is False
    assert "heartbeat_stale" in result["reasons"]


def test_un_feed_viejo_no_esta_listo():
    result = assess(
        fake_engine(last_bar=NOW - timedelta(hours=2)),
        FakeStore(NOW - timedelta(seconds=5)),
        now=NOW,
    )

    assert result["ready"] is False
    assert "feed_stale" in result["reasons"]


def test_un_motor_parado_no_esta_listo_pero_se_distingue():
    result = assess(fake_engine(status="stopped"), FakeStore(NOW), now=NOW)

    assert result["ready"] is False
    assert "engine_stopped" in result["reasons"]
    assert result["engine"]["status"] == "stopped"


def test_arranque_sin_vela_todavia_no_es_fallo_de_feed():
    result = assess(fake_engine(last_bar=None), FakeStore(NOW), now=NOW)

    assert result["ready"] is True
    assert result["last_bar_age_s"] is None


def test_sin_heartbeat_guardado_no_esta_listo():
    result = assess(fake_engine(), FakeStore(None), now=NOW)

    assert result["ready"] is False
    assert "heartbeat_missing" in result["reasons"]
