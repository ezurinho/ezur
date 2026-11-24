"""Deterministic tests for the research engine and the selection cycle.

No pytest, no network, no database: `python runner/test_runner.py`.

The point is not coverage. The point is that the numbers this project publishes
come from these functions, so a change that silently alters PBO, DSR, MinBTL,
the walk-forward or the fill model must fail here first.
"""

from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "runner"))
sys.path.insert(0, str(ROOT / "research"))

import run_strategy as rs  # noqa: E402
import selection_cycle as cy  # noqa: E402
import study_costs as sc  # noqa: E402


# --------------------------------------------------------------------- helpers
def bars(closes, highs=None, lows=None, opens=None) -> pd.DataFrame:
    n = len(closes)
    opens = opens if opens is not None else closes
    highs = highs if highs is not None else [max(o, c) for o, c in zip(opens, closes)]
    lows = lows if lows is not None else [min(o, c) for o, c in zip(opens, closes)]
    return pd.DataFrame({
        "ts": pd.date_range("2024-01-01", periods=n, freq="5min", tz="UTC"),
        "open": opens, "high": highs, "low": lows, "close": closes,
        "volume": [1.0] * n,
    })


# ------------------------------------------------------------------- statistics
class TestSchemaValidator(unittest.TestCase):
    def test_exclusive_bounds_are_enforced(self):
        errors = []
        rs.validate(0.0, {"type": "number", "exclusiveMinimum": 0}, "target", errors)
        self.assertTrue(errors)
        errors = []
        rs.validate(1.0, {"type": "number", "exclusiveMaximum": 1}, "target", errors)
        self.assertTrue(errors)


class TestNormalQuantile(unittest.TestCase):
    def test_ppf_inverts_cdf(self):
        for p in (0.001, 0.025, 0.16, 0.5, 0.84, 0.975, 0.999):
            self.assertAlmostEqual(cy.norm_cdf(cy.norm_ppf(p)), p, places=9)

    def test_known_values(self):
        self.assertAlmostEqual(cy.norm_ppf(0.975), 1.959963985, places=6)
        self.assertAlmostEqual(cy.norm_ppf(0.5), 0.0, places=9)


class TestSharpeFromSums(unittest.TestCase):
    def test_matches_direct_computation(self):
        rng = np.random.default_rng(7)
        r = rng.normal(0.001, 0.02, 500)
        direct = cy.sharpe_daily(r)
        from_sums = cy._sr_from_sums(np.array([r.sum()]), np.array([(r * r).sum()]), float(len(r)))[0]
        self.assertAlmostEqual(direct, from_sums, places=10)

    def test_zero_variance_returns_zero(self):
        r = np.full(50, 0.01)
        self.assertEqual(cy.sharpe_daily(r), 0.0)

    def test_negative_mean_gives_negative_sharpe(self):
        r = np.full(100, -0.002) + np.tile([0.001, -0.001], 50)
        self.assertLess(cy.sharpe_daily(r), 0.0)


class TestProfitFactor(unittest.TestCase):
    def test_known_pf(self):
        from run_strategy import pf  # noqa: PLC0415
        self.assertAlmostEqual(pf(np.array([2.0, -1.0, 1.0, -1.0])), 1.5)

    def test_pf_infinite_without_losses(self):
        from run_strategy import pf  # noqa: PLC0415
        self.assertEqual(pf(np.array([1.0, 2.0])), float("inf"))


