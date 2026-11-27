"""Validación cruzada del motor de la re-medición de H5.

Compara `scripts/h5_on_h10_panel.py` con `server/funding_xs.py` sobre los mismos
20 majors y la misma ventana OOS, y atribuye cada diferencia a una convención:

- episodio semanal forzado (mi motor) frente a posición persistente que sólo se
  cierra cuando sale de la cartera (el suyo);
- precio tal cual frente a `ffill`;
- señal con 60 días mínimos frente a exigir 90 filas de historia;
- funding diario ya sumado frente a `rate × 8 / interval_h` sumado por día;
- deslistado: cierre al último precio disponible frente a dejar la posición
  abierta sin coste de salida.

Uso:
    python scripts/validate_h5_engine.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server.funding_xs import load_panels as h5_load  # noqa: E402

CAPITAL = 25_000.0
R_USD = 250.0
COST_SIDE = 0.0006
START = pd.Timestamp("2025-01-01", tz="UTC")
END = pd.Timestamp("2026-11-01", tz="UTC")


def load_h5():
    funding, prices = h5_load(
        ROOT / "data" / "funding_xs" / "funding_panel.csv",
        ROOT / "data" / "funding_xs" / "perp_1d_panel.csv",
    )
    funding = funding[(funding.index >= START) & (funding.index < END)]
    prices = prices[(prices.index >= START) & (prices.index < END)]
    return funding, prices


def load_h10(min_adv: float = 0.0, folder: str = "h10",
             start: pd.Timestamp = START, end: pd.Timestamp = END):
    funding = pd.read_csv(ROOT / "data" / folder / "funding_daily.csv", parse_dates=["dt"])
    perp = pd.read_csv(ROOT / "data" / folder / "perp_daily.csv", parse_dates=["dt"])
    for frame in (funding, perp):
        frame["dt"] = pd.to_datetime(frame["dt"], utc=True).dt.floor("D")
    rate = funding.pivot_table(index="dt", columns="symbol", values="rate", aggfunc="sum").sort_index()
    close = perp.pivot_table(index="dt", columns="symbol", values="close", aggfunc="last").sort_index()
    quote = perp.pivot_table(index="dt", columns="symbol", values="quote_volume", aggfunc="last").sort_index()
    rate = rate.reindex(index=close.index, columns=close.columns)
    quote = quote.reindex(index=close.index, columns=close.columns)
    rate = rate[(rate.index >= start) & (rate.index < end)]
    close = close[(close.index >= start) & (close.index < end)]
    quote = quote[(quote.index >= start) & (quote.index < end)]
    return rate, close, quote, min_adv


def signal_at(funding: pd.DataFrame, date: pd.Timestamp, lookback: int = 90,
              strict: bool = True, min_periods: int = 60) -> pd.Series:
    history = funding[funding.index < date]
    window = history.tail(lookback)
    if strict:
        if len(window) < lookback:
            return pd.Series(dtype=float)
    elif len(window) < min_periods:
        return pd.Series(dtype=float)
    last_week = window.tail(7).mean()
    mean = window.mean()
    std = window.std().where(lambda value: value > 1e-12)
    return ((last_week - mean) / std).dropna()


def replay(funding: pd.DataFrame, prices: pd.DataFrame, *, persistent: bool,
           ffill: bool, strict: bool, quantile: float = 0.2,
           per_side: int | None = None, min_eligible: int = 10,
           close_on_missing: bool = True, adv: pd.DataFrame | None = None,
           min_adv: float = 0.0, daily_out: bool = False) -> dict:
    frame = prices.ffill() if ffill else prices
    dates = list(prices.index)
    positions: dict[str, dict] = {}
    episodes: list[dict] = []
    # Curva diaria para el neto compuesto (la convención de funding_xs).
    daily = pd.Series(0.0, index=dates)

    def close(symbol: str, date: pd.Timestamp, price: float) -> None:
        # El precio ya se devengó día a día; aquí sólo se paga el coste de salida.
        position = positions.pop(symbol)
        cost = COST_SIDE * position["notional"]
        position["costs"] += cost
        daily.at[date] -= cost / CAPITAL
        episodes.append({
            "symbol": symbol,
            "net": position["price"] + position["funding"] - position["costs"],
            "price": position["price"],
            "funding": position["funding"],
            "costs": position["costs"],
            "date": date.strftime("%Y-%m-%d"),
        })

    for index, date in enumerate(dates):
        if index == 0:
            continue
        # P&L de la cartera abierta, día a día (la convención de funding_xs).
        for symbol, position in list(positions.items()):
            price = frame.at[date, symbol]
            previous = frame.at[dates[index - 1], symbol]
            if not np.isfinite(price) or not np.isfinite(previous) or previous <= 0:
                if close_on_missing and persistent:
                    last = prices[symbol].loc[:date].dropna()
                    if len(last) >= 2:
                        close(symbol, last.index[-1], float(last.iloc[-1]))
                continue
            move = position["sign"] * (price / previous - 1.0) * position["notional"]
            position["price"] += move
            daily.iloc[index] += move / CAPITAL
            funded = funding.at[date, symbol] if symbol in funding.columns else np.nan
            if np.isfinite(funded) and position["entry"] < date:
                payment = -position["sign"] * float(funded) * position["notional"]
                position["funding"] += payment
                daily.iloc[index] += payment / CAPITAL

        if date.weekday() != 0:
            continue

        signal = signal_at(funding, date, strict=strict)
        available = [s for s in signal.index if np.isfinite(frame.at[date, s]) and frame.at[date, s] > 0]
        if min_adv > 0 and adv is not None:
            available = [s for s in available if np.isfinite(adv.at[date, s]) and adv.at[date, s] >= min_adv]
        signal = signal[available].sort_values()
        if len(signal) < min_eligible:
            continue

        k = per_side if per_side else max(2, int(round(len(signal) * quantile)))
        k = min(k, max(1, len(signal) // 2))
        target = {s: 1 for s in signal.index[:k]} | {s: -1 for s in signal.index[-k:]}
        notional = CAPITAL * 0.5 / k

        if not persistent:
            for symbol in list(positions):
                close(symbol, date, float(frame.at[date, symbol]))
        for symbol in list(positions):
            if symbol not in target:
                close(symbol, date, float(frame.at[date, symbol]))
        for symbol, sign in target.items():
            if symbol in positions:
                if positions[symbol]["sign"] != sign:
                    close(symbol, date, float(frame.at[date, symbol]))
                else:
                    continue
            price = float(frame.at[date, symbol])
            positions[symbol] = {
                "sign": sign, "notional": notional, "entry": date, "entry_price": price,
                "last_price": price, "price": 0.0, "funding": 0.0, "costs": COST_SIDE * notional,
            }
            daily.iloc[index] -= COST_SIDE * notional / CAPITAL

    # Cierre final: lo que quede abierto se liquida al último precio disponible.
    for symbol in list(positions):
        last = prices[symbol].dropna()
        close(symbol, dates[-1], float(last.iloc[-1]))

    frame_eps = pd.DataFrame(episodes)
    if frame_eps.empty:
        return {"episodios": 0}
    operations = 2 * len(frame_eps)
    net = float(frame_eps["net"].sum())
    wins = float(frame_eps.loc[frame_eps["net"] > 0, "net"].sum())
    losses = float(-frame_eps.loc[frame_eps["net"] < 0, "net"].sum())
    top5 = float(frame_eps["net"].nlargest(5).sum())
    frame_eps["year"] = frame_eps["date"].str[:4]
    por_anio = {
        str(year): {
            "episodios": int(len(group)),
            "neto": round(float(group["net"].sum()), 2),
            "sin_top5": round(float(group["net"].sum() - group["net"].nlargest(5).sum()), 2),
            "precio": round(float(group["price"].sum()), 2),
            "funding": round(float(group["funding"].sum()), 2),
        }
        for year, group in frame_eps.groupby("year")
    }
    return {
        "por_anio": por_anio,
        "episodios": int(len(frame_eps)),
        "operaciones": int(operations),
        "neto": round(net, 2),
        "neto_compuesto": round(float((1.0 + daily).prod() - 1.0) * CAPITAL, 2),
        "pf": round(wins / losses, 4) if losses > 0 else None,
        "esperanza_R": round(net / operations / R_USD, 4),
        "coste_R": round(float(frame_eps["costs"].sum()) / operations / R_USD, 5),
        "sin_top5": round(net - top5, 2),
        "precio": round(float(frame_eps["price"].sum()), 2),
        "funding": round(float(frame_eps["funding"].sum()), 2),
        "costes": round(float(frame_eps["costs"].sum()), 2),
        **({"diario": {d.strftime("%Y-%m-%d"): round(float(v), 10)
                       for d, v in daily.items() if v != 0.0}} if daily_out else {}),
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    funding, prices = load_h5()
    print(f"H5: {prices.shape[1]} símbolos, {len(prices)} días "
          f"({prices.index.min().date()}/{prices.index.max().date()})")

    published = {"episodios": 400, "operaciones": 800, "pf": 1.1114, "esperanza_R": 0.0301,
                 "coste_R": 0.0075, "sin_top5": -1863.63, "precio": 6672.63,
                 "funding": 856.8, "neto": 6086.46}

    runs = {
        "A · convenciones de H5 (persistente, ffill, 90 estricto)": dict(
            persistent=True, ffill=True, strict=True),
        "B · A con episodio semanal forzado": dict(
            persistent=False, ffill=True, strict=True),
        "C · A sin ffill (deslistado al último precio)": dict(
            persistent=True, ffill=False, strict=True),
        "D · A con señal de 60 días mínimos": dict(
            persistent=True, ffill=True, strict=False),
        "E · mi motor sobre los majors (semanal, sin ffill, 60 mín.)": dict(
            persistent=False, ffill=False, strict=False),
    }
    results = {"publicado": published}
    for label, kwargs in runs.items():
        results[label] = replay(funding, prices, **kwargs)
        print(f"\n{label}")
        print(json.dumps(results[label], ensure_ascii=False))

    # El motor validado, sobre el panel de H10.
    rate, close, quote, _ = load_h10()
    adv = quote.rolling(30, min_periods=20).median().shift(1)
    h10 = {}
    for label, per_side in (("quintil sin filtro", None), ("quintil con filtro 5M", None),
                            ("k=4 con filtro 5M", 4)):
        min_adv = 0.0 if "sin filtro" in label else 5_000_000.0
        h10[label] = replay(rate, close, persistent=True, ffill=False, strict=False,
                            per_side=per_side, adv=adv, min_adv=min_adv)
        print(f"\nH10 · {label} (motor persistente)")
        print(json.dumps(h10[label], ensure_ascii=False))

    target = ROOT / "data" / "h10" / "validation_h5.json"
    target.write_text(json.dumps({"majors": results, "h10_persistente": h10}, indent=2,
                                 ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nescrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
