"""PBO, DSR y CPCV de la medición H5-sobre-H10, con el panel extendido.

La primera versión de `docs/MEDICION-H5-PANEL-H10.md` decía que el bloque de
desarrollo (2020-2024) no se podía reproducir y que por eso no había PBO, DSR ni
CPCV. Era falso: `data/h10ext` cubre 2020-01/2026-10 con el mismo panel y el
motor validado. Este script cierra esa deuda.

No mide una familia nueva ni toca el holdout: corre el motor ya validado sobre
las tres geometrías que el documento publicó y calcula las tres métricas de
selección sobre la matriz diaria que forman. El espacio de búsqueda es, por
tanto, el que de verdad se consideró al elegir qué publicar, no una rejilla
inventada después.

Uso:
    python scripts/selection_h10ext.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from server.selection import (  # noqa: E402
    _psr_from, cpcv, cscv_pbo, deflated_sharpe, norm_ppf, sharpe_daily,
)
from validate_h5_engine import load_h10, replay  # noqa: E402

PANEL = "h10ext"
BLOCKS = 10
TRIALS_LAB = 54
GAMMA = 0.5772156649015329

WINDOWS = {
    "desarrollo 2020-2024": (pd.Timestamp("2020-04-01", tz="UTC"),
                             pd.Timestamp("2025-01-01", tz="UTC")),
    "completo 2020-2026": (pd.Timestamp("2020-04-01", tz="UTC"),
                           pd.Timestamp("2026-11-01", tz="UTC")),
}

CONFIGS = (
    ("quintil sin filtro", None, 0.0),
    ("quintil con filtro 5M", None, 5_000_000.0),
    ("k=4 con filtro 5M", 4, 5_000_000.0),
)


def run_window(start: pd.Timestamp, end: pd.Timestamp) -> dict:
    rate, close, quote, _ = load_h10(folder=PANEL, start=start, end=end)
    adv = quote.rolling(30, min_periods=20).median().shift(1)
    curves: dict[str, pd.Series] = {}
    summary: dict[str, dict] = {}
    for label, per_side, min_adv in CONFIGS:
        result = replay(rate, close, persistent=True, ffill=False, strict=False,
                        per_side=per_side, adv=adv, min_adv=min_adv, daily_out=True)
        daily = result.pop("diario")
        curves[label] = pd.Series({pd.Timestamp(d, tz="UTC"): v
                                   for d, v in daily.items()}).sort_index()
        summary[label] = {k: result[k] for k in
                          ("episodios", "operaciones", "neto_compuesto", "pf",
                           "esperanza_R", "coste_R", "sin_top5")}
        summary[label]["sharpe_diario"] = round(float(sharpe_daily(
            curves[label].to_numpy())), 5)
        print(f"  {label}: {summary[label]}", flush=True)

    matrix = pd.concat(curves, axis=1).fillna(0.0)
    matrix = matrix.loc[matrix.index < end]
    srs = np.array([sharpe_daily(matrix[c].to_numpy()) for c in matrix.columns])
    best = matrix.columns[int(np.argmax(srs))]
    r = matrix[best].to_numpy()
    n = r.size
    skew = float(pd.Series(r).skew())
    kurt = float(pd.Series(r).kurt()) + 3.0

    # Umbral de 54 ensayos bajo nulos independientes: Var(SR) ≈ 1/T.
    sr0_54 = (math.sqrt(1.0 / n)
              * ((1 - GAMMA) * norm_ppf(1 - 1 / TRIALS_LAB)
                 + GAMMA * norm_ppf(1 - 1 / (TRIALS_LAB * math.e))))
    psr_54 = _psr_from(float(srs.max()), n, skew, kurt, sr0_54)

    per_config = {c: deflated_sharpe(matrix[c].to_numpy(), srs)
                  for c in matrix.columns}
    dsr_54 = {}
    for name, value in per_config.items():
        if value.get("dsr") is None:
            dsr_54[name] = None
            continue
        adjusted = _psr_from(float(value["sharpe_daily"]), n, float(value["skew"]),
                             float(value["kurtosis"]), sr0_54)
        dsr_54[name] = None if adjusted is None else round(float(adjusted), 4)

    return {
        "desde": start.strftime("%Y-%m-%d"),
        "hasta": end.strftime("%Y-%m-%d"),
        "dias": int(n),
        "configs": summary,
        "pbo": cscv_pbo(matrix, blocks=BLOCKS),
        "cpcv": cpcv(matrix, blocks=BLOCKS, test_blocks=2, purge=1),
        "dsr_espacio": deflated_sharpe(matrix[best].to_numpy(), srs),
        "dsr_por_config": per_config,
        "dsr_54_por_config": dsr_54,
        "dsr_54_nulo": {
            "dsr": None if psr_54 is None else round(float(psr_54), 4),
            "mejor": best,
            "sharpe_diario": round(float(srs.max()), 5),
            "sr0_diario": round(float(sr0_54), 5),
            "observaciones": int(n),
            "supuesto": "Var(SR)=1/T, 54 ensayos independientes; no es la "
                        "dispersión empírica del ledger, que no se guarda",
        },
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    payload = {
        "panel": PANEL,
        "motor": "scripts/validate_h5_engine.py · replay (validado contra funding_xs)",
        "ventanas": {},
        "nota": "Diagnóstico de selección sobre familias ya archivadas. No añade "
                "ensayos ni mide el holdout.",
    }
    for label, (start, end) in WINDOWS.items():
        print(f"\n{label} ({start.date()}/{end.date()})", flush=True)
        payload["ventanas"][label] = run_window(start, end)

    target = ROOT / "data" / PANEL / "selection.json"
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(f"\nescrito {target}")
    for label, block in payload["ventanas"].items():
        print(f"{label}: PBO {block['pbo'].get('pbo')} · "
              f"CPCV bajo mediana {block['cpcv'].get('share_below_median')} · "
              f"DSR(3) {block['dsr_espacio'].get('dsr')} · "
              f"DSR(54) {block['dsr_54_nulo']['dsr']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
