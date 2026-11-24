"""El contador del día no debe sobrevivir a un reinicio del día siguiente."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from server.config import InstrumentsConfig, Settings
from server.db import Store
from server.engine import TradingEngine
from server.models import TradeRecord

NOW = datetime.now(timezone.utc)
TODAY = NOW.strftime("%Y-%m-%d")
YESTERDAY = "2020-01-01"


def _settings() -> Settings:
    """Sesión de 24 h en UTC, como el perfil que opera: el día es el día."""
    return Settings(
        instruments=InstrumentsConfig(
            primary="BTC",
            items=[
                {
                    "symbol": "BTC",
                    "venue_symbol": "BTC-USDT",
                    "tick_size": 0.01,
                    "tick_value": 0.01,
                    "role": "primary",
                    "session_template": "CRYPTO24",
                }
            ],
            templates=[
                {
                    "name": "CRYPTO24",
                    "timezone": "UTC",
                    "open": "00:00",
                    "close": "23:59",
                    "weekdays": [0, 1, 2, 3, 4, 5, 6],
                }
            ],
        )
    )


def _trade(closed: datetime, pnl: float, key: str) -> TradeRecord:
    return TradeRecord(
        symbol="BTC",
        side="long",
        units=1,
        entry_price=100.0,
        exit_price=100.0 + pnl,
        opened_ts=closed,
        closed_ts=closed,
        pnl_gross=pnl,
        fees=0.0,
        pnl_net=pnl,
        signal_key=key,
    )


def _store(tmp_path, trades: list[TradeRecord]) -> Store:
    store = Store(tmp_path / "terminal.db")
    for trade in trades:
        store.insert_trade(trade)
    return store


def test_el_contador_de_ayer_no_bloquea_el_dia_de_hoy(tmp_path):
    store = _store(
        tmp_path,
        [
            _trade(datetime(2020, 1, 1, 10, tzinfo=timezone.utc), -50.0, "vieja-1"),
            _trade(datetime(2020, 1, 1, 11, tzinfo=timezone.utc), -50.0, "vieja-2"),
            _trade(NOW, 25.0, "hoy-1"),
        ],
    )
    store.kv_set("session_id", f"{YESTERDAY}:CRYPTO24")
    store.kv_set(
        "day_stats",
        {"trades": 2, "wins": 0, "losses": 2, "pnl": -100.0, "consecutive_losses": 2},
    )
    try:
        engine = TradingEngine(_settings(), store, feed=None)
        stats = engine.state.day_stats
        assert stats.trades == 1
        assert stats.wins == 1
        assert stats.pnl == pytest.approx(25.0)
        assert stats.consecutive_losses == 0
        assert store.kv_get("session_id").startswith(TODAY)
    finally:
        store.close()


def test_el_contador_de_la_misma_sesion_se_respeta(tmp_path):
    store = _store(tmp_path, [_trade(NOW, 10.0, "hoy-1")])
    session = TradingEngine(_settings(), store, feed=None).state.session
    assert session is not None
    store.kv_set("session_id", session.id)
    store.kv_set(
        "day_stats",
        {"trades": 5, "wins": 3, "losses": 2, "pnl": 80.0, "consecutive_losses": 0},
    )
    try:
        engine = TradingEngine(_settings(), store, feed=None)
        assert engine.state.day_stats.trades == 5
        assert engine.state.day_stats.pnl == pytest.approx(80.0)
    finally:
        store.close()


def test_sin_operaciones_de_hoy_el_dia_arranca_a_cero(tmp_path):
    store = _store(tmp_path, [_trade(datetime(2020, 1, 1, 10, tzinfo=timezone.utc), -50.0, "a")])
    store.kv_set("session_id", f"{YESTERDAY}:CRYPTO24")
    store.kv_set(
        "day_stats",
        json.dumps({"trades": 3, "wins": 0, "losses": 3, "pnl": -9.0, "consecutive_losses": 3}),
    )
    try:
        engine = TradingEngine(_settings(), store, feed=None)
        assert engine.state.day_stats.trades == 0
        assert engine.state.day_stats.pnl == 0
    finally:
        store.close()
