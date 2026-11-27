"""Canarios de look-ahead y baseline nulo sobre `server/funding_xs.py`.

El cribado ya tenía estas pruebas; el motor que produjo el resultado de H5 no.
Aquí se le aplican las mismas, con una diferencia deliberada: como el motor tiene
dos patas —precio y funding—, la nulidad se corre dos veces.

- **Nulidad A (funding barajado)**: se baraja el funding de cada símbolo en el
  tiempo. La señal deja de informar y el funding cobrado deja de ser el que
  provocó la posición. Es la nulidad completa: si H5 tiene edge, debe quedar
  fuera de esta distribución.
- **Aislamiento de la pata de funding**: se corre el motor con los precios
  constantes (1,0 donde había precio, NaN donde no había) y el funding intacto.
  El P&L de precio se anula por construcción y quedan sólo carry y costes: dice
  cuánto del resultado era prima y cuánto beta, sin permutaciones de por medio.
  Barajar los *niveles* de precio no sirve: rompe la continuidad de los retornos
  y fabrica un P&L de ruido enorme que no es una nulidad.

Uso:
    python scripts/engine_validation.py --permutations 50
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

from server.funding_xs import (  # noqa: E402
    _zscore_signal,
    load_panels,
    run_funding_xs,
)

START = pd.Timestamp("2025-01-01", tz="UTC")
END = pd.Timestamp("2026-11-01", tz="UTC")
R_USD = 250.0


def load():
    funding, prices = load_panels(ROOT / "data" / "funding_xs" / "funding_panel.csv",
                                  ROOT / "data" / "funding_xs" / "perp_1d_panel.csv")
    funding = funding[(funding.index >= START) & (funding.index < END)]
    prices = prices[(prices.index >= START) & (prices.index < END)]
    return funding, prices


def metrics(episodes: list[dict]) -> dict:
    if not episodes:
        return {"episodios": 0, "operaciones": 0, "neto": 0.0, "pf": None,
                "esperanza_R": 0.0, "precio": 0.0, "funding": 0.0}
    operations = sum(e["operations"] for e in episodes)
    net = float(sum(e["net"] for e in episodes))
    wins = float(sum(e["net"] for e in episodes if e["net"] > 0))
    losses = float(-sum(e["net"] for e in episodes if e["net"] < 0))
    return {
        "episodios": len(episodes),
        "operaciones": operations,
        "neto": round(net, 2),
        "pf": round(wins / losses, 4) if losses > 0 else None,
        "esperanza_R": round(net / operations / R_USD, 4) if operations else 0.0,
        "precio": round(float(sum(e["price_pnl"] for e in episodes)), 2),
        "funding": round(float(sum(e["funding_pnl"] for e in episodes)), 2),
    }


def shuffle_columns(frame: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Baraja cada columna en el tiempo conservando los NaN."""
    values = frame.to_numpy(dtype=float, copy=True)
    for column in range(values.shape[1]):
        series = values[:, column]
        mask = np.isfinite(series)
        block = series[mask]
        rng.shuffle(block)
        series[mask] = block
        values[:, column] = series
    return pd.DataFrame(values, index=frame.index, columns=frame.columns)


