"""Monitor de régimen del carry, según `docs/PRE-REGISTRO-MONITOR-REGIMEN.md`.

Mediana móvil de 13 ventanas de dispersión capturada frente a la barra de 240 pb
de la geometría de H10. No calcula P&L, no abre nada y no reabre el archivo.

Uso:
    python scripts/regime_monitor.py
    python scripts/regime_monitor.py --panel-dir data/h10ext
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_h10_dispersion as screen_mod  # noqa: E402

LOOKBACK_WEEKS = 13
BAR_BP = 240.0
CUTOFF = "2026-11-30"  # nunca dentro del holdout


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Monitor de régimen del carry")
    parser.add_argument("--panel-dir", default=str(ROOT / "data" / "h10ext"))
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    funding, perp, _freeze = screen_mod.load(Path(args.panel_dir))
    rate, close, quote = screen_mod.panels(funding, perp)

    # Se recorta antes de medir: el holdout no se lee nunca.
    limit = pd.Timestamp(CUTOFF, tz="UTC")
    rate = rate.loc[rate.index <= limit]
    close = close.loc[close.index <= limit]
    quote = quote.loc[quote.index <= limit]

    result = screen_mod.screen(rate, close, quote, screen_mod.DEFAULT_MAX_PER_SIDE)
    series = pd.DataFrame(result["series"])
    series["date"] = pd.to_datetime(series["date"], utc=True)
    series = series.sort_values("date").reset_index(drop=True)
    series["rolling_13"] = series["captured_bp"].rolling(LOOKBACK_WEEKS).median()

    last = series.iloc[-1]
    status = "ACTIVE" if last["rolling_13"] >= BAR_BP else "INACTIVE"
    active = series[series["rolling_13"] >= BAR_BP]
    streak = 0
    for value in reversed(series["rolling_13"].tolist()):
        if np.isnan(value) or value < BAR_BP:
            break
        streak += 1

    summary = {
        "corte": CUTOFF,
        "ultima_semana": last["date"].strftime("%Y-%m-%d"),
        "capturado_ultima_bp": round(float(last["captured_bp"]), 2),
        "mediana_13_bp": round(float(last["rolling_13"]), 2),
        "barra_bp": BAR_BP,
        "estado": status,
        "semanas_activo": int(streak),
        "primera_semana_activa": active["date"].iloc[0].strftime("%Y-%m-%d")
        if len(active) else None,
        "semanas_activas": int(len(active)),
        "ventanas": int(len(series)),
        "regla": "mediana movil 13 semanas >= 240 pb (docs/PRE-REGISTRO-MONITOR-REGIMEN.md)",
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    target = Path(args.json) if args.json else Path(args.panel_dir) / "regime_monitor.json"
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"escrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
