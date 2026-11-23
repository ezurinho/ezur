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
from pathlib import Path
from typing import Any

from .config import Settings, load_settings
from .env import env
from .market.okx import MAX_LIMIT, OKXFeed
from .models import Bar

HEADER = ["ts", "symbol", "o", "h", "l", "c", "v"]


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

    args = parser.parse_args()
    if args.command == "list":
        for item in list_datasets(args.dir):
            print(item)
        return

    settings = load_settings(args.config)
    path = pull(settings, bars=args.bars, output=args.out)
    with path.open(encoding="utf-8") as handle:
        rows = sum(1 for _ in handle) - 1
    print(f"{path} · {rows} filas · {len(settings.instruments.enabled)} instrumentos")


if __name__ == "__main__":
    main()