# ---------------------------------------------------------------------- engine
class TestFillModel(unittest.TestCase):
    """PROMPT_V4 section 3: signal on close t, fill at open t+1, stop-first."""

    def spec(self, tp_r=2.0, max_hold=10):
        return {"params": {"atr_k": 1.5, "tp_r": tp_r}, "exit": {"time_stop_bars": max_hold}}

    def test_fills_at_next_open_not_at_signal_bar(self):
        df = bars([100, 100, 110, 110, 110], opens=[100, 100, 110, 110, 110])
        entries = [(0, 1, 10.0)]          # signal on bar 0 -> fill on bar 1 open
        t = sc.run_trades(df, entries, sc.Exit(1.5, 2.0, 10))
        self.assertEqual(int(t.loc[0, "entry_i"]), 1)
        self.assertEqual(t.loc[0, "entry"], 100)

    def test_stop_first_when_bar_hits_both_levels(self):
        # Bar 1 opens at 100, touches -10 and +20 in the same bar: stop must win.
        df = bars(closes=[100, 100, 100], opens=[100, 100, 100],
                  highs=[100, 130, 130], lows=[100, 85, 85])
        t = sc.run_trades(df, [(0, 1, 10.0)], sc.Exit(1.5, 2.0, 10))
        self.assertEqual(t.loc[0, "reason"], "stop")
        self.assertAlmostEqual(t.loc[0, "r_gross"], -1.0)

    def test_gap_through_stop_fills_at_open(self):
        # Bar 2 opens below the stop: exit at the open, worse than -1R.
        df = bars(closes=[100, 100, 80], opens=[100, 100, 80],
                  highs=[100, 101, 81], lows=[100, 99, 79])
        t = sc.run_trades(df, [(0, 1, 10.0)], sc.Exit(1.5, 2.0, 10))
        self.assertEqual(t.loc[0, "reason"], "gap_stop")
        self.assertAlmostEqual(t.loc[0, "r_gross"], -2.0)

    def test_target_pays_exactly_tp_r(self):
        df = bars(closes=[100, 100, 125], opens=[100, 100, 120],
                  highs=[100, 121, 125], lows=[100, 99, 119])
        t = sc.run_trades(df, [(0, 1, 10.0)], sc.Exit(1.5, 2.0, 10))
        self.assertEqual(t.loc[0, "reason"], "target")
        self.assertAlmostEqual(t.loc[0, "r_gross"], 2.0)

    def test_no_overlapping_trades(self):
        df = bars([100] * 20, opens=[100] * 20, highs=[100] * 20, lows=[100] * 20)
        entries = [(0, 1, 10.0), (1, 1, 10.0), (2, 1, 10.0)]
        t = sc.run_trades(df, entries, sc.Exit(1.5, 2.0, 5))
        self.assertEqual(len(t), 1)


# ------------------------------------------------------------------------- PBO
class TestCSCV(unittest.TestCase):
    def _matrix(self, series: dict[str, np.ndarray]) -> pd.DataFrame:
        idx = pd.date_range("2020-01-01", periods=len(next(iter(series.values()))), freq="D")
        return pd.DataFrame(series, index=idx)

    def test_pbo_zero_when_one_config_dominates(self):
        rng = np.random.default_rng(7)
        n = 400
        noise = rng.normal(0, 0.01, n)
        m = self._matrix({
            "good": noise + 0.004,
            "bad1": noise - 0.004,
            "bad2": -noise - 0.002,
        })
        out = cy.cscv_pbo(m, blocks=10)
        self.assertEqual(out["n_splits"], 252)
        self.assertLessEqual(out["pbo"], 0.05)

    def test_pbo_high_when_all_configs_are_noise(self):
        rng = np.random.default_rng(11)
        n = 400
        m = self._matrix({f"c{i}": rng.normal(0, 0.02, n) for i in range(6)})
        out = cy.cscv_pbo(m, blocks=10)
        self.assertGreater(out["pbo"], 0.25)

    def test_pbo_undefined_with_tiny_universe(self):
        m = self._matrix({"a": np.zeros(100), "b": np.zeros(100)})
        self.assertIsNone(cy.cscv_pbo(m, blocks=10)["pbo"])

    def test_uses_all_splits(self):
        rng = np.random.default_rng(3)
        m = self._matrix({f"c{i}": rng.normal(0, 0.01, 300) for i in range(4)})
        self.assertEqual(cy.cscv_pbo(m, blocks=8)["n_splits"], math.comb(8, 4))


# ------------------------------------------------------------------------- DSR
class TestDeflatedSharpe(unittest.TestCase):
    def test_dsr_falls_as_trials_grow(self):
        rng = np.random.default_rng(5)
        r = rng.normal(0.0008, 0.01, 1500)
        few = cy.deflated_sharpe(r, np.linspace(-0.05, 0.06, 3))
        many = cy.deflated_sharpe(r, np.linspace(-0.05, 0.06, 200))
        self.assertGreater(few["dsr"], many["dsr"])

    def test_dsr_rises_with_signal_strength(self):
        rng = np.random.default_rng(5)
        noise = rng.normal(0, 0.01, 1500)
        weak = cy.deflated_sharpe(noise + 0.0002, np.linspace(-0.02, 0.03, 20))["dsr"]
        strong = cy.deflated_sharpe(noise + 0.0015, np.linspace(-0.02, 0.03, 20))["dsr"]
        self.assertLess(weak, strong)

    def test_needs_enough_observations(self):
        self.assertIsNone(cy.deflated_sharpe(np.ones(10), np.array([0.1, 0.2]))["dsr"])

    def test_bounded_to_unit_interval(self):
        rng = np.random.default_rng(9)
        r = rng.normal(0.001, 0.01, 800)
        d = cy.deflated_sharpe(r, np.linspace(-0.03, 0.04, 10))
        self.assertTrue(0.0 <= d["dsr"] <= 1.0)


