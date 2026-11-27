"""Diagnóstico de señal de funding (ver docs/PRE-REGISTRO-SENAL.md).

Mide si la señal de H5/H10 —media de funding de 7 días, z-score de 90— predice el
funding de las semanas siguientes, sin construir ninguna cartera: rank-IC
transversal, decaimiento a 1/2/4 semanas, autocorrelación de la dispersión y
estabilidad por régimen, en tres universos fijados de antemano.

Uso:
    python scripts/signal_diagnostics.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
H10 = ROOT / "data" / "h10"
H5 = ROOT / "data" / "funding_xs"
OUT = ROOT / "data" / "signal"

WINDOW = 7
LOOKBACK = 90
MIN_HISTORY = 90
MIN_ADV_USD = 5_000_000.0
MIN_NAMES = 10
HORIZONS = (1, 2, 4)
START = pd.Timestamp("2023-01-01", tz="UTC")
END = pd.Timestamp("2026-10-31", tz="UTC")


def load_h5():
    """Los 20 majors: el panel de H10 los excluye por construcción."""
    funding = pd.read_csv(H5 / "funding_panel.csv", parse_dates=["dt"])
    prices = pd.read_csv(H5 / "perp_1d_panel.csv", parse_dates=["dt"])
    funding["rate_8h"] = funding["rate"] * 8.0 / funding["interval_h"].clip(lower=1)
    funding["dt"] = funding["dt"].dt.floor("D")
    prices["dt"] = prices["dt"].dt.floor("D")
    rate = funding.groupby(["dt", "symbol"])["rate_8h"].sum().unstack("symbol").sort_index()
    close = prices.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    rate = rate.reindex(index=close.index, columns=close.columns)
    return rate, close


def load():
    funding = pd.read_csv(H10 / "funding_daily.csv", parse_dates=["dt"])
    perp = pd.read_csv(H10 / "perp_daily.csv", parse_dates=["dt"])
    for frame in (funding, perp):
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True).dt.floor("D")
    rate = funding.pivot_table(index="dt", columns="symbol", values="rate", aggfunc="sum").sort_index()
    close = perp.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    quote = perp.pivot_table(index="dt", columns="symbol", values="quote_volume", aggfunc="last").sort_index()
    rate = rate.reindex(index=close.index, columns=close.columns)
    quote = quote.reindex(index=close.index, columns=close.columns)
    return rate, close, quote


def spearman(a: pd.Series, b: pd.Series) -> float:
    if len(a) < MIN_NAMES:
        return float("nan")
    return float(a.rank().corr(b.rank()))


def forward_mean(rate: pd.DataFrame, start: int, end: int) -> pd.Series:
    block = rate.iloc[start:end]
    return block.mean(axis=0)


def evaluate(rate: pd.DataFrame, close: pd.DataFrame, quote: pd.DataFrame,
             columns: list[str], min_adv: float, label: str) -> dict:
    sub = rate[columns]
    price = close[columns]
    quote_sub = quote[columns]

    signal = sub.rolling(WINDOW, min_periods=5).mean().shift(1)
    mean90 = sub.rolling(LOOKBACK, min_periods=60).mean().shift(1)
    std90 = sub.rolling(LOOKBACK, min_periods=60).std().shift(1)
    zscore = (signal - mean90) / std90.where(std90 > 1e-12)
    history = price.notna().cumsum().shift(1)

    adv = quote_sub.rolling(30, min_periods=20).median().shift(1) if min_adv > 0 else None

    dates = close.index
    mondays = [i for i, d in enumerate(dates) if d.weekday() == 0 and START <= d <= END]
    rows = []
    dispersion, level = [], []

    for i in mondays:
        if i < LOOKBACK:
            continue
        date = dates[i]
        tradable = (history.iloc[i] >= MIN_HISTORY) & price.iloc[i].gt(0) & zscore.iloc[i].notna()
        if adv is not None:
            tradable &= adv.iloc[i] >= min_adv
        names = [s for s in columns if bool(tradable.get(s, False))]
        if len(names) < MIN_NAMES:
            continue

        sig = zscore.iloc[i][names]
        raw = signal.iloc[i][names]
        dispersion.append(float(raw.std()))
        level.append(float(raw.median()))

        record = {"date": date.strftime("%Y-%m-%d")}
        for h in HORIZONS:
            end = i + WINDOW * h
            if end > len(dates) - 1:
                record[f"ic{h}"] = float("nan")
                continue
            target = forward_mean(sub, i + 1, end + 1)[names]
            valid = target.notna()
            record[f"ic{h}"] = spearman(sig[valid], target[valid])
        rows.append(record)

    frame = pd.DataFrame(rows)
    if frame.empty or "date" not in frame.columns:
        return {"universo": label, "simbolos": len(columns), "semanas": 0, "error": "sin semanas"}
    frame["year"] = frame["date"].str[:4]
    dispersion_series = pd.Series(dispersion)

    summary = {
        "universo": label,
        "simbolos": len(columns),
        "semanas": int(len(frame)),
    }
    for h in HORIZONS:
        values = frame[f"ic{h}"].dropna()
        summary[f"ic{h}"] = {
            "mediana": round(float(values.median()), 4),
            "media": round(float(values.mean()), 4),
            "sem_semanas_positivas": round(float((values > 0).mean()), 3),
            "n": int(len(values)),
        }
    summary["por_anio"] = {
        str(year): {
            "semanas": int(len(group)),
            "ic1_mediana": round(float(group["ic1"].median()), 4),
            "ic1_positivas": round(float((group["ic1"] > 0).mean()), 3),
        }
        for year, group in frame.groupby("year")
    }
    terciles = dispersion_series.quantile([1 / 3, 2 / 3]).tolist()
    frame["disp"] = dispersion_series.values[: len(frame)]
    frame["regimen"] = pd.cut(frame["disp"], bins=[-np.inf, terciles[0], terciles[1], np.inf],
                              labels=["baja", "media", "alta"])
    summary["por_regimen"] = {
        str(name): {
            "semanas": int(len(group)),
            "ic1_mediana": round(float(group["ic1"].median()), 4),
            "ic1_positivas": round(float((group["ic1"] > 0).mean()), 3),
        }
        for name, group in frame.groupby("regimen", observed=True)
    }
    summary["dispersion"] = {
        "mediana_bp": round(float(dispersion_series.median()) * 1e4, 1),
        "autocorr_lag1_4": [round(float(dispersion_series.autocorr(lag)), 3) for lag in range(1, 5)],
    }
    summary["nivel"] = {
        "mediana_bp": round(float(pd.Series(level).median()) * 1e4, 2),
        "autocorr_lag1_4": [round(float(pd.Series(level).autocorr(lag)), 3) for lag in range(1, 5)],
    }
    summary["muestras"] = frame[[f"ic{h}" for h in HORIZONS]].dropna().head(3).to_dict("records")
    return summary


def gates(summary: dict) -> dict:
    years = [v["ic1_mediana"] for v in summary["por_anio"].values()]
    return {
        "F1 ic1 mediana >= 0,05": summary["ic1"]["mediana"] >= 0.05,
        "F2 semanas positivas >= 60 %": summary["ic1"]["sem_semanas_positivas"] >= 0.60,
        "F3 ic4 mediana >= 0,03": summary["ic4"]["mediana"] >= 0.03,
        "F4 >= 3 anios con ic1 > 0": sum(1 for v in years if v > 0) >= 3,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)

    rate_h10, close_h10, quote_h10 = load()
    rate_h5, close_h5 = load_h5()

    empty = pd.DataFrame(index=close_h5.index, columns=close_h5.columns, dtype=float)
    results = {}
    for label, (rate, close, quote), columns, min_adv in (
        ("U20 majors de H5", (rate_h5, close_h5, empty), list(close_h5.columns), 0.0),
        ("ANCHO panel completo", (rate_h10, close_h10, quote_h10), list(close_h10.columns), 0.0),
        ("FILTRADO ADV >= 5M", (rate_h10, close_h10, quote_h10), list(close_h10.columns), MIN_ADV_USD),
    ):
        summary = evaluate(rate, close, quote, columns, min_adv, label)
        summary["puertas"] = gates(summary)
        results[label] = summary
        print(f"\n== {label} · {summary['simbolos']} símbolos · {summary['semanas']} semanas")
        print(f"  IC1 mediana {summary['ic1']['mediana']:+.4f} · positivas "
              f"{summary['ic1']['sem_semanas_positivas']:.1%} · IC2 {summary['ic2']['mediana']:+.4f}"
              f" · IC4 {summary['ic4']['mediana']:+.4f}")
        print(f"  por año {[(y, v['ic1_mediana']) for y, v in summary['por_anio'].items()]}")
        print(f"  por régimen {[(r, v['ic1_mediana']) for r, v in summary['por_regimen'].items()]}")
        print(f"  dispersión {summary['dispersion']['mediana_bp']} pb · autocorr "
              f"{summary['dispersion']['autocorr_lag1_4']} · nivel autocorr "
              f"{summary['nivel']['autocorr_lag1_4']}")
        print(f"  puertas {summary['puertas']}")

    (OUT / "diagnostics.json").write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n",
                                          encoding="utf-8")
    print(f"\nescrito {OUT / 'diagnostics.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
