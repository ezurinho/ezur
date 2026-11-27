"""Sensibilidad de coste de las familias archivadas con el coste medido.

Aplica el *fallback* declarado en `docs/PRE-REGISTRO-COSTE.md` §6 —medianas
empíricas por cubeta y tamaño, con interpolación log-log entre tamaños medidos—
porque el ajuste `a + b·sqrt(S/ADV)` no pasó sus puertas (G2 y G5).

No re-ejecuta ningún simulador: re-expresa el coste de cada familia, que es lineal
en el nocional, sobre los componentes ya publicados en sus archivos.

Uso:
    python scripts/cost_sensitivity.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / "data" / "cost" / "model.json"
R_USD = 250.0

# Componentes publicados en cada archivo; el coste declarado va en pb por lado.
FAMILIES = [
    {"name": "H5 candidata (Q20-Z90-W)", "file": "ARCHIVO-H5", "price": 6672.63,
     "funding": 856.80, "costs": 1500.00, "ops": 800, "notional": 3125.0,
     "declared_bp": 6.0, "buckets": ["C4 20-100M", "C5 >100M"]},
    {"name": "H5 raw (Q20-RAW-W)", "file": "ARCHIVO-H5", "price": 7092.37,
     "funding": 2442.63, "costs": 1192.50, "ops": 636, "notional": 3125.0,
     "declared_bp": 6.0, "buckets": ["C4 20-100M", "C5 >100M"]},
    {"name": "H8 spread entre venues", "file": "ARCHIVO-H8", "price": 19.20,
     "funding": 179.90, "costs": 119.00, "ops": 34, "notional": 3125.0,
     "declared_bp": 7.0, "buckets": ["C5 >100M"]},
    {"name": "H9 basis spot-perp", "file": "ARCHIVO-H9", "price": 18.39,
     "funding": 122.37, "costs": 192.50, "ops": 44, "notional": 3125.0,
     "declared_bp": 10.0, "buckets": ["C4 20-100M", "C5 >100M"]},
    {"name": "H10 quintil (k=9)", "file": "MEDICION-H5-PANEL-H10", "price": 9563.23,
     "funding": 7533.23, "costs": 1502.03, "ops": 9404, "notional": 1389.0,
     "declared_bp": 10.0, "buckets": ["C3 5-20M"]},
    {"name": "H10 k=4 (extremo)", "file": "MEDICION-H5-PANEL-H10", "price": 7165.68,
     "funding": 33894.44, "costs": 2190.00, "ops": 1168, "notional": 3125.0,
     "declared_bp": 10.0, "buckets": ["C3 5-20M", "C4 20-100M"]},
]


def cost_at(bucket: dict, size: float) -> float:
    """Interpolación log-log sobre las medianas medidas (None si falta el tamaño)."""
    points = []
    for key, value in bucket.items():
        if not key.startswith("coste_"):
            continue
        points.append((float(key.split("_")[1]), value["mediana"]))
    points.sort()
    if not points:
        raise SystemExit("cubeta sin costes medidos")
    xs = np.log([p[0] for p in points])
    ys = np.log([max(p[1], 1e-6) for p in points])
    value = float(np.exp(np.interp(np.log(size), xs, ys))) if len(points) > 1 else points[0][1]
    return value


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    model = json.loads(MODEL.read_text(encoding="utf-8"))
    if not all(model["puertas"].values()):
        print("modelo NO usable (fallan puertas): se aplica el fallback declarado\n")

    out = []
    for family in FAMILIES:
        measured = [cost_at(model["por_cubeta"][b], family["notional"]) for b in family["buckets"]]
        low, high = min(measured), max(measured)
        row = {"familia": family["name"], "declarado_bp": family["declared_bp"],
               "medido_bp": [round(low, 2), round(high, 2)]}
        for label, value in (("declarado", family["declared_bp"]), ("medido_bajo", low),
                             ("medido_alto", high)):
            costs = family["costs"] * value / family["declared_bp"]
            net = family["price"] + family["funding"] - costs
            row[f"neto_{label}"] = round(net, 2)
            row[f"esperanza_{label}"] = round(net / (family["ops"] * R_USD), 5)
        out.append(row)
        print(f"{row['familia']:28s} declarado {row['declarado_bp']:5.1f} pb  "
              f"medido {row['medido_bp'][0]:5.2f}-{row['medido_bp'][1]:5.2f} pb  "
              f"neto {row['neto_declarado']:9.2f} -> {row['neto_medido_bajo']:9.2f} / "
              f"{row['neto_medido_alto']:9.2f}  esp {row['esperanza_declarado']:7.5f} -> "
              f"{row['esperanza_medido_bajo']:7.5f} / {row['esperanza_medido_alto']:7.5f}")

    target = ROOT / "data" / "cost" / "sensitivity.json"
    target.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nescrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