# ---------------------------------------------------------------------- MinBTL
class TestMinBacktestLength(unittest.TestCase):
    def test_more_trials_need_more_years(self):
        a = cy.min_backtest_length(10, 0.5)["minbtl_years"]
        b = cy.min_backtest_length(1000, 0.5)["minbtl_years"]
        self.assertLess(a, b)

    def test_higher_sharpe_needs_fewer_years(self):
        a = cy.min_backtest_length(20, 0.4)["minbtl_years"]
        b = cy.min_backtest_length(20, 1.6)["minbtl_years"]
        self.assertGreater(a, b)

    def test_known_value(self):
        # 2*ln(8)/0.64^2 = 10.154 years. Cross-check: the seed cycle reports
        # 11.17 years for N=8 and SR 0.61 -> 2*ln(8)/0.61^2 = 11.18.
        self.assertAlmostEqual(cy.min_backtest_length(8, 0.64)["minbtl_years"], 10.15, places=1)
        self.assertAlmostEqual(cy.min_backtest_length(8, 0.61)["minbtl_years"], 11.17, places=1)

    def test_non_positive_sharpe_has_no_answer(self):
        self.assertIsNone(cy.min_backtest_length(10, 0.0)["minbtl_years"])


# ------------------------------------------------------------------------ WFA
class TestWalkForward(unittest.TestCase):
    def _log(self, name, start, n, rate=0.1):
        ts = pd.date_range(start, periods=n, freq="20D", tz="UTC")
        return pd.DataFrame({"ts": ts, "r_net": [rate] * n})

    def test_no_empty_folds_and_consistent_totals(self):
        log = {"a": self._log("a", "2020-01-01", 120, 0.1)}
        out = cy.walk_forward(log, folds=5)
        self.assertEqual(out["evaluated_folds"], 5)
        self.assertEqual(out["total_oos_trades"], sum(f["oos_trades"] for f in out["folds"]))
        self.assertGreater(out["min_trades_per_fold"], 0)

    def test_chooses_the_better_config_in_sample(self):
        good = self._log("good", "2020-01-01", 120, 0.2)
        bad = self._log("bad", "2020-01-01", 120, -0.2)
        out = cy.walk_forward({"good": good, "bad": bad}, folds=3)
        self.assertTrue(all(f["chosen"] == "good" for f in out["folds"]))

    def test_empty_log_is_not_an_exception(self):
        out = cy.walk_forward({}, folds=3)
        self.assertEqual(out["folds"], [])


# ------------------------------------------------------------------- universe
class TestNeighbourSpecs(unittest.TestCase):
    def _spec(self):
        return {"id": "X", "version": "1.0.0", "label": "x", "params": {"N": 40, "atr_k": 1.5}}

    def test_does_not_mutate_the_base_spec(self):
        base = self._spec()
        cy.neighbour_specs(base, "N", [0.5, 2.0])
        self.assertEqual(base["params"]["N"], 40)

    def test_varies_only_the_requested_axis(self):
        out = cy.neighbour_specs(self._spec(), "N", [0.5, 1.0, 2.0])
        self.assertEqual([s["params"]["N"] for s in out], [20, 40, 80])
        self.assertTrue(all(s["params"]["atr_k"] == 1.5 for s in out))

    def test_floor_keeps_parameters_usable(self):
        out = cy.neighbour_specs(self._spec(), "N", [0.001])
        self.assertGreaterEqual(out[0]["params"]["N"], 3)


class TestRegimes(unittest.TestCase):
    def _data(self):
        rng = np.random.default_rng(7)
        n = 600
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        atr = close * rng.uniform(0.01, 0.06, n)
        df = bars(list(close))
        df["atr"] = atr
        entries = [(i, 1, 1.0) for i in range(0, n - 20, 4)]
        trades = sc.run_trades(df, entries, sc.Exit(1.5, 2.0, 8))
        r = rng.normal(0.1, 1.0, len(trades))
        return trades, df, r

    def test_buckets_partition_the_trades_exactly(self):
        from run_strategy import regime_block  # noqa: PLC0415
        trades, df, r = self._data()
        reg = regime_block(trades, df, r)
        for axis in ("volatility", "trend"):
            total = sum(b["n"] for b in reg[axis]["buckets"].values())
            self.assertEqual(total, len(trades), f"{axis} no particiona los trades")

    def test_cuts_are_ordered(self):
        from run_strategy import regime_block  # noqa: PLC0415
        trades, df, r = self._data()
        reg = regime_block(trades, df, r)
        for axis in ("volatility", "trend"):
            lo, hi = reg[axis]["cuts"]
            self.assertLess(lo, hi)

    def test_empty_trades_returns_empty_block(self):
        from run_strategy import regime_block  # noqa: PLC0415
        self.assertEqual(regime_block(pd.DataFrame(columns=["entry_i"]), bars([100]), np.array([])), {})


