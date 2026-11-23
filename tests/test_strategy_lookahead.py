"""Ningún plugin puede mirar el futuro ni recordar lo que ya vio.

El contrato promete «sólo velas cerradas, sin lookahead, sin estado oculto» y
nada lo comprobaba. Desde fuera sólo se puede verificar una cosa, pero es la que
importa: la misma historia tiene que dar siempre la misma respuesta, aunque el
plugin haya visto antes velas posteriores o sea otra instancia.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone

import pytest

from server.models import Bar, SessionInfo
from server.strategy.base import MarketData
from server.strategy.registry import available, resolve_strategy

NOW = datetime(2026, 1, 15, 14, 0, tzinfo=timezone.utc)
CUTS = (70, 100, 130, 160)
PLUGINS = [strategy_id for strategy_id in available() if strategy_id != "null"]


def _session() -> SessionInfo:
    return SessionInfo(id="2026-01-15:RTH", label="RTH", is_open=True, phase="open")


def _series(count: int = 170) -> list[Bar]:
    """Determinista, con tendencia y oscilación: hay cruces y rupturas."""
    bars: list[Bar] = []
    price = 100.0
    for index in range(count):
        step = 0.12 * math.sin(index / 5.0) + 0.02
        close = price + step
        bars.append(
            Bar(
                t=NOW + timedelta(minutes=index),
                o=price,
                h=max(price, close) + 0.3,
                l=min(price, close) - 0.3,
                c=close,
                v=10,
            )
        )
        price = close
    return bars


def _market(bars: list[Bar]) -> MarketData:
    return MarketData(
        session=_session(),
        clock=bars[-1].t,
        primary="PRIMARY",
        bars={"PRIMARY": bars},
    )


@pytest.mark.parametrize("strategy_id", PLUGINS)
def test_the_same_history_gives_the_same_answer(strategy_id):
    strategy = resolve_strategy(strategy_id, {})
    bars = _series()
    for cut in CUTS:
        prefix = bars[:cut]
        first = strategy.evaluate(_market(prefix))
        # El plugin ve el futuro y vuelve al mismo punto: si guardara algo, cambiaría.
        strategy.evaluate(_market(bars))
        again = strategy.evaluate(_market(prefix))
        assert first == again, f"{strategy_id} cambió su salida en la vela {cut}"


@pytest.mark.parametrize("strategy_id", PLUGINS)
def test_a_fresh_plugin_gives_the_same_answer(strategy_id):
    prefix = _series()[: CUTS[-1]]
    first = resolve_strategy(strategy_id, {}).evaluate(_market(prefix))
    second = resolve_strategy(strategy_id, {}).evaluate(_market(prefix))
    assert first == second


def test_the_series_actually_produces_signals():
    """Sin señales, los dos tests anteriores pasarían sin comprobar nada."""
    bars = _series()
    outputs = [
        resolve_strategy(strategy_id, {}).evaluate(_market(bars[:cut]))
        for strategy_id in PLUGINS
        for cut in range(60, len(bars) + 1)
    ]
    assert any(output.signal is not None for output in outputs)
