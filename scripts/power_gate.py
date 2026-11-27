"""Puerta de potencia: ¿puede el mercado dar la muestra que la puerta exige?

Antes de congelar una familia se calcula cuántos episodios hacen falta para
detectar el edge mínimo con potencia suficiente. Si el mercado no puede darlos en
la ventana disponible, el pre-registro se rechaza **antes** de medir: no es un
resultado, es un diseño inviable.

La fórmula es la del test t unilateral con corrección por no normalidad
(Bailey & López de Prado, *The Sharpe Ratio Efficient Frontier*, 2012, §3):

    n ≈ (z_{1-α} + z_{1-β})² · (1 − γ3·SR + (γ4−1)/4·SR²) / (SR − SR*)²

con SR en la frecuencia nativa del episodio. Con SR* = 0 y retornos normales se
reduce a `(z_α + z_β)² / SR²`; el término de colas gordas sólo sube `n`.

En unidades del laboratorio: `SR = esperanza / desviación` del P&L por episodio.
La esperanza mínima es 40 pb del nocional (convención del plan) y la desviación
sale del propio P&L de la familia o, como cota superior para un carry
market-neutral, de la dispersión semanal de la oportunidad.

Uso:
    python scripts/power_gate.py --sigma-bp 400 --edge-bp 40 --available 187
    python scripts/power_gate.py --table
    python scripts/power_gate.py --sigma-bp 120 --edge-bp 40 --skew -1.5 --kurt 9
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCREEN_JSON = ROOT / "data" / "h10ext" / "screen_2020_2026.json"


def _z(p: float) -> float:
    """Inversa de la normal estándar por bisección (sin scipy)."""
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if 0.5 * (1.0 + math.erf(mid / math.sqrt(2.0))) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def required_episodes(edge: float, sigma: float, alpha: float = 0.05,
                      power: float = 0.80, skew: float = 0.0,
                      kurt: float = 3.0) -> float:
    """Episodios necesarios para detectar `edge` con `power` y significación `alpha`."""
    if edge <= 0 or sigma <= 0:
        raise ValueError("edge y sigma deben ser positivos")
    sr = edge / sigma
    tail = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    return (tail) * ((_z(1 - alpha) + _z(power)) ** 2) / (sr * sr)


def empirical_sigma_bp() -> tuple[float, int]:
    """Desviación de la dispersión semanal capturada, como cota superior."""
    if not SCREEN_JSON.is_file():
        raise SystemExit(f"falta {SCREEN_JSON}")
    payload = json.loads(SCREEN_JSON.read_text(encoding="utf-8"))
    # El JSON sólo guarda una muestra de 8 filas; la desviación se estima del
    # rango intercuartílico, que es robusto a las colas del carry.
    iqr = float(payload["p75_bp"]) - float(payload["p25_bp"])
    if iqr <= 0:
        raise SystemExit("el JSON del cribado no trae cuartiles útiles")
    return iqr / 1.349, int(payload["windows"])


def report(edge_bp: float, sigma_bp: float, available: int | None,
           alpha: float, power: float, skew: float, kurt: float) -> dict:
    n = required_episodes(edge_bp, sigma_bp, alpha, power, skew, kurt)
    years = n / 52.0
    verdict = None
    if available is not None:
        verdict = "PASA" if available >= n else "NO PASA"
    return {
        "edge_bp": edge_bp,
        "sigma_bp": sigma_bp,
        "alpha": alpha,
        "power": power,
        "skew": skew,
        "kurt": kurt,
        "episodes_needed": round(n, 1),
        "years_needed_weekly": round(years, 1),
        "available": available,
        "verdict": verdict,
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Puerta de potencia estadística")
    parser.add_argument("--edge-bp", type=float, default=40.0,
                        help="esperanza mínima por episodio en pb (convención: 40)")
    parser.add_argument("--sigma-bp", type=float, default=None,
                        help="desviación del P&L por episodio; si falta, se estima")
    parser.add_argument("--available", type=int, default=None,
                        help="episodios que el mercado puede dar en la ventana")
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--power", type=float, default=0.80)
    parser.add_argument("--skew", type=float, default=0.0)
    parser.add_argument("--kurt", type=float, default=3.0)
    parser.add_argument("--table", action="store_true", help="tabla de sensibilidad")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    sigma = args.sigma_bp
    if sigma is None:
        sigma, n_obs = empirical_sigma_bp()
        print(f"sigma estimada de la oportunidad: {sigma:.1f} pb "
              f"({n_obs} ventanas del cribado 2020-2026)")
        print("  es una cota superior para un carry market-neutral: el P&L de una "
              "posición cubierta tiene menos varianza que la oportunidad\n")

    if args.table:
        edges = (20.0, 40.0, 80.0, 120.0)
        sigmas = (50.0, 100.0, 200.0, 400.0)
        header = "sigma/edge"
        print(f"{header:>12}" + "".join(f"{e:>14.0f} pb" for e in edges))
        for s in sigmas:
            row = [f"{required_episodes(e, s):>16.0f}" for e in edges]
            print(f"{s:>10.0f} pb" + "".join(row))
        print("\nepisodios necesarios (α = 5 %, potencia = 80 %, retornos normales)")
        print("un año de datos semanales da 52 episodios; cinco años, 260")
        return 0

    result = report(args.edge_bp, sigma, args.available, args.alpha,
                    args.power, args.skew, args.kurt)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.available is not None and result["verdict"] == "NO PASA":
        print(f"\nNO PASA: hacen falta {result['episodes_needed']:.0f} episodios y "
              f"hay {args.available}. El pre-registro se rechaza antes de medir.")
        return 2
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