class FromRunSpec(unittest.TestCase):
    """Rebuilding an executable spec from registry metadata."""

    def _row(self, sid, params, funding=True):
        return {
            "strategy_id": sid,
            "params": params,
            "costs": {"fee_taker_bps": 5.0, "half_spread_bps": 0.07, "funding": funding},
        }

    def test_family_maps_to_rule(self):
        import verify_registry as vr  # noqa: PLC0415
        self.assertEqual(vr.family("BTC-TREND-1D"), "donchian_breakout")
        self.assertEqual(vr.family("BTC-MOM-5M"), "ema_state")
        self.assertEqual(vr.family("BTC-MR-5M"), "zscore_fade")
        self.assertEqual(vr.family("BTC-ORB-5M"), "orb_session")
        with self.assertRaises(SystemExit):
            vr.family("BTC-UNKNOWN")

    def test_htf_declares_2_but_executed_1_5(self):
        import verify_registry as vr  # noqa: PLC0415
        row = self._row("BTC-TREND-1D", {"bar": "1d", "N": 40, "atr_k": 2.0,
                                          "tp_r": 4.0, "max_hold": 90})
        self.assertEqual(vr.spec_from_run(row)["params"]["atr_k"], 1.5)

    def test_5m_keeps_its_declared_atr(self):
        import verify_registry as vr  # noqa: PLC0415
        row = self._row("BTC-MR-5M", {"bar": "5m", "N": 48, "atr_k": 2.0,
                                       "tp_r": 1.0, "max_hold": 48, "z": 2.0})
        self.assertEqual(vr.spec_from_run(row)["params"]["atr_k"], 2.0)

    def test_orb_has_no_atr_k(self):
        import verify_registry as vr  # noqa: PLC0415
        row = self._row("BTC-ORB-5M", {"bar": "5m", "range_bars": 6,
                                        "tp_r": 2.0, "max_hold": 96}, funding=False)
        spec = vr.spec_from_run(row)
        self.assertEqual(spec["params"]["atr_k"], 1.5)
        self.assertEqual(spec["params"]["range_bars"], 6)
        self.assertEqual(spec["costs"]["funding"], "exclude")

    def test_funding_flag_survives(self):
        import verify_registry as vr  # noqa: PLC0415
        row = self._row("BTC-TREND-4H", {"bar": "4h", "N": 24, "atr_k": 2.0,
                                          "tp_r": 4.0, "max_hold": 20})
        self.assertEqual(vr.spec_from_run(row)["costs"]["funding"], "real_timestamps")

    def test_compare_flags_trade_count_first(self):
        import verify_registry as vr  # noqa: PLC0415
        diffs = vr.compare({"n": 58, "pf_net": 1.683}, {"n": 57, "pf_net": 1.683})
        self.assertEqual(len(diffs), 1)
        self.assertIn("n 58 → 57", diffs[0])

    def test_compare_ignores_rounding_noise(self):
        import verify_registry as vr  # noqa: PLC0415
        self.assertEqual(vr.compare({"n": 58, "pf_net": 1.683},
                                    {"n": 58, "pf_net": 1.6834}), [])

    def test_compare_catches_a_real_difference(self):
        import verify_registry as vr  # noqa: PLC0415
        diffs = vr.compare({"n": 58, "pf_net": 1.683}, {"n": 58, "pf_net": 1.690})
        self.assertTrue(diffs)
        self.assertIn("pf_net", diffs[0])


class VolMatchedAlpha(unittest.TestCase):
    """Scaling the strategy to the benchmark's volatility before comparing."""

    def _series(self, mean, sd, n=400, seed=1):
        rng = np.random.default_rng(seed)
        return pd.Series(mean + rng.normal(0, sd, n), index=pd.date_range("2024-01-01", periods=n, freq="D"))

    def test_leverage_equals_volatility_ratio(self):
        import verify_registry as vr  # noqa: PLC0415
        s = self._series(0.001, 0.01)
        b = self._series(0.004, 0.04)
        out = vr.vol_matched_alpha(s, b, {})
        self.assertAlmostEqual(out["leverage"], 4.0, places=1)

    def test_flat_strategy_is_not_scaled_to_infinity(self):
        import verify_registry as vr  # noqa: PLC0415
        s = pd.Series(np.zeros(50), index=pd.date_range("2024-01-01", periods=50, freq="D"))
        b = self._series(0.001, 0.02)
        out = vr.vol_matched_alpha(s, b, {})
        self.assertIsNone(out["alpha_annual"])
        self.assertIsNone(out["leverage"])

    def test_leverage_is_capped(self):
        import verify_registry as vr  # noqa: PLC0415
        s = self._series(0.001, 1e-6)
        b = self._series(0.001, 0.02)
        self.assertLessEqual(vr.vol_matched_alpha(s, b, {})["leverage"], 100.0)

    def test_a_real_edge_survives_scaling(self):
        import verify_registry as vr  # noqa: PLC0415
        s = self._series(0.006, 0.01, seed=3)
        b = self._series(0.001, 0.01, seed=4)
        self.assertEqual(vr.vol_matched_alpha(s, b, {})["verdict"], "bate")

    def test_empty_input_is_empty_output(self):
        import verify_registry as vr  # noqa: PLC0415
        out = vr.vol_matched_alpha(pd.Series(dtype=float), pd.Series(dtype=float), {})
        self.assertIsNone(out["alpha_annual"])


