"""Modelo de coste real de ejecución (ver docs/PRE-REGISTRO-COSTE.md).

Muestrea libros de OKX SWAP por cubeta de ADV, mide el coste por lado en pb a
cuatro tamaños de orden, lo ajusta como `a + b·sqrt(S/ADV)` y calcula el techo de
capacidad. El spread del tramo sin libro se estima con Corwin-Schultz sobre las
velas mensuales congeladas.

No produce P&L ni añade ensayos: mide un input.

Uso:
    python scripts/measure_execution_cost.py
"""

from __future__ import annotations

import io
import json
import time
import urllib.request
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
H10 = ROOT / "data" / "h10"
OUT = ROOT / "data" / "cost"

SIZES = [500.0, 1562.0, 3125.0, 12_500.0]
BUCKETS = [
    ("C1 <1M", 0.0, 1e6),
    ("C2 1-5M", 1e6, 5e6),
    ("C3 5-20M", 5e6, 2e7),
    ("C4 20-100M", 2e7, 1e8),
    ("C5 >100M", 1e8, float("inf")),
]
SAMPLE_PER_BUCKET = 25
MIN_LEVELS = 20
OKX_BOOKS = "https://www.okx.com/api/v5/market/books?instId={inst}&sz=400"
OKX_INSTRUMENTS = "https://www.okx.com/api/v5/public/instruments?instType=SWAP"
SPOT_DEPTH = "https://data-api.binance.vision/api/v3/depth?symbol={sym}&limit=100"
CS_DAYS = 21


HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) cost-probe/1.0"}


def get_json(url: str, tries: int = 3) -> dict:
    for attempt in range(tries):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=25) as response:
                return json.loads(response.read().decode())
        except Exception:
            if attempt == tries - 1:
                raise
            time.sleep(1.0 + attempt)
    return {}


def adv_by_symbol() -> pd.Series:
    perp = pd.read_csv(H10 / "perp_daily.csv", parse_dates=["dt"])
    perp["dt"] = pd.to_datetime(perp["dt"], utc=True).dt.floor("D")
    tail = perp[perp["dt"] >= perp["dt"].max() - pd.Timedelta(days=30)]
    adv = tail.groupby("symbol")["quote_volume"].median().dropna()
    # Sin volumen en los últimos 30 días no hay cubeta ni ADV con el que dividir.
    return adv[adv > 0]


def okx_ctval() -> dict[str, float]:
    payload = get_json(OKX_INSTRUMENTS)
    out = {}
    for row in payload.get("data", []):
        inst = row.get("instId", "")
        if inst.endswith("-USDT-SWAP"):
            out[inst.split("-")[0]] = float(row.get("ctVal") or 1.0)
    return out


def _consume(levels, size_usd: float, ctval: float) -> float | None:
    """VWAP de recorrer el libro hasta gastar `size_usd`. None si no alcanza."""
    spent_value = 0.0
    spent_qty = 0.0
    for price, quantity in levels:
        notional = price * quantity * ctval
        take = min(notional, size_usd - spent_value)
        spent_value += take
        spent_qty += take / price
        if spent_value >= size_usd - 1e-9:
            return spent_value / spent_qty
    return None


def book_costs(inst: str, ctval: float) -> dict | None:
    payload = get_json(OKX_BOOKS.format(inst=inst))
    data = payload.get("data") or []
    if not data:
        return None
    book = data[0]
    bids = [(float(p), float(q)) for p, q, *_ in book.get("bids", [])]
    asks = [(float(p), float(q)) for p, q, *_ in book.get("asks", [])]
    if len(bids) < MIN_LEVELS or len(asks) < MIN_LEVELS:
        return None
    mid = (bids[0][0] + asks[0][0]) / 2.0
    result = {"spread_bp": (asks[0][0] - bids[0][0]) / mid * 1e4, "costs": {}}
    for size in SIZES:
        buy = _consume(asks, size, ctval)
        sell = _consume(bids, size, ctval)
        if buy is None or sell is None:
            continue
        result["costs"][size] = (buy - sell) / (2.0 * mid) * 1e4
    return result


