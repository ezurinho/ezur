from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from server.models import Bar, SessionInfo
from server.strategy.base import MarketData
from server.strategy.donchian import DonchianParams, DonchianStrategy
from server.strategy.fade import FadeParams, FadeStrategy

NOW = datetime(2026, 1, 15, 15, 0, tzinfo=timezone.utc)


def _session() -> SessionInfo:
    return SessionInfo(id="2026-01-15:RTH", label="RTH", is_open=True, phase="open")


def _bars(bars: list[tuple[float, float, float, float]]) -> list[Bar]:
    return [
        Bar(
            t=NOW + timedelta(minutes=index),
            o=values[0],
            h=values[1],
            l=values[2],
            c=values[3],
            v=10,
        )
        for index, values in enumerate(bars)
    ]


def _flat_bars(count: int, price: float = 100.0, width: float = 0.5) -> list[Bar]:
    return _bars(
        [(price, price + width, price - width, price) for _ in range(count)]
    )


def _oscillating_bars(count: int, amplitude: float = 1.0) -> list[Bar]:
    """Bars with a non-zero deviation so the bands are not degenerate."""
    prices = [100.0 + (amplitude if index % 2 else -amplitude) for index in range(count)]
    return _bars([(price, price + 0.4, price - 0.4, price) for price in prices])


def _market(bars: list[Bar]) -> MarketData:
    return MarketData(
        session=_session(),
        clock=bars[-1].t,
        primary="PRIMARY",
        bars={"PRIMARY": bars},
    )


# --- Donchian -------------------------------------------------------------


def test_donchian_needs_warmup_before_anything_else():
    strategy = DonchianStrategy({"channel": 20})
    output = strategy.evaluate(_market(_flat_bars(5)))
    assert output.state == "warmup"
    assert output.signal is None
    assert output.phases[0].status == "active"


def test_donchian_emits_a_long_signal_on_an_upside_breakout():
    strategy = DonchianStrategy({"channel": 10, "atr_period": 5, "stop_atr": 1.0, "rr": 2.0})
    bars = _flat_bars(20) + _bars([(100.0, 106.0, 99.9, 105.5)])
    output = strategy.evaluate(_market(bars))
    assert output.signal is not None
    assert output.signal.side == "long"
    assert output.signal.stop_price < 105.5
    assert output.signal.target_price > 105.5
    assert output.state == "armed"


def test_donchian_emits_a_short_signal_on_a_downside_breakout():
    strategy = DonchianStrategy({"channel": 10, "atr_period": 5})
    bars = _flat_bars(20) + _bars([(100.0, 100.1, 94.0, 94.5)])
    output = strategy.evaluate(_market(bars))
    assert output.signal is not None
    assert output.signal.side == "short"
    assert output.signal.stop_price > 94.5


def test_donchian_stays_flat_inside_the_channel():
    strategy = DonchianStrategy({"channel": 10, "atr_period": 5})
    bars = _flat_bars(20) + _bars([(100.0, 100.4, 99.6, 100.1)])
    output = strategy.evaluate(_market(bars))
    assert output.signal is None
    assert output.state == "scanning"
    assert len(output.zones) == 1


def test_donchian_buffer_delays_the_breakout():
    tight = DonchianStrategy({"channel": 10, "atr_period": 5, "buffer_ticks": 0})
    wide = DonchianStrategy({"channel": 10, "atr_period": 5, "buffer_ticks": 20})
    bars = _flat_bars(20) + _bars([(100.0, 100.9, 99.9, 100.6)])
    assert tight.evaluate(_market(bars)).signal is not None
    assert wide.evaluate(_market(bars)).signal is None


def test_donchian_rejects_unknown_params():
    with pytest.raises(ValidationError):
        DonchianParams(canal=10)


def test_donchian_declares_its_warmup_requirement():
    assert DonchianStrategy({"channel": 30, "atr_period": 14}).warmup_requirements().bars == {"*": 32}


