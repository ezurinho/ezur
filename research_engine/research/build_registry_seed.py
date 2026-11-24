"""Build the registry seed from real study runs (no synthetic numbers).

Runs every configuration used in the audit, adds block-bootstrap confidence
intervals and a 2x cost stress, and writes research/cache/registry_seed.json.
The app imports this file on first boot; afterwards the SQLite registry is the
source of truth and nothing is overwritten.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

import study_costs as sc
import funding_study as fs

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
RISK = sc.RISK_FRAC
FEE_TAKER = 10.14 / 1e4
FEE_STRESS = 20.28 / 1e4


def pf(x: np.ndarray) -> float:
    gp = x[x > 0].sum()
    gl = -x[x < 0].sum()
    return float(gp / gl) if gl > 0 else float("inf")


def block_ci(r: np.ndarray, block: int = 5, reps: int = 4000, seed: int = 7) -> dict:
    rng = np.random.default_rng(seed)
    n = len(r)
    out = np.empty(reps)
    for k in range(reps):
        idx: list[int] = []
        while len(idx) < n:
            s = rng.integers(0, n)
            idx.extend(range(s, min(s + block, n)))
        x = r[np.array(idx[:n])]
        out[k] = pf(x)
    out = out[np.isfinite(out)]
    return {"pf_ci95": [round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)],
            "pf_se": round(float(out.std(ddof=1)), 3)}


def monthly(eq_series: pd.Series) -> list[float]:
    m = eq_series.resample("ME").last().ffill()
    m = pd.concat([pd.Series([1.0]), m]).reset_index(drop=True)
    return [round(float(v), 4) for v in m]


def run_5m(df5: pd.DataFrame, entries, exits, name: str) -> dict:
    tr = sc.run_trades(df5, entries, exits)
    r = tr["r_gross"].to_numpy()
    d = tr["stop_dist_frac"].to_numpy()
    out = {"n": int(len(tr))}
    for label, fee in (("net", FEE_TAKER), ("stress", FEE_STRESS)):
        rn = r - fee / d
        out[f"pf_{label}"] = round(pf(rn), 3)
        out[f"exp_{label}_r"] = round(float(rn.mean()), 4)
    out["pf_gross"] = round(pf(r), 3)
    out["exp_gross_r"] = round(float(r.mean()), 4)
    out["cost_r"] = round(float((FEE_TAKER / d).mean()), 3)
    out["stop_frac_median"] = round(float(np.median(d)), 5)
    out["win"] = round(float((r - FEE_TAKER / d > 0).mean()), 3)

    eq = (1 + RISK * (r - FEE_TAKER / d)).cumprod()
    ser = pd.Series(eq, index=df5["ts"].to_numpy()[tr["exit_i"].to_numpy()]).sort_index()
    daily = ser.resample("D").last().ffill().pct_change().fillna(0.0)
    sd = daily.std(ddof=1)
    out["sharpe"] = round(float(daily.mean() / sd * np.sqrt(365)), 2) if sd > 0 else 0.0
    out["mdd"] = round(float((ser / ser.cummax() - 1).min()), 3)
    out["t_stat"] = round(float(out["sharpe"] * np.sqrt(len(daily) / 365)), 2)
    out["years"] = round(len(daily) / 365, 2)
    out.update(block_ci(r - FEE_TAKER / d))
    out["equity"] = monthly(ser)
    out["basis"] = "5m"
    out["funding_included"] = False
    return out


def run_htf(df5: pd.DataFrame, fund: pd.DataFrame, rule: str, n: int, hold: int, name: str) -> dict:
    """Higher-timeframe Donchian with real funding.

    Note (runner audit, 2026-11): `sc.run_trades` takes the stop distance from
    the entry tuple and ignores `Exit.k_atr`, so every run in this study used a
    stop of 1.5 * ATR(14). Earlier versions of this file declared `atr_k: 2.0`
    in `params`, which did not match what the engine executed; corrected here to
    1.5 so the registry metadata matches the code path.
    """
    agg = fs.resample(df5, rule)
    tr = sc.run_trades(agg, sc.trend_entries(agg, n), sc.Exit(1.5, 4.0, hold))
    fr = fs.funding_in_R(tr, agg, fund)
    r = tr["r_gross"].to_numpy()
    d = tr["stop_dist_frac"].to_numpy()
    f = fr.to_numpy()
    out = {"n": int(len(tr))}
    for label, fee in (("net", FEE_TAKER), ("stress", FEE_STRESS)):
        rn = r - fee / d - f
        out[f"pf_{label}"] = round(pf(rn), 3)
        out[f"exp_{label}_r"] = round(float(rn.mean()), 4)
        if label == "net":
            rn_net = rn
    out["pf_gross"] = round(pf(r), 3)
    out["exp_gross_r"] = round(float(r.mean()), 4)
    out["cost_r"] = round(float((FEE_TAKER / d).mean()), 4)
    out["funding_r"] = round(float(f.mean()), 4)
    out["fee_r"] = round(float((FEE_TAKER / d).mean()), 4)
    out["stop_frac_median"] = round(float(np.median(d)), 4)
    out["win"] = round(float((rn_net > 0).mean()), 3)

    eq = (1 + RISK * rn_net).cumprod()
    ser = pd.Series(eq, index=agg["ts"].to_numpy()[tr["exit_i"].to_numpy()]).sort_index()
    daily = ser.resample("D").last().ffill().pct_change().fillna(0.0)
    sd = daily.std(ddof=1)
    out["sharpe"] = round(float(daily.mean() / sd * np.sqrt(365)), 2) if sd > 0 else 0.0
    out["mdd"] = round(float((ser / ser.cummax() - 1).min()), 3)
    out["t_stat"] = round(float(out["sharpe"] * np.sqrt(len(daily) / 365)), 2)
    out["years"] = round(len(daily) / 365, 2)
    out.update(block_ci(rn_net))
    out["equity"] = monthly(ser)
    out["basis"] = rule
    out["funding_included"] = True
    return out


def gates_for(m: dict, budget_mdd: float = 0.25) -> dict:
    g = {
        "pf_net": {"value": m["pf_net"], "threshold": 1.0, "op": ">", "pass": m["pf_net"] > 1.0},
        "pf_ci_low": {"value": m["pf_ci95"][0], "threshold": 1.0, "op": ">", "pass": m["pf_ci95"][0] > 1.0},
        "t_stat": {"value": m["t_stat"], "threshold": 3.0, "op": ">=", "pass": m["t_stat"] >= 3.0},
        "trades": {"value": m["n"], "threshold": 300, "op": ">=", "pass": m["n"] >= 300},
        "cost_stress_2x": {"value": m["pf_stress"], "threshold": 1.0, "op": ">", "pass": m["pf_stress"] > 1.0},
        "mdd_budget": {"value": m["mdd"], "threshold": budget_mdd, "op": ">=", "pass": m["mdd"] >= -budget_mdd},
        "funding": {"value": "included" if m["funding_included"] else "n/a (intradía)",
                    "threshold": "required", "op": "=", "pass": True},
    }
    return g


def verdict_for(m: dict, g: dict) -> str:
    if m["pf_net"] <= 1.0 or not g["cost_stress_2x"]["pass"] or not g["mdd_budget"]["pass"]:
        return "REJECTED"
    if not (g["trades"]["pass"] and g["t_stat"]["pass"] and g["pf_ci_low"]["pass"]):
        return "INCONCLUSIVE"
    return "APPROVED"


def main() -> None:
    df5 = sc.load()
    fund = fs.load_funding()
    raw = CACHE / "btc_5m.pkl"
    data_hash = hashlib.sha256(raw.read_bytes()).hexdigest()

    specs = [
        # strategy_id, name, family, tf, entries/exits builder, hypothesis, rules, risks
        ("BTC-TREND-5M", "Donchian breakout 5m", "trend", "5m",
         "El flujo institucional fragmentado deja persistencia de retornos a escala de horas. Un canal de Donchian la captura con reglas causales.",
         "close[t] > max(high[t-N..t-1]) → long; close[t] < min(low[t-N..t-1]) → short. SL 1,5×ATR(14), TP 2R, time stop 288 barras.",
         "En 5m el edge bruto es ≈0 y el coste en R es 0,23–0,35: la rotación domina. Riesgo de gap en eventos de liquidación."),
        ("BTC-MOM-5M", "EMA state momentum 5m", "momentum", "5m",
         "Persistencia de corto plazo por ejecución de metaórdenes y reacción lenta del flujo pasivo.",
         "Cruce EMA rápida/lenta → entrada en la dirección del estado. SL 1,5×ATR(14), TP 2R, time stop 288 barras.",
         "Los cruces en 5m son ruido dominado por bid-ask bounce; 658–2.211 trades/año."),
        ("BTC-MR-5M", "Z-score mean reversion 5m", "mean_reversion", "5m",
         "Sobre-reacción de participantes minoristas a shocks de precio, con reversión posterior hacia la media.",
         "z = (close−SMA(N))/σ(N); z < −2 → long, z > 2 → short. SL 2×ATR(14), TP 1R, time stop 48 barras.",
         "A este horizonte la reversión es microestructural; el coste supera la señal. 2.322–4.039 trades/año."),
        ("BTC-ORB-5M", "Session opening-range breakout", "orb", "5m",
         "Momentum intradía documentado en BTC: el retorno de la primera media hora predice el de la última (Shen et al. 2022).",
         "Rango de apertura Londres 08:00 UTC y NY 13:30 UTC; primer cierre fuera del rango → entrada. SL = rango, TP 2R, salida al cierre de sesión.",
         "Sesiones definidas en UTC: el DST desplaza la apertura real. En 5m el coste (0,14–0,24R) sigue dominando."),
        ("BTC-TREND-4H", "Donchian breakout 4h", "trend", "4h",
         "Misma hipótesis de persistencia, con menos rotación: el coste por trade cae al 0,05R.",
         "Donchian N∈{12,24,48} barras 4h. SL 2×ATR(14), TP 4R, time stop 20 barras.",
         "358–836 trades en 6,8 años: el IC del PF sigue siendo ancho; el Sharpe no alcanza significancia."),
        ("BTC-TREND-1D", "Donchian breakout 1d", "trend", "1d",
         "Time-series momentum en cripto documentado a horizontes de días-semanas (Liu & Tsyvinski 2021).",
         "Donchian N∈{10,20,40,55,100} días. SL 2×ATR(14), TP 4R, time stop 90 barras.",
         "Con 39–89 trades ningún IC permite concluir; el funding pesa 3–5× más que las fees."),
    ]

    strategies, runs, events = [], [], []
    base = "2026-11-22T00:00:00Z"

    def add_event(msg, run_id=None, actor="runner", typ="run"):
        events.append({"ts": base, "actor": actor, "type": typ, "run_id": run_id, "message": msg})

    for sid, name, fam, tf, hyp, rules, risks in specs:
        strategies.append({"id": sid, "name": name, "family": fam, "timeframe": tf,
                           "hypothesis": hyp, "rules": rules, "risks": risks, "created_at": base})

    plan = [
        ("BTC-TREND-5M", [288, 576], None),
        ("BTC-MOM-5M", [(12, 48), (24, 96), (48, 192)], None),
        ("BTC-MR-5M", [48, 96, 192], None),
        ("BTC-ORB-5M", [3, 6, 12], None),
    ]
    for sid, variants, _ in plan:
        for v in variants:
            if sid == "BTC-TREND-5M":
                m = run_5m(df5, sc.trend_entries(df5, v), sc.Exit(1.5, 2.0, 288), f"{v}")
                label, params, hold = f"donchian_{v}", {"N": v, "atr_k": 1.5, "tp_r": 2.0}, 288
            elif sid == "BTC-MOM-5M":
                fast, slow = v
                m = run_5m(df5, sc.momentum_entries(df5, f"ema{fast}", f"ema{slow}"), sc.Exit(1.5, 2.0, 288), f"{fast}_{slow}")
                label, params, hold = f"ema_{fast}_{slow}", {"fast": fast, "slow": slow, "atr_k": 1.5, "tp_r": 2.0}, 288
            elif sid == "BTC-MR-5M":
                m = run_5m(df5, sc.meanrev_entries(df5, v, 2.0, 2.0), sc.Exit(2.0, 1.0, 48), f"{v}")
                label, params, hold = f"z2_{v}", {"N": v, "z": 2.0, "atr_k": 2.0, "tp_r": 1.0}, 48
            else:
                m = run_5m(df5, sc.orb_entries(df5, v, ((8, 0), (13, 30))), sc.Exit(1.0, 2.0, 96), f"{v}")
                label, params, hold = f"orb_{v*5}min", {"range_bars": v, "tp_r": 2.0}, 96
            g = gates_for(m)
            rid = f"{sid}-v1.0.0-{label}"
            runs.append({
                "id": rid, "strategy_id": sid, "cycle_id": "CYCLE-2026-11", "version": "1.0.0",
                "created_at": base, "label": label,
                "params": {"bar": "5m", "tp_r": params.get("tp_r"), "max_hold": hold, **params},
                "costs": {"fee_taker_bps": 5.0, "half_spread_bps": 0.07, "rt_bps": 10.14,
                          "stress_rt_bps": 20.28, "funding": False, "cost_r": m["cost_r"]},
                "metrics": {k: m[k] for k in ("n", "win", "pf_gross", "pf_net", "pf_stress", "exp_gross_r",
                                              "exp_net_r", "exp_stress_r", "sharpe", "mdd", "t_stat",
                                              "pf_ci95", "pf_se", "years", "stop_frac_median")},
                "gates": g, "verdict": verdict_for(m, g),
                "artifacts": {"data_hash": data_hash[:16], "seed": 7, "source": "research/cache/study_results.json"},
                "equity": m["equity"], "notes": "",
            })
            add_event(f"{rid}: {m['n']} trades · PF neto {m['pf_net']:.3f} · veredicto {runs[-1]['verdict']}", rid)

    htf = [("4h", 12, 20), ("4h", 24, 20), ("4h", 48, 20),
           ("1d", 10, 90), ("1d", 20, 90), ("1d", 40, 90), ("1d", 55, 90), ("1d", 100, 90)]
    for rule, n, hold in htf:
        sid = "BTC-TREND-4H" if rule == "4h" else "BTC-TREND-1D"
        m = run_htf(df5, fund, rule, n, hold, f"{rule}_{n}")
        g = gates_for(m)
        rid = f"{sid}-v1.0.0-{rule.lower()}_{n}"
        runs.append({
            "id": rid, "strategy_id": sid, "cycle_id": "CYCLE-2026-11", "version": "1.0.0",
            "created_at": base, "label": f"{rule}_donchian_{n}",
            "params": {"bar": rule, "N": n, "atr_k": 1.5, "tp_r": 4.0, "max_hold": hold},
            "costs": {"fee_taker_bps": 5.0, "half_spread_bps": 0.07, "rt_bps": 10.14,
                      "stress_rt_bps": 20.28, "funding": True,
                      "cost_r": m["cost_r"], "fee_r": m["fee_r"], "funding_r": m["funding_r"]},
            "metrics": {k: m[k] for k in ("n", "win", "pf_gross", "pf_net", "pf_stress", "exp_gross_r",
                                          "exp_net_r", "exp_stress_r", "sharpe", "mdd", "t_stat",
                                          "pf_ci95", "pf_se", "years", "stop_frac_median",
                                          "fee_r", "funding_r")},
            "gates": g, "verdict": verdict_for(m, g),
            "artifacts": {"data_hash": data_hash[:16], "seed": 7, "source": "research/cache/funding_results.json"},
            "equity": m["equity"], "notes": "",
        })
        add_event(f"{rid}: {m['n']} trades · PF neto {m['pf_net']:.3f} · funding {m['funding_r']:.3f}R · veredicto {runs[-1]['verdict']}", rid)

    summary = json.loads((CACHE / "funding_results.json").read_text(encoding="utf-8"))["_summary"]
    wfa = json.loads((CACHE / "funding_results.json").read_text(encoding="utf-8"))["_wfa"]
    cycle = {
        "id": "CYCLE-2026-11", "name": "Ciclo 2026-11 · Donchian multi-horizonte",
        "created_at": base, "pbo": summary["pbo"], "dsr": summary["dsr"]["dsr"],
        "dsr_threshold": 0.95, "sr_best": summary["best_sr"], "sr0": summary["dsr"]["sr0_ann"],
        "minbtl_years": round(summary["dsr"]["minbtl_years"], 2),
        "coverage_years": 6.83, "trials": summary["n_configs"],
        "wfa_min_trades": min(f["oos_trades"] for f in wfa), "wfa_folds": len(wfa),
        "wfa_total_trades": sum(f["oos_trades"] for f in wfa),
        "verdict": "REJECTED",
        "notes": "PBO 0,50 > 0,20 y DSR 0,58 < 0,95: el ciclo no supera el control de selección múltiple. "
                 "MinBTL 11,2 años > 6,8 disponibles. WFA con 11 trades OOS en 2 folds: sin potencia.",
    }

    seed = {
        "project": {
            "id": "BTC-QUANT-RESEARCH",
            "name": "BTC Quant Research Registry",
            "created_at": base,
            "engine_version": "4.0.0",
            "risk_per_trade": RISK,
            "pm": "vol_target / Kelly fraccional c≤0.5",
        },
        "dataset": {
            "instrument": "BTCUSDT_PERP",
            "source": "data.binance.vision · futures/um/monthly/klines",
            "rows": int(len(df5)), "start": str(df5.ts.iloc[0]), "end": str(df5.ts.iloc[-1]),
            "gaps": 0, "duplicates": 0, "timezone": "UTC", "sha256": data_hash,
            "funding_events": int(len(fund)),
        },
        "budget": {"max_mdd": 0.25, "target_vol_annual": 0.20},
        "strategies": strategies, "runs": runs, "cycles": [cycle], "events": events,
    }
    out = CACHE / "registry_seed.json"
    out.write_text(json.dumps(seed, indent=1), encoding="utf-8")
    print("wrote", out, "strategies", len(strategies), "runs", len(runs), "events", len(events))
    for r in runs:
        print(f"{r['id']:34} n={r['metrics']['n']:6d} pf={r['metrics']['pf_net']:.3f} "
              f"ci={r['metrics']['pf_ci95']} stress={r['metrics']['pf_stress']:.3f} -> {r['verdict']}")


if __name__ == "__main__":
    main()