def corwin_schultz(symbol: str, months: list[str]) -> float | None:
    highs, lows = [], []
    for month in months:
        path = H10 / "cache" / "klines" / f"{symbol}-{month}.zip"
        if not path.is_file():
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                raw = archive.read(archive.namelist()[0]).decode(errors="replace")
        except Exception:
            continue
        frame = pd.read_csv(io.StringIO(raw), header=None)
        if frame.iloc[0, 0] == "open_time":
            frame = frame.iloc[1:]
        if frame.shape[1] < 5:
            continue
        highs.append(pd.to_numeric(frame[2], errors="coerce"))
        lows.append(pd.to_numeric(frame[3], errors="coerce"))
    if not highs:
        return None
    high = pd.concat(highs, ignore_index=True).to_numpy(dtype=float)
    low = pd.concat(lows, ignore_index=True).to_numpy(dtype=float)
    mask = np.isfinite(high) & np.isfinite(low) & (high > 0) & (low > 0)
    high, low = high[mask], low[mask]
    if len(high) < CS_DAYS + 2:
        return None
    log_hl = np.log(high / low) ** 2
    beta = log_hl[:-1] + log_hl[1:]
    gamma = np.log(np.maximum(high[:-1], high[1:]) / np.minimum(low[:-1], low[1:])) ** 2
    root = np.sqrt(2.0)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / (3.0 - 2.0 * root) \
        - np.sqrt(gamma / (3.0 - 2.0 * root))
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    spread = np.where(spread < 0, 0.0, spread)
    return float(np.median(spread[-CS_DAYS:]) * 1e4)


def fit(rows: list[dict]) -> dict:
    rows = [r for r in rows if r["adv"] > 0]
    x = np.array([[1.0, np.sqrt(r["size"] / r["adv"])] for r in rows])
    y = np.array([r["cost_bp"] for r in rows])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    pred = x @ coef
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return {
        "alpha": float(coef[0]),
        "beta": float(coef[1]),
        "r2": 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0,
        "mae": float(np.median(np.abs(y - pred))),
        "n": int(len(y)),
    }


def capacity(alpha: float, beta: float, adv: float, limit_bp: float) -> float | None:
    if beta <= 0:
        return None if alpha > limit_bp else float("inf")
    if alpha > limit_bp:
        return 0.0
    ratio = (limit_bp - alpha) / beta
    return float(ratio ** 2 * adv)


