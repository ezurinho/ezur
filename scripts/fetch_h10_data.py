"""Descarga y congela el panel de H10 (carry cross-sectional en el tramo largo).

Universo: perpetuos USD-M con liquidación en USDT, fuera de los 20 mayores de H5,
con datos entre 2023-01 y 2026-10. Incluye los deslistados: el símbolo entra en
su primer mes con datos y sale en el último, sin usar el exchangeInfo de hoy.

Fuentes públicas y gratuitas de Binance Vision, cada ZIP verificado contra su
``.CHECKSUM`` mensual:

- ``futures/um/monthly/fundingRate/<SYM>``
- ``futures/um/monthly/klines/<SYM>/1d``

Salidas en ``data/h10/``: ``funding_daily.csv``, ``perp_daily.csv`` y
``freeze.json`` con SHA-256, conteo de filas y cobertura por símbolo. El panel se
escribe antes de cualquier cribado o medida y no se recalcula después de ver un
resultado.

Uso:
    python scripts/fetch_h10_data.py --workers 12
    python scripts/fetch_h10_data.py --symbols BTCUSDT,ICXUSDT   # prueba
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

BASE = "https://data.binance.vision/data"
S3 = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"
USER_AGENT = "ezur-h10-loader/1.0"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "data" / "h10"
CACHE = OUT_DIR / "cache"

START = "2023-01"
END = "2026-10"  # incluido
MAJORS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT", "DOGEUSDT",
    "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "BCHUSDT", "TRXUSDT", "ATOMUSDT",
    "NEARUSDT", "ETCUSDT", "FILUSDT", "UNIUSDT", "AAVEUSDT", "SANDUSDT",
}
RETRIES = 5


def _get(url: str, timeout: float = 45.0) -> bytes:
    last: Exception | None = None
    for attempt in range(RETRIES):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise
            last = error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last = error
        time.sleep(0.4 * (2 ** attempt))
    raise RuntimeError(f"{url}: {last}")


def months(start: str = START, end: str = END) -> list[str]:
    first = pd.Period(start, freq="M")
    last = pd.Period(end, freq="M")
    return [str(period) for period in pd.period_range(first, last, freq="M")]


def list_symbols() -> list[str]:
    """Símbolos con fundingRate mensual en Vision."""
    found: list[str] = []
    marker = ""
    prefix = "data/futures/um/monthly/fundingRate/"
    while True:
        query = {"prefix": prefix, "delimiter": "/", "max-keys": "1000"}
        if marker:
            query["marker"] = marker
        xml = _get(f"{S3}?{urllib.parse.urlencode(query)}").decode("utf-8", "replace")
        found.extend(re.findall(r"<Prefix>(.*?)</Prefix>", xml))
        if "<IsTruncated>true</IsTruncated>" not in xml:
            break
        nxt = re.search(r"<NextMarker>(.*?)</NextMarker>", xml)
        marker = nxt.group(1) if nxt else (found[-1] if found else "")
        if not marker:
            break
    return sorted({item.rstrip("/").split("/")[-1] for item in found})


def _funding_url(symbol: str, month: str) -> str:
    return f"{BASE}/futures/um/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip"


def _kline_url(symbol: str, month: str) -> str:
    return f"{BASE}/futures/um/monthly/klines/{symbol}/1d/{symbol}-1d-{month}.zip"


def fetch_one(kind: str, symbol: str, month: str) -> tuple[str, str, str | None]:
    """Descarga (o reutiliza) y verifica un ZIP. Devuelve (estado, ruta, error)."""
    target = CACHE / kind / f"{symbol}-{month}.zip"
    missing = CACHE / kind / f"{symbol}-{month}.missing"
    if target.is_file() and target.stat().st_size > 0:
        return "cached", str(target), None
    if missing.is_file():
        return "missing", "", None
    url = _funding_url(symbol, month) if kind == "funding" else _kline_url(symbol, month)
    try:
        payload = _get(url)
        expected = _get(url + ".CHECKSUM").decode("utf-8", "replace").split()
        digest = hashlib.sha256(payload).hexdigest()
        if expected and digest != expected[0].strip().lower():
            return "badsum", "", f"{symbol} {month}: sha256 {digest} != {expected[0]}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        return "downloaded", str(target), None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            missing.parent.mkdir(parents=True, exist_ok=True)
            missing.write_bytes(b"")
            return "missing", "", None
        return "error", "", f"{symbol} {month}: HTTP {error.code}"
    except UnicodeEncodeError:
        # Un símbolo fuera de ASCII no tiene URL válida: no existe como perpetuo.
        missing.parent.mkdir(parents=True, exist_ok=True)
        missing.write_bytes(b"")
        return "missing", "", None
    except RuntimeError as error:
        return "error", "", str(error)


def _stamp(raw: int) -> pd.Timestamp:
    micros = raw > 100_000_000_000_000
    seconds = raw / 1_000_000 if micros else raw / 1_000
    return pd.Timestamp(datetime.fromtimestamp(seconds, tz=UTC)).floor("D")


def parse_funding(path: Path) -> list[tuple[pd.Timestamp, float]]:
    rows: list[tuple[pd.Timestamp, float]] = []
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            return rows
        with archive.open(names[0]) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                line = line.strip()
                if not line or line.lower().startswith("calc_time"):
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                try:
                    rows.append((_stamp(int(float(parts[0]))), float(parts[2])))
                except (ValueError, OverflowError):
                    continue
    return rows


def parse_klines(path: Path) -> list[tuple[pd.Timestamp, float, float]]:
    rows: list[tuple[pd.Timestamp, float, float]] = []
    with zipfile.ZipFile(path) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith(".csv")]
        if not names:
            return rows
        with archive.open(names[0]) as raw:
            for line in io.TextIOWrapper(raw, encoding="utf-8"):
                line = line.strip()
                if not line or line.lower().startswith("open_time"):
                    continue
                parts = line.split(",")
                if len(parts) < 8:
                    continue
                try:
                    rows.append((_stamp(int(float(parts[0]))), float(parts[4]), float(parts[7])))
                except (ValueError, OverflowError):
                    continue
    return rows


def build(symbols: list[str], workers: int) -> dict:
    month_list = months()
    jobs = [(kind, symbol, month) for symbol in symbols for month in month_list
            for kind in ("funding", "klines")]
    print(f"{len(symbols)} símbolos × {len(month_list)} meses × 2 series = {len(jobs)} ficheros",
          flush=True)

    stats = {"downloaded": 0, "cached": 0, "missing": 0, "badsum": 0, "error": 0}
    errors: list[str] = []
    paths: dict[tuple[str, str, str], str] = {}

    def run(job: tuple[str, str, str]) -> tuple[tuple[str, str, str], str, str | None]:
        state, path, error = fetch_one(*job)
        return job, state, (error or (path if state in {"downloaded", "cached"} else None))

    done = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for job, state, info in pool.map(run, jobs):
            done += 1
            stats[state] += 1
            if state in {"downloaded", "cached"} and info:
                paths[job] = info
            elif state in {"badsum", "error"} and info:
                errors.append(info)
            if done % 2000 == 0:
                elapsed = time.perf_counter() - started
                print(f"  {done}/{len(jobs)} · {done / elapsed:.0f}/s · {stats}", flush=True)

    funding_rows: list[dict] = []
    perp_rows: list[dict] = []
    for symbol in symbols:
        for month in month_list:
            path = paths.get(("funding", symbol, month))
            if path:
                for stamp, rate in parse_funding(Path(path)):
                    funding_rows.append({"symbol": symbol, "dt": stamp, "rate": rate})
            path = paths.get(("klines", symbol, month))
            if path:
                for stamp, close, quote in parse_klines(Path(path)):
                    perp_rows.append({"symbol": symbol, "dt": stamp, "close": close,
                                      "quote_volume": quote})

    funding = pd.DataFrame(funding_rows)
    perp = pd.DataFrame(perp_rows)
    if funding.empty or perp.empty:
        raise RuntimeError("el panel quedó vacío")

    funding["dt"] = pd.to_datetime(funding["dt"], utc=True).dt.floor("D")
    perp["dt"] = pd.to_datetime(perp["dt"], utc=True).dt.floor("D")
    funding = funding.groupby(["symbol", "dt"], as_index=False).agg(rate=("rate", "sum"))
    perp = perp.drop_duplicates(["symbol", "dt"]).sort_values(["symbol", "dt"])
    funding = funding.sort_values(["symbol", "dt"])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    funding_path = OUT_DIR / "funding_daily.csv"
    perp_path = OUT_DIR / "perp_daily.csv"
    funding.to_csv(funding_path, index=False, date_format="%Y-%m-%d")
    perp.to_csv(perp_path, index=False, date_format="%Y-%m-%d")

    coverage = {}
    for symbol in sorted(set(funding["symbol"]) | set(perp["symbol"])):
        f = funding[funding["symbol"] == symbol]
        p = perp[perp["symbol"] == symbol]
        coverage[symbol] = {
            "funding_days": int(len(f)),
            "funding_start": f["dt"].min().strftime("%Y-%m-%d") if len(f) else None,
            "funding_end": f["dt"].max().strftime("%Y-%m-%d") if len(f) else None,
            "perp_days": int(len(p)),
            "perp_start": p["dt"].min().strftime("%Y-%m-%d") if len(p) else None,
            "perp_end": p["dt"].max().strftime("%Y-%m-%d") if len(p) else None,
        }

    def sha(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 20), b""):
                digest.update(chunk)
        return digest.hexdigest()

    freeze = {
        "source": "data.binance.vision futures/um monthly fundingRate + klines 1d",
        "universe": "perpetuos USD-M en USDT fuera de los 20 mayores de H5, con deslistados",
        "excluded_majors": sorted(MAJORS),
        "period": {"start": f"{START}-01", "end": f"{END}-31", "end_exclusive": False},
        "symbols": len(coverage),
        "funding_rows": int(len(funding)),
        "perp_rows": int(len(perp)),
        "funding_sha256": sha(funding_path),
        "perp_sha256": sha(perp_path),
        "fetch_stats": stats,
        "errors": errors[:20],
        "coverage": coverage,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (OUT_DIR / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: freeze[k] for k in ("symbols", "funding_rows", "perp_rows",
                                             "funding_sha256", "perp_sha256", "fetch_stats")},
                     indent=2), flush=True)
    return freeze


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Panel de H10 con deslistados")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--symbols", default="", help="lista separada por comas (prueba)")
    args = parser.parse_args()

    if args.symbols:
        symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    else:
        everything = list_symbols()
        symbols = [
            s for s in everything
            if s.endswith("USDT") and s not in MAJORS
        ]
        ascii_only = [s for s in symbols if s.isascii() and s.isalnum()]
        dropped = len(symbols) - len(ascii_only)
        if dropped:
            print(f"  {dropped} símbolos fuera de [A-Z0-9] descartados", flush=True)
        symbols = ascii_only
        print(f"{len(everything)} símbolos en Vision; {len(symbols)} en el universo H10", flush=True)

    build(symbols, args.workers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
