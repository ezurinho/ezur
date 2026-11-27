"""El R de una operacion se mide contra el stop inicial, no contra el trailing."""

from types import SimpleNamespace

from server.config import Settings
from server.db import Store
from server.engine import TradingEngine
from server.strategy.spec_driven import DonchianTrendStrategy


def test_el_riesgo_no_se_encoge_cuando_el_trailing_sube_el_stop():
    settings = Settings()
    primary = settings.instruments.primary
    store = Store(":memory:")
    try:
        engine = TradingEngine(
            settings,
            store,
            feed=None,
            strategy=DonchianTrendStrategy({"N": 15, "atr_k": 3, "trail_atr_k": 3}),
        )
        position = SimpleNamespace(
            symbol=primary,
            entry_price=100.0,
            stop_price=105.0,
            initial_stop_price=90.0,
        )

        risk = engine.execution._risk_per_unit(position)

        spec = settings.instruments.by_symbol(primary)
        assert risk == 10.0 / spec.tick_size * spec.tick_value
    finally:
        store.close()
