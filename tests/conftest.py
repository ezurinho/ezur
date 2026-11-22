from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.main import create_app
from server.models import Bar, PortfolioState, SessionInfo
from server.strategy.base import MarketData, Signal
from pydantic import BaseModel

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


class EmptyParams(BaseModel):
    pass


def make_bar(**overrides) -> Bar:
    payload = dict(t=NOW, o=100.0, h=101.0, l=99.8, c=100.5, v=100.0)
    payload.update(overrides)
    return Bar(**payload)


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def store(tmp_path: Path):
    database = Store(tmp_path / "terminal.db")
    yield database
    database.close()


@pytest.fixture
def engine(settings: Settings, store: Store) -> TradingEngine:
    return TradingEngine(settings, store, feed=None)


@pytest.fixture
def client(tmp_path: Path):
    app = create_app(config_path=tmp_path / "config.json", db_path=tmp_path / "api.db")
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def session_info() -> SessionInfo:
    return SessionInfo(
        id="2026-01-15:RTH",
        label="RTH",
        is_open=True,
        open_ts=NOW - timedelta(hours=5),
        close_ts=NOW + timedelta(hours=1),
        phase="open",
    )


@pytest.fixture
def md_fixture(settings: Settings, session_info: SessionInfo) -> MarketData:
    primary = settings.instruments.primary
    bars = [
        make_bar(t=NOW - timedelta(minutes=index), o=100 + index * 0.1,
                 c=100 + index * 0.1, h=100.5 + index * 0.1, l=99.5 + index * 0.1)
        for index in range(5, 0, -1)
    ]
    return MarketData(
        session=session_info,
        clock=NOW,
        primary=primary,
        bars={primary: bars},
        params=EmptyParams(),
    )


@pytest.fixture
def signal_long() -> Signal:
    return Signal(
        key="2026-01-15:long:1500",
        side="long",
        reason="test",
        ts=NOW,
        stop_price=99.5,
        target_price=102.25,
    )


@pytest.fixture
def portfolio() -> PortfolioState:
    return PortfolioState(equity=25000.0, last_price=100.0)


@pytest.fixture
def dataset_path(tmp_path: Path, settings: Settings) -> Path:
    """Two aligned series, deterministic, valid for the validator."""
    path = tmp_path / "bars.csv"
    symbols = settings.instruments.symbols
    start = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        for index in range(60):
            stamp = (start + timedelta(minutes=index)).isoformat()
            for offset, symbol in enumerate(symbols):
                base = 100.0 + offset * 50 + index * 0.25
                writer.writerow([stamp, symbol, base, base + 0.5, base - 0.5, base + 0.25, 100])
    return path
