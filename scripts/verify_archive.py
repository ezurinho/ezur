"""Verifica que las cifras publicadas se siguen reproduciendo.

El producto del laboratorio es el archivo: si un número deriva en silencio —otra
versión de pandas, un panel regenerado, un script editado—, el informe de cierre
se podre y nadie lo nota. Este comando vuelve a medir lo barato y compara con lo
publicado, con tolerancias explícitas.

Comprueba:
1. los hashes de los dos paneles contra su `freeze.json`;
2. que el cribado sobre el panel congelado dé 80,51 pb;
3. que las seis familias de la convención de esperanza sigan con el mismo veredicto;
4. que la dispersión de 2026 siga en 30,25 pb en cash y 189,49 en 8 h;
5. que la cadena del ledger de ensayos esté intacta.

Uso:
    python scripts/verify_archive.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check(name: str, ok: bool, detail: str) -> bool:
    print(f"{'PASA' if ok else 'FALLA'}  {name}: {detail}")
    return ok


def check_panel(folder: Path) -> bool:
    freeze = json.loads((folder / "freeze.json").read_text(encoding="utf-8"))
    funding = folder / "funding_daily.csv"
    perp = folder / "perp_daily.csv"
    ok_funding = sha(funding) == freeze["funding_sha256"]
    ok_perp = sha(perp) == freeze["perp_sha256"]
    return check(f"hashes {folder.name}", ok_funding and ok_perp,
                 f"funding {'ok' if ok_funding else 'NO'} · "
                 f"velas {'ok' if ok_perp else 'NO'}")


def run_json(script: str, json_path: Path, *args: str) -> dict | None:
    command = [PY, str(ROOT / "scripts" / script), "--json", str(json_path), *args]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
    if not json_path.is_file():
        print(f"  salida de {script}: {result.stdout[-300:]} {result.stderr[-300:]}")
        return None
    return json.loads(json_path.read_text(encoding="utf-8"))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    import pandas as pd  # sólo para reportar versiones

    print(f"entorno: python {sys.version.split()[0]} · pandas {pd.__version__}")
    ok = True
    ok &= check_panel(ROOT / "data" / "h10")
    ok &= check_panel(ROOT / "data" / "h10ext")

    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "screen.json"
        payload = run_json("screen_h10_dispersion.py", target)
        if payload is None:
            ok = False
        else:
            ok &= check("cribado H10", abs(payload["median_bp"] - 80.51) < 0.01,
                        f"{payload['median_bp']} pb (esperado 80,51)")

    convention = ROOT / "data" / "expectancy_convention.json"
    if convention.is_file():
        payload = json.loads(convention.read_text(encoding="utf-8"))
        # Nunca se da por bueno un campo ausente: un `None` que pasa el filtro
        # sería un falso positivo de la verificación.
        changed = payload.get("cambios")
        rows = payload.get("filas") or []
        ok &= check("convención de esperanza",
                    changed == 0 and len(rows) == 6,
                    f"{changed} de {len(rows)} veredictos cambian (esperado 0 de 6)")
    else:
        ok = check("convención de esperanza", False, "falta el JSON")

    dispersion = ROOT / "data" / "h10ext" / "dispersion.json"
    if dispersion.is_file():
        payload = json.loads(dispersion.read_text(encoding="utf-8"))
        year = payload["por_anio"]["2026"]
        ok &= check("dispersión 2026", abs(year["disp_cash_bp"] - 30.25) < 0.02
                    and abs(year["disp_eq8h_bp"] - 189.49) < 0.05,
                    f"cash {year['disp_cash_bp']} · 8h {year['disp_eq8h_bp']}")
    else:
        ok = check("dispersión 2026", False, "falta el JSON")

    ledger = ROOT / "data" / "lab_ledger.jsonl"
    if ledger.is_file():
        result = subprocess.run([PY, str(ROOT / "scripts" / "lab_ledger.py"), "--verify"],
                                cwd=ROOT, capture_output=True, text=True)
        ok &= check("ledger de ensayos", result.returncode == 0,
                    result.stdout.strip() or result.stderr.strip())
    else:
        ok = check("ledger de ensayos", False, "falta data/lab_ledger.jsonl")

    print("\n" + ("ARCHIVO VERIFICADO" if ok else "EL ARCHIVO NO REPRODUCE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
