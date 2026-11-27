"""Congela con hashes el panel base de H11, sin medir la estrategia.

H11 se evalúa en 2027-06-01/2028-05-31. Hoy el dato llega al 2026-10-31, así que
lo que se puede congelar es la **base** y la **construcción**: los CSV del panel,
el descargador y el motor, más el contrato pre-registrado. La rebanada de
evaluación no existe todavía; cuando exista se descarga con el mismo fetcher y se
hashea antes de la primera lectura, tal como exige `docs/PRE-REGISTRO-H11.md`.

No simula nada: sólo lee ficheros y calcula SHA-256.

Uso:
    python scripts/freeze_h11_panel.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "data" / "h10ext"
OUT = ROOT / "data" / "h11"

# Contrato y configuración congelados. Si cualquiera cambia, cambia el hash.
CONFIG = {
    "k_por_lado": 4,
    "bruto_usd": 25_000.0,
    "nocional_por_posicion_usd": 3_125.0,
    "coste_pb_por_lado": 10.0,
    "min_elegibles": 20,
    "min_adv_usd": 5_000_000.0,
    "senal": "media de funding de 7 días, z-score de 90 días, shift(1)",
    "rebalanceo": "lunes al cierre UTC, posición persistente",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    base_manifest = json.loads((BASE / "freeze.json").read_text(encoding="utf-8"))
    funding = BASE / "funding_daily.csv"
    perp = BASE / "perp_daily.csv"
    funding_hash, perp_hash = sha256(funding), sha256(perp)
    if funding_hash != base_manifest["funding_sha256"] or perp_hash != base_manifest["perp_sha256"]:
        print("FALLA: el panel base no coincide con su manifiesto; no se congela nada")
        return 1

    builders = {
        "fetch_h10_data.py": ROOT / "scripts" / "fetch_h10_data.py",
        "extend_panel_2020.py": ROOT / "scripts" / "extend_panel_2020.py",
        "validate_h5_engine.py": ROOT / "scripts" / "validate_h5_engine.py",
    }
    contracts = {
        "PRE-REGISTRO-H11.md": ROOT / "docs" / "PRE-REGISTRO-H11.md",
        "PRE-REGISTRO-H10.md": ROOT / "docs" / "PRE-REGISTRO-H10.md",
    }

    start = pd.Timestamp("2027-06-01", tz="UTC")
    first_signal = start + pd.Timedelta(days=90)

    manifest = {
        "familia": "H11 · extremo del panel con tamaño fijo",
        "congelado": datetime.now(timezone.utc).isoformat(),
        "base": {
            "panel": "data/h10ext",
            "periodo": base_manifest["period"],
            "simbolos": base_manifest["symbols"],
            "filas_funding": base_manifest["rows"],
            "filas_perp": base_manifest["perp_rows"],
            "funding_sha256": funding_hash,
            "perp_sha256": perp_hash,
            "manifiesto": "data/h10ext/freeze.json",
            "fuente": base_manifest["source"],
            "universo": base_manifest["universe"],
        },
        "construccion_sha256": {name: sha256(path) for name, path in builders.items()},
        "contrato_sha256": {name: sha256(path) for name, path in contracts.items()},
        "config": CONFIG,
        "ventana": {
            "pre_registro": "2027-06-01/2028-05-31",
            "holdout_sellado": "2026-12-01/2027-05-31",
            "primera_senal_sin_holdout": first_signal.strftime("%Y-%m-%d"),
            "nota": "el motor exige 90 filas de historia; usar el holdout como "
                    "calentamiento sería usarlo. La ventana efectiva empieza en la "
                    "primera señal, no el 2027-06-01.",
        },
        "rebanada_evaluacion": {
            "estado": "pendiente",
            "nota": "se descarga con fetch_h10_data.py al abrir la ventana y se "
                    "hashea en este manifiesto antes de la primera lectura",
        },
        "ensayos": "no añade; H11 es el ensayo 54 y se lee una vez",
    }

    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "freeze.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")

    print(json.dumps({
        "escrito": str(target.relative_to(ROOT)),
        "funding_sha256": funding_hash,
        "perp_sha256": perp_hash,
        "contrato": manifest["contrato_sha256"],
        "construccion": manifest["construccion_sha256"],
        "primera_senal_sin_holdout": manifest["ventana"]["primera_senal_sin_holdout"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
