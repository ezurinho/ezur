"""Reconcilia las dos fuentes BTC y construye la fuente única del ciclo.

El CSV de 15m es Binance Spot: es exactamente el remuestreo de
``data/BTC_1m_binance.csv`` y coincide con ``data/BTC_15m_binance.csv``. El
pickle de 5m es Binance USDⓈ-M Futures perpetual (``BTCUSDT_PERP``), según su
manifiesto. Mezclarlos cambia el precio y el volumen de una corrida a otra.

Este script no "corrige" los futuros para que parezcan spot: deja constancia
de la base y del volumen, y construye un 5m desde la misma fuente spot que usa
el perfil. El pickle de futuros se conserva como referencia, no se sobrescribe.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
SPOT_1M = DATA / "BTC_1m_binance.csv"
SPOT_15M = DATA / "BTC_15m_2025.csv"
FUTURES_5M = DATA / "btc_5m.pkl"
FUTURES_MANIFEST = DATA / "btc_5m.freeze.json"
OUT_5M = DATA / "btc_5m_spot.pkl"
OUT_5M_CSV = DATA / "BTC_5m_spot.csv"
OUT_MANIFEST = DATA / "btc_5m_spot.freeze.json"
REPORT = DATA / "research" / "reconciliation" / "btc_sources_2025.json"
SYMBOL_ALIAS = "BTCUSDT_PERP"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _frame15(frame: pd.DataFrame) -> pd.DataFrame:
    typed = frame.copy()
    typed["ts"] = pd.to_datetime(typed["ts"], utc=True)
    typed = typed.sort_values("ts").set_index("ts")
    return (
        typed.resample("15min", label="left", closed="left")
        .agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"})
        .dropna()
    )


def _read_1m() -> pd.DataFrame:
    one = pd.read_csv(SPOT_1M)
    one["ts"] = pd.to_datetime(one["ts"], utc=True)
    one = one.sort_values("ts").set_index("ts")
    if one.index.duplicated().any():
        raise SystemExit("1m spot tiene timestamps duplicados")
    if one.isna().any().any():
        raise SystemExit("1m spot tiene nulos")
    return one


def build_spot_5m(one: pd.DataFrame) -> pd.DataFrame:
    bars = (
        one.resample("5min", label="left", closed="left")
        .agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"})
        .dropna()
        .reset_index()
    )
    bars["symbol"] = SYMBOL_ALIAS
    return bars[["ts", "symbol", "o", "h", "l", "c", "v"]]


def verify_15m(one: pd.DataFrame) -> dict[str, float]:
    spot = _frame15(one.reset_index())
    profile = pd.read_csv(SPOT_15M)
    profile["ts"] = pd.to_datetime(profile["ts"], utc=True)
    profile = profile.set_index("ts").sort_index()
    common = profile.index.intersection(spot.index)
    # El CSV es la ventana 2025-01 -> 2026-10; el 1m spot llega más atrás.
    # Se exige que el CSV esté contenido y que no falte ninguna de sus velas.
    if len(common) != len(profile):
        raise SystemExit(
            f"la rejilla 15m no cubre el CSV: csv={len(profile)} "
            f"spot={len(spot)} común={len(common)}"
        )
    differences = {
        column: float((profile.loc[common, column] - spot.loc[common, column]).abs().max())
        for column in "ohlcv"
    }
    if any(value > 1e-8 for value in differences.values()):
        raise SystemExit(f"la rejilla 15m no coincide: {differences}")
    return differences


def align_2025(one: pd.DataFrame) -> tuple[dict, dict, dict]:
    profile = pd.read_csv(SPOT_15M)
    profile["ts"] = pd.to_datetime(profile["ts"], utc=True)
    profile = profile.set_index("ts").sort_index()
    futures = pd.read_pickle(FUTURES_5M)
    futures["ts"] = pd.to_datetime(futures["ts"], utc=True)
    futures = futures.set_index("ts").sort_index()

    start = pd.Timestamp("2025-01-01", tz="UTC")
    end = pd.Timestamp("2026-01-01", tz="UTC")
    spot15 = profile[(profile.index >= start) & (profile.index < end)]
    futures15 = _frame15(futures.reset_index())
    futures15 = futures15[(futures15.index >= start) & (futures15.index < end)]

    common = spot15.index.intersection(futures15.index)
    missing_profile = int(len(spot15.index.difference(futures15.index)))
    missing_cycle = int(len(futures15.index.difference(spot15.index)))
    spot15 = spot15.loc[common]
    futures15 = futures15.loc[common]
    price = {}
    for column in "ohlcv":
        basis = (futures15[column] / spot15[column] - 1.0) * 10_000.0
        price[column] = {
            "median_bp": float(basis.median()),
            "p95_abs_bp": float(basis.abs().quantile(0.95)),
            "max_abs_bp": float(basis.abs().max()),
        }
    ratio = futures15["v"] / spot15["v"]
    alignment = {
        "common_15m_rows": int(len(common)),
        "missing_profile": missing_profile,
        "missing_cycle": missing_cycle,
        "close_correlation": float(spot15["c"].corr(futures15["c"])),
        "price": price,
        "volume_ratio_cycle_over_profile": {
            "median": float(ratio.median()),
            "p05": float(ratio.quantile(0.05)),
            "p95": float(ratio.quantile(0.95)),
            "note": (
                "los volúmenes pertenecen a mercados distintos; no existe un "
                "factor constante que los haga intercambiables"
            ),
        },
    }
    return alignment, spot15, futures15


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcilia spot y futuros BTC")
    parser.add_argument(
        "--force",
        action="store_true",
        help="sobrescribe las salidas si ya existen (por defecto se niega)",
    )
    args = parser.parse_args()

    if OUT_5M.exists() and not args.force:
        raise SystemExit(f"{OUT_5M} ya existe; usa --force solo si quieres rehacerlo")
    if not all(path.exists() for path in (SPOT_1M, SPOT_15M, FUTURES_5M, FUTURES_MANIFEST)):
        raise SystemExit("faltan una o más fuentes en data/")

    one = _read_1m()
    differences = verify_15m(one)
    bars = build_spot_5m(one)
    bars.to_pickle(OUT_5M)
    bars.to_csv(OUT_5M_CSV, index=False)

    alignment, spot15, futures15 = align_2025(one)
    futures_manifest = json.loads(FUTURES_MANIFEST.read_text(encoding="utf-8"))
    report = {
        "scope": "BTC 15m, 2025-01-01 -> 2026-01-01",
        "profile_source": {
            "path": str(SPOT_15M.relative_to(ROOT)),
            "market": "Binance Spot BTCUSDT",
            "evidence": (
                "BTC_15m_2025.csv == remuestreo 15m de BTC_1m_binance.csv y "
                "subconjunto exacto de BTC_15m_binance.csv"
            ),
            "raw_source": "data.binance.vision spot monthly 1m klines",
            "sha256": _sha256(SPOT_15M),
            "rows_2025": int(len(spot15)),
        },
        "cycle_source": {
            "path": str(FUTURES_5M.relative_to(ROOT)),
            "market": "Binance USDⓈ-M Futures BTCUSDT perpetual (BTCUSDT_PERP)",
            "evidence": futures_manifest["source"],
            "sha256": futures_manifest["sha256"],
            "rows_2025_15m": int(len(futures15)),
        },
        "alignment": alignment,
        "canonical_spot_5m": {
            "path": str(OUT_5M.relative_to(ROOT)),
            "csv": str(OUT_5M_CSV.relative_to(ROOT)),
            "rows": int(len(bars)),
            "first": bars["ts"].iloc[0].isoformat(),
            "last": bars["ts"].iloc[-1].isoformat(),
            "sha256": _sha256(OUT_5M),
            "symbol_alias": (
                f"{SYMBOL_ALIAS}: alias interno que declaran las cinco specs; "
                "precios y volumen son Binance Spot"
            ),
        },
        "decision": (
            "usar Binance Spot 1m como fuente única: el perfil usa su rejilla "
            "15m y el ciclo su rejilla 5m; el pickle de futuros queda como "
            "referencia de reconciliación"
        ),
        "fifteen_minute_match_max_abs": differences,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    manifest = {
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "source": "data.binance.vision spot 1m BTCUSDT",
        "raw": str(SPOT_1M.relative_to(ROOT)),
        "raw_sha256": _sha256(SPOT_1M),
        "rows": int(len(bars)),
        "first": bars["ts"].iloc[0].isoformat(),
        "last": bars["ts"].iloc[-1].isoformat(),
        "sha256": _sha256(OUT_5M),
        "symbol_alias": SYMBOL_ALIAS,
        "note": "rejilla 5m derivada por OHLCV; no se inventan velas",
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(json.dumps({"report": str(REPORT.relative_to(ROOT)), **report["canonical_spot_5m"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
