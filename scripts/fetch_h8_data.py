"""Descarga y congela el panel de funding/precios de H8.

Fuentes públicas:
- Binance USD-M: panel ya congelado en data/funding_xs.
- Hyperliquid: funding horario y velas diarias; su API devuelve 500 eventos por
  llamada, así que se pagina por ``startTime``.
- OKX: se comprueba su cobertura, pero no entra en el panel: su API pública
  solo conserva 67 días de funding (2026-08-26/2026-10-31). El pre-registro se
  enmienda antes de medir; no se usa un tramo parcial.

El corte es 2026-11-01 exclusive. No se descarga ni se usa el holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from functools import partial
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BINANCE_FUNDING = ROOT / "data" / "funding_xs" / "funding_panel.csv"
BINANCE_PRICES = ROOT / "data" / "funding_xs" / "perp_1d_panel.csv"
OUT_DIR = ROOT / "data" / "funding_spread"

USED_VENUES = ("binance", "hyperliquid")
ASSETS = {
    "BTC": {"binance": "BTCUSDT", "okx": "BTC-USDT-SWAP", "hyperliquid": "BTC"},
    "ETH": {"binance": "ETHUSDT", "okx": "ETH-USDT-SWAP", "hyperliquid": "ETH"},
    "SOL": {"binance": "SOLUSDT", "okx": "SOL-USDT-SWAP", "hyperliquid": "SOL"},
    "XRP": {"binance": "XRPUSDT", "okx": "XRP-USDT-SWAP", "hyperliquid": "XRP"},
    "DOGE": {"binance": "DOGEUSDT", "okx": "DOGE-USDT-SWAP", "hyperliquid": "DOGE"},
}

START = "2023-05-12"
END = "2026-11-01"  # exclusive
OKX = "https://www.okx.com/api/v5"
HYPERLIQUID = "https://api.hyperliquid.xyz/info"
USER_AGENT = "ezur-bot-research/0.1 (H8 funding spread)"


def _ms(value: str) -> int:
    return int(pd.Timestamp(value, tz="UTC").timestamp() * 1000)


def _get_json(
    url: str,
    params: dict | None = None,
    payload: dict | None = None,
    retries: int = 8,
) -> object:
    if params:
        url = f"{url}?{urlencode(params)}"
    data = None
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = Request(url, data=data, headers=headers, method="POST" if data else "GET")
            with urlopen(request, timeout=40) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            last_error = error
            if error.code == 404:
                raise
            if error.code == 429:
                retry_after = error.headers.get("Retry-After") if error.headers else None
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 20.0
                time.sleep(delay)
            else:
                time.sleep(2.0 * (attempt + 1))
        except (URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            time.sleep(2.0 * (attempt + 1))
    raise RuntimeError(f"falló {url}: {last_error}")


def _cache_dir() -> Path:
    path = Path(tempfile.gettempdir()) / "ezur_h8_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cached(cache: Path, name: str, loader) -> list[tuple[int, float]]:
    path = cache / f"{name}.csv"
    if path.exists():
        frame = pd.read_csv(path)
        return [(int(row.ts), float(row.value)) for row in frame.itertuples()]
    rows = loader()
    pd.DataFrame(rows, columns=["ts", "value"]).to_csv(path, index=False)
    return rows


def _okx_rows(path: str, params: dict) -> list[list[str]]:
    payload = _get_json(f"{OKX}{path}", params=params)
    if not isinstance(payload, dict) or payload.get("code") != "0":
        raise RuntimeError(f"OKX {path} devolvió {payload!r}")
    return payload.get("data", [])


def fetch_okx_funding(inst_id: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    rows: dict[int, float] = {}
    cursor: int | None = None
    while True:
        params = {"instId": inst_id, "limit": "100"}
        if cursor is not None:
            params["after"] = str(cursor)
        data = _okx_rows("/public/funding-rate-history", params)
        if not data:
            break
        times = []
        for item in data:
            timestamp = int(item["fundingTime"])
            times.append(timestamp)
            if start_ms <= timestamp < end_ms:
                rate = item.get("realizedRate") or item.get("fundingRate")
                if rate not in (None, ""):
                    rows[timestamp] = float(rate)
        oldest = min(times)
        if oldest <= start_ms or (cursor is not None and oldest >= cursor):
            break
        cursor = oldest
        time.sleep(0.25)
    return sorted(rows.items())


def fetch_okx_prices(inst_id: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    rows: dict[int, float] = {}
    cursor: int | None = None
    while True:
        params = {"instId": inst_id, "bar": "1D", "limit": "100"}
        if cursor is not None:
            params["after"] = str(cursor)
        data = _okx_rows("/market/history-candles", params)
        if not data:
            break
        times = []
        for item in data:
            timestamp = int(item[0])
            times.append(timestamp)
            if start_ms <= timestamp < end_ms:
                close = float(item[4])
                if close > 0:
                    rows[timestamp] = close
        oldest = min(times)
        if oldest <= start_ms or (cursor is not None and oldest >= cursor):
            break
        cursor = oldest
        time.sleep(0.25)
    return sorted(rows.items())


def fetch_hl_funding(coin: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    rows: dict[int, float] = {}
    cursor = start_ms
    while cursor < end_ms:
        data = _get_json(
            HYPERLIQUID,
            payload={"type": "fundingHistory", "coin": coin, "startTime": cursor},
        )
        if not isinstance(data, list) or not data:
            break
        batch = []
        for item in data:
            timestamp = int(item["time"])
            batch.append(timestamp)
            if start_ms <= timestamp < end_ms:
                rows[timestamp] = float(item["fundingRate"])
        last = max(batch)
        if len(data) < 500 or last < cursor:
            break
        cursor = last + 1
        time.sleep(1.15)
    return sorted(rows.items())


def fetch_hl_prices(coin: str, start_ms: int, end_ms: int) -> list[tuple[int, float]]:
    data = _get_json(
        HYPERLIQUID,
        payload={
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": "1d",
                "startTime": start_ms,
                "endTime": end_ms - 1,
            },
        },
    )
    if not isinstance(data, list):
        raise RuntimeError(f"Hyperliquid candles devolvió {data!r}")
    rows = []
    for item in data:
        timestamp = int(item["t"])
        close = float(item["c"])
        if start_ms <= timestamp < end_ms and close > 0:
            rows.append((timestamp, close))
    return sorted(dict(rows).items())


def _binance_funding(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, float]]:
    frame = pd.read_csv(BINANCE_FUNDING, parse_dates=["dt"])
    frame = frame[(frame["symbol"] == symbol) & (frame["dt"] >= start) & (frame["dt"] < end)]
    return [(int(row.dt.timestamp() * 1000), float(row.rate)) for row in frame.itertuples()]


def _binance_prices(symbol: str, start: pd.Timestamp, end: pd.Timestamp) -> list[tuple[int, float]]:
    frame = pd.read_csv(BINANCE_PRICES, parse_dates=["dt"])
    frame = frame[(frame["symbol"] == symbol) & (frame["dt"] >= start) & (frame["dt"] < end)]
    return [(int(row.dt.timestamp() * 1000), float(row.close)) for row in frame.itertuples()]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(start: str, end: str, out_dir: Path) -> dict:
    start_ts = pd.Timestamp(start, tz="UTC")
    end_ts = pd.Timestamp(end, tz="UTC")
    start_ms, end_ms = _ms(start), _ms(end)
    events: list[dict] = []
    prices: list[dict] = []
    cache = _cache_dir()

    for asset, symbols in ASSETS.items():
        for timestamp, rate in _binance_funding(symbols["binance"], start_ts, end_ts):
            events.append({"asset": asset, "venue": "binance", "ts": timestamp, "rate": rate})
        for timestamp, close in _binance_prices(symbols["binance"], start_ts, end_ts):
            prices.append({"asset": asset, "venue": "binance", "ts": timestamp, "close": close})
        for timestamp, rate in _cached(
            cache,
            f"{asset}_hl_funding",
            partial(fetch_hl_funding, symbols["hyperliquid"], start_ms, end_ms),
        ):
            events.append({"asset": asset, "venue": "hyperliquid", "ts": timestamp, "rate": rate})
        for timestamp, close in _cached(
            cache,
            f"{asset}_hl_prices",
            partial(fetch_hl_prices, symbols["hyperliquid"], start_ms, end_ms),
        ):
            prices.append({"asset": asset, "venue": "hyperliquid", "ts": timestamp, "close": close})

    event_frame = pd.DataFrame(events).drop_duplicates(["asset", "venue", "ts"])
    price_frame = pd.DataFrame(prices).drop_duplicates(["asset", "venue", "ts"])
    if event_frame.empty or price_frame.empty:
        raise RuntimeError("el panel quedó vacío")

    event_frame["date"] = pd.to_datetime(event_frame["ts"], unit="ms", utc=True).dt.floor("D")
    price_frame["date"] = pd.to_datetime(price_frame["ts"], unit="ms", utc=True).dt.floor("D")
    funding_daily = (
        event_frame.groupby(["asset", "venue", "date"], as_index=False)
        .agg(rate=("rate", "sum"), events=("rate", "size"))
        .sort_values(["asset", "venue", "date"])
    )
    prices_daily = (
        price_frame.sort_values(["asset", "venue", "ts"])
        .drop_duplicates(["asset", "venue", "date"], keep="last")
        .loc[:, ["asset", "venue", "date", "close"]]
        .sort_values(["asset", "venue", "date"])
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    funding_path = out_dir / "funding_daily.csv"
    prices_path = out_dir / "prices_daily.csv"
    events_path = out_dir / "funding_events.csv"
    funding_daily.to_csv(funding_path, index=False, date_format="%Y-%m-%d")
    prices_daily.to_csv(prices_path, index=False, date_format="%Y-%m-%d")
    event_frame.sort_values(["asset", "venue", "ts"]).to_csv(events_path, index=False)

    coverage: dict[str, dict[str, dict]] = {}
    for asset in ASSETS:
        coverage[asset] = {}
        for venue in USED_VENUES:
            subset = funding_daily[(funding_daily["asset"] == asset) & (funding_daily["venue"] == venue)]
            price_subset = prices_daily[(prices_daily["asset"] == asset) & (prices_daily["venue"] == venue)]
            coverage[asset][venue] = {
                "funding_days": int(subset["date"].nunique()),
                "funding_rows": int(len(subset)),
                "funding_start": subset["date"].min().strftime("%Y-%m-%d") if len(subset) else None,
                "funding_end": subset["date"].max().strftime("%Y-%m-%d") if len(subset) else None,
                "funding_events": int(subset["events"].sum()) if len(subset) else 0,
                "price_days": int(price_subset["date"].nunique()),
                "price_start": price_subset["date"].min().strftime("%Y-%m-%d") if len(price_subset) else None,
                "price_end": price_subset["date"].max().strftime("%Y-%m-%d") if len(price_subset) else None,
            }

    freeze = {
        "source": "Binance Vision (panel H5), OKX public API, Hyperliquid public API",
        "bybit": "excluido: bloqueo CloudFront para esta región; no se elude",
        "okx": "excluido antes de medir: la API pública solo conserva 67 días de funding",
        "assets": list(ASSETS),
        "venues": list(USED_VENUES),
        "period": {"start": start, "end": end, "end_exclusive": True},
        "funding_events": int(len(event_frame)),
        "funding_daily_rows": int(len(funding_daily)),
        "price_rows": int(len(prices_daily)),
        "funding_sha256": _sha256(funding_path),
        "prices_sha256": _sha256(prices_path),
        "events_sha256": _sha256(events_path),
        "coverage": coverage,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (out_dir / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze


def main() -> None:
    parser = argparse.ArgumentParser(description="Descarga el panel de funding de H8")
    parser.add_argument("--start", default=START)
    parser.add_argument("--end", default=END)
    parser.add_argument("--out", default=str(OUT_DIR))
    args = parser.parse_args()
    freeze = build(args.start, args.end, Path(args.out))
    print(json.dumps(freeze, indent=2))


if __name__ == "__main__":
    main()