# --- Fade -----------------------------------------------------------------


def test_fade_needs_warmup_before_anything_else():
    output = FadeStrategy().evaluate(_market(_flat_bars(4)))
    assert output.state == "warmup"
    assert output.signal is None


def test_fade_buys_a_close_below_the_lower_band():
    strategy = FadeStrategy({"period": 10, "sigma": 1.5, "atr_period": 5, "require_close_inside": False})
    bars = _flat_bars(20) + _bars([(100.0, 100.2, 96.0, 96.5)])
    output = strategy.evaluate(_market(bars))
    assert output.signal is not None
    assert output.signal.side == "long"
    assert output.signal.target_price > output.signal.stop_price


def test_fade_sells_a_close_above_the_upper_band():
    strategy = FadeStrategy({"period": 10, "sigma": 1.5, "atr_period": 5, "require_close_inside": False})
    bars = _flat_bars(20) + _bars([(100.0, 104.0, 99.8, 103.5)])
    output = strategy.evaluate(_market(bars))
    assert output.signal is not None
    assert output.signal.side == "short"


def test_fade_requires_the_close_to_come_back_inside_when_configured():
    strict = FadeStrategy(
        {"period": 10, "sigma": 0.5, "atr_period": 5, "require_close_inside": True}
    )
    loose = FadeStrategy(
        {"period": 10, "sigma": 0.5, "atr_period": 5, "require_close_inside": False}
    )
    base = _oscillating_bars(20, amplitude=1.0)

    # Wick below the band but the close stays outside: only the loose version fires.
    closed_outside = base + _bars([(100.0, 100.2, 93.0, 93.5)])
    assert strict.evaluate(_market(closed_outside)).signal is None
    assert loose.evaluate(_market(closed_outside)).signal is not None

    # Wick below and close back inside, still under the mean: both fire.
    closed_inside = base + _bars([(100.0, 100.4, 93.0, 99.8)])
    assert strict.evaluate(_market(closed_inside)).signal is not None
    assert strict.evaluate(_market(closed_inside)).signal.side == "long"


def test_fade_does_not_emit_a_target_behind_the_entry():
    """La media es el objetivo: si el cierre ya la cruzó, no hay recorrido."""
    strategy = FadeStrategy({"period": 10, "sigma": 1.5, "atr_period": 5})

    # Pincha la banda inferior y vuelve a cerrar dentro, pero por encima de la media.
    below_the_mean = _flat_bars(20) + _bars([(100.0, 100.6, 96.0, 100.5)])
    long_side = strategy.evaluate(_market(below_the_mean))
    assert long_side.signal is None
    assert long_side.state == "scanning"

    # Espejo: pincha la banda superior y cierra por debajo de la media.
    above_the_mean = _flat_bars(20) + _bars([(100.0, 104.0, 99.4, 99.5)])
    short_side = strategy.evaluate(_market(above_the_mean))
    assert short_side.signal is None
    assert short_side.state == "scanning"


def test_fade_stays_flat_inside_the_bands():
    wide = FadeStrategy({"period": 10, "sigma": 6.0, "atr_period": 5})
    output = wide.evaluate(_market(_oscillating_bars(30, amplitude=1.0)))
    assert output.signal is None
    assert output.state == "scanning"


def test_fade_does_not_crash_on_a_degenerate_band():
    output = FadeStrategy().evaluate(_market(_flat_bars(30)))
    assert output.signal is None


def test_fade_publishes_the_mean_line_zone():
    strategy = FadeStrategy({"period": 10, "sigma": 2.0, "atr_period": 5})
    bars = _flat_bars(20) + _bars([(100.0, 100.2, 99.8, 100.1)])
    output = strategy.evaluate(_market(bars))
    kinds = {zone.kind for zone in output.zones}
    assert "band" in kinds
    assert "line" in kinds


def test_fade_rejects_unknown_params():
    with pytest.raises(ValidationError):
        FadeParams(periodo=10)
