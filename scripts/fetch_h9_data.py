"""Descarga y congela el panel spot/perp de H9 (basis spot-perp).

Fuentes públicas y gratuitas:
- Spot: klines diarias de Binance Vision (``spot/monthly/klines/<SYM>/1d``),
  verificadas contra el ``.CHECKSUM`` mensual publicado por Binance.
- Perpetuo: ``data/funding_xs/perp_1d_panel.csv`` (panel H5, ya congelado).
- Funding: ``data/funding_xs/funding_panel.csv``, sumado por día UTC.

El corte es 2026-11-01 exclusive: no se descarga ni se usa el holdout. El panel
se escribe antes de ejecutar el simulador; ``freeze.json`` guarda los hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import tempfile
import urllib.error
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.market.binance_vision import BASE_URL, USER_AGENT  # noqa: E402
PERP_SOURCE = ROOT / "data" / "funding_xs" / "perp_1d_panel.csv"
FUNDING_SOURCE = ROOT / "data" / "funding_xs" / "funding_panel.csv"
OUT_DIR = ROOT / "data" / "basis"

ASSETS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
    "LTCUSDT",
    "BCHUSDT",
    "TRXUSDT",
    "ATOMUSDT",
    "NEARUSDT",
    "ETCUSDT",
    "FILUSDT",
    "UNIUSDT",
    "AAVEUSDT",
    "SANDUSDT",
)
START = "2023-05-12"
END = "2026-11-01"  # exclusive


def _months(start: str, end: str) -> list[str]:
    first = pd.Period(start, freq="M")
    last = pd.Period(pd.Timestamp(end) - pd.Timedelta(days=1), freq="M")
    return [str(period) for period in pd.period_range(first, last, freq="M")]


def _url(symbol: str, month: str) -> str:
    return f"{BASE_URL}/spot/monthly/klines/{symbol}/1d/{symbol}-1d-{month}.zip"


def _checksum(symbol: str, month: str) -> str:
    request = urllib.request.Request(_url(symbol, month) + ".CHECKSUM", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        text = response.read().decode("utf-8", "replace")
    return text.split()[0].strip().lower() if text.split() else ""


def _download(symbol: str, month: str, cache: Path, retries: int = 5) -> Path:
    target = cache / f"{symbol}-1d-{month}.zip"
    if target.is_file() and target.stat().st_size > 0:
        return target
    last_error: Exception | None = None
    for _attempt in range(retries):
        try:
            request = urllib.request.Request(_url(symbol, month), headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            if not payload:
                raise ValueError("Binance devolvió un fichero vacío")
            expected = _checksum(symbol, month)
            digest = hashlib.sha256(payload).hexdigest()
            if expected and digest != expected:
                raise ValueError(f"sha256 {digest} != {expected}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            return target
        except (urllib.error.URLError, ValueError, TimeoutError) as error:
            last_error = error
    raise RuntimeError(f"{symbol} {month}: {last_error}")


def _closes(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> dict[pd.Timestamp, float]:
    result: dict[pd.Timestamp, float] = {}
    with zipfile.ZipFile(path) as archive:
        names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if not names:
            raise ValueError(f"{path.name}: el ZIP no trae CSV")
        with archive.open(names[0]) as raw:
            frame = pd.read_csv(io.TextIOWrapper(raw, encoding="utf-8"), header=None)
    # open_time, open, high, low, close, volume, close_time, ...
    if str(frame.iloc[0, 0]).lower().startswith("open_time"):
        frame = frame.iloc[1:].reset_index(drop=True)
    for row in frame.itertuples(index=False):
        stamp = pd.to_datetime(int(row[0]), unit="us" if int(row[0]) > 10**14 else "ms", utc=True).floor("D")
        if start <= stamp < end:
            close = float(row[4])
            if close > 0:
                result[stamp] = close
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(start: str, end: str, out_dir: Path) -> dict:
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    months = _months(start, end)
    cache = Path(tempfile.gettempdir()) / "ezur_h9_spot_cache"
    cache.mkdir(parents=True, exist_ok=True)

    spot_rows: list[dict] = []
    jobs = [(symbol, month) for symbol in ASSETS for month in months]
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_download, symbol, month, cache): (symbol, month) for symbol, month in jobs}
        for future in as_completed(futures):
            symbol, month = futures[future]
            path = future.result()
            for stamp, close in _closes(path, start_ts, end_ts).items():
                spot_rows.append({"symbol": symbol, "dt": stamp, "close": close})
            if month == months[-1]:
                print(f"{symbol}: {len(spot_rows)} filas acumuladas", flush=True)

    spot = pd.DataFrame(spot_rows).drop_duplicates(["symbol", "dt"]).sort_values(["symbol", "dt"])
    perp = pd.read_csv(PERP_SOURCE, parse_dates=["dt"])
    perp["dt"] = pd.to_datetime(perp["dt"], utc=True).dt.floor("D")
    perp = perp[(perp["dt"] >= start_ts) & (perp["dt"] < end_ts) & (perp["symbol"].isin(ASSETS))]
    perp = perp.drop_duplicates(["symbol", "dt"]).sort_values(["symbol", "dt"])

    funding = pd.read_csv(FUNDING_SOURCE, parse_dates=["dt"])
    funding["dt"] = pd.to_datetime(funding["dt"], utc=True).dt.floor("D")
    funding = funding[(funding["dt"] >= start_ts) & (funding["dt"] < end_ts) & (funding["symbol"].isin(ASSETS))]
    funding = (
        funding.groupby(["symbol", "dt"], as_index=False)
        .agg(rate=("rate", "sum"))
        .sort_values(["symbol", "dt"])
    )

    if spot.empty or perp.empty or funding.empty:
        raise RuntimeError("el panel quedó vacío")

    out_dir.mkdir(parents=True, exist_ok=True)
    spot_path = out_dir / "spot_daily.csv"
    perp_path = out_dir / "perp_daily.csv"
    funding_path = out_dir / "funding_daily.csv"
    for frame, path in ((spot, spot_path), (perp, perp_path), (funding, funding_path)):
        frame.to_csv(path, index=False, date_format="%Y-%m-%d")

    coverage: dict[str, dict] = {}
    for symbol in ASSETS:
        s = spot[spot["symbol"] == symbol]
        p = perp[perp["symbol"] == symbol]
        f = funding[funding["symbol"] == symbol]
        coverage[symbol] = {
            "spot_days": int(len(s)),
            "spot_start": s["dt"].min().strftime("%Y-%m-%d") if len(s) else None,
            "spot_end": s["dt"].max().strftime("%Y-%m-%d") if len(s) else None,
            "perp_days": int(len(p)),
            "perp_start": p["dt"].min().strftime("%Y-%m-%d") if len(p) else None,
            "perp_end": p["dt"].max().strftime("%Y-%m-%d") if len(p) else None,
            "funding_days": int(len(f)),
            "funding_start": f["dt"].min().strftime("%Y-%m-%d") if len(f) else None,
            "funding_end": f["dt"].max().strftime("%Y-%m-%d") if len(f) else None,
        }

    freeze = {
        "source": "Binance Vision spot monthly klines 1d; paneles H5 de perpetuo y funding",
        "assets": list(ASSETS),
        "period": {"start": start, "end": end, "end_exclusive": True},
        "spot_rows": int(len(spot)),
        "perp_rows": int(len(perp)),
        "funding_rows": int(len(funding)),
        "spot_sha256": _sha256(spot_path),
        "perp_sha256": _sha256(perp_path),
        "funding_sha256": _sha256(funding_path),
        "coverage": coverage,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga el panel spot/perp de H9")
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    freeze = build(args.start, args.end, Path(args.out))
    print(json.dumps(freeze, indent=2))


if __name__ == "__main__":
    main()
