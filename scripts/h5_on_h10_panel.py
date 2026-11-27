"""H5 re-hecho sobre el panel congelado de H10, con sus reglas intactas.

SUPERADO. Este motor cierra y reabre la posición cada semana, mientras H5 la
mantiene abierta mientras siga en la cartera. Validado contra
`server/funding_xs.py`, esa diferencia parte la esperanza por dos (0,0155 R frente
a 0,0301 R en los majors de H5), así que **sus cifras no se usan**. El motor
validado y los números vigentes están en `scripts/validate_h5_engine.py` y
`docs/MEDICION-H5-PANEL-H10.md`. Se conserva por trazabilidad.

H5 pre-registró sus reglas sobre 20 perpetuos elegidos por liquidez de 2026, un
sesgo de supervivencia que su archivo declara. El panel de H10 corrige justo eso
(887 símbolos, deslistados dentro, liquidez punto en tiempo), así que este script
aplica las reglas de H5 tal como están escritas —señal z90 de 7 días, quintil,
dollar-neutral, 25.000 USD de bruto, 6 pb por posición y lado, rebalanceo
semanal— cambiando sólo el universo por el del panel.

Dos geometrías, porque H5 no las separa y aquí importan:

- `quintil`: `k = round(n/5)` por lado, la fórmula del pre-registro. Con ~180
  elegibles son ~36 posiciones por lado de ~347 USD.
- `k4`: 4 por lado, que es lo que daba la fórmula con los 20 majors de H5 y la
  única geometría comparable con su resultado publicado.

Las puertas de H5 están en R y en dólares, no en pb, así que se aplican sin
tocar. La ventana es la de validación de H5 (2025-01-01/2026-10-31, recortada al
panel): es una ventana ya gastada, así que un resultado positivo no confirmaría
nada; sólo el fallo es informativo.

Uso:
    python scripts/h5_on_h10_panel.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "h10"

GROSS_USD = 25_000.0
PER_SIDE_USD = GROSS_USD / 2.0
R_USD = 250.0
COST_BP_PER_SIDE = 6.0
WINDOW = 7
LOOKBACK = 90
MIN_HISTORY = 90
MIN_ELIGIBLE = 10
START = pd.Timestamp("2025-01-01", tz="UTC")
END = pd.Timestamp("2026-11-01", tz="UTC")


def load_panels():
    funding = pd.read_csv(DATA / "funding_daily.csv", parse_dates=["dt"])
    perp = pd.read_csv(DATA / "perp_daily.csv", parse_dates=["dt"])
    for frame in (funding, perp):
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True).dt.floor("D")
    rate = funding.pivot_table(index="dt", columns="symbol", values="rate", aggfunc="sum").sort_index()
    close = perp.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    quote = perp.pivot_table(index="dt", columns="symbol", values="quote_volume", aggfunc="last").sort_index()
    rate = rate.reindex(index=close.index, columns=close.columns)
    quote = quote.reindex(index=close.index, columns=close.columns)
    return rate, close, quote


def run(rate: pd.DataFrame, close: pd.DataFrame, quote: pd.DataFrame,
        per_side: int | None, min_adv: float = 0.0) -> dict:
    history = close.notna().cumsum().shift(1)
    adv = quote.rolling(30, min_periods=20).median().shift(1)
    signal = rate.rolling(WINDOW, min_periods=5).mean().shift(1)
    mean90 = rate.rolling(LOOKBACK, min_periods=60).mean().shift(1)
    std90 = rate.rolling(LOOKBACK, min_periods=60).std().shift(1)
    zscore = (signal - mean90) / std90.where(std90 > 1e-12)

    dates = close.index[(close.index >= START) & (close.index < END)]
    mondays = [d for d in dates if d.weekday() == 0]

    episodes: list[dict] = []
    previous: tuple[list[str], list[str]] | None = None

    for date in mondays:
        tradable = (history.loc[date] >= MIN_HISTORY) & close.loc[date].gt(0) & zscore.loc[date].notna()
        if min_adv > 0:
            tradable &= adv.loc[date] >= min_adv
        members = [s for s in zscore.columns if bool(tradable.get(s, False))]
        if len(members) < MIN_ELIGIBLE:
            continue

        ranked = zscore.loc[date, members].sort_values()
        k = per_side if per_side else max(2, int(round(len(members) * 0.2)))
        k = min(k, len(members) // 2)
        longs = list(ranked.index[:k])
        shorts = list(ranked.index[-k:])
        previous = (longs, shorts)

        exit_date = date + pd.Timedelta(days=WINDOW)
        horizon = dates[(dates > date) & (dates <= exit_date)]
        if len(horizon) == 0:
            continue
        funding_days = rate.loc[horizon]
        notional = PER_SIDE_USD / k

        for side, names, sign in (("long", longs, 1.0), ("short", shorts, -1.0)):
            for symbol in names:
                entry = close.at[date, symbol]
                if not np.isfinite(entry) or entry <= 0:
                    continue
                series = close[symbol].loc[horizon].dropna()
                if series.empty:
                    continue
                exit_price = float(series.iloc[-1])
                price = sign * (exit_price / float(entry) - 1.0) * notional
                funding_rate = funding_days[symbol].dropna().sum()
                funding = -sign * float(funding_rate) * notional
                cost = 2.0 * (COST_BP_PER_SIDE / 1e4) * notional
                episodes.append({
                    "date": date.strftime("%Y-%m-%d"),
                    "symbol": symbol,
                    "side": side,
                    "price": price,
                    "funding": funding,
                    "cost": cost,
                    "net": price + funding - cost,
                })

    frame = pd.DataFrame(episodes)
    if frame.empty:
        raise SystemExit("sin episodios: revisa la ventana y la elegibilidad")

    operations = 2 * len(frame)
    net = float(frame["net"].sum())
    wins = float(frame.loc[frame["net"] > 0, "net"].sum())
    losses = float(-frame.loc[frame["net"] < 0, "net"].sum())
    top5 = float(frame["net"].nlargest(5).sum())

    by_year = {}
    frame["year"] = frame["date"].str[:4]
    for year, group in frame.groupby("year"):
        by_year[year] = {
            "episodios": int(len(group)),
            "neto": round(float(group["net"].sum()), 2),
            "top5_sin": round(float(group["net"].sum() - group["net"].nlargest(5).sum()), 2),
            "precio": round(float(group["price"].sum()), 2),
            "funding": round(float(group["funding"].sum()), 2),
        }

    return {
        "posiciones_por_lado_mediana": int(np.median([len(previous[0])])) if previous else 0,
        "episodios": int(len(frame)),
        "operaciones": int(operations),
        "neto": round(net, 2),
        "pf": round(wins / losses, 4) if losses > 0 else None,
        "esperanza_R_op": round(net / operations / R_USD, 4),
        "coste_R_op": round(float(frame["cost"].sum()) / operations / R_USD, 4),
        "top5_sin": round(net - top5, 2),
        "precio": round(float(frame["price"].sum()), 2),
        "funding": round(float(frame["funding"].sum()), 2),
        "coste": round(float(frame["cost"].sum()), 2),
        "por_anio": by_year,
        "puertas": {
            "ops >= 100": int(operations) >= 100,
            "PF > 1,10": (wins / losses if losses > 0 else 0) > 1.10,
            "esperanza > 0,05 R": (net / operations / R_USD) > 0.05,
            "coste < 0,25 R": (float(frame["cost"].sum()) / operations / R_USD) < 0.25,
            "sin top-5 > 0": (net - top5) > 0,
        },
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rate, close, quote = load_panels()
    print(f"panel: {close.shape[1]} símbolos, {len(close)} días "
          f"({close.index.min().date()} / {close.index.max().date()})")
    results = {}
    configs = (
        ("quintil sin filtro de liquidez", None, 0.0),
        ("quintil con el filtro del panel (5 M USD)", None, 5_000_000.0),
        ("k=4 sobre el panel filtrado", 4, 5_000_000.0),
    )
    for label, per_side, min_adv in configs:
        results[label] = run(rate, close, quote, per_side, min_adv)
        result = results[label]
        print(f"\n== {label} · {result['posiciones_por_lado_mediana']} por lado ==")
        print(json.dumps({k: v for k, v in result.items() if k != "por_anio"}, indent=2, ensure_ascii=False))
        print(json.dumps(result["por_anio"], indent=2, ensure_ascii=False))

    target = DATA / "h5_on_h10.json"
    target.write_text(json.dumps(results, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nescrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
