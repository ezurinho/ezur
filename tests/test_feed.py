from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from itertools import islice

import pytest

from server.market.feed import CSVFeed, LiveFeed, SimulatedFeed


def test_synthetic_feed_is_deterministic_for_same_date():
    first = list(
        islice(SimulatedFeed("2026-01-15", ["PRIMARY", "CTX_A"]).iter_ticks(), 50)
    )
    second = list(
        islice(SimulatedFeed("2026-01-15", ["PRIMARY", "CTX_A"]).iter_ticks(), 50)
    )
    assert first == second


def test_different_dates_produce_different_data():
    first = list(islice(SimulatedFeed("2026-01-15", ["PRIMARY"]).iter_ticks(), 5))
    second = list(islice(SimulatedFeed("2026-01-16", ["PRIMARY"]).iter_ticks(), 5))
    assert first != second


def test_feed_emits_tick_keyed_by_configured_symbols():
    tick = next(SimulatedFeed("2026-01-15", ["AAA", "BBB"]).iter_ticks())
    assert set(tick.bars) == {"AAA", "BBB"}
    assert tick.bars["AAA"].h >= tick.bars["AAA"].l


def test_tick_timestamps_are_monotonic():
    ticks = list(islice(SimulatedFeed("2026-01-15", ["PRIMARY"]).iter_ticks(), 20))
    stamps = [tick.ts for tick in ticks]
    assert stamps == sorted(stamps)


def test_live_feed_without_adapter_raises():
    with pytest.raises(NotImplementedError):
        next(LiveFeed().iter_ticks())


def test_csv_feed_requires_existing_file(tmp_path):
    feed = CSVFeed(tmp_path / "missing.csv", ["PRIMARY"])
    with pytest.raises(FileNotFoundError):
        next(feed.iter_ticks())


def test_csv_feed_yields_only_complete_ticks(dataset_path):
    ticks = list(CSVFeed(dataset_path, ["PRIMARY"]).iter_ticks())
    assert len(ticks) == 60
    assert set(ticks[0].bars) == {"PRIMARY"}

def _write_csv(path, rows) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ts", "symbol", "o", "h", "l", "c", "v"])
        writer.writerows(rows)


def test_csv_feed_emits_multi_symbol_ticks_in_streaming(tmp_path):
    start = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    rows = []
    for index in range(3):
        stamp = (start + timedelta(minutes=index)).isoformat()
        for symbol in ("AAA", "BBB"):
            rows.append([stamp, symbol, 100, 101, 99, 100.5, 1])
    path = tmp_path / "dos.csv"
    _write_csv(path, rows)

    ticks = list(CSVFeed(path, ["AAA", "BBB"]).iter_ticks())

    assert len(ticks) == 3
    assert all(set(tick.bars) == {"AAA", "BBB"} for tick in ticks)


def test_csv_feed_rejects_an_unsorted_dataset(tmp_path):
    start = datetime(2026, 1, 15, 14, 30, tzinfo=timezone.utc)
    path = tmp_path / "desordenado.csv"
    _write_csv(
        path,
        [
            [(start + timedelta(minutes=1)).isoformat(), "AAA", 100, 101, 99, 100.5, 1],
            [start.isoformat(), "AAA", 100, 101, 99, 100.5, 1],
        ],
    )

    with pytest.raises(ValueError, match="no ordenado"):
        list(CSVFeed(path, ["AAA"]).iter_ticks())
