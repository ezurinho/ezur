"""Congela BTCUSDT perpetuo 5m desde el caché de research.

El caché se alimenta de los archivos públicos de Binance Vision. Los mensuales
solo existen cuando el mes ha terminado; para llegar al último día completo se
completan los días que falten con los archivos diarios. El resultado se escribe
en ``data/btc_5m.pkl`` con el formato que lee el motor y un manifiesto con
filas, cobertura, huecos, duplicados y hashes.

La escritura es atómica y solo ocurre si la validación pasa: un hueco o un
duplicado no se tapan con una fila inventada ni se publican como si el dataset
estuviera limpio.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))
import load_multi  # noqa: E402

ROOT = HERE.parents[1]
CACHE = HERE / "cache" / "btc_5m.pkl"
FROZEN = ROOT / "data" / "btc_5m.pkl"
MANIFEST = ROOT / "data" / "btc_5m.freeze.json"
LOG = ROOT / "data" / "freeze_btc_5m.log"

SYMBOL = "BTCUSDT"
BOT_SYMBOL = "BTCUSDT_PERP"
BAR = pd.Timedelta(minutes=5)
SOURCE = "data.binance.vision futures/um 5m BTCUSDT"
COLD_START = date(2020, 1, 1)


def log(message: str, *, quiet: bool = False) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp} {message}"
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    if not quiet:
        print(line)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_pickle(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    frame.to_pickle(temporary)
    os.replace(temporary, path)


def _atomic_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    os.replace(temporary, path)


def _empty() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "ts",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
            "count",
            "taker_buy_volume",
        ]
    )


def _read_cache() -> pd.DataFrame:
    if not CACHE.is_file():
        return _empty()
    frame = pd.read_pickle(CACHE)
    if "ts" not in frame.columns:
        raise ValueError(f"{CACHE} no trae columna ts")
    frame["ts"] = pd.to_datetime(frame["ts"], utc=True)
    return frame


def _merge(parts: list[pd.DataFrame]) -> tuple[pd.DataFrame, int]:
    if not parts:
        return _empty(), 0
    merged = pd.concat(parts, ignore_index=True)
    merged["ts"] = pd.to_datetime(merged["ts"], utc=True)
    before = len(merged)
    merged = merged.drop_duplicates("ts", keep="last").sort_values("ts")
    merged = merged.reset_index(drop=True)
    return merged, before - len(merged)


def _days(first: date, last: date) -> list[date]:
    if last < first:
        return []
    return [first + timedelta(days=offset) for offset in range((last - first).days + 1)]


def _month_of(day: date) -> str:
    return day.strftime("%Y-%m")


def _month_days(month: str) -> list[date]:
    period = pd.Period(month, freq="M")
    return _days(period.start_time.date(), period.end_time.date())


def _fetch_days(days: list[date]) -> list[pd.DataFrame]:
    if not days:
        return []
    with ThreadPoolExecutor(max_workers=8) as pool:
        parts = list(
            pool.map(
                lambda day: load_multi.fetch_klines_daily(
                    SYMBOL, day.strftime("%Y-%m-%d")
                ),
                days,
            )
        )
    return [part for part in parts if part is not None]


def _collect(cache: pd.DataFrame, end: date) -> tuple[list[pd.DataFrame], list[str]]:
    """Descarga lo que falte entre el final del caché y `end`."""
    parts: list[pd.DataFrame] = []
    missing: list[str] = []
    last = (
        pd.to_datetime(cache["ts"], utc=True).max().date()
        if not cache.empty
        else COLD_START - timedelta(days=1)
    )
    wanted = _days(last + timedelta(days=1), end)
    if not wanted:
        return parts, missing

    by_month: dict[str, list[date]] = {}
    for day in wanted:
        by_month.setdefault(_month_of(day), []).append(day)

    for month, days in sorted(by_month.items()):
        full_month = _month_days(month)
        if days == full_month and month < _month_of(end):
            part = load_multi.fetch_klines(SYMBOL, month)
            if part is not None:
                parts.append(part)
                continue
        fetched = _fetch_days(days)
        if len(fetched) != len(days):
            got = {str(part["ts"].iloc[0].date()) for part in fetched if len(part)}
            missing.extend(
                day.isoformat() for day in days if day.isoformat() not in got
            )
        parts.extend(fetched)
    return parts, missing


def _fill_gaps(frame: pd.DataFrame) -> tuple[pd.DataFrame, list[str], int]:
    """Intenta recuperar huecos con el archivo diario, sin inventar velas."""
    attempted: set[date] = set()
    unrecovered: list[str] = []
    for _ in range(2):
        steps = frame["ts"].diff()
        holes = frame.index[steps > BAR]
        if not len(holes):
            return frame, [], 0
        wanted: list[date] = []
        for index in holes:
            start = frame["ts"].iloc[index - 1].date()
            end = frame["ts"].iloc[index].date()
            for day in _days(start + timedelta(days=1), end):
                if day not in attempted:
                    attempted.add(day)
                    wanted.append(day)
        if not wanted:
            break
        parts = _fetch_days(wanted)
        if not parts:
            break
        frame, _ = _merge([frame, *parts])
    steps = frame["ts"].diff()
    holes = frame.index[steps > BAR]
    unrecovered = [
        f"{frame['ts'].iloc[index - 1]} -> {frame['ts'].iloc[index]}"
        for index in holes
    ]
    return frame, unrecovered, int((steps > BAR).sum())


def _check(frame: pd.DataFrame, end: date) -> dict:
    ts = pd.to_datetime(frame["ts"], utc=True)
    steps = ts.diff().dropna()
    missing_bars = int(((steps // BAR) - 1).clip(lower=0).sum())
    gaps = int((steps > BAR).sum())
    duplicates = int(ts.duplicated().sum())
    bad_ohlc = int(
        (
            (frame["high"] < frame[["open", "close"]].max(axis=1))
            | (frame["low"] > frame[["open", "close"]].min(axis=1))
            | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
            | (frame["volume"] < 0)
        ).sum()
    )
    return {
        "rows": int(len(frame)),
        "first": str(ts.min()),
        "last": str(ts.max()),
        "duplicates": duplicates,
        "gaps": gaps,
        "missing_bars": missing_bars,
        "max_gap_minutes": round(float(steps.max().total_seconds() / 60), 2)
        if len(steps)
        else None,
        "bad_ohlc": bad_ohlc,
        "stale": ts.max().date() < end,
    }


def _frozen(frame: pd.DataFrame) -> pd.DataFrame:
    ts = pd.to_datetime(frame["ts"], utc=True)
    return pd.DataFrame(
        {
            "ts": ts.dt.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
            "symbol": BOT_SYMBOL,
            "o": frame["open"].astype(float),
            "h": frame["high"].astype(float),
            "l": frame["low"].astype(float),
            "c": frame["close"].astype(float),
            "v": frame["volume"].astype(float),
        }
    )


def freeze(end: date, *, quiet: bool = False, dry_run: bool = False) -> int:
    cache = _read_cache()
    original_rows = len(cache)
    parts, missing = _collect(cache, end)
    frame, removed = _merge([cache, *parts]) if parts else (cache, 0)
    frame, unrecovered, gaps = _fill_gaps(frame)

    report = _check(frame, end)
    report["duplicates_removed"] = removed
    report["new_rows"] = len(frame) - original_rows
    report["missing_downloads"] = missing
    report["unrecovered_gaps"] = unrecovered[:10]

    log(
        " ".join(
            [
                f"rows={report['rows']}",
                f"first={report['first']}",
                f"last={report['last']}",
                f"new={report['new_rows']}",
                f"dupes_removed={removed}",
                f"dupes={report['duplicates']}",
                f"gaps={report['gaps']}",
                f"missing_bars={report['missing_bars']}",
                f"bad_ohlc={report['bad_ohlc']}",
            ]
        ),
        quiet=quiet,
    )

    errors = []
    if report["duplicates"]:
        errors.append(f"{report['duplicates']} duplicados")
    if report["gaps"]:
        errors.append(f"{report['gaps']} huecos ({report['missing_bars']} velas)")
    if report["bad_ohlc"]:
        errors.append(f"{report['bad_ohlc']} velas OHLC inválidas")
    if report["stale"]:
        errors.append(f"el último dato {report['last']} no llega a {end}")
    if errors:
        log("ERROR: " + "; ".join(errors) + "; no se escribe el congelado", quiet=quiet)
        return 1

    if dry_run:
        log("dry-run: validación correcta, sin escribir", quiet=quiet)
        return 0

    _atomic_pickle(frame, CACHE)
    frozen = _frozen(frame)
    _atomic_pickle(frozen, FROZEN)
    manifest = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": SOURCE,
        "cutoff": end.isoformat(),
        **report,
        "sha256": _sha256(FROZEN),
        "cache_sha256": _sha256(CACHE),
        "frozen": str(FROZEN.relative_to(ROOT)),
        "cache": str(CACHE.relative_to(ROOT)),
    }
    _atomic_json(manifest, MANIFEST)
    log(
        f"escrito {FROZEN.relative_to(ROOT)} sha256={manifest['sha256'][:16]} "
        f"manifiesto={MANIFEST.relative_to(ROOT)}",
        quiet=quiet,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Congela BTC 5m desde research")
    parser.add_argument(
        "--end",
        default=None,
        help="último día completo UTC (YYYY-MM-DD); por defecto, ayer",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    end = (
        date.fromisoformat(args.end)
        if args.end
        else datetime.now(timezone.utc).date() - timedelta(days=1)
    )
    return freeze(end, quiet=args.quiet, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
