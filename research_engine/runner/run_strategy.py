"""Deterministic strategy runner for BTC Quant Research Engine v4.0.0.

The runner is the only component allowed to turn a `strategy_spec` into
performance numbers (PROMPT_V4 section 0, rule 2). It executes one spec against
the frozen 5m BTCUSDT perp dataset, applies the execution model of section 3,
evaluates the gates of section 6 and writes a `result.json` that a language
model is only allowed to *cite*.

    python runner/run_strategy.py --spec runner/specs/btc-trend-1d-donchian-40.json
    python runner/run_strategy.py --spec ... --register http://127.0.0.1:8787
    python runner/run_strategy.py --spec ... --dry-run      # validate + cost admission only

Design constraints:
  * no network, no exchange client, no order routing;
  * every number is reproducible from spec + data hash + seed;
  * gates that need the full selection cycle (PBO, DSR, MinBTL, WFA) are
    reported as `null` with an explicit `missing_artifacts` entry, and the
    verdict degrades to INCONCLUSIVE instead of inventing them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
sys.path.insert(0, str(RESEARCH))

import funding_study as fs  # noqa: E402
import study_costs as sc  # noqa: E402

SCHEMA_PATH = Path(__file__).resolve().parent / "strategy_spec.schema.json"
OUT_DIR = Path(__file__).resolve().parent / "out"
DATA = RESEARCH / "cache" / "btc_5m.pkl"
FUND = RESEARCH / "cache" / "funding.parquet"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gates as gc  # noqa: E402  contrato único: config/gates.json del bot

BPS = 1e-4
STRESS_MULT = gc.COST_STRESS_MULTIPLIER
RISK = sc.RISK_FRAC
BLOCK, REPS = 5, 4000
VALIDATION_DIR = ROOT / "runner" / "validation"
VALIDATION_DEFAULT = VALIDATION_DIR / "CYCLE-2026-11.json"

# Hard gates of PROMPT_V4 section 6, with the failure mode each one carries.
REJECT_ON_FAIL = (
    "data_integrity", "pbo", "dsr", "oos_t_stat", "oos_pf_ci_low",
    "cost_stress_2x", "funding_included", "plateau", "benchmark_alpha", "mdd_budget",
)
INCONCLUSIVE_ON_FAIL = ("trades", "wfa_min_trades", "minbtl")


# --------------------------------------------------------------------- schema
_TYPES = {
    "object": dict, "array": list, "string": str, "boolean": bool, "null": type(None),
}


def _type_ok(value, name: str) -> bool:
    if name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py = _TYPES.get(name)
    return py is not None and isinstance(value, py)


def validate(instance, schema: dict, path: str = "$", errors: list[str] | None = None) -> list[str]:
    """Minimal JSON Schema 2020-12 validator covering the keywords this schema uses."""
    errors = [] if errors is None else errors

    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(instance, n) for n in names):
            errors.append(f"{path}: expected {'|'.join(names)}, got {type(instance).__name__}")
            return errors

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in {schema['enum']}")

    if isinstance(instance, str):
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} does not match {schema['pattern']}")
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")

    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{path}: < minimum {schema['minimum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: <= exclusiveMinimum {schema['exclusiveMinimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{path}: > maximum {schema['maximum']}")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append(f"{path}: >= exclusiveMaximum {schema['exclusiveMaximum']}")

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append(f"{path}: missing required property {key!r}")
        props = schema.get("properties", {})
        extra = schema.get("additionalProperties", True)
        for key, value in instance.items():
            if key in props:
                validate(value, props[key], f"{path}.{key}", errors)
            elif extra is False:
                errors.append(f"{path}: unexpected property {key!r}")
            elif isinstance(extra, dict):
                validate(value, extra, f"{path}.{key}", errors)

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if schema.get("uniqueItems") and len(set(map(repr, instance))) != len(instance):
            errors.append(f"{path}: items are not unique")
        if isinstance(schema.get("items"), dict):
            for i, item in enumerate(instance):
                validate(item, schema["items"], f"{path}[{i}]", errors)

    return errors


def load_spec(path: Path) -> dict:
    spec = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = validate(spec, schema)
    if errors:
        raise SystemExit("spec inválida:\n  " + "\n  ".join(errors))
    split = spec["validation"]["is_oos_split"]
    if abs(sum(float(x) for x in split.split("/")) - 1.0) > 1e-9:
        raise SystemExit(f"spec inválida: is_oos_split {split} no suma 1.00")
    if spec["entry"].get("cooldown_bars", 0):
        raise SystemExit("spec inválida: cooldown_bars no está implementado en el motor 4.0.0")
    rule = spec["entry"]["rule"]
    if rule in ("donchian_breakout", "zscore_fade") and "N" not in spec["params"]:
        raise SystemExit(f"spec inválida: la regla {rule} requiere params.N")
    if rule == "ema_state" and not {"fast", "slow"} <= set(spec["params"]):
        raise SystemExit("spec inválida: la regla ema_state requiere params.fast y params.slow")
    if rule == "orb_session" and not spec["entry"].get("sessions"):
        raise SystemExit("spec inválida: la regla orb_session requiere entry.sessions")
    return spec


def spec_path_display(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(ROOT)) if resolved.is_relative_to(ROOT) else str(resolved)


def canonical_hash(obj) -> str:
    """Stable hash of the spec as executed (key order and whitespace independent)."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def code_hash() -> str:
    h = hashlib.sha256()
    for p in (Path(__file__).resolve(), SCHEMA_PATH, RESEARCH / "study_costs.py",
              RESEARCH / "funding_study.py"):
        h.update(p.read_bytes())
    return h.hexdigest()


# ----------------------------------------------------------------------- data
def load_data() -> tuple[pd.DataFrame, dict]:
    """Frozen 5m dataset plus its integrity report (PROMPT_V4 section 2)."""
    raw = DATA.read_bytes()
    df = sc.load()
    ts = df["ts"]
    step = ts.diff().dropna()
    expected = pd.Timedelta(minutes=5)
    gaps = int((step > expected).sum())
    dupes = int(ts.duplicated().sum())
    monotonic = bool(ts.is_monotonic_increasing)
    info = {
        "instrument": "BTCUSDT_PERP",
        "source": "data.binance.vision · futures/um/monthly/klines",
        "bars": int(len(df)),
        "start": str(ts.iloc[0]),
        "end": str(ts.iloc[-1]),
        "timezone": "UTC",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "integrity": {
            "gaps": gaps, "duplicates": dupes, "monotonic": monotonic,
            "unexplained_gaps": gaps,
        },
    }
    return df, info


_RULE = re.compile(r"(\d+)([mhd])")


