"""Tests for the maker fill model. No network, no database.

Run from the research_engine directory:
    .venv/Scripts/python.exe runner/test_maker_fills.py
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "research"))

from maker_fills import MakerFillConfig, try_maker_fill  # noqa: E402


def bars(rows: list[tuple[float, float, float, float, float, float]]) -> pd.DataFrame:
    start = pd.Timestamp("2024-01-01T00:00:00Z")
    return pd.DataFrame(
        {
            "ts": [start + pd.Timedelta(minutes=5 * i) for i in range(len(rows))],
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [r[4] for r in rows],
            "taker_buy_volume": [r[5] for r in rows],
        }
    )


START = pd.Timestamp("2024-01-01T00:00:00Z")


class TestMakerFills(unittest.TestCase):
    def test_no_touch_does_not_fill(self):
        frame = bars([(100.2, 100.5, 100.1, 100.4, 1000, 400)])
        result = try_maker_fill(
            frame, START, "long", 100.0, MakerFillConfig(order_notional_usd=1000)
        )
        self.assertFalse(result.filled)
        self.assertEqual(result.reason, "no_touch")
        self.assertEqual(result.touch_bars, 0)

    def test_gap_through_the_limit_is_not_a_passive_fill(self):
        frame = bars([(99.5, 99.9, 99.4, 99.8, 1000, 400)])
        result = try_maker_fill(
            frame, START, "long", 100.0, MakerFillConfig(order_notional_usd=1000)
        )
        self.assertFalse(result.filled)
        self.assertEqual(result.reason, "gap_through_limit")
        self.assertEqual(result.gap_bars, 1)

    def test_queue_can_block_a_touch(self):
        frame = bars([(100.2, 100.5, 99.9, 99.8, 1000, 400)])
        result = try_maker_fill(
            frame,
            START,
            "long",
            100.0,
            MakerFillConfig(queue_fraction=0.5, order_notional_usd=100_000),
        )
        self.assertFalse(result.filled)
        self.assertEqual(result.reason, "queue")
        self.assertLess(result.best_fraction, 1.0)

    def test_adverse_rebound_can_block_a_fill(self):
        frame = bars([(100.2, 101.0, 99.9, 100.9, 1000, 400)])
        result = try_maker_fill(
            frame,
            START,
            "long",
            100.0,
            MakerFillConfig(
                queue_fraction=0.0,
                order_notional_usd=1000,
                adverse_rebound_bps=10,
                rebound_penalty=1.0,
            ),
        )
        self.assertFalse(result.filled)
        self.assertEqual(result.reason, "adverse_rebound")
        self.assertGreater(result.favorable_bps, 0)

    def test_adverse_close_fills_at_the_limit(self):
        frame = bars([(100.2, 100.5, 99.9, 99.8, 1000, 400)])
        result = try_maker_fill(
            frame,
            START,
            "long",
            100.0,
            MakerFillConfig(
                queue_fraction=0.0,
                order_notional_usd=1000,
                adverse_rebound_bps=10,
                rebound_penalty=1.0,
            ),
        )
        self.assertTrue(result.filled)
        self.assertEqual(result.reason, "filled")
        self.assertEqual(result.fill_price, 100.0)
        self.assertEqual(result.fill_ts, START)
        self.assertEqual(result.fill_fraction, 1.0)

    def test_short_side_mirrors_the_model(self):
        frame = bars([(99.8, 100.2, 99.5, 100.1, 1000, 700)])
        result = try_maker_fill(
            frame,
            START,
            "short",
            100.0,
            MakerFillConfig(
                queue_fraction=0.0,
                order_notional_usd=1000,
                adverse_rebound_bps=10,
                rebound_penalty=1.0,
            ),
        )
        self.assertTrue(result.filled)
        self.assertEqual(result.fill_price, 100.0)

    def test_no_adverse_penalty_is_an_upper_bound(self):
        frame = bars([(100.2, 101.0, 99.9, 100.9, 1000, 400)])
        result = try_maker_fill(
            frame,
            START,
            "long",
            100.0,
            MakerFillConfig(
                queue_fraction=0.0,
                order_notional_usd=1000,
                adverse_rebound_bps=10,
                rebound_penalty=0.0,
            ),
        )
        self.assertTrue(result.filled)

    def test_wait_window_excludes_later_bars(self):
        frame = bars(
            [
                (100.2, 100.4, 100.1, 100.3, 1000, 400),
                (100.2, 100.4, 99.9, 99.8, 1000, 400),
            ]
        )
        # The requested start is after every bar in the frame: no execution
        # data inside the wait window.
        result = try_maker_fill(
            frame,
            START + pd.Timedelta(hours=1),
            "long",
            100.0,
            MakerFillConfig(order_notional_usd=1000),
        )
        self.assertFalse(result.filled)
        self.assertEqual(result.reason, "no_data")

    def test_deterministic(self):
        frame = bars([(100.2, 100.5, 99.9, 99.8, 1000, 400)])
        config = MakerFillConfig(order_notional_usd=1000)
        first = try_maker_fill(frame, START, "long", 100.0, config)
        second = try_maker_fill(frame, START, "long", 100.0, config)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main(verbosity=2)
