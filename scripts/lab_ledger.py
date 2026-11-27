"""Ledger del laboratorio: el denominador del DSR, con cadena de hash.

`docs/TRIALS.md` es la fuente de verdad de los ensayos, pero es una tabla a mano:
se puede editar sin rastro y no registra las consultas exploratorias que también
consumen presupuesto de búsqueda. Este script la convierte en un JSONL
encadenado —cada línea lleva el hash de la anterior— y publica el recuento que el
DSR debe declarar.

No cambia ningún veredicto ni cuenta ensayos nuevos: las filas son las que ya
están en la tabla. Lo que añade es que ahora se puede comprobar que nadie borró
una fila después de ver un resultado, y que el número de ensayos exploratorios
declarados en `docs/QUERIES.md` queda separado del de variantes medidas.

Uso:
    python scripts/lab_ledger.py
    python scripts/lab_ledger.py --verify
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIALS = ROOT / "docs" / "TRIALS.md"
QUERIES = ROOT / "docs" / "QUERIES.md"
OUT = ROOT / "data" / "lab_ledger.jsonl"


def _cell(text: str) -> str:
    return text.strip().strip("`").strip()


def parse_trials(path: Path = TRIALS) -> list[dict]:
    """Filas de la tabla de familias medidas, en orden de aparición."""
    rows: list[dict] = []
    in_table = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("| Familia |"):
            in_table = True
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        cells = [c for c in stripped.strip("|").split("|")]
        if len(cells) < 5 or set(cells[0]) <= {"-", ":", " "}:
            continue
        family = _cell(cells[0])
        variants_raw = _cell(cells[1])
        if not re.fullmatch(r"\d+", variants_raw):
            continue
        rows.append({
            "familia": family,
            "variantes": int(variants_raw),
            "periodo": _cell(cells[2]),
            "resultado": _cell(cells[3]),
            "archivo": _cell(cells[4]),
        })
    return rows


def count_queries(path: Path = QUERIES) -> int:
    """Consultas exploratorias declaradas (una por línea que empiece por '- ')."""
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines()
               if line.startswith("- "))


def build(rows: list[dict]) -> list[dict]:
    chain = "0" * 64
    ledger: list[dict] = []
    for index, row in enumerate(rows, start=1):
        record = {"seq": index, **row, "prev": chain}
        digest = hashlib.sha256(
            (chain + json.dumps(row, sort_keys=True, ensure_ascii=False)).encode("utf-8")
        ).hexdigest()
        record["hash"] = digest
        chain = digest
        ledger.append(record)
    return ledger


def verify(ledger: list[dict]) -> tuple[bool, int]:
    """Recalcula la cadena y devuelve (ok, filas comprobadas)."""
    chain = "0" * 64
    for record in ledger:
        row = {k: record[k] for k in ("familia", "variantes", "periodo",
                                      "resultado", "archivo")}
        digest = hashlib.sha256(
            (chain + json.dumps(row, sort_keys=True, ensure_ascii=False)).encode("utf-8")
        ).hexdigest()
        if digest != record["hash"]:
            return False, record["seq"]
        chain = digest
    return True, len(ledger)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Ledger del laboratorio")
    parser.add_argument("--verify", action="store_true", help="sólo comprobar la cadena")
    args = parser.parse_args()

    if args.verify:
        if not OUT.is_file():
            raise SystemExit(f"falta {OUT}: ejecuta el script sin --verify")
        ledger = [json.loads(line) for line in
                  OUT.read_text(encoding="utf-8").splitlines() if line.strip()]
        ok, position = verify(ledger)
        print(f"{'OK' if ok else 'ROTO en la fila ' + str(position)}: "
              f"{len(ledger)} registros")
        return 0 if ok else 1

    rows = parse_trials()
    ledger = build(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in ledger),
                   encoding="utf-8")

    measured = sum(r["variantes"] for r in rows)
    exploratory = count_queries()
    print(f"{len(rows)} familias · {measured} variantes medidas · "
          f"{exploratory} consultas exploratorias declaradas")
    print(f"denominador del DSR: {measured} (+{exploratory} exploratorias si se "
          f"quiere el escenario conservador: {measured + exploratory})")
    print(f"escrito {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