def resample_rule(tf: str) -> str:
    """Offset de pandas para un marco del esquema (`15m` -> `15min`).

    pandas 3 retiró los alias de minutos sin sufijo: `15m` se leía como
    "15 meses" y el resample reventaba, así que ningún marco salvo 5 m se
    podía medir. El esquema y el bot hablan en minutos; la traducción vive
    aquí, en un sitio, y no repartida por cada llamada.
    """
    match = _RULE.fullmatch(tf.strip())
    if match is None:
        raise SystemExit(f"marco no soportado: {tf!r} (usa 5m, 15m, 30m, 1h, 4h o 1d)")
    size, unit = match.group(1), match.group(2)
    return f"{size}min" if unit == "m" else f"{size}{unit}"


def bars_for(df5: pd.DataFrame, tf: str) -> tuple[pd.DataFrame, str]:
    """Resample the frozen 5m series to the signal timeframe (no new data)."""
    if tf == "5m":
        return df5, "5m (native)"
    bars = fs.resample(df5, resample_rule(tf))
    return bars, "resampled from 5m"


def ensure_emas(bars: pd.DataFrame, fast: int, slow: int) -> pd.DataFrame:
    for span in (fast, slow):
        col = f"ema{span}"
        if col not in bars.columns:
            bars[col] = bars["close"].ewm(span=span, adjust=False).mean()
    return bars


# ------------------------------------------------------------------- entries
def _donchian(bars: pd.DataFrame, n: int, atr_k: float) -> list[tuple[int, int, float]]:
    hi, lo, c, atr = (bars[k].to_numpy() for k in ("high", "low", "close", "atr"))
    up = pd.Series(hi).rolling(n).max().shift(1).to_numpy()
    dn = pd.Series(lo).rolling(n).min().shift(1).to_numpy()
    out = []
    for i in range(n + 1, len(bars) - 1):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if c[i] > up[i]:
            out.append((i, 1, atr_k * atr[i]))
        elif c[i] < dn[i]:
            out.append((i, -1, atr_k * atr[i]))
    return out


def _ema_state(bars: pd.DataFrame, fast: int, slow: int,
               atr_k: float) -> list[tuple[int, int, float]]:
    f, s, atr = bars[f"ema{fast}"].to_numpy(), bars[f"ema{slow}"].to_numpy(), bars["atr"].to_numpy()
    state = np.where(f > s, 1, -1)
    change = np.r_[False, state[1:] != state[:-1]]
    out = []
    for i in range(1, len(bars) - 1):
        if change[i] and np.isfinite(atr[i]) and atr[i] > 0:
            out.append((i, int(state[i]), atr_k * atr[i]))
    return out


def _zscore(bars: pd.DataFrame, n: int, z: float,
            atr_k: float) -> list[tuple[int, int, float]]:
    c, atr = bars["close"].to_numpy(), bars["atr"].to_numpy()
    ma = pd.Series(c).rolling(n).mean().to_numpy()
    sd = pd.Series(c).rolling(n).std().to_numpy()
    out = []
    for i in range(n + 1, len(bars) - 1):
        if not np.isfinite(sd[i]) or sd[i] <= 0 or not np.isfinite(atr[i]):
            continue
        zz = (c[i] - ma[i]) / sd[i]
        if zz < -z:
            out.append((i, 1, atr_k * atr[i]))
        elif zz > z:
            out.append((i, -1, atr_k * atr[i]))
    return out


def _orb(bars: pd.DataFrame, range_bars: int, sessions, atr_k: float) -> list[tuple[int, int, float]]:
    ts = bars["ts"]
    hi, lo, c, atr = (bars[k].to_numpy() for k in ("high", "low", "close", "atr"))
    dates = ts.dt.strftime("%Y-%m-%d").to_numpy()
    minutes = (ts.dt.hour * 60 + ts.dt.minute).to_numpy()
    out: list[tuple[int, int, float]] = []
    start_idx: dict[tuple[str, int], int] = {}
    for i in range(len(bars)):
        for k, (hh, mm) in enumerate(sessions):
            if minutes[i] == hh * 60 + mm:
                start_idx[(dates[i], k)] = i
        for k, _ in enumerate(sessions):
            s = start_idx.get((dates[i], k))
            if s is None:
                continue
            r_end, session_end = s + range_bars, s + 96
            if i <= r_end or i >= min(session_end, len(bars) - 1):
                continue
            if not np.isfinite(atr[i]) or atr[i] <= 0:
                continue
            # only the first breakout of the session, and no entries in the last 12 bars
            rng_hi, rng_lo = float(np.max(hi[s:r_end + 1])), float(np.min(lo[s:r_end + 1]))
            if any(c[j] > rng_hi or c[j] < rng_lo for j in range(r_end + 1, i)):
                continue
            if i > session_end - 12:
                continue
            if rng_hi - rng_lo <= 0:
                continue
            if c[i] > rng_hi:
                out.append((i, 1, max(rng_hi - rng_lo, 0.5 * atr[i])))
            elif c[i] < rng_lo:
                out.append((i, -1, max(rng_hi - rng_lo, 0.5 * atr[i])))
    return out


def build_entries(bars: pd.DataFrame, spec: dict) -> list[tuple[int, int, float]]:
    """Signal bars -> (bar index, side, absolute stop distance). No lookahead."""
    p, entry = spec["params"], spec["entry"]
    rule, atr_k = entry["rule"], float(p["atr_k"])
    if rule == "donchian_breakout":
        entries = _donchian(bars, int(p["N"]), atr_k)
    elif rule == "ema_state":
        bars = ensure_emas(bars, int(p["fast"]), int(p["slow"]))
        entries = _ema_state(bars, int(p["fast"]), int(p["slow"]), atr_k)
    elif rule == "zscore_fade":
        entries = _zscore(bars, int(p["N"]), float(p.get("z", 2.0)), atr_k)
    elif rule == "orb_session":
        sessions = tuple((int(h), int(m)) for h, m in (s.split(":") for s in entry["sessions"]))
        entries = _orb(bars, int(p["range_bars"]), sessions, atr_k)
    else:  # pragma: no cover - guarded by the schema
        raise SystemExit(f"regla desconocida: {rule}")

    floor = float(p.get("stop_floor_frac") or 0.0)
    if floor:
        close = bars["close"].to_numpy()
        entries = [(i, side, max(dist, floor * close[i])) for i, side, dist in entries]
    return entries


# -------------------------------------------------------------------- engine
def run_trades(bars: pd.DataFrame, entries, spec: dict) -> pd.DataFrame:
    ex = sc.Exit(float(spec["params"]["atr_k"]), float(spec["params"]["tp_r"]),
                 int(spec["exit"]["time_stop_bars"]))
    return sc.run_trades(bars, entries, ex)


