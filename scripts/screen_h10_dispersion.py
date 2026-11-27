"""Cribado económico de H10 (regla 10 del plan), antes de calcular P&L.

Mide la dispersión de funding que la cartera habría capturado, no lo que habría
ganado: en ventanas no solapadas de 7 días, la media de funding de los `k` nombres
con señal más alta menos la de los `k` más baja, sumada sobre la ventana y
expresada en pb del nocional por posición.

La barra **no es una constante**: sale de la geometría. La regla 10 exige que cada
posición cubra 0,1 R más dos veces su coste, que con R = 250 USD son 37,50 USD por
posición. El nocional por posición es 12.500 / k, así que la barra en pb es
37,50 / (12.500 / k) × 10.000 = **30 × k**: 120 pb con 4 posiciones por lado, 240
con 8, 1.110 con 37. Comparar una mediana obtenida con k = 37 contra 120 pb no es
un cribado, es un error de unidades; por eso el JSON publica la barra y la
geometría que la produjeron.

Reglas, copiadas del pre-registro y no ajustadas aquí:

- elegibilidad en t: >= 90 días de funding y precio antes de t, volumen medio
  diario (mediana de 30 días, con datos hasta t-1) >= 5 M USD, y precio y volumen
  no nulos en t;
- señal: media del funding diario de los 7 días anteriores a t, estandarizada
  contra su media y desviación de 90 días;
- cartera: `k = max(2, round(n/5))` por lado, topado por `--max-per-side` (8 por
  defecto), largo del extremo inferior de la señal;
- ventana: 7 días desde t; si un miembro desaparece, aporta los días que tiene.

No se calcula retorno, ni precio relativo, ni coste: si el cribado falla, la
familia se archiva sin backtest.

Uso:
    python scripts/screen_h10_dispersion.py
    python scripts/screen_h10_dispersion.py --max-per-side 37
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "h10"

# Geometría de la cartera, la del pre-registro: 25.000 USD de bruto.
GROSS_USD = 25_000.0
PER_SIDE_USD = GROSS_USD / 2.0
# 0,1 R (R = 250 USD) + 2 × coste de una posición de referencia, en dólares.
BAR_USD_PER_POSITION = 37.5

LOOKBACK = 90
WINDOW = 7
MIN_HISTORY = 90
MIN_ADV_USD = 5_000_000.0
MIN_ELIGIBLE = 20
DEFAULT_MAX_PER_SIDE = 8


def bar_bp(k: int) -> float:
    """Barra de la regla 10 en pb del nocional, dada la geometría.

    Con `k` posiciones por lado el nocional es 12.500 / k, y la barra en dólares se
    mantiene en 37,50 por posición: 37,50 / (12.500 / k) × 10.000 = 30 × k.
    """
    return BAR_USD_PER_POSITION / (PER_SIDE_USD / k) * 1e4


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    freeze_path = DATA / "freeze.json"
    if not freeze_path.is_file():
        raise SystemExit("falta data/h10/freeze.json: el panel no está congelado")
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))

    funding_path = DATA / "funding_daily.csv"
    perp_path = DATA / "perp_daily.csv"
    for path, key in ((funding_path, "funding_sha256"), (perp_path, "perp_sha256")):
        if _sha(path) != freeze[key]:
            raise SystemExit(f"{path.name} no coincide con el hash congelado")

    funding = pd.read_csv(funding_path, parse_dates=["dt"])
    perp = pd.read_csv(perp_path, parse_dates=["dt"])
    funding["dt"] = pd.to_datetime(funding["dt"], utc=True).dt.floor("D")
    perp["dt"] = pd.to_datetime(perp["dt"], utc=True).dt.floor("D")
    return funding, perp, freeze


def panels(funding: pd.DataFrame, perp: pd.DataFrame):
    rate = funding.pivot_table(index="dt", columns="symbol", values="rate", aggfunc="sum").sort_index()
    close = perp.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    quote = perp.pivot_table(index="dt", columns="symbol", values="quote_volume", aggfunc="last").sort_index()
    # Mismo índice y mismas columnas en las tres series.
    rate = rate.reindex(index=close.index, columns=close.columns)
    quote = quote.reindex(index=close.index, columns=close.columns)
    return rate, close, quote


def screen(rate: pd.DataFrame, close: pd.DataFrame, quote: pd.DataFrame,
           max_per_side: int = DEFAULT_MAX_PER_SIDE) -> dict:
    # Todo con datos hasta t-1: se desplaza un día antes de usarlo como filtro.
    adv = quote.rolling(30, min_periods=20).median().shift(1)
    history = close.notna().cumsum().shift(1)
    funding_days = rate.notna().cumsum().shift(1)

    signal = rate.rolling(WINDOW, min_periods=5).mean().shift(1)
    mean90 = rate.rolling(LOOKBACK, min_periods=60).mean().shift(1)
    std90 = rate.rolling(LOOKBACK, min_periods=60).std().shift(1)
    zscore = (signal - mean90) / std90.where(std90 > 1e-12)

    dates = close.index
    monday = [d for d in dates if d.weekday() == 0]
    windows: list[dict] = []
    eligible_counts: list[int] = []

    for date in monday:
        tradable = (
            (history.loc[date] >= MIN_HISTORY)
            & (funding_days.loc[date] >= MIN_HISTORY)
            & (adv.loc[date] >= MIN_ADV_USD)
            & (close.loc[date] > 0)
            & (quote.loc[date] > 0)
            & zscore.loc[date].notna()
        )
        members = [s for s in zscore.columns if bool(tradable.get(s, False))]
        eligible_counts.append(len(members))
        if len(members) < MIN_ELIGIBLE:
            continue

        ranked = zscore.loc[date, members].sort_values()
        count = max(2, int(round(len(members) * 0.2)))
        count = min(count, max_per_side)
        longs = list(ranked.index[:count])
        shorts = list(ranked.index[-count:])

        horizon = dates[(dates >= date) & (dates < date + pd.Timedelta(days=WINDOW))]
        if len(horizon) < WINDOW - 1:
            continue
        short_mean = rate.loc[horizon, shorts].mean(axis=1)
        long_mean = rate.loc[horizon, longs].mean(axis=1)
        daily = (short_mean - long_mean).dropna()
        if len(daily) < WINDOW - 2:
            continue

        captured_bp = float(daily.sum() * 1e4)
        required_bp = bar_bp(count)
        windows.append({
            "date": date.strftime("%Y-%m-%d"),
            "eligible": len(members),
            "k_per_side": count,
            "notional_usd": round(PER_SIDE_USD / count, 2),
            "bar_bp": round(required_bp, 2),
            "captured_bp": round(captured_bp, 2),
            "margin_bp": round(captured_bp - required_bp, 2),
        })

    if not windows:
        raise SystemExit("no hay ventanas válidas: revisa la elegibilidad")

    frame = pd.DataFrame(windows)
    frame["year"] = frame["date"].str[:4]
    values = frame["captured_bp"].to_numpy()
    bars = frame["bar_bp"].to_numpy()
    margins = frame["margin_bp"].to_numpy()

    by_year: dict[str, dict] = {}
    for year, group in frame.groupby("year"):
        by_year[year] = {
            "windows": int(len(group)),
            "median_bp": round(float(group["captured_bp"].median()), 2),
            "median_bar_bp": round(float(group["bar_bp"].median()), 2),
            "share_ge_bar": round(float((group["margin_bp"] >= 0).mean()), 3),
            "median_margin_bp": round(float(group["margin_bp"].median()), 2),
        }

    median_k = int(np.median(frame["k_per_side"]))
    median_eligible = int(np.median(eligible_counts)) if eligible_counts else 0
    return {
        "geometry": {
            "gross_usd": GROSS_USD,
            "per_side_usd": PER_SIDE_USD,
            "bar_usd_per_position": BAR_USD_PER_POSITION,
            "bar_bp_formula": "30 * k  (37,50 USD dividido por 12.500 / k)",
            "max_per_side": max_per_side,
            "k_per_side": {
                "min": int(frame["k_per_side"].min()),
                "median": median_k,
                "max": int(frame["k_per_side"].max()),
            },
            "notional_per_position_usd_median": round(PER_SIDE_USD / median_k, 2),
            "bar_bp": {
                "min": round(float(bars.min()), 2),
                "median": round(float(np.median(bars)), 2),
                "max": round(float(bars.max()), 2),
            },
        },
        "windows": int(len(values)),
        "median_bp": round(float(np.median(values)), 2),
        "mean_bp": round(float(values.mean()), 2),
        "p25_bp": round(float(np.percentile(values, 25)), 2),
        "p75_bp": round(float(np.percentile(values, 75)), 2),
        "bar_bp_applied": round(float(np.median(bars)), 2),
        "margin_bp": {
            "median": round(float(np.median(margins)), 2),
            "share_ge_bar": round(float((margins >= 0).mean()), 3),
        },
        "median_eligible": median_eligible,
        "min_eligible": int(min(eligible_counts)) if eligible_counts else 0,
        "by_year": by_year,
        "passed": bool(np.median(margins) >= 0 and median_eligible >= MIN_ELIGIBLE),
        "sample": windows[:5] + windows[-3:],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Cribado de dispersión de H10")
    parser.add_argument("--max-per-side", type=int, default=DEFAULT_MAX_PER_SIDE,
                        help="tope de posiciones por lado (0 = sin tope, quintil puro)")
    parser.add_argument("--json", default=str(DATA / "screen.json"))
    args = parser.parse_args()

    funding, perp, freeze = load()
    print(f"panel congelado: {freeze['symbols']} símbolos, "
          f"{freeze['funding_rows']} filas de funding, {freeze['perp_rows']} de velas")
    is_rate_frame, close, quote = panels(funding, perp)
    cap = args.max_per_side if args.max_per_side > 0 else 10_000
    result = screen(is_rate_frame, close, quote, cap)

    print(json.dumps({k: v for k, v in result.items() if k != "sample"}, indent=2, ensure_ascii=False))
    target = Path(args.json)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    geometry = result["geometry"]
    print(f"\ngeometría: {geometry['k_per_side']['median']} por lado · "
          f"{geometry['notional_per_position_usd_median']} USD por posición · "
          f"barra {result['bar_bp_applied']} pb (30 × k)")
    print(f"{'PASA' if result['passed'] else 'NO PASA'}: mediana {result['median_bp']} pb "
          f"frente a {result['bar_bp_applied']} pb · margen {result['margin_bp']['median']} pb · "
          f"escrito {target}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
