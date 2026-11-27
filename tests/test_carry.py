"""El carry entra con funding positivo, sale con negativo y cobra la prima."""

import pandas as pd

from server.carry import run_carry

START = pd.Timestamp("2025-01-01", tz="UTC")
GRID = pd.date_range(START, periods=50, freq="8h")


def _series(value: float) -> pd.Series:
    return pd.Series(value, index=GRID)


def test_cobra_funding_y_paga_costes():
    funding = pd.Series([0.001] * 35 + [-0.001] * 15, index=GRID)
    spot = _series(100.0)
    perp = _series(100.0)

    result = run_carry(funding, spot, perp, window=9, threshold=0.00005, capital=25_000)

    assert len(result.episodes) == 1
    episode = result.episodes[0]
    assert episode.funding > 0
    assert episode.basis == 0
    assert episode.costs == 62.5
    assert episode.net == episode.funding - 62.5
    assert result.summary()["expectancy_r"] > 0


def test_sin_funding_positivo_no_entra():
    funding = _series(-0.001)
    result = run_carry(funding, _series(100.0), _series(100.0), window=9, threshold=0.00005)
    assert result.episodes == []


def test_el_basis_se_suma_al_funding():
    funding = pd.Series([0.001] * 35 + [-0.001] * 15, index=GRID)
    spot = pd.Series([100.0] * 50, index=GRID)
    perp = pd.Series([100.0] * 50, index=GRID)
    perp.iloc[30:] = 98.0  # el perpetuo cae: el corto gana

    result = run_carry(funding, spot, perp, window=9, threshold=0.00005, capital=25_000)

    assert len(result.episodes) == 1
    assert result.episodes[0].basis > 0
