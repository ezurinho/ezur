from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from itertools import islice

import pytest

from server.config import InstrumentConfig, InstrumentsConfig, Settings
from server.main import build_feed
from server.market import synthetic
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


def test_simulated_feed_uses_reference_price_per_symbol():
    tick = next(
        SimulatedFeed(
            "2026-01-15",
            ["AAA", "BBB"],
            tick_size=0.01,
            reference_prices={"AAA": 60_000, "BBB": 0.01},
        ).iter_ticks()
    )
    assert tick.bars["AAA"].o == pytest.approx(60_000, abs=0.02)
    assert tick.bars["BBB"].o == pytest.approx(0.01, abs=0.0001)


def test_simulated_feed_uses_tick_size_per_symbol():
    tick = next(
        SimulatedFeed(
            "2026-01-15",
            ["AAA", "BBB"],
            tick_size=0.25,
            tick_sizes={"AAA": 0.01, "BBB": 0.5},
            reference_prices={"AAA": 100.03, "BBB": 100.03},
        ).iter_ticks()
    )
    assert tick.bars["AAA"].o == pytest.approx(100.03)
    assert tick.bars["BBB"].o == pytest.approx(100.0)


def test_build_feed_propagates_each_instrument_tick_size():
    settings = Settings()
    settings.feed.provider = "simulated"
    settings.instruments = InstrumentsConfig(
        items=[
            InstrumentConfig(symbol="AAA", role="primary", tick_size=0.01, reference_price=100.03),
            InstrumentConfig(symbol="BBB", tick_size=0.5, reference_price=100.03),
        ],
        primary="AAA",
    )
    tick = next(build_feed(settings).iter_ticks())
    assert tick.bars["AAA"].o == pytest.approx(100.03)
    assert tick.bars["BBB"].o == pytest.approx(100.0)


def test_simulated_feed_tick_map_falls_back_to_the_global_tick():
    tick = next(
        SimulatedFeed(
            "2026-01-15",
            ["AAA", "BBB"],
            tick_size=0.5,
            tick_sizes={"AAA": 0.01},
            reference_prices={"AAA": 100.03, "BBB": 100.03},
        ).iter_ticks()
    )
    assert tick.bars["AAA"].o == pytest.approx(100.03)
    assert tick.bars["BBB"].o == pytest.approx(100.0)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), None, "0.01"])
def test_simulated_feed_rejects_invalid_tick_metadata_at_construction(value):
    with pytest.raises(ValueError, match="tick_size"):
        SimulatedFeed("2026-01-15", ["AAA"], tick_sizes={"AAA": value})


def test_tick_timestamps_are_monotonic():
    ticks = list(islice(SimulatedFeed("2026-01-15", ["PRIMARY"]).iter_ticks(), 20))
    stamps = [tick.ts for tick in ticks]
    assert stamps == sorted(stamps)


def test_synthetic_bars_can_use_the_instrument_reference_price():
    bars = synthetic.generate_session(
        "2026-01-15",
        "BTC",
        start=datetime(2026, 1, 15, tzinfo=timezone.utc),
        bars=3,
        tick_size=0.01,
        reference_price=60_000,
    )
    assert bars[0].o == pytest.approx(60_000, abs=0.02)
    assert bars[0].h >= bars[0].o
    assert bars[0].l <= bars[0].o


def test_synthetic_volatility_scales_with_the_reference_price():
    bars = synthetic.generate_session(
        "2026-01-15",
        "BTC",
        start=datetime(2026, 1, 15, tzinfo=timezone.utc),
        bars=20,
        tick_size=0.01,
        reference_price=60_000,
    )
    assert max(bar.h - bar.l for bar in bars) > 1.0


def test_default_synthetic_series_keeps_its_legacy_scale():
    bars = synthetic.generate_session(
        "2026-01-15",
        "PRIMARY",
        start=datetime(2026, 1, 15, tzinfo=timezone.utc),
        bars=1,
    )
    bar = bars[0]
    assert (bar.o, bar.h, bar.l, bar.c) == pytest.approx(
        (79.5, 79.594175, 79.282097, 79.425157), abs=1e-6
    )
    assert bar.v == 124


def test_reference_price_below_one_tick_never_generates_a_zero_open():
    bars = synthetic.generate_session(
        "2026-01-15",
        "CHEAP",
        start=datetime(2026, 1, 15, tzinfo=timezone.utc),
        bars=1,
        tick_size=0.25,
        reference_price=0.001,
    )
    assert bars[0].o == pytest.approx(0.25)
    assert bars[0].c >= 0.25


def test_tiny_tick_sizes_survive_price_rounding():
    bars = synthetic.generate_session(
        "2026-01-15",
        "TINY",
        start=datetime(2026, 1, 15, tzinfo=timezone.utc),
        bars=1,
        tick_size=1e-7,
        reference_price=1e-9,
    )
    assert bars[0].o >= 1e-7
    assert bars[0].h >= bars[0].o
    assert bars[0].l > 0
    assert bars[0].c >= 1e-7


def test_unrepresentable_tick_size_is_rejected():
    with pytest.raises(ValueError, match="tick_size"):
        synthetic.generate_session(
            "2026-01-15",
            "TINY",
            start=datetime(2026, 1, 15, tzinfo=timezone.utc),
            bars=1,
            tick_size=1e-16,
            reference_price=1e-16,
        )


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
