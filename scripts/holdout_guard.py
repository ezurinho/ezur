"""Candado del holdout 2026-12-01/2027-05-31.

El plan dice que el holdout permanece sellado, y hasta ahora eso era una promesa
en un documento. Este módulo lo convierte en una comprobación: cualquier script
que lea fechas del panel debe pasar por `guard`, que aborta si aparece una fila
dentro del tramo o si se ha pedido expresamente abrirlo sin un pre-registro
firmado.

No borra datos ni cifra ficheros: el panel vive en disco y borrar filas sería
irreversible. Lo que impide el uso accidental es el candado en el lector, no la
ausencia del dato.

Uso como módulo:
    from holdout_guard import guard
    frame = guard(frame)                      # aborta si toca el holdout

Uso como CLI (comprueba un CSV):
    python scripts/holdout_guard.py data/h10ext/funding_daily.csv
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import pandas as pd

HOLDOUT_START = pd.Timestamp("2026-12-01", tz="UTC")
HOLDOUT_END = pd.Timestamp("2027-05-31 23:59:59", tz="UTC")
SEAL_ENV = "EZUR_HOLDOUT_UNSEAL"
SEAL_FILE = Path(__file__).resolve().parents[1] / "data" / "holdout" / "PREREGISTRO.sha256"


class HoldoutSealed(RuntimeError):
    """Se intentó leer el holdout sin autorización registrada."""


def _unsealed() -> bool:
    """Sólo se abre con la variable de entorno y un pre-registro hasheado."""
    if os.environ.get(SEAL_ENV) != "1":
        return False
    if not SEAL_FILE.is_file():
        raise HoldoutSealed(
            f"{SEAL_ENV}=1 pero falta {SEAL_FILE}: sin pre-registro firmado no se abre")
    return True


def guard(frame: pd.DataFrame, column: str = "dt") -> pd.DataFrame:
    """Devuelve el frame si no toca el holdout; aborta si lo toca."""
    if column not in frame.columns:
        raise KeyError(f"falta la columna {column!r}")
    dates = pd.to_datetime(frame[column], utc=True)
    inside = (dates >= HOLDOUT_START) & (dates <= HOLDOUT_END)
    count = int(inside.sum())
    if count == 0:
        return frame
    if _unsealed():
        print(f"AVISO: holdout abierto con pre-registro {SEAL_FILE.name}; {count} filas",
              file=sys.stderr)
        return frame
    raise HoldoutSealed(
        f"{count} filas dentro del holdout {HOLDOUT_START.date()}/{HOLDOUT_END.date()}. "
        f"El tramo está sellado: hace falta un pre-registro hasheado en {SEAL_FILE} "
        f"y {SEAL_ENV}=1. No se abre para mirar.")


def seal_digest(path: Path) -> str:
    """SHA-256 de un pre-registro, para escribirlo en PREREGISTRO.sha256."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _self_test() -> int:
    outside = pd.DataFrame({"dt": pd.to_datetime(["2026-11-30", "2026-12-01"],
                                                utc=True)})
    try:
        guard(outside)
    except HoldoutSealed as error:
        print(f"OK: detecta el holdout → {error}".split(".")[0])
    else:
        print("FALLO: no detectó el holdout")
        return 1
    clean = pd.DataFrame({"dt": pd.to_datetime(["2020-01-01", "2026-11-30"], utc=True)})
    guard(clean)
    print("OK: deja pasar las fechas fuera del holdout")
    return 0


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = (argv if argv is not None else sys.argv[1:])
    if not args or args[0] in {"--test", "-t"}:
        return _self_test()
    path = Path(args[0])
    frame = pd.read_csv(path, parse_dates=["dt"])
    guard(frame)
    print(f"OK: {path} no toca el holdout ({len(frame)} filas)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
