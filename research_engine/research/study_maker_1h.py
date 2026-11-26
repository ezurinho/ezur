"""Measure the 1h Donchian with a maker-limit fill model.

This is deliberately separate from ``runner/run_strategy.py``.  The runner's
execution model fills every signal at the next bar open and charges taker fees;
using ``fee_maker_bps`` there would be a label, not a measurement.  Here the
entry is a resting limit at the signal close, and the fill has to clear the
queue and survive the adverse-selection filter in ``maker_fills.py``.

Data: the frozen 5m BTCUSDT perp cache, resampled to 1h for the signal.  The
separate spot 1h CSV is not mixed in: its closes differ from the perp cache by
hundreds of dollars, and mixing them would make the comparison meaningless.

Run from research_engine:
    .venv/Scripts/python.exe research/study_maker_1h.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import funding_study as fs
import maker_fills as mf

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
DATA = CACHE / "btc_5m.pkl"
OUT = CACHE / "maker_1h_results.json"

RISK_FRAC = 0.005
MAKER_BPS = 2.0
TAKER_BPS = 5.0
HALF_SPREAD_BPS = 0.07
BPS = 1e-4


def load_5m() -> tuple[pd.DataFrame, str]:
    raw = DATA.read_bytes()
    df = pd.read_pickle(DATA).sort_values("ts").reset_index(drop=True)
    return df, hashlib.sha256(raw).hexdigest()


def resample_1h(df5: pd.DataFrame) -> pd.DataFrame:
    bars = (
        df5.set_index("ts")
        .resample("1h", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
            quote_volume=("quote_volume", "sum"),
            taker_buy_volume=("taker_buy_volume", "sum"),
        )
        .dropna()
        .reset_index()
    )
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True)
    prev_close = bars["close"].shift(1)
    true_range = pd.concat(
        [
            bars["high"] - bars["low"],
            (bars["high"] - prev_close).abs(),
            (bars["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    bars["atr"] = true_range.rolling(14).mean()
    return bars


def donchian_entries(bars: pd.DataFrame, channel: int, atr_k: float) -> list[tuple[int, int, float]]:
    high = bars["high"].to_numpy(dtype=float)
    low = bars["low"].to_numpy(dtype=float)
    close = bars["close"].to_numpy(dtype=float)
    atr = bars["atr"].to_numpy(dtype=float)
    upper = pd.Series(high).rolling(channel).max().shift(1).to_numpy()
    lower = pd.Series(low).rolling(channel).min().shift(1).to_numpy()
    entries: list[tuple[int, int, float]] = []
    for i in range(channel + 1, len(bars) - 1):
        if not np.isfinite(atr[i]) or atr[i] <= 0:
            continue
        if close[i] > upper[i]:
            entries.append((i, 1, atr_k * atr[i]))
        elif close[i] < lower[i]:
            entries.append((i, -1, atr_k * atr[i]))
    return entries


def _utc_naive(value: object) -> pd.Timestamp:
    stamp = pd.Timestamp(value)
    return stamp.tz_convert("UTC").tz_localize(None) if stamp.tzinfo is not None else stamp


def _index_at(stamps: np.ndarray, value: object) -> int:
    return int(np.searchsorted(stamps, _utc_naive(value).to_datetime64(), side="left"))


def simulate_exit(
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    stamps: np.ndarray,
    start_i: int,
    side: int,
    entry: float,
    stop: float,
    target: float,
    entry_ts: pd.Timestamp,
    hold_hours: int,
) -> tuple[int, float, str]:
    """Exit on 5m bars, starting at ``start_i``.

    A maker fill can occur anywhere inside its 5m bar, so its caller starts at
    the next bar: using the fill bar's low/high would be look-ahead.  A taker
    fill at the bar open can start on the same bar.
    """
    deadline = _utc_naive(entry_ts + pd.Timedelta(hours=hold_hours)).to_datetime64()

    for j in range(max(start_i, 0), len(stamps)):
        if stamps[j] >= deadline:
            return j, float(opens[j]), "time"
        if side == 1:
            if opens[j] <= stop:
                return j, float(opens[j]), "gap_stop"
            if opens[j] >= target:
                return j, float(opens[j]), "target"
            if lows[j] <= stop and highs[j] >= target:
                return j, float(stop), "stop"
            if lows[j] <= stop:
                return j, float(stop), "stop"
            if highs[j] >= target:
                return j, float(target), "target"
        else:
            if opens[j] >= stop:
                return j, float(opens[j]), "gap_stop"
            if opens[j] <= target:
                return j, float(opens[j]), "target"
            if highs[j] >= stop and lows[j] <= target:
                return j, float(stop), "stop"
            if highs[j] >= stop:
                return j, float(stop), "stop"
            if lows[j] <= target:
                return j, float(target), "target"

    j = len(stamps) - 1
    return j, float(closes[j]), "time"


def fee_r(entry: float, exit_price: float, reason: str, stop_frac: float, maker: bool) -> float:
    """Fee in R.  Maker entry and target exit; stop/time exits are taker."""
    if maker:
        entry_bps = MAKER_BPS
        exit_bps = MAKER_BPS if reason == "target" else TAKER_BPS + HALF_SPREAD_BPS
    else:
        entry_bps = TAKER_BPS + HALF_SPREAD_BPS
        exit_bps = TAKER_BPS + HALF_SPREAD_BPS
    risk_per_unit = entry * stop_frac
    return (entry * entry_bps + exit_price * exit_bps) * BPS / risk_per_unit


def funding_r(
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    side: int,
    stop_frac: float,
    funding: pd.DataFrame,
) -> float:
    mask = (funding["ts"] > entry_ts) & (funding["ts"] <= exit_ts)
    rate_sum = float(funding.loc[mask, "last_funding_rate"].sum())
    return side * rate_sum / stop_frac


def run_scenario(
    bars: pd.DataFrame,
    df5: pd.DataFrame,
    entries: list[tuple[int, int, float]],
    *,
    maker: bool,
    fill_config: mf.MakerFillConfig | None,
    hold_hours: int,
    tp_r: float,
    funding: pd.DataFrame,
) -> tuple[pd.DataFrame, dict]:
    stamps5 = df5["ts"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    bars_ts = bars["ts"].dt.tz_convert("UTC").dt.tz_localize(None).to_numpy()
    opens5 = df5["open"].to_numpy(dtype=float)
    highs5 = df5["high"].to_numpy(dtype=float)
    lows5 = df5["low"].to_numpy(dtype=float)
    closes5 = df5["close"].to_numpy(dtype=float)
    rows: list[dict] = []
    misses: dict[str, int] = {}
    fill_fractions: list[float] = []
    fill_delays: list[float] = []
    skipped_overlap = 0
    last_exit_i = -1

    for sig_i, side, dist in entries:
        if sig_i <= last_exit_i:
            skipped_overlap += 1
            continue
        if sig_i + 1 >= len(bars):
            break
        start_ts = pd.Timestamp(bars["ts"].iloc[sig_i + 1])
        signal_close = float(bars["close"].iloc[sig_i])

        if maker:
            assert fill_config is not None
            fill = mf.try_maker_fill(df5, start_ts, "long" if side == 1 else "short", signal_close, fill_config)
            if not fill.filled:
                misses[fill.reason] = misses.get(fill.reason, 0) + 1
                continue
            assert fill.fill_ts is not None
            fill_i = _index_at(stamps5, fill.fill_ts)
            entry = signal_close
            entry_ts = pd.Timestamp(fill.fill_ts)
            start_exit_i = fill_i + 1
            fill_fractions.append(fill.fill_fraction)
            fill_delays.append((entry_ts - start_ts).total_seconds() / 60.0)
        else:
            fill_i = _index_at(stamps5, start_ts)
            entry = float(df5["open"].iloc[fill_i])
            entry_ts = pd.Timestamp(df5["ts"].iloc[fill_i])
            start_exit_i = fill_i

        stop = entry - side * dist
        target = entry + side * tp_r * dist
        exit_i5, exit_price, reason = simulate_exit(
            opens5, highs5, lows5, closes5, stamps5,
            start_exit_i, side, entry, stop, target, entry_ts, hold_hours,
        )
        exit_ts = pd.Timestamp(df5["ts"].iloc[exit_i5])
        entry_i1h = max(0, int(np.searchsorted(bars_ts, _utc_naive(entry_ts).to_datetime64(), side="right")) - 1)
        exit_i1h = max(0, int(np.searchsorted(bars_ts, _utc_naive(exit_ts).to_datetime64(), side="right")) - 1)
        stop_frac = dist / entry
        gross = side * (exit_price - entry) / dist
        fee = fee_r(entry, exit_price, reason, stop_frac, maker)
        fund = funding_r(entry_ts, exit_ts, side, stop_frac, funding)
        rows.append(
            {
                "sig_i": sig_i,
                "entry_i": entry_i1h,
                "exit_i": exit_i1h,
                "side": side,
                "entry": entry,
                "exit": exit_price,
                "stop_dist": dist,
                "stop_dist_frac": stop_frac,
                "r_gross": gross,
                "fee_r": fee,
                "funding_r": fund,
                "r_net": gross - fee - fund,
                "reason": reason,
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "fill_fraction": fill_fractions[-1] if maker else 1.0,
            }
        )
        last_exit_i = exit_i1h

    trades = pd.DataFrame(rows)
    eligible = max(0, len(entries) - skipped_overlap)
    meta = {
        "signals": len(entries),
        "eligible_signals": eligible,
        "trades": int(len(trades)),
        "skipped_overlap": skipped_overlap,
        "misses": misses,
        "fill_rate": (len(trades) / eligible) if eligible else 0.0,
        "fill_fraction_mean": float(np.mean(fill_fractions)) if fill_fractions else None,
        "fill_delay_min_mean": float(np.mean(fill_delays)) if fill_delays else None,
    }
    return trades, meta


def _pf(values: np.ndarray) -> float:
    gains = values[values > 0].sum()
    losses = -values[values < 0].sum()
    return float(gains / losses) if losses > 0 else float("inf")


def _pf_ci(values: np.ndarray, *, block: int = 5, reps: int = 2000, seed: int = 7) -> list[float] | None:
    """Stationary block bootstrap of PF; descriptive, not a promotion gate."""
    if len(values) < 10:
        return None
    rng = np.random.default_rng(seed)
    n = len(values)
    out = np.empty(reps, dtype=float)
    for k in range(reps):
        idx: list[int] = []
        while len(idx) < n:
            start = int(rng.integers(0, n))
            idx.extend(range(start, min(start + block, n)))
        sample = values[np.asarray(idx[:n])]
        out[k] = _pf(sample)
    out = out[np.isfinite(out)]
    if not len(out):
        return None
    return [round(float(np.percentile(out, 2.5)), 3), round(float(np.percentile(out, 97.5)), 3)]


def _metrics(trades: pd.DataFrame, bars: pd.DataFrame) -> dict:
    if trades.empty:
        return {"n": 0}
    t = trades.sort_values("exit_ts").copy()
    t["ret"] = RISK_FRAC * t["r_net"]
    eq = (1.0 + t["ret"]).cumprod()
    mdd = float((eq / eq.cummax() - 1.0).min())
    daily = t.groupby(t["exit_ts"].dt.floor("D"))["ret"].sum()
    days = pd.date_range(
        bars["ts"].iloc[0].floor("D"), bars["ts"].iloc[-1].floor("D"), freq="D"
    )
    daily = daily.reindex(days, fill_value=0.0)
    sd = daily.std(ddof=1)
    sharpe = float(daily.mean() / sd * math.sqrt(365)) if sd and sd > 0 else 0.0
    years = (bars["ts"].iloc[-1] - bars["ts"].iloc[0]).days / 365.25
    occupied = np.zeros(len(bars), dtype=bool)
    for entry_i, exit_i in zip(t["entry_i"].to_numpy(), t["exit_i"].to_numpy(), strict=False):
        occupied[int(entry_i) : min(int(exit_i) + 1, len(bars))] = True
    r_net = t["r_net"].to_numpy()
    return {
        "n": int(len(t)),
        "win": round(float((r_net > 0).mean()), 4),
        "pf_gross": round(_pf(t["r_gross"].to_numpy()), 4),
        "pf_net": round(_pf(r_net), 4),
        "pf_ci95": _pf_ci(r_net),
        "exp_gross_r": round(float(t["r_gross"].mean()), 4),
        "exp_net_r": round(float(r_net.mean()), 4),
        "net_r": round(float(r_net.sum()), 2),
        "fee_r": round(float(t["fee_r"].mean()), 4),
        "funding_r": round(float(t["funding_r"].mean()), 4),
        "sharpe": round(sharpe, 2),
        "t_stat": round(float(sharpe * math.sqrt(years)), 2),
        "mdd": round(mdd, 4),
        "years": round(float(years), 2),
        "time_in_market": round(float(occupied.mean()), 3),
        "trades_per_year": round(float(len(t) / years), 1) if years else None,
        "stop_rate": round(float(t["reason"].isin(["stop", "gap_stop"]).mean()), 4),
        "target_rate": round(float((t["reason"] == "target").mean()), 4),
        "by_year": {
            str(year): {
                "n": int(len(group)),
                "net_r": round(float(group["r_net"].sum()), 2),
                "pf": round(_pf(group["r_net"].to_numpy()), 3),
            }
            for year, group in t.groupby(t["exit_ts"].dt.year)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Donchian 1h con fills maker modelados")
    parser.add_argument("--channel", type=int, default=240)
    parser.add_argument("--atr-k", type=float, default=4.0)
    parser.add_argument("--tp-r", type=float, default=2.0)
    parser.add_argument("--hold-hours", type=int, default=240)
    parser.add_argument("--queue-fraction", type=float, default=0.5)
    parser.add_argument("--order-notional", type=float, default=10_000.0)
    parser.add_argument("--adverse-bps", type=float, default=10.0)
    parser.add_argument("--rebound-penalty", type=float, default=1.0)
    parser.add_argument("--max-wait", type=int, default=1)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--no-sensitivity", action="store_true")
    args = parser.parse_args()

    df5, data_hash = load_5m()
    bars = resample_1h(df5)
    entries = donchian_entries(bars, args.channel, args.atr_k)
    funding = fs.load_funding()
    print(
        f"data 5m {len(df5):,} barras · 1h {len(bars):,} · {bars.ts.iloc[0]} -> {bars.ts.iloc[-1]}"
    )
    print(f"señales Donchian {args.channel}: {len(entries)}")

    base_config = mf.MakerFillConfig(
        queue_fraction=args.queue_fraction,
        order_notional_usd=args.order_notional,
        max_wait_bars=args.max_wait,
        adverse_rebound_bps=args.adverse_bps,
        rebound_penalty=args.rebound_penalty,
    )
    scenarios: list[tuple[str, bool, mf.MakerFillConfig | None]] = [
        ("taker", False, None),
        (
            "maker_optimistic",
            True,
            mf.MakerFillConfig(
                queue_fraction=0.0,
                order_notional_usd=args.order_notional,
                max_wait_bars=args.max_wait,
                adverse_rebound_bps=args.adverse_bps,
                rebound_penalty=0.0,
            ),
        ),
        (
            "maker_no_adverse",
            True,
            mf.MakerFillConfig(
                queue_fraction=args.queue_fraction,
                order_notional_usd=args.order_notional,
                max_wait_bars=args.max_wait,
                adverse_rebound_bps=args.adverse_bps,
                rebound_penalty=0.0,
            ),
        ),
        ("maker_base", True, base_config),
        (
            "maker_adverse_only",
            True,
            mf.MakerFillConfig(
                queue_fraction=0.0,
                order_notional_usd=args.order_notional,
                max_wait_bars=args.max_wait,
                adverse_rebound_bps=args.adverse_bps,
                rebound_penalty=args.rebound_penalty,
            ),
        ),
    ]
    if not args.no_sensitivity:
        # A deep queue at a capacity-sized order: this is where the queue term
        # actually bites.  The $10k retail order clears it almost always, and
        # that is a finding, not a reason to hide the term.
        scenarios.append(
            (
                "maker_queue_deep",
                True,
                mf.MakerFillConfig(
                    queue_fraction=0.95,
                    order_notional_usd=250_000.0,
                    max_wait_bars=args.max_wait,
                    adverse_rebound_bps=args.adverse_bps,
                    rebound_penalty=args.rebound_penalty,
                ),
            )
        )

    results: dict[str, dict] = {}
    for name, maker, config in scenarios:
        trades, meta = run_scenario(
            bars,
            df5,
            entries,
            maker=maker,
            fill_config=config,
            hold_hours=args.hold_hours,
            tp_r=args.tp_r,
            funding=funding,
        )
        results[name] = {
            "maker": maker,
            "fill_config": asdict(config) if config else None,
            "fills": meta,
            "metrics": _metrics(trades, bars),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "dataset": {
            "path": str(DATA.relative_to(HERE.parent)),
            "sha256": data_hash,
            "bars_5m": int(len(df5)),
            "bars_1h": int(len(bars)),
            "start": str(bars["ts"].iloc[0]),
            "end": str(bars["ts"].iloc[-1]),
            "basis": "1h resampleado del 5m BTCUSDT perp; no se mezcla el CSV spot de 1h",
        },
        "strategy": {
            "rule": "donchian_breakout",
            "channel": args.channel,
            "atr_k": args.atr_k,
            "tp_r": args.tp_r,
            "hold_hours": args.hold_hours,
            "entry": "limit maker en el cierre de la señal, ventana de 1 barra 1h",
            "exit": "stop/target/time; target maker, stop/time taker",
        },
        "costs": {
            "maker_bps": MAKER_BPS,
            "taker_bps": TAKER_BPS,
            "half_spread_bps": HALF_SPREAD_BPS,
            "funding": "real_timestamps",
        },
        "signals": len(entries),
        "scenarios": results,
        "note": (
            "El modelo de cola usa volumen agresor y penetración del rango, no L2. "
            "El filtro de rebote usa el cierre de la vela de 5m para aproximar la "
            "selección adversa; es conservador y se contrasta con la variante sin "
            "filtro y con la variante optimista de 2 bps. Ninguna variante es una "
            "puerta de promoción."
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    header = (
        f"{'escenario':<20} {'fills':>6} {'fill%':>7} {'PF bruto':>9} "
        f"{'PF neto':>8} {'exp R':>8} {'neto R':>9} {'fee R':>7} {'fund R':>7} {'MDD':>7}"
    )
    print("\n" + header)
    for name, result in results.items():
        m = result["metrics"]
        fills = result["fills"]
        print(
            f"{name:<20} {fills['trades']:>6} {fills['fill_rate']*100:>6.1f}% "
            f"{m.get('pf_gross', float('nan')):>9.3f} {m.get('pf_net', float('nan')):>8.3f} "
            f"{m.get('exp_net_r', float('nan')):>+8.3f} {m.get('net_r', float('nan')):>+9.2f} "
            f"{m.get('fee_r', float('nan')):>7.4f} {m.get('funding_r', float('nan')):>7.4f} "
            f"{m.get('mdd', float('nan')):>7.2%}"
        )
    print("\nPF neto IC95% (block bootstrap):")
    for name, result in results.items():
        print(f"  {name:<20} {result['metrics'].get('pf_ci95')}")
    print("\nfills base:", results["maker_base"]["fills"])
    print("resultado:", args.out)


if __name__ == "__main__":
    main()
