"""Datasets on disk: pull real candles from the venue and write them as CSV.

The backtest engine reads CSV; the terminal should not require a separate
download script. ``python -m server.datasets pull`` asks the active profile's
venue for candles, aligns them and writes the exact format the validator
expects: ``ts,symbol,o,h,l,c,v`` oldest first.

Synthetic candles stay available for tests, but a dataset pulled from a venue is
the only kind that can support a real verdict.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .env import env
from .market.okx import MAX_LIMIT, OKXFeed
from .models import Bar

HEADER = ["ts", "symbol", "o", "h", "l", "c", "v"]


def _bucket(stamp: datetime, rule: str) -> datetime:
    if rule == "1D":
        return stamp.replace(hour=0, minute=0, second=0, microsecond=0)
    if rule == "4H":
        return stamp.replace(hour=(stamp.hour // 4) * 4, minute=0, second=0, microsecond=0)
    if rule == "15m":
        return stamp.replace(minute=(stamp.minute // 15) * 15, second=0, microsecond=0)
    if rule == "1H":
        return stamp.replace(minute=0, second=0, microsecond=0)
    raise ValueError(f"regla no soportada: {rule!r} (usa 15m, 1H, 4H o 1D)")


def resample(source: Path | str, output: Path | str, rule: str = "1D") -> dict[str, Any]:
    """Agrega velas por cubo UTC: un cubo por (símbolo, intervalo).

    El fichero puede traer los símbolos intercalados vela a vela —es lo que
    escribe `write_dataset`—, así que comparar con la fila anterior no agrega
    nada: cada fila sería su propio cubo. Se acumula un cubo por clave y se
    vuelca al final; para 1 m a 1 h o 1 D son decenas de miles de claves, no
    millones de velas.
    """
    src = Path(source)
    dst = Path(output)
    dst.parent.mkdir(parents=True, exist_ok=True)
    buckets: dict[tuple[str, str], list[float]] = {}

    with src.open(encoding="utf-8", newline="") as fin:
        for row in csv.DictReader(fin):
            stamp = datetime.fromisoformat(row["ts"])
            key = (row["symbol"], _bucket(stamp, rule).isoformat())
            price = float(row["c"])
            volume = float(row["v"])
            bucket = buckets.get(key)
            if bucket is None:
                buckets[key] = [
                    float(row["o"]),
                    float(row["h"]),
                    float(row["l"]),
                    price,
                    volume,
                ]
            else:
                bucket[1] = max(bucket[1], float(row["h"]))
                bucket[2] = min(bucket[2], float(row["l"]))
                bucket[3] = price
                bucket[4] += volume

    ordered = sorted(buckets, key=lambda item: (item[1], item[0]))
    with dst.open("w", encoding="utf-8", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(HEADER)
        for key in ordered:
            o, h, low, c, v = buckets[key]
            writer.writerow([key[1], key[0], o, h, low, c, v])

    first = ordered[0][1] if ordered else None
    last = ordered[-1][1] if ordered else None
    return {"path": str(dst), "rows": len(ordered), "first": first, "last": last}


def data_dir() -> Path:
    """`EZUR_DATA_DIR` wins, then `data/`, then the working directory."""
    configured = env("DATA_DIR")
    if configured:
        return Path(configured)
    root = Path("data")
    return root if root.is_dir() else Path(".")


def list_datasets(directory: Path | str | None = None) -> list[str]:
    target = Path(directory) if directory is not None else data_dir()
    if not target.exists():
        return []
    return sorted(path.as_posix() for path in target.glob("*.csv"))


def write_dataset(path: Path | str, series: dict[str, list[Bar]]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    stamps = sorted({bar.t for bars in series.values() for bar in bars})
    aligned = {symbol: {bar.t: bar for bar in bars} for symbol, bars in series.items()}
    with target.open("w", newline="", encoding="utf-8") as handle:
        handle.write(",".join(HEADER) + "\n")
        for stamp in stamps:
            if not all(stamp in bars for bars in aligned.values()):
                continue
            for symbol, bars in aligned.items():
                bar = bars[stamp]
                handle.write(
                    f"{bar.t.isoformat()},{symbol},{bar.o},{bar.h},{bar.l},{bar.c},{bar.v}\n"
                )
    return target


def pull(
    settings: Settings,
    *,
    bars: int = 600,
    output: Path | str | None = None,
) -> Path:
    """Fetch `bars` one-minute candles for every enabled instrument."""
    instruments = list(settings.instruments.enabled)
    if not instruments:
        raise ValueError("el perfil no tiene instrumentos habilitados")
    symbols = {item.symbol: item.venue_symbol or item.symbol for item in instruments}
    feed = OKXFeed(symbols, bars=min(bars, MAX_LIMIT))

    collected: dict[str, list[Bar]] = {symbol: [] for symbol in symbols}
    cursor: str | None = None
    remaining = bars
    while remaining > 0:
        chunk = feed.fetch(min(remaining, MAX_LIMIT), after=cursor)
        if not chunk or all(not value for value in chunk.values()):
            break
        for symbol, rows in chunk.items():
            collected[symbol].extend(rows)
        oldest = min(rows[0].t for rows in chunk.values() if rows)
        cursor = str(int(oldest.timestamp() * 1000))
        remaining -= max(len(rows) for rows in chunk.values())

    # De-duplicar por minuto: la paginación de OKX repite el borde.
    deduped: dict[str, list[Bar]] = {}
    for symbol, rows in collected.items():
        seen: dict[Any, Bar] = {bar.t: bar for bar in rows}
        deduped[symbol] = [seen[stamp] for stamp in sorted(seen)]

    target = Path(output) if output is not None else data_dir() / "dataset_1m.csv"
    return write_dataset(target, deduped)


def main() -> None:
    parser = argparse.ArgumentParser(description="Datasets de velas para backtest")
    sub = parser.add_subparsers(dest="command", required=True)

    pull_cmd = sub.add_parser("pull", help="descarga velas 1m del venue del perfil")
    pull_cmd.add_argument("--bars", type=int, default=600)
    pull_cmd.add_argument("--out", default=None, help="ruta del CSV de salida")
    pull_cmd.add_argument("--config", default=None, help="config.json alternativo")

    list_cmd = sub.add_parser("list", help="lista los CSV disponibles")
    list_cmd.add_argument("--dir", default=None)

    vision_cmd = sub.add_parser("vision", help="descarga velas históricas de Binance Vision")
    vision_cmd.add_argument("--symbol", default="BTCUSDT")
    vision_cmd.add_argument("--bot-symbol", default="BTC")
    vision_cmd.add_argument("--interval", default="1m")
    vision_cmd.add_argument("--market", default="spot", choices=["spot", "um"])
    vision_cmd.add_argument("--start", required=True, help="YYYY-MM")
    vision_cmd.add_argument("--end", required=True, help="YYYY-MM")
    vision_cmd.add_argument("--out", default="data/BTC_1m_binance.csv")
    vision_cmd.add_argument("--cache", default="data/vision")

    resample_cmd = sub.add_parser("resample", help="agrega un CSV a 1H/4H/1D")
    resample_cmd.add_argument("--in", dest="source", required=True)
    resample_cmd.add_argument("--out", required=True)
    resample_cmd.add_argument("--rule", default="1D", choices=["15m", "1H", "4H", "1D"])

    args = parser.parse_args()
    if args.command == "list":
        for item in list_datasets(args.dir):
            print(item)
        return

    if args.command == "vision":
        from .market import binance_vision

        def report(month: str, count: int, total: int, state: str) -> None:
            print(f"{month} · {count:>6} velas · {state} · total {total}", flush=True)

        result = binance_vision.build(
            args.out,
            args.cache,
            binance_vision.months(args.start, args.end),
            bot_symbol=args.bot_symbol,
            symbol=args.symbol,
            interval=args.interval,
            market=args.market,
            report=report,
        )
        print(
            f"{result['path']} · {result['rows']} filas · {result['first']} -> {result['last']}"
        )
        return

    if args.command == "resample":
        result = resample(args.source, args.out, args.rule)
        print(f"{result['path']} · {result['rows']} filas · {result['first']} -> {result['last']}")
        return

    settings = load_settings(args.config)
    path = pull(settings, bars=args.bars, output=args.out)
    with path.open(encoding="utf-8") as handle:
        rows = sum(1 for _ in handle) - 1
    print(f"{path} · {rows} filas · {len(settings.instruments.enabled)} instrumentos")


if __name__ == "__main__":
    main()
