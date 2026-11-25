"""Primitivas de indicadores: las comparten todos los plugins."""
from __future__ import annotations

import pytest

from server.strategy.indicators import atr, ema, highest, lowest, sma, stdev
from tests.conftest import NOW, make_bar


def _bars(closes: list[float], highs: list[float], lows: list[float]):
    return [
        make_bar(t=NOW, o=close, h=high, l=low, c=close, v=1.0)
        for close, high, low in zip(closes, highs, lows, strict=True)
    ]


def test_sma_y_stdev_exigen_ventana_suficiente():
    assert sma([1, 2, 3], 0) is None
    assert sma([1, 2], 3) is None
    assert sma([1, 2, 3, 4], 2) == pytest.approx(3.5)
    assert stdev([1, 2, 3], 1) is None
    assert stdev([1, 2], 3) is None
    assert stdev([2, 4, 4, 4, 5, 5, 7, 9], 8) == pytest.approx(2.0)


def test_atr_usa_el_rango_verdadero_contra_el_cierre_anterior():
    bars = _bars([100, 101, 103], [101, 102, 105], [99, 100, 102])

    assert atr(bars, 0) is None
    assert atr(bars, 3) is None
    # (max(2, 2, 0) + max(3, 4, 1)) / 2
    assert atr(bars, 2) == pytest.approx(3.0)


def test_highest_y_lowest_miran_solo_la_ventana():
    bars = _bars([100, 101, 103], [101, 104, 102], [99, 98, 100])

    assert highest(bars, 0) is None
    assert highest(bars, 2) == 104
    assert lowest(bars, 0) is None
    assert lowest(bars, 2) == 98


def test_ema_arranca_con_la_media_y_suaviza_despues():
    assert ema([1, 2], 0) is None
    assert ema([1, 2], 3) is None
    assert ema([1, 2, 3], 3) == pytest.approx(2.0)
    # alpha = 2/(3+1) = 0,5: 0,5*3 + 0,5*2
    assert ema([1, 2, 3, 3], 3) == pytest.approx(2.5)