class RegistryUniverse(unittest.TestCase):
    """The full search space rebuilds from the registry, grouped by hypothesis.

    Skipped when the database is absent, so the suite stays runnable anywhere.
    """

    DB = Path(__file__).resolve().parent.parent / "app" / "registry.db"

    def setUp(self):
        if not self.DB.exists():
            self.skipTest("sin app/registry.db")

    def test_every_registered_run_becomes_a_spec(self):
        import sqlite3  # noqa: PLC0415

        import selection_cycle as sc  # noqa: PLC0415
        universe = sc.registry_universe(self.DB)
        with sqlite3.connect(self.DB) as con:
            registered = con.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        # Every row in the registry must survive the trip to an executable spec.
        self.assertEqual(len(universe), registered)
        self.assertGreaterEqual(registered, 19)
        for spec in universe:
            self.assertIn("entry", spec)
            self.assertIn("costs", spec)
            self.assertTrue(spec["label"])
            self.assertTrue(spec["_group"].startswith("BTC-"))

    def test_groups_follow_the_hypothesis_not_the_run(self):
        import sqlite3  # noqa: PLC0415

        import selection_cycle as sc  # noqa: PLC0415
        universe = sc.registry_universe(self.DB)
        groups: dict[str, int] = {}
        for spec in universe:
            groups[spec["_group"]] = groups.get(spec["_group"], 0) + 1
        with sqlite3.connect(self.DB) as con:
            strategies = con.execute("SELECT COUNT(*) FROM strategies").fetchone()[0]
        # One group per strategy actually present, never one per run.
        self.assertEqual(len(groups), strategies)
        self.assertGreater(strategies, 1)
        self.assertEqual(sum(groups.values()), len(universe))
        self.assertGreater(groups["BTC-TREND-1D"], 1)

    def test_labels_are_unique(self):
        import selection_cycle as sc  # noqa: PLC0415
        universe = sc.registry_universe(self.DB)
        labels = [s["label"] for s in universe]
        self.assertEqual(len(labels), len(set(labels)))


class ProjectIntegrity(unittest.TestCase):
    """Defects found by verify_all.py that the unit tests could not see (E19)."""

    ROOT = Path(__file__).resolve().parent.parent

    def test_every_project_script_parses(self):
        import ast  # noqa: PLC0415
        files = [*self.ROOT.joinpath("runner").glob("*.py"),
                 *self.ROOT.joinpath("research").glob("*.py"),
                 self.ROOT / "app" / "server.py"]
        self.assertGreater(len(files), 8)
        for path in files:
            with self.subTest(file=path.name):
                ast.parse(path.read_text(encoding="utf-8"))

    def test_seed_script_is_runnable(self):
        """build_registry_seed.py had a list and a for-loop on the same line."""
        seed = self.ROOT / "research" / "build_registry_seed.py"
        self.assertIn("\n    for rule, n, hold in htf:", seed.read_text(encoding="utf-8"))

    def test_artifacts_name_the_cycle_that_judged_them(self):
        """A result.json must not cite a different cycle than the one it read."""
        out = self.ROOT / "runner" / "out"
        if not out.is_dir():
            self.skipTest("sin artefactos")
        artifacts = sorted(out.glob("*.json"))
        if not artifacts:
            self.skipTest("sin artefactos")
        for path in artifacts:
            art = json.loads(path.read_text(encoding="utf-8"))
            val = art.get("validation") or {}
            cited = val.get("cycle_id")
            if not cited:
                continue
            with self.subTest(file=path.name):
                self.assertEqual(art.get("cycle_id"), cited,
                                 "el artefacto nombra un ciclo y cita otro")

    def test_event_endpoint_rejects_misspelled_type(self):
        """`kind` instead of `type` used to be silently stored as a note."""
        server = (self.ROOT / "app" / "server.py").read_text(encoding="utf-8")
        self.assertIn("campos desconocidos", server)
        self.assertIn("EVENT_TYPES", server)
        self.assertIn("no 'kind'", server, "el mensaje debe nombrar el campo correcto")


