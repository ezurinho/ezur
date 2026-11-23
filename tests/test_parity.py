"""Paridad backtest ↔ motor vivo sobre las mismas velas.

Nautilus insiste en «identical strategy implementations between research and live
deployment»; la única forma de afirmarlo es ejecutar los dos caminos con el mismo
input y comparar los fills. Aquí el «vivo» es el motor en modo paper consumiendo
el mismo CSV: si los resultados difieren, la diferencia está en el motor, no en
el mercado.
"""

from __future__ import annotations

from pathlib import Path

from server.backtest import run_backtest
from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.market.feed import CSVFeed
from server.strategy.registry import resolve_strategy

from tests.test_api_backtest import _dataset


def _settings() -> Settings:
    settings = Settings()
    settings.instruments.items = [
        type(settings.instruments.items[0])(symbol="PRIMARY", role="primary"),
        type(settings.instruments.items[0])(symbol="CTX_A", role="context"),
    ]
    settings.strategy.id = "reference"
    return settings


def _fingerprint(rows: list[dict]) -> list[tuple]:
    return [
        (
            row["symbol"],
            row["side"],
            float(row["entry_price"]),
            float(row["exit_price"]),
            float(row["pnl_net"]),
            int(row["units"]),
            row["exit_reason"],
        )
        for row in rows
    ]


def test_backtest_and_live_engine_produce_the_same_trades(tmp_path: Path):
    settings = _settings()
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=180)

    backtest = run_backtest(settings, path)
    backtest_rows = [trade.model_dump(mode="json") for trade in backtest.trades]

    store = Store(tmp_path / "live.db")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=CSVFeed(path, settings.instruments.symbols),
            strategy=resolve_strategy("reference", None),
            mode="paper",
        )
        engine.start()
        for tick in CSVFeed(path, settings.instruments.symbols).iter_ticks():
            engine._process(tick)
        live_rows = list(reversed(store.list_trades(limit=1_000_000)))
    finally:
        store.close()

    assert len(backtest_rows) == len(live_rows) > 0
    assert _fingerprint(backtest_rows) == _fingerprint(live_rows)


def test_parity_holds_for_a_different_strategy(tmp_path: Path):
    settings = _settings()
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=180)

    backtest = run_backtest(
        settings, path, resolve_strategy("donchian", None)
    )
    backtest_rows = [trade.model_dump(mode="json") for trade in backtest.trades]

    store = Store(tmp_path / "live2.db")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=CSVFeed(path, settings.instruments.symbols),
            strategy=resolve_strategy("donchian", None),
            mode="paper",
        )
        engine.start()
        for tick in CSVFeed(path, settings.instruments.symbols).iter_ticks():
            engine._process(tick)
        live_rows = list(reversed(store.list_trades(limit=1_000_000)))
    finally:
        store.close()

    assert len(backtest_rows) == len(live_rows)
    assert _fingerprint(backtest_rows) == _fingerprint(live_rows)


def test_pnl_totals_match_to_the_cent(tmp_path: Path):
    settings = _settings()
    path = _dataset(tmp_path / "bars.csv", settings, ["PRIMARY", "CTX_A"], bars=180)

    backtest = run_backtest(settings, path)
    total = sum(trade.pnl_net for trade in backtest.trades)

    store = Store(tmp_path / "live3.db")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=CSVFeed(path, settings.instruments.symbols),
            strategy=resolve_strategy("reference", None),
            mode="paper",
        )
        engine.start()
        for tick in CSVFeed(path, settings.instruments.symbols).iter_ticks():
            engine._process(tick)
        live_total = sum(float(row["pnl_net"]) for row in store.list_trades(limit=1_000_000))
    finally:
        store.close()

    assert round(total - live_total, 6) == 0
