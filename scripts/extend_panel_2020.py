"""Panel extendido 2020-2026 con el funding normalizado por intervalo.

Reutiliza el descargador de H10 (`scripts/fetch_h10_data.py`) para bajar sólo el
funding de 2020-01 a 2022-12 —los meses que el panel congelado no tiene— y
reconstruye el panel completo leyendo de la caché existente los meses 2023-2026.

Escribe en `data/h10ext/`, así que **no toca el panel congelado de H10 ni sus
hashes**. Tres medidas por símbolo y día:

- `rate`: suma de las tasas del día. Es el coste real en fracción del nocional:
  cada evento cobra su tasa, sin importar cuántos haya.
- `rate8h`: suma de `tasa × 8 / intervalo`. Es la convención de H5 y **duplica el
  funding de un símbolo con intervalo de 4 h** (multiplica cada evento por 2
  cuando además hay el doble de eventos).
- `interval_h`: mediana de los intervalos del día.

Uso:
    python scripts/extend_panel_2020.py --workers 32
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_h10_data as f10  # noqa: E402

OUT_DIR = ROOT / "data" / "h10ext"
CACHE = OUT_DIR / "cache"
BASE_CACHE = ROOT / "data" / "h10" / "cache"
EXT_START = "2020-01"
EXT_END = "2022-12"


def parse_events(path: Path) -> list[tuple[str, float, float]]:
    """(fecha, tasa, intervalo en horas) de un ZIP mensual de fundingRate."""
    rows: list[tuple[str, float, float]] = []
    with zipfile.ZipFile(path) as archive:
        raw = archive.read(archive.namelist()[0]).decode("utf-8", "replace")
    for line in raw.splitlines():
        parts = line.strip().split(",")
        if len(parts) < 3:
            continue
        try:
            stamp = f10._stamp(int(float(parts[0])))
            interval = float(parts[1])
            rate = float(parts[2])
        except (ValueError, OverflowError):
            continue
        if interval <= 0:
            continue
        rows.append((stamp, rate, interval))
    return rows


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Panel extendido con intervalo")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--klines", action="store_true",
                        help="baja también las velas 1d de 2020-2022")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    f10.CACHE = CACHE

    symbols = [
        s for s in f10.list_symbols()
        if s.endswith("USDT") and s.isascii() and s.isalnum() and s not in f10.MAJORS
    ]
    ext_months = f10.months(EXT_START, EXT_END)
    old_months = f10.months("2023-01", "2026-10")
    print(f"{len(symbols)} símbolos · {len(ext_months)} meses nuevos · "
          f"{len(symbols) * len(ext_months)} ficheros de funding", flush=True)

    jobs = [(symbol, month, kind) for symbol in symbols for month in ext_months
            for kind in ("funding",) if not args.klines]
    if args.klines:
        jobs = [(symbol, month, kind) for symbol in symbols for month in ext_months
                for kind in ("funding", "klines")]
    stats = {"downloaded": 0, "cached": 0, "missing": 0, "badsum": 0, "error": 0}

    def run(job: tuple[str, str, str]) -> tuple[tuple[str, str, str], str]:
        state, _path, _error = f10.fetch_one(job[2], job[0], job[1])
        return job, state

    done = 0
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for _job, state in pool.map(run, jobs):
            done += 1
            stats[state] += 1
            if done % 2000 == 0:
                elapsed = time.perf_counter() - started
                print(f"  {done}/{len(jobs)} · {done / elapsed:.0f}/s · {stats}", flush=True)

    perp_records: list[dict] = []
    if args.klines:
        for symbol in symbols:
            for month in ext_months:
                path = CACHE / "klines" / f"{symbol}-{month}.zip"
                if path.is_file():
                    for stamp, close, quote in f10.parse_klines(path):
                        perp_records.append({"symbol": symbol, "dt": stamp, "close": close,
                                             "quote_volume": quote})
            for month in old_months:
                path = BASE_CACHE / "klines" / f"{symbol}-{month}.zip"
                if path.is_file():
                    for stamp, close, quote in f10.parse_klines(path):
                        perp_records.append({"symbol": symbol, "dt": stamp, "close": close,
                                             "quote_volume": quote})

    records: list[dict] = []
    for symbol in symbols:
        for month in ext_months:
            path = CACHE / "funding" / f"{symbol}-{month}.zip"
            if path.is_file():
                for stamp, rate, interval in parse_events(path):
                    records.append({"symbol": symbol, "dt": stamp, "rate": rate,
                                    "interval_h": interval})
        for month in old_months:
            path = BASE_CACHE / "funding" / f"{symbol}-{month}.zip"
            if path.is_file():
                for stamp, rate, interval in parse_events(path):
                    records.append({"symbol": symbol, "dt": stamp, "rate": rate,
                                    "interval_h": interval})

    events = pd.DataFrame(records)
    if events.empty:
        raise SystemExit("sin eventos de funding")
    events["dt"] = pd.to_datetime(events["dt"], utc=True).dt.floor("D")
    events["rate8h"] = events["rate"] * 8.0 / events["interval_h"].clip(lower=1)

    daily = events.groupby(["symbol", "dt"], as_index=False).agg(
        rate=("rate", "sum"),
        rate8h=("rate8h", "sum"),
        interval_h=("interval_h", "median"),
        eventos=("rate", "size"),
    ).sort_values(["symbol", "dt"])

    path = OUT_DIR / "funding_daily.csv"
    daily.to_csv(path, index=False, date_format="%Y-%m-%d")

    digest = hashlib.sha256(path.read_bytes()).hexdigest()

    perp = pd.DataFrame(perp_records)
    perp_sha = None
    if not perp.empty:
        perp["dt"] = pd.to_datetime(perp["dt"], utc=True).dt.floor("D")
        perp = perp.drop_duplicates(["symbol", "dt"]).sort_values(["symbol", "dt"])
        perp_path = OUT_DIR / "perp_daily.csv"
        perp.to_csv(perp_path, index=False, date_format="%Y-%m-%d")
        perp_sha = hashlib.sha256(perp_path.read_bytes()).hexdigest()

    freeze = {
        "source": "data.binance.vision futures/um monthly fundingRate",
        "universe": "perpetuos USD-M en USDT fuera de los 20 mayores de H5",
        "period": {"start": f"{EXT_START}-01", "end": "2026-10-31"},
        "symbols": int(daily["symbol"].nunique()),
        "rows": int(len(daily)),
        "events": int(len(events)),
        "perp_rows": int(len(perp)),
        "funding_sha256": digest,
        "perp_sha256": perp_sha,
        "events_per_year": {
            str(year): int(len(group)) for year, group in events.groupby(events["dt"].dt.year)
        },
        "fetch_stats": stats,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    (OUT_DIR / "freeze.json").write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: freeze[k] for k in ("symbols", "rows", "events", "perp_rows",
                                             "funding_sha256", "perp_sha256",
                                             "events_per_year", "fetch_stats")}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