def vol_factors(bars: pd.DataFrame, trades: pd.DataFrame, spec: dict) -> np.ndarray:
    """Per-trade size multiplier from realised volatility *before* the entry.

    Volatility targeting (Barroso & Santa-Clara 2015) applied to crypto momentum
    lifts the Sharpe because the strategy's own variance is predictable even when
    its mean is not: the position shrinks when the tape is violent. The multiplier
    uses only bars up to the signal bar, so there is no lookahead, and it is
    floored and capped so a quiet stretch cannot lever the book and a crash cannot
    switch the strategy off.
    """
    risk = spec.get("risk") or {}
    target = risk.get("target_vol_annual")
    if risk.get("sizing") != "vol_target" or not target:
        return np.ones(len(trades))

    lookback = int((spec.get("params") or {}).get("vol_lookback_bars") or 30)
    floor = float((spec.get("params") or {}).get("vol_floor_mult") or 0.5)
    cap = float(risk.get("max_gross_leverage") or 2.0)

    close = bars["close"].to_numpy(dtype=float)
    ret = np.zeros_like(close)
    ret[1:] = close[1:] / close[:-1] - 1.0

    entry = trades["entry_i"].to_numpy()
    out = np.ones(len(trades))
    for k, i in enumerate(entry):
        lo = max(int(i) - lookback, 1)
        # `entry_i` es la vela de entrada: su retorno usa su cierre, que aún no
        # existía cuando se decidió abrir en la siguiente apertura.
        window = ret[lo:int(i)]
        if window.size < 5:
            continue
        sd = float(window.std(ddof=1))
        if not np.isfinite(sd) or sd <= 0:
            continue
        realised_annual = sd * math.sqrt(365)
        out[k] = min(max(float(target) / realised_annual, floor), cap)
    return out


def run_portfolio(bars: pd.DataFrame, spec: dict, trades_of, entries_of):
    """Run one spec, or every component of a portfolio spec, as one trade stream.

    Returns `(trades, weights)`. `weights` is None for a single spec and a per-trade
    array for a portfolio. Components run sequentially and their trades merge by exit
    time, so the merged stream is what a single account would have experienced, not a
    sum of independent backtests. Weights come from the spec and are never fitted.
    """
    port = spec.get("portfolio")
    if not port:
        entries = entries_of(bars, spec)
        return trades_of(bars, entries, spec), None

    comps = port["components"]
    if port["weighting"] == "equal":
        raw = {c["label"]: 1.0 / len(comps) for c in comps}
    else:
        raw = {c["label"]: float(c.get("weight") or 0.0) for c in comps}
    total = sum(raw.values())
    if total <= 0:
        raise SystemExit("portfolio sin pesos positivos")
    w = {k: v / total for k, v in raw.items()}

    frames = []
    for c in comps:
        sub = json.loads(json.dumps(spec))
        sub["portfolio"] = None
        sub["params"] = {**spec["params"], **c["params"]}
        sub["label"] = c["label"]
        t = trades_of(bars, entries_of(bars, sub), sub).copy()
        if t.empty:
            continue
        t["component"] = c["label"]
        t["weight"] = w[c["label"]]
        frames.append(t)
    if not frames:
        return pd.DataFrame(), None
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.sort_values(["exit_i", "entry_i"], kind="stable").reset_index(drop=True)
    return merged, merged["weight"].to_numpy(dtype=float)


# ------------------------------------------------------------------ metrics
def pf(x: np.ndarray) -> float:
    gp = x[x > 0].sum()
    gl = -x[x < 0].sum()
    return float(gp / gl) if gl > 0 else float("inf")


def block_ci(r: np.ndarray, block: int = BLOCK, reps: int = REPS, seed: int = 7) -> dict:
    """Stationary block bootstrap of the profit factor (PROMPT_V4 section 5.8)."""
    rng = np.random.default_rng(seed)
    n = len(r)
    out = np.empty(reps)
    for k in range(reps):
        idx: list[int] = []
        while len(idx) < n:
            s = int(rng.integers(0, n))
            idx.extend(range(s, min(s + block, n)))
        out[k] = pf(r[np.array(idx[: n])])
    out = out[np.isfinite(out)]
    if not len(out):
        return {"pf_ci95": [None, None], "pf_se": None}
    return {
        "pf_ci95": [round(float(np.percentile(out, 2.5)), 3),
                    round(float(np.percentile(out, 97.5)), 3)],
        "pf_se": round(float(out.std(ddof=1)), 3),
    }


def annualised_alpha(strategy_daily: pd.Series, bh_daily: pd.Series,
                     seed: int = 7, block: int = BLOCK, reps: int = REPS) -> dict:
    """Excess annualised return versus buy & hold, with a block-bootstrap CI."""
    joined = pd.concat([strategy_daily.rename("s"), bh_daily.rename("b")], axis=1,
                       sort=False).fillna(0.0)
    diff = (joined["s"] - joined["b"]).to_numpy()
    if not len(diff):
        return {"alpha_annual": None, "ci95": [None, None], "method": "empty"}
    rng = np.random.default_rng(seed)
    n = len(diff)
    boot = np.empty(reps)
    for k in range(reps):
        idx: list[int] = []
        while len(idx) < n:
            s = int(rng.integers(0, n))
            idx.extend(range(s, min(s + block, n)))
        boot[k] = diff[np.array(idx[:n])].mean()
    return {
        "alpha_annual": round(float(diff.mean() * 365), 4),
        "ci95": [round(float(np.percentile(boot, 2.5) * 365), 4),
                 round(float(np.percentile(boot, 97.5) * 365), 4)],
        "method": "mean daily excess return vs vol-unmatched buy & hold, stationary "
                  f"block bootstrap block={block} reps={reps} seed={seed}",
        "bh_cagr": round(float((1 + bh_daily).prod() ** (365.25 / max(len(bh_daily), 1)) - 1), 4),
        "strategy_cagr": round(float((1 + strategy_daily).prod() ** (365.25 / max(len(strategy_daily), 1)) - 1), 4),
    }


def subset(trades: pd.DataFrame, bars: pd.DataFrame, lo: float, hi: float) -> pd.DataFrame:
    if trades.empty:
        return trades
    ts = bars["ts"].to_numpy()[trades["exit_i"].to_numpy()]
    years = (bars["ts"].iloc[-1] - bars["ts"].iloc[0]).days / 365.25
    start = bars["ts"].iloc[0]
    sel = (ts >= start + pd.Timedelta(days=lo * years * 365.25)) & \
          (ts < start + pd.Timedelta(days=hi * years * 365.25))
    return trades.loc[sel]


