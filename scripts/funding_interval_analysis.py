"""Cuánto de la dispersión de funding explica el intervalo corto y cuánto la prima.

Sobre el panel extendido 2020-2026 con `interval_h`, mide por año y por semana:

- dispersión transversal del funding diario real (`rate`, cash) y de la
  convención de 8 h (`rate8h`, la de H5, que multiplica cada evento por 8/interval);
- proporción de símbolos con intervalo < 8 h;
- descomposición de la varianza entre grupos (corto vs 8 h);
- contrafactual: dispersión si se excluyen los de intervalo corto;
- y el contraste dentro del mismo símbolo (semanas de 8 h frente a semanas cortas).

Uso:
    python scripts/funding_interval_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data" / "h10ext" / "funding_daily.csv"
OUT = ROOT / "data" / "h10ext" / "dispersion.json"


def weekly(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["week"] = frame["dt"].dt.to_period("W-SUN")
    grouped = frame.groupby(["symbol", "week"], as_index=False).agg(
        cash=("rate", "mean"),
        eq8h=("rate8h", "mean"),
        interval=("interval_h", "median"),
        days=("rate", "size"),
    )
    return grouped[grouped["days"] >= 3]


def decompose(group: pd.DataFrame) -> dict:
    cash = group["cash"].to_numpy()
    short = (group["interval"] < 8).to_numpy()
    total_var = float(np.var(cash, ddof=1)) if len(cash) > 2 else 0.0
    if short.sum() < 10 or (~short).sum() < 10:
        return {"var_total": total_var, "entre_grupos": None}
    mean_short = float(cash[short].mean())
    mean_eight = float(cash[~short].mean())
    share = float(short.mean())
    between = share * (mean_short - float(cash.mean())) ** 2 \
        + (1 - share) * (mean_eight - float(cash.mean())) ** 2
    return {
        "var_total": total_var,
        "var_entre": float(between),
        "entre_pct": round(100 * between / total_var, 1) if total_var > 0 else None,
        "media_corta_bp": round(mean_short * 1e4, 2),
        "media_8h_bp": round(mean_eight * 1e4, 2),
        "proporcion_corta": round(share, 3),
        "disp_8h_solo_bp": round(float(np.std(cash[~short], ddof=1)) * 1e4, 2),
        "disp_corta_bp": round(float(np.std(cash[short], ddof=1)) * 1e4, 2),
        "n_corta": int(short.sum()),
        "n_8h": int((~short).sum()),
        "var_corta_share": round(float(np.var(cash[short], ddof=1) * short.mean() / total_var), 3)
        if total_var > 0 else None,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    frame = pd.read_csv(PANEL, parse_dates=["dt"])
    frame["dt"] = pd.to_datetime(frame["dt"], utc=True).dt.floor("D")
    weeks = weekly(frame)
    weeks["year"] = weeks["week"].dt.year

    out: dict = {"por_anio": {}}
    for year, group in weeks.groupby("year"):
        cash_bp = group["cash"] * 1e4
        eq_bp = group["eq8h"] * 1e4
        record = {
            "simbolos": int(group["symbol"].nunique()),
            "semanas": int(group["week"].nunique()),
            "observaciones": int(len(group)),
            "cash_medio_bp": round(float(cash_bp.mean()), 2),
            "cash_p50_bp": round(float(cash_bp.median()), 2),
            "disp_cash_bp": round(float(cash_bp.std(ddof=1)), 2),
            "disp_eq8h_bp": round(float(eq_bp.std(ddof=1)), 2),
            "p90_p10_cash_bp": round(float(cash_bp.quantile(0.9) - cash_bp.quantile(0.1)), 2),
            "proporcion_corta": round(float((group["interval"] < 8).mean()), 3),
        }
        record.update(decompose(group))
        out["por_anio"][str(year)] = record
        print(f"{year}: {record['simbolos']:4d} símbolos · cortos {record['proporcion_corta']:.1%} · "
              f"cash medio {record['cash_medio_bp']:7.2f} pb/día · disp cash {record['disp_cash_bp']:7.2f} · "
              f"disp 8h-eq {record['disp_eq8h_bp']:7.2f} · entre-grupos {record.get('entre_pct')}% "
              f"· disp 8h-solo {record.get('disp_8h_solo_bp')}")

    # Contraste dentro del mismo símbolo en 2026.
    w26 = weeks[weeks["year"] == 2026]
    inside = []
    for symbol, group in w26.groupby("symbol"):
        short = group[group["interval"] < 8]["cash"]
        eight = group[group["interval"] >= 8]["cash"]
        if len(short) >= 4 and len(eight) >= 4:
            inside.append({
                "symbol": symbol,
                "cash_corto_bp": float(short.mean() * 1e4),
                "cash_8h_bp": float(eight.mean() * 1e4),
            })
    out["dentro_2026"] = {
        "simbolos_que_cambian": len(inside),
        "cash_medio_corto_bp": round(float(np.mean([r["cash_corto_bp"] for r in inside])), 2)
        if inside else None,
        "cash_medio_8h_bp": round(float(np.mean([r["cash_8h_bp"] for r in inside])), 2)
        if inside else None,
        "ratio_mediana": round(float(np.median([r["cash_corto_bp"] / r["cash_8h_bp"] for r in inside
                                                if r["cash_8h_bp"] > 0])), 3) if inside else None,
    }
    print(f"\ndentro del mismo símbolo en 2026: {out['dentro_2026']}")

    # Cuánto de la subida 2023-25 -> 2026 viene del grupo corto.
    base = weeks[weeks["year"].between(2023, 2025)]
    now = w26
    for label, group in (("2023-2025", base), ("2026", now)):
        eight = group[group["interval"] >= 8]["cash"] * 1e4
        print(f"{label}: disp solo 8h {float(eight.std(ddof=1)):.2f} pb · "
              f"disp total {float((group['cash'] * 1e4).std(ddof=1)):.2f} pb")

    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nescrito {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
