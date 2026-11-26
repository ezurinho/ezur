"""Coste de ejecución: slippage por tamaño y funding de perpetuos."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from server.config import ExecutionConfig, Settings
from server.execution import ExecutionEngine

SETTINGS = Settings()
SYMBOL = SETTINGS.instruments.primary
SPEC = SETTINGS.instruments.by_symbol(SYMBOL)


def _engine(**overrides) -> ExecutionEngine:
    return ExecutionEngine(ExecutionConfig(**overrides), {SYMBOL: SPEC})


def test_el_slippage_crece_con_el_tamano_y_respeta_el_tope():
    engine = _engine(
        slippage_ticks=1,
        max_slippage_ticks=5,
        slippage_ticks_per_100_units=1.0,
    )

    assert engine._slippage_ticks(0) == 1.0
    assert engine._slippage_ticks(100) == 2.0
    assert engine._slippage_ticks(10_000) == 5.0


def test_el_largo_paga_funding_en_cada_frontera_de_8h():
    engine = _engine(funding="real_timestamps", funding_rate_bps_8h=1.0)
    opened = datetime(2026, 11, 26, 7, 0, tzinfo=timezone.utc)
    position = SimpleNamespace(
        symbol=SYMBOL, side="long", units=1, entry_price=100.0, opened_ts=opened
    )

    funding = engine._funding(position, opened + timedelta(hours=10), 100.0)

    contract = SPEC.tick_value / SPEC.tick_size
    expected = -(1 * contract * 100.0) * 1.0 * 1e-4 * 2  # 08:00 y 16:00
    assert funding == pytest.approx(expected)


def test_el_corto_cobra_el_mismo_funding():
    engine = _engine(funding="real_timestamps", funding_rate_bps_8h=1.0)
    opened = datetime(2026, 11, 26, 7, 0, tzinfo=timezone.utc)
    position = SimpleNamespace(
        symbol=SYMBOL, side="short", units=1, entry_price=100.0, opened_ts=opened
    )

    assert engine._funding(position, opened + timedelta(hours=10), 100.0) > 0


def test_sin_fronteras_cruzadas_o_sin_tasa_no_hay_funding():
    engine = _engine(funding="real_timestamps", funding_rate_bps_8h=1.0)
    opened = datetime(2026, 11, 26, 9, 0, tzinfo=timezone.utc)
    position = SimpleNamespace(
        symbol=SYMBOL, side="long", units=1, entry_price=100.0, opened_ts=opened
    )

    assert engine._funding(position, opened + timedelta(hours=2), 100.0) == 0.0

    zero = _engine(funding="none")
    assert zero._funding(position, opened + timedelta(days=1), 100.0) == 0.0
