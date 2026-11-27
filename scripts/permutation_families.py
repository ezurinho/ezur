"""Nulidad por permutación para H6, H7 y H9.

Cada familia tiene su motor y su dato de señal, así que la permutación se aplica
sobre lo que hace de señal, nunca sobre la serie de P&L de la estrategia (el
Sharpe y la esperanza son invariantes al orden de los retornos: ese null sería
degenerado).

- **H6 (TSMOM)**: la señal sale del propio precio. Se barajan los **retornos
  diarios** de cada símbolo y se reconstruye el precio: se destruye la
  persistencia de tendencia y se conserva la distribución marginal.
- **H7 (flujo de taker)**: se baraja el **ratio de flujo** de cada símbolo en el
  tiempo; precios, volumen y funding quedan reales.
- **H9 (basis)**: se baraja el **funding** de cada símbolo. Aviso: la señal de H9
  suma basis y funding, y el basis queda intacto, así que esta nulidad sólo mide
  la parte de funding. Para la parte de basis se corre además el motor con
  `perp = spot` (basis exactamente cero), que aísla el carry.

La pregunta no es «¿es significativo el beneficio?» —las tres pierden— sino
«¿es el veredicto distinguible del ruido?»: si el observado cae dentro de la
nulidad, el archivo se sostiene en la puerta, no en evidencia de daño.

Uso:
    python scripts/permutation_families.py --permutations 50
    python scripts/permutation_families.py --family H7 --permutations 20
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.basis_carry import load_panels as load_basis, run_basis_carry  # noqa: E402
from server.taker_flow import load_data as load_flow, run_flow  # noqa: E402
from server.tsmom import load_prices, run_tsmom  # noqa: E402

START = pd.Timestamp("2025-01-01", tz="UTC")
END = pd.Timestamp("2026-11-01", tz="UTC")
YEARS = (END - START).days / 365.25


def shuffle_columns(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    values = frame.to_numpy(dtype=float, copy=True)
    for column in range(values.shape[1]):
        series = values[:, column]
        mask = np.isfinite(series)
        block = series[mask]
        rng.shuffle(block)
        series[mask] = block
        values[:, column] = series
    return pd.DataFrame(values, index=frame.index, columns=frame.columns)


def shuffle_returns(prices: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Baraja retornos y reconstruye el precio, conservando los huecos."""
    returns = prices.pct_change(fill_method=None)
    values = returns.to_numpy(dtype=float, copy=True)
    for column in range(values.shape[1]):
        series = values[:, column]
        mask = np.isfinite(series)
        block = series[mask]
        rng.shuffle(block)
        series[mask] = block
        values[:, column] = series
    growth = np.where(np.isfinite(values), 1.0 + values, 1.0)
    base = prices.apply(lambda column: column.dropna().iloc[0] if column.notna().any() else np.nan)
    rebuilt = pd.DataFrame(growth, index=prices.index, columns=prices.columns).cumprod() * base
    return rebuilt.where(prices.notna())


def metrics(summary: dict) -> dict:
    return {
        "episodios": summary.get("episodes", 0),
        "operaciones": summary.get("operations", 0),
        "esperanza_R": round(float(summary.get("expectancy_r", 0.0)), 4),
        "pf": summary.get("profit_factor"),
        "neto_pct": summary.get("net_pct"),
    }


def run_h6(prices: pd.DataFrame) -> dict:
    return metrics(run_tsmom(prices, 28, False, 7).summary(years=YEARS))


def run_h7(ratio, close, notional, funding) -> dict:
    return metrics(run_flow(ratio, close, notional, funding, lookback=20,
                            signal_days=3, hold=3, quantile=0.2).summary(years=YEARS))


def run_h9(spot, perp, funding) -> dict:
    return metrics(run_basis_carry(spot, perp, funding,
                                   start=START.strftime("%Y-%m-%d"),
                                   end=END.strftime("%Y-%m-%d"),
                                   lookback=7, rebalance="W", quantile=0.2,
                                   entry=0.00025, exit=0.00010).summary(years=YEARS))


def summarise(name: str, observed: dict, null: list[float]) -> dict:
    values = np.array(null, dtype=float)
    observed_r = observed["esperanza_R"]
    p_value = (1 + int((np.abs(values) >= abs(observed_r)).sum())) / (len(values) + 1)
    return {
        "familia": name,
        "observado": observed,
        "nulidad": {
            "permutaciones": len(values),
            "media_R": round(float(values.mean()), 4),
            "p5_R": round(float(np.percentile(values, 5)), 4),
            "p50_R": round(float(np.median(values)), 4),
            "p95_R": round(float(np.percentile(values, 95)), 4),
        },
        "p_valor_dos_colas": round(p_value, 4),
        "percentil_abs": round(float((np.abs(values) < abs(observed_r)).mean() * 100), 1),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Permutaciones de H6, H7 y H9")
    parser.add_argument("--permutations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--family", default="all", choices=("all", "H6", "H7", "H9"))
    parser.add_argument("--json", default=str(ROOT / "data" / "permutation_families.json"))
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    results: dict[str, dict] = {}

    if args.family in ("all", "H6"):
        prices = load_prices(ROOT / "data" / "funding_xs" / "perp_1d_panel.csv")
        prices = prices[(prices.index >= START) & (prices.index < END)]
        observed = run_h6(prices)
        null = [run_h6(shuffle_returns(prices, rng))["esperanza_R"]
                for _ in range(args.permutations)]
        results["H6"] = summarise("H6", observed, null)
        print(f"H6 observado {observed['esperanza_R']} R · "
              f"p = {results['H6']['p_valor_dos_colas']}")

    if args.family in ("all", "H7"):
        ratio, close, notional, funding = load_flow(
            ROOT / "data" / "flow" / "taker_flow_1d.csv",
            ROOT / "data" / "funding_xs" / "funding_panel.csv")
        mask = (close.index >= START) & (close.index < END)
        ratio, close, notional = ratio[mask], close[mask], notional[mask]
        funding = funding[(funding.index >= START) & (funding.index < END)]
        observed = run_h7(ratio, close, notional, funding)
        null = [run_h7(shuffle_columns(ratio, rng), close, notional, funding)["esperanza_R"]
                for _ in range(args.permutations)]
        results["H7"] = summarise("H7", observed, null)
        print(f"H7 observado {observed['esperanza_R']} R · "
              f"p = {results['H7']['p_valor_dos_colas']}")

    if args.family in ("all", "H9"):
        spot, perp, funding = load_basis(ROOT / "data" / "basis" / "spot_daily.csv",
                                         ROOT / "data" / "basis" / "perp_daily.csv",
                                         ROOT / "data" / "basis" / "funding_daily.csv")
        observed = run_h9(spot, perp, funding)
        isolated = run_h9(spot, spot, funding)
        null = [run_h9(spot, perp, shuffle_columns(funding, rng))["esperanza_R"]
                for _ in range(args.permutations)]
        results["H9"] = summarise("H9", observed, null)
        results["H9"]["solo_funding"] = isolated
        print(f"H9 observado {observed['esperanza_R']} R · sólo funding "
              f"{isolated['esperanza_R']} R · p = {results['H9']['p_valor_dos_colas']}")

    print(json.dumps(results, indent=2, ensure_ascii=False))
    target = Path(args.json)
    payload = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else {}
    payload.update(results)
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"escrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