def main() -> int:
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    OUT.mkdir(parents=True, exist_ok=True)

    adv = adv_by_symbol()
    ctvals = okx_ctval()
    print(f"panel: {len(adv)} símbolos con ADV; OKX lista {len(ctvals)} swaps USDT")

    sample: dict[str, list[str]] = {}
    books: dict[str, dict] = {}
    for name, low, high in BUCKETS:
        in_bucket = sorted(s for s, v in adv.items() if low <= v < high)
        listed = [s for s in in_bucket if s.replace("USDT", "") in ctvals]
        chosen = listed[:SAMPLE_PER_BUCKET]
        sample[name] = chosen
        print(f"{name}: {len(in_bucket)} en cubeta, {len(listed)} en OKX, muestreo {len(chosen)}")
        for symbol in chosen:
            inst = f"{symbol.replace('USDT', '')}-USDT-SWAP"
            costs = book_costs(inst, ctvals.get(symbol.replace("USDT", ""), 1.0))
            time.sleep(0.12)
            if costs:
                books[symbol] = {"bucket": name, **costs}

    rows = [
        {"symbol": symbol, "bucket": data["bucket"], "size": size,
         "cost_bp": value, "adv": float(adv[symbol])}
        for symbol, data in books.items()
        for size, value in data["costs"].items()
    ]
    model = fit(rows) if len(rows) >= 20 else {"alpha": None, "beta": None, "r2": 0.0, "mae": None, "n": len(rows)}

    months = ["2026-08", "2026-09", "2026-10"]
    cs: dict[str, float] = {}
    for _name, low, high in BUCKETS:
        in_bucket = sorted(s for s, v in adv.items() if low <= v <= high)
        for symbol in in_bucket[:SAMPLE_PER_BUCKET]:
            value = corwin_schultz(symbol, months)
            if value is not None:
                cs[symbol] = value

    # Contraste con el libro de spot de Binance (misma casa, otro producto).
    spot_spreads: dict[str, float] = {}
    for symbol in [s for s in books if books[s]["bucket"] in ("C4 20-100M", "C5 >100M")][:20]:
        try:
            depth = get_json(SPOT_DEPTH.format(sym=symbol))
            bids = depth.get("bids") or []
            asks = depth.get("asks") or []
            if bids and asks:
                best_bid, best_ask = float(bids[0][0]), float(asks[0][0])
                mid = (best_bid + best_ask) / 2.0
                spot_spreads[symbol] = (best_ask - best_bid) / mid * 1e4
            time.sleep(0.2)
        except Exception:
            continue

    common = [s for s in cs if s in books]
    spearman = None
    if len(common) >= 10:
        a = pd.Series({s: cs[s] for s in common}).rank()
        b = pd.Series({s: books[s]["spread_bp"] for s in common}).rank()
        # Spearman = Pearson sobre rangos (no hay scipy en este entorno).
        spearman = float(a.corr(b))

    by_bucket: dict[str, dict] = {}
    for name, low, high in BUCKETS:
        members = [s for s, d in books.items() if d["bucket"] == name]
        by_bucket[name] = {"libros": len(members)}
        for size in SIZES:
            values = [books[s]["costs"][size] for s in members if size in books[s]["costs"]]
            if values:
                by_bucket[name][f"coste_{int(size)}"] = {
                    "mediana": round(float(np.median(values)), 3),
                    "p25": round(float(np.percentile(values, 25)), 3),
                    "p75": round(float(np.percentile(values, 75)), 3),
                    "n": len(values),
                }
        spreads = [d["spread_bp"] for d in (books[s] for s in members)]
        if spreads:
            by_bucket[name]["spread_mediana_bp"] = round(float(np.median(spreads)), 3)
        cs_bucket = [cs[s] for s in cs if low <= adv[s] < high]
        if cs_bucket:
            by_bucket[name]["cs_mediana_bp"] = round(float(np.median(cs_bucket)), 3)

    gates = {
        "G1 libros validos >= 60": len(books) >= 60,
        "G2 r2 >= 0.50": bool(model.get("r2") is not None and model["r2"] >= 0.5),
        "G3 mae <= 8 pb": bool(model.get("mae") is not None and model["mae"] <= 8.0),
        "G4 monotonia 12.5k > 500": all(
            (by_bucket[n].get("coste_12500", {}).get("mediana", 0) >
             by_bucket[n].get("coste_500", {}).get("mediana", 0))
            for n in by_bucket if by_bucket[n]["libros"] >= 8
        ),
        "G5 spearman >= 0.50": bool(spearman is not None and spearman >= 0.5),
    }

    caps = {}
    if model.get("alpha") is not None and model["beta"] > 0:
        for name, low, high in BUCKETS:
            subset = [v for s, v in adv.items() if low <= v < high and v > 0]
            if not subset:
                continue
            mid = float(np.median(subset))
            caps[name] = {
                "adv_mediana": round(mid, 0),
                "capacidad_6bp_usd": round(capacity(model["alpha"], model["beta"], mid, 6.0) or 0, 0),
                "capacidad_10bp_usd": round(capacity(model["alpha"], model["beta"], mid, 10.0) or 0, 0),
            }

    result = {
        "modelo": model, "puertas": gates, "spearman_cs_libro": spearman,
        "spot_binance": {
            "n": len(spot_spreads),
            "spread_mediana_bp": round(float(np.median(list(spot_spreads.values()))), 3)
            if spot_spreads else None,
            "ratio_vs_okx": round(float(np.median([
                spot_spreads[s] / books[s]["spread_bp"] for s in spot_spreads if s in books
            ])), 3) if spot_spreads else None,
        },
        "por_cubeta": by_bucket, "capacidad": caps,
        "muestra": {k: len(v) for k, v in sample.items()},
        "libros": len(books),
    }
    (OUT / "model.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "books.json").write_text(json.dumps(
        {"books": books, "cs": cs, "adv": {k: float(v) for k, v in adv.items()}}, indent=2) + "\n",
        encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "libros"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