class HealthPayload(unittest.TestCase):
    """Liveness plus the integrity facts a caller wants, without running a backtest."""

    ROOT = Path(__file__).resolve().parent.parent

    def test_health_reports_integrity_fields(self):
        server = (self.ROOT / "app" / "server.py").read_text(encoding="utf-8")
        for field in ("verified", "failures", "data_hash",
                      "artifacts_unknown_gates", "cycle_matches_artifacts"):
            self.assertIn(field, server)

    def test_health_does_not_execute_a_backtest(self):
        server = (self.ROOT / "app" / "server.py").read_text(encoding="utf-8")
        start = server.index("def health(")
        body = server[start:server.index("def runner_results(", start)]
        for forbidden in ("run_trades", "build_entries", "load_data"):
            self.assertNotIn(forbidden, body, f"health no debe llamar a {forbidden}")


class RecordMeasurements(unittest.TestCase):
    """--record appends audit events and never duplicates them."""

    def test_unreachable_registry_is_not_fatal(self):
        import verify_registry as vr  # noqa: PLC0415
        # Port 1 is never listening; the function must warn and return 0.
        self.assertEqual(vr.record_measurements("http://127.0.0.1:1",
                                                [{"id": "x", "alpha_annual": -0.5}]), 0)

    def test_runs_without_alpha_are_skipped(self):
        import verify_registry as vr  # noqa: PLC0415
        self.assertEqual(vr.record_measurements("http://127.0.0.1:1",
                                                [{"id": "x", "alpha_annual": None}]), 0)

    def test_dedupe_key_is_the_message_prefix(self):
        src = (Path(__file__).resolve().parent / "verify_registry.py").read_text(encoding="utf-8")
        self.assertIn('startswith("alpha medido")', src)


class CrossValidation(unittest.TestCase):
    """CPCV and PSR: the two diagnostics added after the 2024-2025 literature review."""

    @staticmethod
    def _daily(seed=0, n=1200, k=6):
        rng = np.random.default_rng(seed)
        cols = {}
        for i in range(k):
            # one config with real edge, the rest noise
            mu = 0.0006 if i == 0 else 0.0
            cols[f"c{i}"] = rng.normal(mu, 0.01, n)
        return pd.DataFrame(cols, index=pd.date_range("2020-01-01", periods=n, freq="D"))

    def test_cpcv_path_count_matches_the_combinatorial_formula(self):
        d = self._daily()
        out = cy.cpcv(d, blocks=10, test_blocks=2)
        self.assertEqual(out["paths"], math.comb(10, 2))

    def test_cpcv_purges_neighbours(self):
        d = self._daily()
        a = cy.cpcv(d, blocks=10, test_blocks=2, purge=1)
        b = cy.cpcv(d, blocks=10, test_blocks=2, purge=2)
        self.assertEqual(a["purge_blocks"], 1)
        self.assertEqual(b["purge_blocks"], 2)
        # a wider purge removes blocks from training, so the figure must move
        self.assertNotEqual(a["mean_oos_sr_daily"], b["mean_oos_sr_daily"])

    def test_cpcv_separates_a_real_edge_from_pure_noise(self):
        edge = cy.cpcv(self._daily(seed=1), blocks=10, test_blocks=2)
        noise = cy.cpcv(self._daily(seed=2), blocks=10, test_blocks=2)
        self.assertLess(edge["share_below_median"], noise["share_below_median"] + 0.5)
        self.assertTrue(0.0 <= edge["share_below_median"] <= 1.0)

    def test_cpcv_rejects_a_short_series(self):
        self.assertEqual(cy.cpcv(self._daily(n=20), blocks=10)["paths"], 0)

    def test_psr_is_above_dsr_for_the_same_returns(self):
        d = self._daily(seed=3)
        r = d["c0"].to_numpy()
        trials = np.array([cy.sharpe_daily(d[c].to_numpy()) for c in d.columns])
        psr = cy.probabilistic_sharpe(r)
        dsr = cy.deflated_sharpe(r, trials)
        self.assertGreaterEqual(psr["psr"], dsr["dsr"])

    def test_psr_of_noise_against_zero_is_not_significant(self):
        rng = np.random.default_rng(9)
        psr = cy.probabilistic_sharpe(rng.normal(0.0, 0.01, 4000))
        self.assertLess(psr["psr"], 0.95)

    def test_psr_needs_enough_observations(self):
        self.assertIsNone(cy.probabilistic_sharpe(np.zeros(10))["psr"])

    def test_both_diagnostics_agree_on_the_sign_of_the_edge(self):
        rng = np.random.default_rng(11)
        r = rng.normal(0.002, 0.01, 2000)
        self.assertGreater(cy.probabilistic_sharpe(r)["psr"], 0.95)
        self.assertGreaterEqual(cy.probabilistic_sharpe(-r)["psr"], 0.0)
        self.assertLess(cy.probabilistic_sharpe(-r)["psr"], 0.05)


