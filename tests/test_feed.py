from __future__ import annotations

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
