"""El basis spot-perp cobra convergencia y funding, y no confunde beta con carry."""

import numpy as np
import pandas as pd
import pytest

from server.basis_carry import ASSETS, COST_PER_LEG_SIDE, run_basis_carry

START = pd.Timestamp("2024-01-01", tz="UTC")


def _panels(
    days: int = 120,
    assets: tuple[str, ...] = ("BTCUSDT",),
    basis: float = 0.01,
    funding: float = 0.0001,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    dates = pd.date_range(START, periods=days, freq="D", tz="UTC")
    spot = pd.DataFrame(100.0, index=dates, columns=assets)
    perp = pd.DataFrame(100.0 * (1.0 + basis), index=dates, columns=assets)
    funding_frame = pd.DataFrame(funding, index=dates, columns=assets)
    return spot, perp, funding_frame


def _run(spot, perp, funding, **kwargs):
    return run_basis_carry(
        spot,
        perp,
        funding,
        lookback=kwargs.pop("lookback", 7),
        rebalance=kwargs.pop("rebalance", "D"),
        quantile=kwargs.pop("quantile", 1.0),
        entry=kwargs.pop("entry", 0.00025),
        exit=kwargs.pop("exit", 0.00010),
        assets=tuple(spot.columns),
        **kwargs,
    )


def test_largo_spot_corto_perp_cobra_la_convergencia_y_el_funding():
    spot, perp, funding = _panels()
    perp.iloc[30:] = np.linspace(101.0, 100.0, len(perp) - 30).reshape(-1, 1)

    result = _run(spot, perp, funding)

    assert result.episodes
    summary = result.summary(capital=25_000.0)
    assert summary["price_pnl_usd"] > 0
    assert summary["funding_pnl_usd"] > 0
    assert summary["net_usd"] > 0


def test_si_spot_y_perp_se_mueven_igual_el_precio_no_aporta():
    spot, perp, funding = _panels(funding=0.001)
    path = 1.001 ** np.arange(len(spot))
    spot = spot.mul(path, axis=0)
    perp = perp.mul(path, axis=0)

    result = _run(spot, perp, funding, entry=0.00025, exit=0.00005)

    assert result.episodes
    assert abs(result.summary(capital=25_000.0)["price_pnl_usd"]) < 1e-6
    assert result.summary(capital=25_000.0)["funding_pnl_usd"] > 0


def test_los_costes_se_cobran_en_entrada_y_salida_de_las_dos_patas():
    spot, perp, funding = _panels(funding=0.001)
    cheap = _run(spot, perp, funding, cost_per_leg_side=0.0)
    expensive = _run(spot, perp, funding, cost_per_leg_side=COST_PER_LEG_SIDE)

    assert cheap.summary(capital=25_000.0)["net_usd"] > expensive.summary(capital=25_000.0)["net_usd"]
    expected = COST_PER_LEG_SIDE * 12_500.0 * 4.0
    assert all(item["costs"] == pytest.approx(expected) for item in expensive.episodes)


def test_el_max_hold_cierra_y_no_reentra_el_mismo_dia():
    spot, perp, funding = _panels(funding=0.001)

    result = _run(spot, perp, funding, max_hold_days=28)

    assert result.episodes
    assert all(item["days"] >= 28 for item in result.episodes[:-1])
    assert all(item["days"] <= 29 for item in result.episodes)


def test_sin_carry_no_hay_posiciones():
    spot, perp, funding = _panels(basis=0.0, funding=0.0)

    result = _run(spot, perp, funding)

    assert result.episodes == []


def test_la_senal_usa_el_basis_hasta_t_menos_1():
    spot, perp, funding = _panels(basis=0.0, funding=0.0, days=70)
    perp.loc[perp.index >= pd.Timestamp("2024-01-08", tz="UTC"), "BTCUSDT"] = 101.0

    result = _run(spot, perp, funding)

    assert result.episodes
    # El basis del 8 de enero entra en la senal del 9: nunca el mismo dia.
    assert result.episodes[0]["entry"] == pd.Timestamp("2024-01-09", tz="UTC")


def test_el_universo_declara_los_veinte_activos():
    assert len(ASSETS) == 20
    assert "BTCUSDT" in ASSETS
    assert "SANDUSDT" in ASSETS
