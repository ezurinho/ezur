"""Simulador de ejecución sobre velas de 1 minuto.

Las medianas de coste por cubeta son un supuesto; esto lo mide sobre el libro que
no tenemos (sólo velas) con una regla explícita: ejecutar como máximo el 10 % del
volumen de cada minuto, pagando el precio típico del minuto, hasta completar el
nocional. El resultado es el deslizamiento medio contra el precio de llegada.

Con velas no se modela la selección adversa ni el impacto permanente; es una cota
inferior del coste, no una medida completa. Sirve para comprobar que un coste
declarado (p. ej. 1,33 pb en la cubeta líquida) es alcanzable con el tamaño real.

Uso:
    python scripts/fill_simulator.py --size-usd 3125 --side buy
    python scripts/fill_simulator.py --csv data/BTC_1m.csv --size-usd 25000 --participation 0.05
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def simulate(frame: pd.DataFrame, size_usd: float, side: str,
             participation: float = 0.10) -> dict:
    frame = frame.sort_values("ts").reset_index(drop=True)
    arrival = float((frame.loc[0, "o"] + frame.loc[0, "c"]) / 2.0)
    remaining = size_usd / arrival  # en unidades del activo
    notional = 0.0
    quantity = 0.0
    bars = 0
    for _, row in frame.iterrows():
        typical = float((row["h"] + row["l"] + row["c"]) / 3.0)
        capacity = float(row["v"]) * participation
        take = min(remaining, capacity)
        if take <= 0:
            break
        quantity += take
        notional += take * typical
        remaining -= take
        bars += 1
        if remaining <= 1e-12:
            break
    if quantity <= 0:
        raise SystemExit("no se ejecutó nada: sin volumen en la serie")
    average = notional / quantity
    slip_bp = (average - arrival) / arrival * 1e4
    if side == "sell":
        slip_bp = -slip_bp
    return {
        "llegada": round(arrival, 4),
        "precio_medio": round(average, 4),
        "nocional_ejecutado_usd": round(notional, 2),
        "completado": bool(remaining <= 1e-6),
        "fraccion_no_ejecutada": round(max(remaining, 0.0) / (size_usd / arrival), 6),
        "minutos": bars,
        "deslizamiento_bp": round(slip_bp, 3),
        "participacion_max": participation,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Simulador de ejecución con 1m")
    parser.add_argument("--csv", default=str(ROOT / "data" / "BTC_1m.csv"))
    parser.add_argument("--size-usd", type=float, default=3125.0)
    parser.add_argument("--side", choices=("buy", "sell"), default="buy")
    parser.add_argument("--participation", type=float, default=0.10)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    path = Path(args.csv)
    if not path.is_file():
        raise SystemExit(f"falta {path}: el simulador necesita velas de 1 minuto")
    frame = pd.read_csv(path, parse_dates=["ts"])
    result = simulate(frame, args.size_usd, args.side, args.participation)
    result.update({"csv": path.name, "lado": args.side,
                   "ventana": [frame["ts"].min().isoformat(),
                               frame["ts"].max().isoformat()]})
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
