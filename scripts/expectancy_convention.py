"""Comprueba que la esperanza en pb no cambia ningún veredicto archivado.

La puerta antigua pedía `esperanza > 0,05 R` por operación, con R = 250 USD fijo.
En pb del nocional eso es `125.000 / nocional` pb, así que la barra se movía con
la geometría: 40 pb con posiciones de 3.125 USD, 90 pb con 1.389 y 450 pb con 278.
La convención nueva mide `neto / (operaciones · nocional)` y exige **40 pb**, que
es el mismo 0,05 R en la geometría de referencia.

Uso:
    python scripts/expectancy_convention.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
R_USD = 250.0
GROSS_USD = 25_000.0
GATE_BP = 40.0          # 0,05 R sobre una posición de 3.125 USD
REFERENCE_NOTIONAL = 3_125.0

FAMILIES = [
    {"name": "H5 candidata", "notional": 3_125.0, "ops": 800, "net": 6029.43, "years": 1.83},
    {"name": "H5 raw", "notional": 3_125.0, "ops": 636, "net": 8342.50, "years": 1.83},
    {"name": "H8 spread entre venues", "notional": 5_000.0, "ops": 34, "net": 80.10, "years": 1.83},
    {"name": "H9 basis spot-perp", "notional": 3_125.0, "ops": 44, "net": -51.74, "years": 1.83},
    {"name": "H10 quintil (k=9)", "notional": 1_389.0, "ops": 9404, "net": 15_594.43, "years": 1.83},
    {"name": "H10 k=4 (extremo)", "notional": 3_125.0, "ops": 1168, "net": 38_870.12, "years": 1.83},
]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    rows = []
    flips = 0
    for family in FAMILIES:
        per_op = family["net"] / family["ops"]
        old_r = per_op / R_USD
        new_bp = per_op / family["notional"] * 1e4
        old_gate_bp = 0.05 * R_USD / family["notional"] * 1e4
        old_pass = old_r > 0.05
        new_pass = new_bp >= GATE_BP
        if old_pass != new_pass:
            flips += 1
        row = {
            "familia": family["name"],
            "nocional": family["notional"],
            "ops": family["ops"],
            "esperanza_R": round(old_r, 5),
            "puerta_antigua_bp": round(old_gate_bp, 2),
            "esperanza_bp": round(new_bp, 2),
            "pasa_antigua": old_pass,
            "pasa_nueva": new_pass,
            "cambia": old_pass != new_pass,
            "retorno_anual_bruto_pct": round(
                (family["net"] / GROSS_USD) / family["years"] * 100, 2),
        }
        rows.append(row)
        print(f"{row['familia']:24s} nocional {row['nocional']:7.0f}  "
              f"R {row['esperanza_R']:+.5f}  pb {row['esperanza_bp']:+8.2f}  "
              f"barra antigua {row['puerta_antigua_bp']:6.2f} pb  "
              f"{'PASA' if old_pass else 'falla'} -> {'PASA' if new_pass else 'falla'}")

    print(f"\nveredictos que cambian: {flips}")
    print(f"ancla: {GATE_BP:.0f} pb por operación = 0,05 R sobre {REFERENCE_NOTIONAL:.0f} USD")
    target = ROOT / "data" / "expectancy_convention.json"
    target.write_text(json.dumps({"gate_bp": GATE_BP, "filas": rows, "cambios": flips},
                                 indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"escrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