def metrics_block(trades: pd.DataFrame, bars: pd.DataFrame, r_net: np.ndarray,
                  r_stress: np.ndarray, fee_r: np.ndarray, fund_r: np.ndarray,
                  seed: int, block: int, reps: int) -> dict:
    if trades.empty:
        return {"n": 0}
    order = np.argsort(bars["ts"].to_numpy()[trades["exit_i"].to_numpy()])
    t = trades.iloc[order]
    rn, rs = r_net[order], r_stress[order]
    exit_ts = pd.DatetimeIndex(bars["ts"].to_numpy()[t["exit_i"].to_numpy()])
    eq = (1 + RISK * rn).cumprod()
    ser = pd.Series(eq, index=exit_ts).sort_index()
    daily = ser.resample("D").last().ffill().pct_change().fillna(0.0)
    sd = daily.std(ddof=1)
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd and sd > 0 else 0.0
    years = len(daily) / 365
    # How much of the sample the book was actually exposed, and how many trades it
    # needed. A profit factor means nothing without this: 1.5 with 3% exposure is a
    # different object than 1.5 always invested, and the first one leaves capital idle.
    entry_i = t["entry_i"].to_numpy()
    exit_i = t["exit_i"].to_numpy()
    # Union, not sum: with a five-component ensemble the bars overlap, and adding
    # each component's holding time would report 100% exposure by construction.
    occupied = np.zeros(len(bars), dtype=bool)
    for a, b in zip(entry_i, exit_i):
        occupied[int(a):min(int(b) + 1, len(bars))] = True
    exposure = float(occupied.mean())
    return {
        "n": int(len(t)),
        "win": round(float((rn > 0).mean()), 3),
        "pf_gross": round(pf(t["r_gross"].to_numpy()), 3),
        "pf_net": round(pf(rn), 3),
        "pf_stress": round(pf(rs), 3),
        "exp_gross_r": round(float(t["r_gross"].mean()), 4),
        "exp_net_r": round(float(rn.mean()), 4),
        "exp_stress_r": round(float(rs.mean()), 4),
        "sharpe": round(sharpe, 2),
        "mdd": round(float((ser / ser.cummax() - 1).min()), 3),
        "t_stat": round(float(sharpe * math.sqrt(years)), 2),
        "years": round(years, 2),
        "time_in_market": round(exposure, 3),
        "trades_per_year": round(float(len(t) / years), 1) if years else None,
        "r_per_year": round(float(rn.sum() / years), 2) if years else None,
        "stop_frac_median": round(float(np.median(t["stop_dist_frac"].to_numpy())), 5),
        "fee_r": round(float(fee_r[order].mean()), 4),
        "funding_r": round(float(fund_r[order].mean()), 4),
        **block_ci(rn, block=block, reps=reps, seed=seed),
        "_daily": daily,
        "_equity_monthly": monthly(ser),
    }


def carry_block(trades: pd.DataFrame, r_net: np.ndarray, fund_r: np.ndarray) -> dict:
    """Split trades by whether the position paid or collected funding.

    Crypto carry (long spot / short perp) was the dominant documented premium and
    its return compressed sharply after 2024 (BIS WP 1087). Here the question is
    narrower and testable: does a trade that *collects* funding beat one that pays
    it, net of everything else? If the two buckets show the same profit factor, the
    funding is a cost to budget and not a signal to trade on.
    """
    if trades.empty or fund_r.size != len(trades):
        return {}
    collects = fund_r < 0          # funding_r is a cost: negative means received
    out = {}
    for label, mask in (("cobra funding", collects), ("paga funding", ~collects)):
        if not mask.any():
            out[label] = {"n": 0}
            continue
        x = r_net[mask]
        gp, gl = x[x > 0].sum(), -x[x < 0].sum()
        out[label] = {
            "n": int(mask.sum()),
            "pf": round(float(gp / gl), 3) if gl > 0 else None,
            "exp_r": round(float(x.mean()), 4),
            "win": round(float((x > 0).mean()), 3),
            "funding_r_mean": round(float(fund_r[mask].mean()), 4),
            "share": round(float(mask.mean()), 3),
        }
    if out.get("cobra funding", {}).get("n") and out.get("paga funding", {}).get("n"):
        a = out["cobra funding"]["pf"] or 0.0
        b = out["paga funding"]["pf"] or 0.0
        out["spread_pf"] = round(float(a - b), 3)
    return out


def regime_block(trades: pd.DataFrame, bars: pd.DataFrame, r_net: np.ndarray) -> dict:
    """Split the trades by the market regime they were opened in.

    Two axes, each cut at its own terciles over the whole sample so the buckets
    are balanced by construction:
      volatility  ATR(14)/close at the entry bar (low / mid / high)
      trend       20-bar absolute return at the entry bar (quiet / drifting / trending)

    Informative, not a gate: the point is to see whether the edge lives in one
    bucket only, which is the same failure mode the plateau study catches in the
    parameter axis.
    """
    if trades.empty:
        return {}
    idx = trades["entry_i"].to_numpy()
    close = bars["close"].to_numpy(dtype=float)
    atr = bars["atr"].to_numpy(dtype=float) if "atr" in bars else None
    if atr is None:
        return {}
    vol = atr[idx] / close[idx]
    look = 20
    trend = np.abs(close[idx] / close[np.maximum(idx - look, 0)] - 1.0)

    def bucket(values: np.ndarray, labels: tuple[str, str, str], name: str) -> dict:
        q1, q2 = np.quantile(values, [1 / 3, 2 / 3])
        masks = (values < q1,
                 (values >= q1) & (values < q2),
                 values >= q2)
        out = {}
        for k, lab in enumerate(labels):
            mask = masks[k]
            if mask.sum() < 3:
                out[lab] = {"n": int(mask.sum()), "pf": None, "exp_r": None, "win": None}
                continue
            r = r_net[mask]
            out[lab] = {
                "n": int(mask.sum()),
                "pf": round(pf(r), 4),
                "exp_r": round(float(r.mean()), 4),
                "win": round(float((r > 0).mean()), 4),
            }
        return {"axis": name, "cuts": [round(float(q1), 6), round(float(q2), 6)], "buckets": out}

    vol_b = bucket(vol, ("baja", "media", "alta"), "volatilidad ATR/close")
    tr_b = bucket(trend, ("quieto", "deriva", "tendencia"), "retorno absoluto 20 barras")
    spreads = {axis: [b["pf"] for b in blk["buckets"].values() if b["pf"] is not None]
               for axis, blk in (("volatility", vol_b), ("trend", tr_b))}
    worst = min((min(v) for v in spreads.values() if v), default=None)
    best = max((max(v) for v in spreads.values() if v), default=None)
    # Concentrated: at least one bucket loses money while another makes money.
    concentrated = any(v and min(v) < 1.0 <= max(v) for v in spreads.values())
    losing = {axis: [k for k, b in blk["buckets"].items() if b["pf"] is not None and b["pf"] < 1.0]
              for axis, blk in (("volatility", vol_b), ("trend", tr_b))}
    return {
        "volatility": vol_b,
        "trend": tr_b,
        "pf_spread": round(float(best - worst), 4) if spreads else None,
        "concentrated": bool(concentrated),
        "losing_buckets": {k: v for k, v in losing.items() if v},
    }