def canary(funding: pd.DataFrame, prices: pd.DataFrame) -> dict:
    """La señal de un día de rebalanceo no puede leer ese día."""
    rebalance = [d for d in funding.index if d.weekday() == 0]
    sample = rebalance[::max(1, len(rebalance) // 8)]
    same_day: list[float] = []
    next_day: list[float] = []
    for day in sample:
        poisoned = funding.copy()
        poisoned.loc[[day]] = poisoned.loc[[day]] * 100.0
        base = _zscore_signal(funding, day, 90, False)
        alt = _zscore_signal(poisoned, day, 90, False)
        common = base.index.intersection(alt.index)
        if len(common):
            same_day.append(float((base[common] - alt[common]).abs().max()))
        following = day + pd.Timedelta(days=1)
        base_next = _zscore_signal(funding, following, 90, False)
        alt_next = _zscore_signal(poisoned, following, 90, False)
        common = base_next.index.intersection(alt_next.index)
        if len(common):
            next_day.append(float((base_next[common] - alt_next[common]).abs().max()))

    # Control de posición: envenenar un día no puede alterar episodios ya cerrados.
    day = rebalance[len(rebalance) // 2]
    poisoned = funding.copy()
    poisoned.loc[[day]] = poisoned.loc[[day]] * 100.0
    clean_eps = [e for e in run_funding_xs(funding, prices).episodes if e["exit"] < day]
    pois_eps = [e for e in run_funding_xs(poisoned, prices).episodes if e["exit"] < day]
    clean_net = round(sum(e["net"] for e in clean_eps), 6)
    pois_net = round(sum(e["net"] for e in pois_eps), 6)
    worst_same = max(same_day) if same_day else 0.0
    best_control = max(next_day) if next_day else 0.0
    return {
        "fechas": len(sample),
        "max_diferencia_mismo_dia": worst_same,
        "max_diferencia_dia_siguiente": best_control,
        "episodios_previos_iguales": bool(clean_net == pois_net and len(clean_eps) == len(pois_eps)),
        "neto_episodios_previos": clean_net,
        "pasa": bool(worst_same < 1e-12 and best_control > 1e-6
                     and clean_net == pois_net and len(clean_eps) == len(pois_eps)),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Nulidad del motor de H5")
    parser.add_argument("--permutations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--json", default=str(ROOT / "data" / "h5_engine_validation.json"))
    args = parser.parse_args()

    funding, prices = load()
    print(f"panel: {prices.shape[1]} símbolos, {len(prices)} días "
          f"({prices.index.min().date()}/{prices.index.max().date()})")
    observed = metrics(run_funding_xs(funding, prices).episodes)
    print(f"observado: PF {observed['pf']} · esperanza {observed['esperanza_R']} R · "
          f"{observed['episodios']} episodios")

    guard = canary(funding, prices)
    print(f"canario: mismo día {guard['max_diferencia_mismo_dia']:.2e}, "
          f"día siguiente {guard['max_diferencia_dia_siguiente']:.2e}, "
          f"episodios previos iguales {guard['episodios_previos_iguales']} → "
          f"{'PASA' if guard['pasa'] else 'FALLA'}")

    # Pata de funding sola: precios constantes, misma cobertura que el panel.
    flat = prices.notna().astype(float).replace(0.0, np.nan)
    isolated = metrics(run_funding_xs(funding, flat).episodes)
    print(f"sólo funding: neto {isolated['neto']} · "
          f"esperanza {isolated['esperanza_R']} R")

    rng = np.random.default_rng(args.seed)
    null_a: list[float] = []
    for index in range(args.permutations):
        result = run_funding_xs(shuffle_columns(funding, rng), prices)
        null_a.append(metrics(result.episodes)["esperanza_R"])
        if (index + 1) % 10 == 0:
            print(f"  permutación {index + 1}/{args.permutations}", flush=True)

    a = np.array(null_a)
    observed_r = observed["esperanza_R"]
    p_value = (1 + int((a >= observed_r).sum())) / (len(a) + 1)
    summary = {
        "observado": observed,
        "canario": guard,
        "nulidad_funding_barajado": {
            "permutaciones": len(a),
            "media_R": round(float(a.mean()), 4),
            "p50_R": round(float(np.median(a)), 4),
            "p95_R": round(float(np.percentile(a, 95)), 4),
            "max_R": round(float(a.max()), 4),
            "percentil_observado": round(float((a < observed_r).mean() * 100), 1),
            "p_valor": round(p_value, 4),
        },
        "solo_funding": isolated,
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    target = Path(args.json)
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"escrito {target}")
    return 0 if guard["pasa"] else 1


if __name__ == "__main__":
    sys.exit(main())