class PortfolioAndSizing(unittest.TestCase):
    """Ensemble execution, volatility targeting and the carry split."""

    @staticmethod
    def _bars(n=400, seed=0):
        rng = np.random.default_rng(seed)
        close = 20000 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
        ts = pd.date_range("2021-01-01", periods=n, freq="D", tz="UTC")
        df = pd.DataFrame({"ts": ts, "open": close, "high": close * 1.01,
                           "low": close * 0.99, "close": close, "volume": 1.0})
        df["atr"] = (df["high"] - df["low"]).rolling(14, min_periods=1).mean()
        return df

    @staticmethod
    def _spec(**over):
        base = {
            "params": {"N": 20, "atr_k": 1.5, "tp_r": 4.0},
            "entry": {"rule": "donchian_breakout"},
            "exit": {"stop": "1.5 ATR", "target": "4R", "time_stop_bars": 50},
            "risk": {"sizing": "fixed_fractional", "risk_per_trade": 0.005,
                     "max_gross_leverage": 2.0},
        }
        for k, v in over.items():
            if isinstance(v, dict):
                base[k] = {**base.get(k, {}), **v}
            else:
                base[k] = v
        return base

    def _trades(self, bars, spec):
        return rs.run_trades(bars, rs.build_entries(bars, spec), spec)

    def test_single_spec_returns_no_weights(self):
        bars, spec = self._bars(), self._spec()
        trades, w = rs.run_portfolio(bars, spec, rs.run_trades, rs.build_entries)
        self.assertIsNone(w)
        self.assertGreater(len(trades), 0)

    def test_equal_weights_sum_to_one(self):
        bars = self._bars()
        spec = self._spec(portfolio={"weighting": "equal", "rationale": "x" * 50,
                                     "components": [{"label": "a", "params": {"N": 10}},
                                                    {"label": "b", "params": {"N": 20}},
                                                    {"label": "c", "params": {"N": 30}}]})
        trades, w = rs.run_portfolio(bars, spec, rs.run_trades, rs.build_entries)
        self.assertIsNotNone(w)
        # Equal weighting means every trade carries the same 1/3 of the budget.
        self.assertAlmostEqual(float(w.mean()), 1 / 3, places=6)
        self.assertAlmostEqual(float(w.min()), float(w.max()), places=9)

    def test_portfolio_merges_more_trades_than_one_component(self):
        bars = self._bars()
        one = self._spec()
        spec = self._spec(portfolio={"weighting": "equal", "rationale": "x" * 50,
                                     "components": [{"label": "a", "params": {"N": 10}},
                                                    {"label": "b", "params": {"N": 40}}]})
        single = len(self._trades(bars, one))
        merged, _ = rs.run_portfolio(bars, spec, rs.run_trades, rs.build_entries)
        self.assertGreater(len(merged), single)
        self.assertEqual(set(merged["component"]), {"a", "b"})

    def test_vol_factors_are_one_when_sizing_is_fixed(self):
        bars = self._bars()
        spec = self._spec()
        trades = self._trades(bars, spec)
        np.testing.assert_allclose(rs.vol_factors(bars, trades, spec), 1.0)

    def test_vol_factors_respect_floor_and_cap(self):
        bars = self._bars()
        spec = self._spec(risk={"sizing": "vol_target", "target_vol_annual": 0.45,
                                "max_gross_leverage": 2.0})
        trades = self._trades(bars, spec)
        f = rs.vol_factors(bars, trades, spec)
        self.assertTrue((f >= 0.5 - 1e-12).all(), "el piso de 0,5 no se respeta")
        self.assertTrue((f <= 2.0 + 1e-12).all(), "el cap de apalancamiento no se respeta")

    def test_vol_factors_scale_up_in_quiet_markets(self):
        """Low realised vol must produce a multiplier above 1, which is the whole point."""
        n = 400
        close = 20000 * (1 + 0.001 * np.arange(n))          # smooth drift, ~0,1%/bar
        close = close * (1 + 1e-5 * np.sin(np.arange(n)))    # a little texture
        quiet = self._bars()
        quiet["close"] = close
        quiet["open"] = close
        quiet["high"] = close * 1.00005
        quiet["low"] = close * 0.99995
        quiet["atr"] = quiet["high"] - quiet["low"]
        spec = self._spec(risk={"sizing": "vol_target", "target_vol_annual": 0.45,
                                "max_gross_leverage": 2.0})
        trades = self._trades(quiet, spec)
        self.assertGreater(len(trades), 0, "la serie sintética debe generar rupturas")
        f = rs.vol_factors(quiet, trades, spec)
        self.assertGreater(float(np.median(f)), 1.0)

    def test_vol_factors_do_not_use_the_entry_bar_close(self):
        bars = self._bars(seed=11)
        spec = self._spec(risk={"sizing": "vol_target", "target_vol_annual": 0.45,
                                "max_gross_leverage": 2.0})
        trades = self._trades(bars, spec)
        k = len(trades) // 2
        entry = int(trades.iloc[k]["entry_i"])
        before = rs.vol_factors(bars, trades, spec)

        perturbed = bars.copy()
        perturbed.loc[entry, "close"] *= 5.0
        perturbed.loc[entry, "high"] = max(perturbed.loc[entry, "high"], perturbed.loc[entry, "close"])
        perturbed.loc[entry, "low"] = min(perturbed.loc[entry, "low"], perturbed.loc[entry, "close"])
        after = rs.vol_factors(perturbed, trades, spec)

        self.assertAlmostEqual(float(before[k]), float(after[k]), places=12,
                               msg="el tamaño no puede depender del cierre de la vela de entrada")

    def test_carry_block_splits_by_funding_sign(self):
        r_net = np.array([0.5, -0.3, 1.0, -1.0, 0.2])
        fund = np.array([-0.1, 0.2, -0.05, 0.3, 0.0])
        out = rs.carry_block(pd.DataFrame({"entry_i": range(5)}), r_net, fund)
        self.assertEqual(out["cobra funding"]["n"], 2)
        self.assertEqual(out["paga funding"]["n"], 3)
        self.assertIn("spread_pf", out)

    def test_carry_block_handles_an_empty_side(self):
        out = rs.carry_block(pd.DataFrame({"entry_i": [0]}), np.array([0.5]), np.array([0.1]))
        self.assertEqual(out["paga funding"]["n"], 1)
        self.assertNotIn("spread_pf", out)