def monthly(ser: pd.Series) -> list[float]:
    m = ser.resample("ME").last().ffill()
    m = pd.concat([pd.Series([1.0]), m]).reset_index(drop=True)
    return [round(float(v), 4) for v in m]


def breakeven_rt_bps(trades: pd.DataFrame, fund_r: np.ndarray, lo=0.0, hi=500.0) -> float:
    """Round-trip cost in bps at which net profit factor crosses 1.00."""
    if trades.empty:
        return float("nan")

    def net_pf(rt_bps: float) -> float:
        r = trades["r_gross"].to_numpy() - (rt_bps * BPS) / trades["stop_dist_frac"].to_numpy() - fund_r
        return pf(r)

    if net_pf(lo) <= 1.0:
        return None
    if net_pf(hi) > 1.0:
        return hi
    for _ in range(60):
        mid = (lo + hi) / 2
        if net_pf(mid) > 1.0:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 2)


# ------------------------------------------------------------------- plateau
def perturbation_points(spec: dict) -> list[tuple[str, float, int]]:
    p = spec["params"]
    key = next((k for k in ("N", "range_bars", "fast", "slow") if k in p), None)
    if key is None:
        return []
    base = int(p[key])
    floor = 1 if key == "range_bars" else 2
    pts = []
    for delta in (-0.20, -0.10, 0.10, 0.20):
        val = max(floor, int(round(base * (1 + delta))))
        if val != base:
            pts.append((key, delta, val))
    return pts


def run_plateau(df5, spec, bars, fund, fee_rt_bps, seed, block, reps) -> dict:
    rows = []
    for key, delta, value in perturbation_points(spec):
        variant = json.loads(json.dumps(spec))
        variant["params"][key] = value
        try:
            vb, _ = bars_for(df5, spec["timeframe_signal"])
            trades = run_trades(vb, build_entries(vb, variant), variant)
            if trades.empty:
                rows.append({"param": key, "change": delta, "value": value, "pf_net": None})
                continue
            fund_r = funding_in(spec, trades, vb, fund)
            rn = trades["r_gross"].to_numpy() - (fee_rt_bps * BPS) / trades["stop_dist_frac"].to_numpy() - fund_r
            rows.append({"param": key, "change": delta, "value": value,
                         "n": int(len(trades)), "pf_net": round(pf(rn), 3),
                         "exp_net_r": round(float(rn.mean()), 4)})
        except Exception as exc:  # noqa: BLE001
            rows.append({"param": key, "change": delta, "value": value, "error": str(exc)})
    ok = [r for r in rows if r.get("pf_net") is not None]
    passed = bool(ok) and all(r["pf_net"] > gc.MIN_PLATEAU_PF for r in ok) and len(ok) == len(rows) and bool(rows)
    return {"points": rows, "pass": passed if rows else None,
            "rule": f"PF neto > {gc.MIN_PLATEAU_PF:.2f} en todo el vecindario ±10% / ±20%"}


# -------------------------------------------------------------------- funding
def funding_in(spec: dict, trades: pd.DataFrame, bars: pd.DataFrame, fund: pd.DataFrame | None) -> np.ndarray:
    if spec["costs"]["funding"] != "real_timestamps" or fund is None or trades.empty:
        return np.zeros(len(trades))
    return fs.funding_in_R(trades, bars, fund).to_numpy()


# --------------------------------------------------------------------- gates
def gate(value, threshold, op: str, passed) -> dict:
    return {"value": value, "threshold": threshold, "op": op, "pass": passed}


def evaluate(spec: dict, data: dict, all_m: dict, oos_m: dict, stress: dict,
             plateau: dict, bench: dict, missing: list[str],
             validation: dict | None = None) -> tuple[dict, list[str], str]:
    budget = float(spec["risk"]["max_mdd_budget"])
    val = validation or {}
    g: dict = {}

    g["data_integrity"] = gate(data["integrity"]["unexplained_gaps"], 0, "==",
                               data["integrity"]["unexplained_gaps"] == 0
                               and data["integrity"]["duplicates"] == 0)
    pbo_v = (val.get("pbo") or {}).get("pbo")
    dsr_v = (val.get("dsr") or {}).get("dsr")
    wfa_v = (val.get("wfa") or {}).get("min_trades_per_fold")
    g["pbo"] = gate(pbo_v, gc.MAX_PBO, "≤", (pbo_v <= gc.MAX_PBO) if pbo_v is not None else None)
    g["dsr"] = gate(dsr_v, gc.MIN_DSR, "≥", (dsr_v >= gc.MIN_DSR) if dsr_v is not None else None)
    g["oos_t_stat"] = gate(oos_m.get("t_stat"), gc.MIN_OOS_T_STAT, "≥",
                           (oos_m.get("t_stat") or 0) >= gc.MIN_OOS_T_STAT if oos_m.get("n") else None)
    ci_low = (oos_m.get("pf_ci95") or [None])[0]
    g["oos_pf_ci_low"] = gate(ci_low, gc.MIN_OOS_PF_CI_LOW, ">",
                              (ci_low > gc.MIN_OOS_PF_CI_LOW) if ci_low is not None else None)
    g["trades"] = gate(all_m.get("n"), gc.MIN_TRADES, "≥",
                       (all_m.get("n") or 0) >= gc.MIN_TRADES)
    g["wfa_min_trades"] = gate(wfa_v, gc.MIN_WFA_TRADES_PER_FOLD, "≥",
                               (wfa_v >= gc.MIN_WFA_TRADES_PER_FOLD) if wfa_v is not None else None)
    g["cost_stress_2x"] = gate(stress["pf"], gc.MIN_COST_STRESS_PF, ">",
                               stress["pf"] > gc.MIN_COST_STRESS_PF if stress["pf"] is not None else None)
    g["funding_included"] = gate("included" if spec["costs"]["funding"] == "real_timestamps" else "none",
                                 "required", "=", spec["costs"]["funding"] == "real_timestamps")
    g["plateau"] = gate(plateau.get("pass"), True, "=", plateau.get("pass"))
    g["benchmark_alpha"] = gate(bench.get("alpha_annual"), gc.MIN_BENCHMARK_ALPHA_CI_LOW, ">",
                                (bench["ci95"][0] > gc.MIN_BENCHMARK_ALPHA_CI_LOW)
                                if bench.get("ci95") and bench["ci95"][0] is not None else None)
    g["mdd_budget"] = gate(all_m.get("mdd"), -budget, "≥",
                           (all_m.get("mdd") or 0) >= -budget if all_m.get("n") else None)
    # MinBTL no es un umbral sobre una métrica sino sobre la cobertura: cuántos
    # años hay frente a cuántos pide el Sharpe observado. Razón ≥ 1 = alcanza.
    mbtl_years = (val.get("minbtl") or {}).get("minbtl_years")
    coverage_years = (val.get("inputs") or {}).get("coverage_years")
    coverage = (coverage_years / mbtl_years) if (mbtl_years and coverage_years) else None
    g["minbtl"] = gate(round(coverage, 3) if coverage is not None else None,
                       gc.MIN_MINBTL_COVERAGE, "≥",
                       (coverage >= gc.MIN_MINBTL_COVERAGE) if coverage is not None else None)

    for name, art in (("pbo", "validation/pbo"), ("dsr", "validation/dsr"),
                      ("wfa_min_trades", "validation/wfa"),
                      ("minbtl", "validation/minbtl")):
        if g[name]["pass"] is None and art not in missing:
            missing.append(art)
    failed = [k for k in REJECT_ON_FAIL if g.get(k, {}).get("pass") is False]
    soft = [k for k in INCONCLUSIVE_ON_FAIL if g.get(k, {}).get("pass") is False]
    if failed:
        return g, failed, "REJECTED"
    if soft or missing:
        return g, failed, "INCONCLUSIVE"
    return g, failed, "APPROVED"


