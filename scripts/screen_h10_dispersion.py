"""Cribado económico de H10 (regla 10 del plan), antes de calcular P&L.

Mide la dispersión de funding que la cartera habría capturado, no lo que habría
ganado: en ventanas no solapadas de 7 días, la media de funding del quintil
superior menos la del quintil inferior, sumada sobre la ventana y expresada en pb
del nocional por posición. Se compara con el umbral declarado de 120 pb.

Reglas, copiadas del pre-registro y no ajustadas aquí:

- elegibilidad en t: >= 90 días de funding y precio antes de t, volumen medio
  diario (mediana de 30 días, con datos hasta t-1) >= 5 M USD, y precio y volumen
  no nulos en t;
- señal: media del funding diario de los 7 días anteriores a t, estandarizada
  contra su media y desviación de 90 días;
- cartera: `k = max(2, round(n/5))` por lado, largo del quintil inferior;
- ventana: 7 días desde t; si un miembro desaparece, aporta los días que tiene.

No se calcula retorno, ni precio relativo, ni coste: si el cribado falla, la
familia se archiva sin backtest.

Uso:
    python scripts/screen_h10_dispersion.py
    python scripts/screen_h10_dispersion.py --threshold 120 --json data/h10/screen.json
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
THRESHOLD_BP = 120.0
LOOKBACK = 90
WINDOW = 7
MIN_HISTORY = 90
MIN_ADV_USD = 5_000_000.0
MIN_ELIGIBLE = 20


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
           threshold: float, max_per_side: int = 8) -> dict:
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
        windows.append({
            "date": date.strftime("%Y-%m-%d"),
            "eligible": len(members),
            "longs": count,
            "captured_bp": round(captured_bp, 2),
        })

    if not windows:
        raise SystemExit("no hay ventanas válidas: revisa la elegibilidad")

    values = np.array([w["captured_bp"] for w in windows])
    by_year: dict[str, dict] = {}
    frame = pd.DataFrame(windows)
    frame["year"] = frame["date"].str[:4]
    for year, group in frame.groupby("year"):
        by_year[year] = {
            "windows": int(len(group)),
            "median_bp": round(float(group["captured_bp"].median()), 2),
            "share_ge": round(float((group["captured_bp"] >= threshold).mean()), 3),
        }

    median = float(np.median(values))
    return {
        "threshold_bp": threshold,
        "windows": int(len(values)),
        "median_bp": round(median, 2),
        "mean_bp": round(float(values.mean()), 2),
        "p25_bp": round(float(np.percentile(values, 25)), 2),
        "p75_bp": round(float(np.percentile(values, 75)), 2),
        "share_ge_threshold": round(float((values >= threshold).mean()), 3),
        "median_eligible": int(np.median(eligible_counts)) if eligible_counts else 0,
        "min_eligible": int(min(eligible_counts)) if eligible_counts else 0,
        "by_year": by_year,
        "passed": bool(median >= threshold and (np.median(eligible_counts) if eligible_counts else 0) >= MIN_ELIGIBLE),
        "sample": windows[:5] + windows[-3:],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Cribado de dispersión de H10")
    parser.add_argument("--threshold", type=float, default=THRESHOLD_BP)
    parser.add_argument("--max-per-side", type=int, default=8,
                        help="tope de posiciones por lado (0 = sin tope, quintil puro)")
    parser.add_argument("--json", default=str(DATA / "screen.json"))
    args = parser.parse_args()

    funding, perp, freeze = load()
    print(f"panel congelado: {freeze['symbols']} símbolos, "
          f"{freeze['funding_rows']} filas de funding, {freeze['perp_rows']} de velas")
    is_rate_frame, close, quote = panels(funding, perp)
    cap = args.max_per_side if args.max_per_side > 0 else 10_000
    result = screen(is_rate_frame, close, quote, args.threshold, cap)
    result["max_per_side"] = args.max_per_side

    print(json.dumps({k: v for k, v in result.items() if k != "sample"}, indent=2, ensure_ascii=False))
    target = Path(args.json)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\n{'PASA' if result['passed'] else 'NO PASA'}: mediana {result['median_bp']} pb "
          f"frente a {result['threshold_bp']} pb · escrito {target}")
    return 0 if result["passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
