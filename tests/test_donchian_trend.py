"""H1: ruptura con tendencia y trailing que solo sube."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.models import Bar, SessionInfo
from server.strategy.base import MarketData
from server.strategy.spec_driven import DonchianTrendStrategy

T0 = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _bars(count: int, first: float = 100.0, step: float = 1.0) -> list[Bar]:
    rows = []
    for index in range(count):
        close = first + index * step
        rows.append(
            Bar(
                t=T0 + timedelta(hours=index),
                o=close,
                h=close + 0.5,
                l=close - 0.5,
                c=close,
            )
        )
    return rows


def _flat(count: int) -> list[Bar]:
    return [
        Bar(t=T0 + timedelta(hours=index), o=100.0, h=100.2, l=99.8, c=100.0)
        for index in range(count)
    ]


def test_la_ruptura_solo_entra_larga_con_tendencia():
    strategy = DonchianTrendStrategy(
        {"N": 15, "trend_sma": 200, "atr_k": 3, "trail_atr_k": 3}
    )
    md = MarketData(
        session=SessionInfo(id="test", is_open=True),
        clock=T0 + timedelta(hours=209),
        primary="BTC",
        bars={"BTC": _bars(210)},
    )

    output = strategy.evaluate(md)

    assert output.signal is not None
    assert output.signal.side == "long"
    assert output.signal.stop_price == 304.5
    assert output.signal.target_price == 759.0


def test_sin_ruptura_no_hay_senal():
    strategy = DonchianTrendStrategy(
        {"N": 15, "trend_sma": 200, "atr_k": 3, "trail_atr_k": 3}
    )
    md = MarketData(
        session=SessionInfo(id="test", is_open=True),
        clock=T0 + timedelta(hours=209),
        primary="BTC",
        bars={"BTC": _flat(210)},
    )

    output = strategy.evaluate(md)

    assert output.signal is None


def test_el_trailing_sube_el_stop_y_nunca_lo_baja():
    settings = Settings()
    primary = settings.instruments.primary
    settings.strategy.params = {"trail_atr_k": 3.0, "atr_period": 3}
    store = Store(":memory:")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=None,
            strategy=DonchianTrendStrategy(
                {"N": 15, "atr_k": 3, "trail_atr_k": 3.0}
            ),
        )
        bars = _bars(5, first=100.0, step=2.0)
        engine._bars = {primary: bars}
        engine.execution.position = SimpleNamespace(
            symbol=primary,
            side="long",
            stop_price=90.0,
            opened_ts=bars[0].t,
        )

        engine._update_trailing_stop()

        assert engine.execution.position.stop_price == 101.0

        bars.append(
            Bar(
                t=bars[-1].t + timedelta(hours=1),
                o=107.0,
                h=107.5,
                l=104.5,
                c=106.0,
            )
        )
        engine._update_trailing_stop()

        assert engine.execution.position.stop_price == 101.0
    finally:
        store.close()


def test_sin_parametro_de_trailing_el_stop_no_se_toca():
    settings = Settings()
    primary = settings.instruments.primary
    settings.strategy.params = {}
    store = Store(":memory:")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=None,
            strategy=DonchianTrendStrategy(
                {"N": 15, "atr_k": 3, "trail_atr_k": 3.0}
            ),
        )
        bars = _bars(5, first=100.0, step=2.0)
        engine._bars = {primary: bars}
        engine.execution.position = SimpleNamespace(
            symbol=primary,
            side="long",
            stop_price=90.0,
            opened_ts=bars[0].t,
        )

        engine._update_trailing_stop()

        assert engine.execution.position.stop_price == 90.0
    finally:
        store.close()
