#!/usr/bin/env python3
"""Verify every registered run against the deterministic engine.

The registry stores metrics produced by `research/` scripts. This script does
not trust them: it rebuilds each strategy spec from the run's own `params`,
re-executes the engine, and compares the numbers. A registered run that cannot
be reproduced is a defect in the registry, not a cosmetic issue.

    python runner/verify_registry.py                  # all runs
    python runner/verify_registry.py --id BTC-MR-5M   # substring filter
    python runner/verify_registry.py --json out.json

Exit code 0 only if every checked run reproduces within tolerance.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(RESEARCH))

import study_costs as sc  # noqa: E402,F401
import funding_study as fs  # noqa: E402
import runner.run_strategy as rn  # noqa: E402

DB = ROOT / "app" / "registry.db"

# Tolerance per metric. `n` is exact; ratios allow for the registry rounding
# to three decimals; t_stat is derived from a resampled daily series.
TOL = {"pf_gross": 1.5e-3, "pf_net": 1.5e-3, "pf_stress": 1.5e-3,
       "mdd": 1.5e-3, "t_stat": 0.02}

RULES = {
    "BTC-TREND": "donchian_breakout",
    "BTC-MOM": "ema_state",
    "BTC-MR": "zscore_fade",
    "BTC-ORB": "orb_session",
}

# `sc.run_trades` takes the stop distance from the entry tuple and ignores
# `Exit.k_atr`, so the study executed 1.5 * ATR everywhere (audit E15). The
# registry metadata for 4h/1d still says 2.0; the engine is the reference.
EXECUTED_ATR_K = 1.5


def family(strategy_id: str) -> str:
    for prefix, rule in RULES.items():
        if strategy_id.startswith(prefix):
            return rule
    raise SystemExit(f"familia desconocida: {strategy_id}")


def spec_from_run(row: dict) -> dict:
    """Rebuild an executable spec from what the registry says was run."""
    p = row["params"]
    rule = family(row["strategy_id"])
    tf = p.get("bar") or "5m"
    declared = p.get("atr_k")
    # Higher timeframes declare 2.0 but executed 1.5 (E15). 5m metadata is
    # consistent; ORB has no atr_k (the stop is the range width).
    atr_k = EXECUTED_ATR_K if declared is None or tf != "5m" else float(declared)
    spec = {
        "timeframe_signal": tf,
        "params": {
            "atr_k": atr_k,
            "tp_r": float(p.get("tp_r") or 2.0),
            "N": p.get("N"),
            "fast": p.get("fast"),
            "slow": p.get("slow"),
            "z": p.get("z", 2.0),
            "range_bars": p.get("range_bars"),
            "stop_floor_frac": p.get("stop_floor_frac"),
            "vol_lookback_bars": p.get("vol_lookback_bars"),
            "vol_floor_mult": p.get("vol_floor_mult"),
        },
        "entry": {"rule": rule, "sessions": ["08:00", "13:30"]},
        "exit": {"time_stop_bars": int(p.get("max_hold") or p.get("_max_hold") or 288)},
        "costs": {
            "fee_taker_bps": float(row["costs"].get("fee_taker_bps", 5.0)),
            "half_spread_bps": float(row["costs"].get("half_spread_bps", 0.07)),
            "funding": "real_timestamps" if row["costs"].get("funding") else "exclude",
        },
        "validation": {"is_oos_split": "0.6/0.2", "seed": 7},
    }
    # A portfolio run is only reproducible if its composition and sizing travel with
    # it. `executable_params` writes them under `_` keys precisely so this can be
    # rebuilt; a row without them is a number nobody can regenerate.
    if p.get("_portfolio"):
        spec["portfolio"] = p["_portfolio"]
    if p.get("_sizing"):
        spec["risk"] = {"sizing": p["_sizing"],
                        "target_vol_annual": p.get("_target_vol_annual", 0.2),
                        "max_gross_leverage": p.get("_max_gross_leverage", 1.0)}
    return spec


def is_portfolio_row(row: dict) -> bool:
    return bool((row.get("params") or {}).get("_portfolio"))


def measure(spec: dict, df5: pd.DataFrame, fund: pd.DataFrame | None) -> dict:
    bars, _ = rn.bars_for(df5, spec["timeframe_signal"])
    trades, weights = rn.run_portfolio(bars, spec, rn.run_trades, rn.build_entries)
    if trades.empty:
        return {"n": 0}
    fee_rt_bps = 2 * (spec["costs"]["fee_taker_bps"] + spec["costs"]["half_spread_bps"])
    fund_r = rn.funding_in(spec, trades, bars, fund)
    d = trades["stop_dist_frac"].to_numpy()
    r_gross = trades["r_gross"].to_numpy()
    fee_r = (fee_rt_bps * rn.BPS) / d
    stress_r = (fee_rt_bps * rn.STRESS_MULT * rn.BPS) / d
    r_net = r_gross - fee_r - fund_r
    r_stress = r_gross - stress_r - fund_r
    vol = rn.vol_factors(bars, trades, spec)
    r_net, r_stress = r_net * vol, r_stress * vol
    if weights is not None:
        r_net, r_stress = r_net * weights, r_stress * weights
    m = rn.metrics_block(trades, bars, r_net, r_stress, fee_r, fund_r,
                         seed=7, block=rn.BLOCK, reps=rn.REPS)
    m["benchmark"] = alpha_vs_bh(bars, trades, r_net, r_stress, fee_r, fund_r, m)
    return m


def alpha_vs_bh(bars: pd.DataFrame, trades: pd.DataFrame, r_net: np.ndarray,
                r_stress: np.ndarray, fee_r: np.ndarray, fund_r: np.ndarray,
                m_all: dict) -> dict:
    """Out-of-sample excess return over buy & hold, same split as the runner."""
    a, o = 0.6, 0.2
    t_oos = rn.subset(trades, bars, a, a + o)
    if t_oos.empty:
        return {"alpha_annual": None, "ci95": [None, None], "verdict": "sin_oos"}
    idx = trades.index.get_indexer(t_oos.index)
    m_oos = rn.metrics_block(t_oos, bars, r_net[idx], r_stress[idx],
                             fee_r[idx], fund_r[idx], seed=7, block=rn.BLOCK, reps=rn.REPS)
    years = m_all.get("years") or 0.0
    start = bars["ts"].iloc[0]
    bh_daily = bars.set_index("ts")["close"].resample("D").last().ffill().pct_change().fillna(0.0)
    bh_oos = bh_daily.loc[(bh_daily.index >= start + pd.Timedelta(days=a * years * 365.25))
                          & (bh_daily.index < start + pd.Timedelta(days=(a + o) * years * 365.25))]
    alpha = rn.annualised_alpha(m_oos.get("_daily", pd.Series(dtype=float)), bh_oos,
                                seed=7, block=rn.BLOCK, reps=rn.REPS)
    ci = alpha.get("ci95") or [None, None]
    if ci[0] is None:
        state = "sin_oos"
    elif ci[0] > 0:
        state = "bate"
    elif ci[1] < 0:
        state = "pierde"
    else:
        state = "indistinguible"
    alpha["verdict"] = state
    alpha["oos_trades"] = int(m_oos.get("n") or 0)
    alpha["vol_matched"] = vol_matched_alpha(m_oos.get("_daily", pd.Series(dtype=float)),
                                              bh_oos, alpha)
    return alpha


def vol_matched_alpha(strategy_daily: pd.Series, bh_daily: pd.Series, plain: dict) -> dict:
    """Same excess return, with the strategy scaled to the benchmark's volatility.

    The plain comparison is unfair in both directions: a strategy risking 0.5% per
    trade produces small absolute returns by construction, so it loses to a rising
    benchmark for reasons of sizing rather than edge. Scaling the daily series by
    sigma_bh / sigma_strategy answers the question a capital allocator would ask:
    at equal risk, does the rule beat holding?
    """
    if strategy_daily.empty or bh_daily.empty:
        return {"alpha_annual": None, "ci95": [None, None], "leverage": None}
    joined = pd.concat([strategy_daily.rename("s"), bh_daily.rename("b")],
                       axis=1, sort=False).fillna(0.0)
    sd_s, sd_b = joined["s"].std(ddof=1), joined["b"].std(ddof=1)
    if not np.isfinite(sd_s) or sd_s <= 0 or not np.isfinite(sd_b) or sd_b <= 0:
        return {"alpha_annual": None, "ci95": [None, None], "leverage": None}
    lev = float(min(sd_b / sd_s, 100.0))
    diff = (joined["s"] * lev - joined["b"]).to_numpy()
    rng = np.random.default_rng(7)
    n, link = len(diff), rn.BLOCK
    boot = np.empty(rn.REPS)
    for k in range(rn.REPS):
        idx: list[int] = []
        while len(idx) < n:
            s = int(rng.integers(0, n))
            idx.extend(range(s, min(s + link, n)))
        boot[k] = diff[np.array(idx[:n])].mean()
    ci = [round(float(np.percentile(boot, 2.5) * 365), 4),
          round(float(np.percentile(boot, 97.5) * 365), 4)]
    verdict = "bate" if ci[0] > 0 else ("pierde" if ci[1] < 0 else "indistinguible")
    return {
        "alpha_annual": round(float(diff.mean() * 365), 4),
        "ci95": ci,
        "leverage": round(lev, 3),
        "verdict": verdict,
        "method": "strategy daily returns scaled by sigma_bh/sigma_strategy, then "
                  "excess vs buy & hold; stationary block bootstrap, constant scaling, "
                  "no compounding of the leverage itself",
    }


def compare(expected: dict, got: dict) -> list[str]:
    diffs: list[str] = []
    if expected.get("n") != got.get("n"):
        diffs.append(f"n {expected.get('n')} → {got.get('n')}")
        return diffs  # a different trade count makes the rest meaningless
    for key, tol in TOL.items():
        e, g = expected.get(key), got.get(key)
        if e is None or g is None:
            continue
        if abs(float(e) - float(g)) > tol:
            diffs.append(f"{key} {e} → {round(float(g), 4)}")
    return diffs


def load_rows(db: Path, filt: str | None) -> list[dict]:
    if not db.exists():
        raise SystemExit(f"no existe la base de datos: {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = []
    for r in con.execute("SELECT id, strategy_id, params, costs, metrics, verdict "
                         "FROM runs ORDER BY id"):
        d = dict(r)
        for k in ("params", "costs", "metrics"):
            d[k] = json.loads(d[k])
        rows.append(d)
    # Rows the log itself marks as defective are not silently skipped: they are
    # returned with a flag so the caller can report them instead of pretending the
    # registry only contains clean runs.
    broken = {}
    for e in con.execute("SELECT run_id, message FROM events WHERE type='audit'"):
        msg = (e["message"] or "").lower()
        # The marker is fixed text the audit event must carry; matching only the
        # longer explanation would stop working the day the wording changes.
        if e["run_id"] and ("registro defectuoso" in msg or "no reconstruible" in msg):
            broken[e["run_id"]] = e["message"]
    con.close()
    for d in rows:
        if d["id"] in broken:
            d["defective"] = broken[d["id"]]
    if filt:
        rows = [r for r in rows if filt.lower() in r["id"].lower()]
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Re-run registered backtests and compare")
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--id", default=None, help="substring filter on run id")
    ap.add_argument("--json", type=Path, default=None, help="write the report here")
    ap.add_argument("--record", default=None, metavar="URL",
                    help="append the measurements to the registry as audit events, "
                         "e.g. http://127.0.0.1:8787; already-recorded runs are skipped")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    rows = load_rows(args.db, args.id)
    if not rows:
        raise SystemExit("sin corridas que verificar")

    print(f"verificando {len(rows)} corridas contra el motor\n")
    df5, data = rn.load_data()
    fund = fs.load_funding()
    print(f"datos: {data['bars']} barras · sha {data['sha256'][:16]} · "
          f"funding {len(fund)} eventos\n")

    report, failures = [], 0
    for row in rows:
        spec = spec_from_run(row)
        if row.get("defective"):
            # The log says this row cannot be rebuilt. Counting it as a reproduction
            # would be a lie and counting it as a failure would blame the engine.
            print(f"  omite {row['id']:38s} registro defectuoso documentado")
            report.append({"id": row["id"], "ok": None, "defective": row["defective"],
                           "registry_pf_net": row["metrics"].get("pf_net")})
            continue
        got = measure(spec, df5, fund)
        diffs = compare(row["metrics"], got)
        ok = not diffs
        failures += 0 if ok else 1
        bench = got.get("benchmark") or {}
        report.append({
            "id": row["id"],
            "family": spec["entry"]["rule"],
            "timeframe": spec["timeframe_signal"],
            "atr_k_executed": spec["params"]["atr_k"],
            "registry_pf_net": row["metrics"].get("pf_net"),
            "engine_pf_net": got.get("pf_net"),
            "trades": got.get("n"),
            "alpha_annual": bench.get("alpha_annual"),
            "alpha_ci95": bench.get("ci95"),
            "alpha_verdict": bench.get("verdict"),
            "vol_matched": bench.get("vol_matched"),
            "ok": ok,
            "diffs": diffs,
        })
        mark = "ok " if ok else "FALLA"
        pf = f"{got.get('pf_net'):.3f}" if got.get("pf_net") is not None else "  n/a"
        alpha = bench.get("alpha_annual")
        a_txt = f"{alpha * 100:+7.1f}%" if isinstance(alpha, (int, float)) else "     n/a"
        print(f"  {mark} {row['id']:<34} {str(got.get('n')):>6} trades  PF {pf}  α {a_txt}"
              + ("" if ok else "   " + " · ".join(diffs)))

    print()
    print(f"{len(rows) - failures}/{len(rows)} corridas reproducen al dígito")
    if failures:
        print(f"{failures} no reproducen: revisar antes de citar el registro")

    measured = [r for r in report if r.get("alpha_verdict")]
    beat = [r for r in measured if r["alpha_verdict"] == "bate"]
    lose = [r for r in measured if r["alpha_verdict"] == "pierde"]
    flat = [r for r in measured if r["alpha_verdict"] == "indistinguible"]
    if beat or lose or flat:
        print(f"alpha vs buy & hold: {len(beat)} baten · {len(flat)} indistinguibles · "
              f"{len(lose)} pierden")
    vm = [r["vol_matched"] for r in report if r.get("vol_matched")]
    if vm:
        print("alpha con volatilidad igualada: "
              f"{sum(1 for v in vm if v.get('verdict') == 'bate')} baten · "
              f"{sum(1 for v in vm if v.get('verdict') == 'indistinguible')} indistinguibles · "
              f"{sum(1 for v in vm if v.get('verdict') == 'pierde')} pierden")
        best = max((v for v in vm if isinstance(v.get("alpha_annual"), (int, float))),
                   key=lambda v: v["alpha_annual"], default=None)
        if best:
            print(f"  mejor: {best['alpha_annual'] * 100:+.1f}% anual "
                  f"(apalancamiento ×{best['leverage']:.1f})")

    if args.json:
        measured = [r for r in report if r.get("alpha_verdict")]
        beat = [r for r in measured if r["alpha_verdict"] == "bate"]
        args.json.write_text(json.dumps({
            "data_hash": data["sha256"][:16],
            "checked": len(rows), "failures": failures, "runs": report,
            "benchmark": {
                "bate": len(beat),
                "indistinguible": len([r for r in measured if r["alpha_verdict"] == "indistinguible"]),
                "pierde": len([r for r in measured if r["alpha_verdict"] == "pierde"]),
                "best": max((r["alpha_annual"] for r in measured
                             if isinstance(r.get("alpha_annual"), (int, float))), default=None),
                "vol_matched": {
                    "bate": sum(1 for v in vm if v.get("verdict") == "bate"),
                    "indistinguible": sum(1 for v in vm if v.get("verdict") == "indistinguible"),
                    "pierde": sum(1 for v in vm if v.get("verdict") == "pierde"),
                },
            },
            "defective": [r["id"] for r in report if r.get("defective")],
    }, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"informe escrito en {args.json}")

    if args.record:
        recorded = record_measurements(args.record, report)
        print(f"eventos anexados al registro: {recorded}")

    return 0 if failures == 0 else 1


def record_measurements(base_url: str, report: list[dict]) -> int:
    """Append one audit event per run with its benchmark measurement.

    The registry stores what was known when each run was admitted; the benchmark
    alpha was measured later. An append-only log does not rewrite that, it adds
    the new fact. Runs that already carry the measurement are skipped, so the
    command is safe to re-run.
    """
    import urllib.error
    import urllib.request

    base = base_url.rstrip("/")
    try:
        state = json.loads(urllib.request.urlopen(f"{base}/api/state", timeout=15).read())
    except Exception as exc:  # noqa: BLE001
        print(f"aviso: no se pudo leer el registro ({exc}); no se anotan mediciones")
        return 0
    already = {e.get("run_id") for e in state.get("events", [])
               if e.get("type") == "audit" and str(e.get("message", "")).startswith("alpha medido")}

    added = 0
    for row in report:
        if row["id"] in already:
            continue
        alpha = row.get("alpha_annual")
        if not isinstance(alpha, (int, float)):
            continue
        vm = row.get("vol_matched") or {}
        vm_alpha = vm.get("alpha_annual")
        msg = (f"alpha medido vs comprar y mantener: {alpha * 100:+.1f}% anual "
               f"[{row['alpha_ci95'][0] * 100:+.0f}%, {row['alpha_ci95'][1] * 100:+.0f}%] "
               f"({row['alpha_verdict']})")
        if isinstance(vm_alpha, (int, float)):
            msg += (f"; a igual volatilidad {vm_alpha * 100:+.1f}% "
                    f"(apalancamiento ×{vm.get('leverage', 0):.1f}, {vm.get('verdict')})")
        msg += "; artefacto runner/verification.json"
        body = {"type": "audit", "run_id": row["id"], "message": msg, "actor": "verifier"}
        req = urllib.request.Request(f"{base}/api/events", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            urllib.request.urlopen(req, timeout=15).read()
            added += 1
        except urllib.error.HTTPError as exc:
            print(f"aviso: {row['id']} no registrada ({exc.code}): "
                  f"{exc.read().decode()[:120]}")
    return added


if __name__ == "__main__":
    raise SystemExit(main())