REASONING = {
    "data_integrity": "la serie no es auditable",
    "pbo": "selección indistinguible del ruido",
    "dsr": "el Sharpe no sobrevive al ajuste por múltiples pruebas",
    "oos_t_stat": "sin significancia tras el haircut HLZ",
    "oos_pf_ci_low": "el intervalo contiene 1,00: no concluyente",
    "trades": "sin potencia estadística",
    "wfa_min_trades": "sin potencia estadística por fold",
    "minbtl": "la historia disponible no cubre los años que pide el Sharpe",
    "cost_stress_2x": "el edge es de coste, no de mercado",
    "funding_included": "coste real desconocido sin funding",
    "plateau": "pico aislado: sobreajuste",
    "benchmark_alpha": "no bate al benchmark",
    "mdd_budget": "excede el riesgo declarado en la spec",
}


def es_num(x, n: int = 2, plus: bool = False) -> str:
    """Spanish-formatted number for the human-readable verdict lines."""
    if x is None:
        return "—"
    txt = f"{x:+.{n}f}" if plus else f"{x:.{n}f}"
    return txt.replace(".", ",").replace("-", "−")

def reason_line(name: str, g: dict, bench: dict) -> str:
    """One Spanish line per failed gate, with the number and the threshold."""
    v, t = g.get("value"), g.get("threshold")
    tail = REASONING.get(name, "no cumple")
    if name == "data_integrity":
        return f"{int(v or 0)} gaps no explicados → {tail}"
    if name == "pbo":
        return f"PBO {es_num(v)} > {es_num(t)} → {tail}"
    if name == "dsr":
        return f"DSR {es_num(v)} < {es_num(t)} → {tail}"
    if name == "oos_t_stat":
        return f"t OOS {es_num(v)} < {es_num(t)} → {tail}"
    if name == "oos_pf_ci_low":
        return f"IC95% inferior del PF OOS {es_num(v)} ≤ {es_num(t)} → {tail}"
    if name == "trades":
        return f"{int(v or 0)} trades < {int(t)} → {tail}"
    if name == "wfa_min_trades":
        if v is None:
            return f"sin WFA sobre esta spec ({int(t)} trades por fold exigidos) → {tail}"
        return (f"{int(v)} trades por fold OOS en el ciclo < {int(t)} "
                f"→ {tail} (el WFA mide el procedimiento de selección, no esta spec)")
    if name == "cost_stress_2x":
        return f"PF con coste 2× {es_num(v)} ≤ {es_num(t)} → {tail}"
    if name == "funding_included":
        return f"funding no aplicado con timestamps reales → {tail}"
    if name == "plateau":
        return f"el vecindario ±10% / ±20% no es plano → {tail}"
    if name == "benchmark_alpha":
        ci = (bench.get("ci95") or [0.0, 0.0])
        span = f"[{es_num(ci[0] * 100, 1, True)}%; {es_num(ci[1] * 100, 1, True)}%]"
        if ci[0] is not None and ci[1] is not None and ci[1] < 0:
            why = "negativo y significativo: el benchmark gana en todo el intervalo"
        elif ci[0] is not None and ci[0] > 0:
            why = "positivo y significativo: bate al benchmark en todo el intervalo"
        else:
            why = "contiene 0: indistinguible del benchmark"
        return f"alpha {es_num(v * 100, 1, True)}% anual con IC95% {span} {why}"
    if name == "mdd_budget":
        return f"MDD {es_num(v * 100, 1)}% < presupuesto −{abs(t) * 100:.0f}% → {tail}"
    return f"{name} no cumple → {tail}"