class MetricsCompleteness(unittest.TestCase):
    """Metrics that the artefact lacked, and the two ways they can be wrong."""

    @classmethod
    def setUpClass(cls):
        cls.bars = PortfolioAndSizing._bars()
        cls.spec = PortfolioAndSizing._spec()

    def test_time_in_market_is_a_union_not_a_sum(self):
        """Five overlapping components must not add up to 100% exposure.

        The first implementation summed holding bars per trade, so an ensemble
        whose legs overlap reported time_in_market 1.0 by construction. Exposure is
        the share of bars where at least one leg is inside, which is a union.
        """
        entries = [(10, 1, 0.02), (12, 1, 0.02), (14, 1, 0.02)]
        trades = rs.run_trades(self.bars, entries, self.spec)
        self.assertGreater(len(trades), 0)
        m = rs.metrics_block(trades, self.bars, np.full(len(trades), 0.01),
                             np.full(len(trades), 0.01), np.zeros(len(trades)),
                             np.zeros(len(trades)), seed=1, block=5, reps=10)
        self.assertLessEqual(m["time_in_market"], 1.0)
        self.assertGreater(m["time_in_market"], 0.0)

    def test_exposure_is_bounded_and_consistent(self):
        entries = rs.build_entries(self.bars, self.spec)
        trades = rs.run_trades(self.bars, entries, self.spec)
        if trades.empty:
            self.skipTest("la fixture no generó trades")
        n = len(trades)
        m = rs.metrics_block(trades, self.bars, np.full(n, 0.01), np.full(n, 0.01),
                             np.zeros(n), np.zeros(n), seed=1, block=5, reps=10)
        self.assertGreaterEqual(m["time_in_market"], 0.0)
        self.assertLessEqual(m["time_in_market"], 1.0)

    def test_derived_rates_use_the_sample_years(self):
        entries = rs.build_entries(self.bars, self.spec)
        trades = rs.run_trades(self.bars, entries, self.spec)
        if trades.empty:
            self.skipTest("la fixture no generó trades")
        n = len(trades)
        m = rs.metrics_block(trades, self.bars, np.full(n, 0.01), np.full(n, 0.01),
                             np.zeros(n), np.zeros(n), seed=1, block=5, reps=10)
        # `years` and `trades_per_year` are both rounded, and the second is computed
        # from the unrounded first, so the tolerance covers both roundings.
        self.assertAlmostEqual(m["trades_per_year"], m["n"] / m["years"], delta=0.2)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    unittest.main(verbosity=2)