# ---------------------------------------------------------------------- main
def main() -> None:
    ap = argparse.ArgumentParser(description="Deterministic strategy runner (engine v4.0.0)")
    ap.add_argument("--spec", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--cycle", default="CYCLE-2026-11")
    ap.add_argument("--register", default=None,
                    help="registry base URL, e.g. http://127.0.0.1:8787 (POST /api/runs)")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate the spec and the cost-admission test only, no backtest")
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--validation", type=Path, default=VALIDATION_DIR,
                    help="selection-cycle artifact (PBO/DSR/MinBTL/WFA); a directory "
                         "means 'use the newest one', which is what the registry UI shows")
    args = ap.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    spec = load_spec(args.spec)
    spec_hash = "sha256:" + canonical_hash(spec)
    seed = int(spec["validation"].get("seed", 7))
    block = int((spec["validation"].get("bootstrap") or {}).get("block", BLOCK))
    reps = int((spec["validation"].get("bootstrap") or {}).get("reps", REPS))
    tf = spec["timeframe_signal"]
    fee_rt_bps = 2 * (spec["costs"]["fee_taker_bps"] + spec["costs"]["half_spread_bps"])

    df5, data = load_data()
    if args.dry_run:
        print(json.dumps({
            "spec_hash": spec_hash, "data_hash": data["sha256"][:16],
            "rt_bps": round(fee_rt_bps, 2),
            "expected_cost_R": spec.get("expected", {}).get("cost_R_per_trade") if spec.get("expected") else None,
            "admission": "pass (no backtest executed)",
        }, indent=2))
        return

    bars, basis = bars_for(df5, tf)
    fund = fs.load_funding() if spec["costs"]["funding"] == "real_timestamps" else None

    validation = None
    vpath = args.validation
    if vpath and Path(vpath).is_dir():
        cands = sorted(Path(vpath).glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        vpath = cands[0] if cands else None
    if not vpath:
        cands = sorted(VALIDATION_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        vpath = cands[0] if cands else None
    if vpath and Path(vpath).exists():
        validation = json.loads(Path(vpath).read_text(encoding="utf-8"))
        validation["_source"] = spec_path_display(Path(vpath))
        if validation.get("inputs", {}).get("data_hash") and \
                validation["inputs"]["data_hash"] != data["sha256"][:16]:
            print("aviso: el ciclo de validación se calculó con otro dataset; se ignora",
                  file=sys.stderr)
            validation = None
    elif not args.quiet:
        print("aviso: sin artefacto de validación; PBO/DSR/WFA quedan sin dato", file=sys.stderr)

    entries = build_entries(bars, spec)
    trades, weights = run_portfolio(bars, spec, trades_of=run_trades, entries_of=build_entries)
    if trades.empty:
        raise SystemExit("sin trades: la spec no opera en este dataset")

    fund_r = funding_in(spec, trades, bars, fund)
    d = trades["stop_dist_frac"].to_numpy()
    r_gross = trades["r_gross"].to_numpy()
    fee_r = (fee_rt_bps * BPS) / d
    stress_r = (fee_rt_bps * STRESS_MULT * BPS) / d
    r_net = r_gross - fee_r - fund_r
    r_stress = r_gross - stress_r - fund_r
    # A component's trade risks only its share of the budget, so its contribution
    # to the equity curve is scaled by that share.
    if weights is not None:
        r_net = r_net * weights
        r_stress = r_stress * weights
    vol_mult = vol_factors(bars, trades, spec)
    r_net = r_net * vol_mult
    r_stress = r_stress * vol_mult

    a, o, r = (float(x) for x in spec["validation"]["is_oos_split"].split("/"))
    t_is = subset(trades, bars, 0.0, a)
    t_oos = subset(trades, bars, a, a + o)
    t_res = subset(trades, bars, a + o, 1.0)

    def block_for(t: pd.DataFrame) -> dict:
        if t.empty:
            return {"n": 0}
        idx = trades.index.get_indexer(t.index)
        return metrics_block(t, bars, r_net[idx], r_stress[idx], fee_r[idx], fund_r[idx],
                             seed, block, reps)

    m_all, m_is, m_oos, m_res = block_for(trades), block_for(t_is), block_for(t_oos), block_for(t_res)
    bh_daily = bars.set_index("ts")["close"].resample("D").last().ffill().pct_change().fillna(0.0)
    bh_oos = bh_daily.loc[(bh_daily.index >= bars["ts"].iloc[0] + pd.Timedelta(days=a * m_all["years"] * 365.25))
                          & (bh_daily.index < bars["ts"].iloc[0] + pd.Timedelta(days=(a + o) * m_all["years"] * 365.25))]
    bench = annualised_alpha(m_oos.get("_daily", pd.Series(dtype=float)), bh_oos, seed=seed,
                             block=block, reps=reps) if m_oos.get("n") else {"alpha_annual": None, "ci95": [None, None]}

    stress = {"cost_2x": {"rt_bps": round(fee_rt_bps * STRESS_MULT, 2), "pf": m_all.get("pf_stress")},
              "breakeven_rt_bps": breakeven_rt_bps(trades, fund_r),
              "applied_rt_bps": round(fee_rt_bps, 2)}
    plateau = run_plateau(df5, spec, bars, fund, fee_rt_bps, seed, block, reps)
    regimes = regime_block(trades, bars, r_net)
    carry = carry_block(trades, r_net, fund_r)

    missing: list[str] = []
    gates, failed, verdict = evaluate(spec, data, m_all, m_oos, {"pf": m_all.get("pf_stress")},
                                      plateau, bench, missing, validation)

    for key in ("_daily", "_equity_monthly"):
        for m in (m_all, m_is, m_oos, m_res):
            m.pop(key, None)

    reasoning = []
    for name in failed + [k for k in INCONCLUSIVE_ON_FAIL if gates.get(k, {}).get("pass") is False]:
        reasoning.append(reason_line(name, gates[name], bench))
    if missing and verdict == "INCONCLUSIVE":
        reasoning.append("faltan artefactos del ciclo de selección (" + ", ".join(missing)
                         + "): sin PBO/DSR/WFA el veredicto no puede ser APPROVED")

    # Traceability: the artifact must name the cycle that actually judged it, not
    # the label passed on the command line. Otherwise a run can claim one cycle
    # while citing another cycle's numbers.
    cycle_id = (validation or {}).get("cycle_id") or args.cycle
    if validation and cycle_id != args.cycle:
        print(f"aviso: --cycle {args.cycle} no coincide con el artefacto de validación "
              f"({cycle_id}); se registra el del artefacto", file=sys.stderr)

    result = {
        "spec_id": spec["id"], "version": spec["version"], "name": spec["name"],
        "family": spec["family"], "cycle_id": cycle_id,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": "4.0.0",
        "artifacts": {
            "spec_hash": spec_hash,
            "data_hash": "sha256:" + data["sha256"],
            "code_sha": "sha256:" + code_hash(),
            "seed": seed,
            "env": f"python {sys.version.split()[0]} / pandas {pd.__version__} / numpy {np.__version__}",
            "spec_path": spec_path_display(args.spec),
        },
        "data": {**data, "timeframe_signal": tf, "bars_signal": int(len(bars)), "basis": basis},
        "execution": spec["execution"],
        "costs": {
            "fee_taker_bps": spec["costs"]["fee_taker_bps"],
            "half_spread_bps": spec["costs"]["half_spread_bps"],
            "rt_bps": round(fee_rt_bps, 2),
            "assumed_fill": spec["costs"]["assumed_fill"],
            "impact_model": spec["costs"]["impact_model"],
            "funding": spec["costs"]["funding"],
            "cost_r_mean": (m_all.get("fee_r") or 0) + (m_all.get("funding_r") or 0),
            "fee_r_mean": m_all.get("fee_r"), "funding_r_mean": m_all.get("funding_r"),
        },
        "metrics": {"all": m_all, "is": m_is, "oos": m_oos, "reserve": m_res},
        "stress": stress,
        "robustness": {"perturbation": plateau, "regimes": regimes, "carry": carry},
        "benchmark": bench,
        "validation": {
            "split": spec["validation"]["is_oos_split"],
            "trials_declared": spec["validation"]["trials_declared"],
            "pbo": (validation.get("pbo") or {}).get("pbo") if validation else None,
            "dsr": (validation.get("dsr") or {}).get("dsr") if validation else None,
            "minbtl_years": (validation.get("minbtl") or {}).get("minbtl_years") if validation else None,
            "wfa_min_trades": (validation.get("wfa") or {}).get("min_trades_per_fold") if validation else None,
            "cpcv": ((validation.get("cpcv") or {}).get("share_below_median")
                     if validation else None),
            "cpcv_paths": (validation.get("cpcv") or {}).get("paths") if validation else None,
            "psr": (validation.get("psr") or {}).get("psr") if validation else None,
            "source": validation.get("_source") if validation else None,
            "cycle_id": validation.get("cycle_id") if validation else None,
            "method_version": validation.get("method_version") if validation else None,
            "specs_hash": (validation.get("inputs") or {}).get("specs_hash") if validation else None,
            "universe_size": (validation.get("inputs") or {}).get("universe_size") if validation else None,
            "note": ("PBO, DSR, CPCV y WFA provienen del ciclo de selección y describen el "
                     "procedimiento, no esta configuración suelta. El PSR se reporta contra "
                     "cero y sin deflactar: mide si hay habilidad, no si sobrevive al número "
                     "de pruebas.") if validation else
                    ("PBO/DSR/MinBTL/WFA requieren el ciclo de selección "
                     "(runner/selection_cycle.py); sin él el veredicto no puede pasar de "
                     "INCONCLUSIVE."),
        },
        "gates": gates,
        "verdict": verdict,
        "reasoning": reasoning,
        "missing_artifacts": missing,
        "equity": [],
    }

    # monthly equity for the chart (kept out of the metrics blocks on purpose)
    if m_all.get("n"):
        order = np.argsort(bars["ts"].to_numpy()[trades["exit_i"].to_numpy()])
        rn = (r_gross - fee_r - fund_r)[order]
        ser = pd.Series((1 + RISK * rn).cumprod(),
                        index=pd.DatetimeIndex(bars["ts"].to_numpy()[trades["exit_i"].to_numpy()][order]))
        result["equity"] = monthly(ser.sort_index())

    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / f"{spec['id']}-v{spec['version']}.json"
    out_path.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")

    if not args.quiet:
        print(f"spec   {spec['id']} v{spec['version']}  ({spec['family']}, {tf})")
        print(f"hash   {spec_hash[:23]}  data {data['sha256'][:16]}  bars {len(bars):,} ({basis})")
        print(f"costs  {fee_rt_bps:.2f} bps RT · funding {spec['costs']['funding']}"
              f" · coste medio {result['costs']['cost_r_mean']:.3f} R")
        for label, m in (("all", m_all), ("IS", m_is), ("OOS", m_oos), ("reserve", m_res)):
            if m.get("n"):
                print(f"  {label:8} n={m['n']:6d}  PF neto {m['pf_net']:.3f}  "
                      f"CI95 [{m['pf_ci95'][0]}; {m['pf_ci95'][1]}]  t={m['t_stat']:.2f}  "
                      f"MDD {m['mdd']:.1%}  Sharpe {m['sharpe']:.2f}")
        be = stress["breakeven_rt_bps"]
        print(f"stress 2x PF {stress['cost_2x']['pf']} · break-even "
              + (f"{be} bps RT" if be is not None else "no alcanza PF 1,00 ni con coste 0"))
        print(f"plateau {'OK' if plateau['pass'] else 'FALLA'}: "
              + ", ".join(f"{p['param']}{p['change']:+.0%}={p.get('pf_net')}" for p in plateau["points"]))
        print(f"bench   alpha {bench.get('alpha_annual')} CI95 {bench.get('ci95')}")
        print(f"gates   {sum(1 for v in gates.values() if v['pass'] is True)} pass · "
              f"{len(failed)} fallan · {sum(1 for v in gates.values() if v['pass'] is None)} sin dato")
        print(f"VERDICT {verdict}")
        for line in reasoning:
            print("   ·", line)
        print(f"result  {out_path}")

    if args.register:
        payload = {
            "strategy_id": spec["id"], "version": spec["version"], "cycle_id": cycle_id,
            "label": spec.get("label") or args.spec.stem,
            "params": {**executable_params(spec, tf)},
            "costs": {"fee_taker_bps": spec["costs"]["fee_taker_bps"],
                      "half_spread_bps": spec["costs"]["half_spread_bps"],
                      "rt_bps": round(fee_rt_bps, 2),
                      "stress_rt_bps": round(fee_rt_bps * STRESS_MULT, 2),
                      "funding": spec["costs"]["funding"] == "real_timestamps",
                      "cost_r": round(result["costs"]["cost_r_mean"], 4)},
            "metrics": {k: m_all[k] for k in ("n", "win", "pf_gross", "pf_net", "pf_stress",
                                              "exp_gross_r", "exp_net_r", "exp_stress_r", "sharpe",
                                              "mdd", "t_stat", "pf_ci95", "pf_se", "years",
                                              "time_in_market", "trades_per_year", "r_per_year",
                                              "stop_frac_median", "fee_r", "funding_r")},
            "artifacts": {"spec_hash": spec_hash[:23], "data_hash": data["sha256"][:16],
                          "seed": seed, "source": "runner/run_strategy.py"},
            "equity": result["equity"], "actor": "runner",
            "runner_verdict": verdict,
            "runner_gates": {k: v["pass"] for k, v in gates.items()},
            "alpha_annual": bench.get("alpha_annual"),
            "plateau_pass": plateau["pass"],
            "pbo": (validation.get("pbo") or {}).get("pbo") if validation else None,
            "dsr": (validation.get("dsr") or {}).get("dsr") if validation else None,
            "wfa_min_trades": ((validation.get("wfa") or {}).get("min_trades_per_fold")
                              if validation else None),
            "validation_ref": (validation.get("_source") if validation else None),
            "runner_result": str(out_path.name),
            "notes": "; ".join(reasoning) or "todas las puertas evaluables pasan",
        }
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(f"{args.register.rstrip('/')}/api/runs", data=body,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                print("registro:", resp.status, json.loads(resp.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            print("registro rechazado:", exc.code, exc.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            print("registro fallido:", exc)


def executable_params(spec: dict, tf: str) -> dict:
    """Everything the engine needs to rebuild this run from the registry alone.

    A portfolio run is not defined by `params` alone: the components, the weighting
    and the sizing are what make it different from a single channel. Without them the
    registry row is a number nobody can regenerate, which is the one thing this log
    must never contain. Keys starting with `_` are metadata for the verifier, not
    parameters the rule reads.
    """
    out = {"bar": tf, **{k: v for k, v in spec["params"].items()}}
    out["_max_hold"] = int(spec["exit"]["time_stop_bars"])
    port = spec.get("portfolio")
    if port:
        out["_portfolio"] = {
            "weighting": port["weighting"],
            "components": [{"label": c["label"], "params": c["params"],
                            **(({"weight": c["weight"]}) if c.get("weight") else {})}
                           for c in port["components"]],
        }
    risk = spec.get("risk") or {}
    out["_sizing"] = risk.get("sizing")
    if risk.get("sizing") == "vol_target":
        out["_target_vol_annual"] = risk.get("target_vol_annual")
        out["_max_gross_leverage"] = risk.get("max_gross_leverage")
    return out


if __name__ == "__main__":
    main()
