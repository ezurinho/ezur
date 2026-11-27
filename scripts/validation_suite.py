"""Canarios de look-ahead y baseline nulo del cribado.

Tres pruebas que el archivo necesita para que «no hay look-ahead» sea una
comprobación y no una frase:

1. **Canario de señal**: se envenena la fila del día de evaluación (multiplicarla
   por 100) y se recalcula la señal. Si la señal del propio día cambia, el
   `shift(1)` no está haciendo su trabajo. Debe ser idéntica.
2. **Canario de ruido**: con un pago simulado de ruido puro, la mediana capturada
   debe quedar alrededor de cero. Si no, el motor tiene un sesgo estructural.
3. **Baseline nulo**: se baraja el pago dentro de cada símbolo (se destruye el
   emparejamiento señal-pago y se conserva la distribución marginal) y se mide la
   distribución de la mediana capturada bajo esa nulidad. El percentil de la
   cifra real es la respuesta a «¿es sorprendente 80,51 pb?».

Se baraja el pago y **no** la serie de retornos de la estrategia: el Sharpe y la
mediana son invariantes al orden de los retornos, así que ese null sería
degenerado (Aronson, *Monte-Carlo Evaluation of Trading Systems*, 2006; §6 del
informe de práctica estadística).

Uso:
    python scripts/validation_suite.py --panel-dir data/h10 --permutations 50
    python scripts/validation_suite.py --panel-dir data/h10ext --start 2020-04-01
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
sys.path.insert(0, str(ROOT))

import screen_h10_dispersion as screen_mod  # noqa: E402


def load_panels(panel_dir: Path):
    funding, perp, _freeze = screen_mod.load(panel_dir)
    return screen_mod.panels(funding, perp)


def canary_signal(rate: pd.DataFrame, stride: int = 10) -> dict:
    """La señal de t no puede depender de la fila de t.

    Se envenena **una sola fila** por prueba y se compara la señal de ese mismo
    día: debe ser idéntica. Como control de mutación se comprueba que la señal
    del día siguiente sí cambia — si no cambiara, el veneno no estaría haciendo
    nada y la prueba no valdría.
    """
    base = screen_mod.signal_frame(rate)
    mondays = [d for d in rate.index if d.weekday() == 0][::stride]
    same_day: list[float] = []
    next_day: list[float] = []
    for day in mondays:
        poisoned = rate.copy()
        poisoned.loc[[day]] = poisoned.loc[[day]] * 100.0
        alt = screen_mod.signal_frame(poisoned)
        same_day.append(_max_abs(alt.loc[day], base.loc[day]))
        following = day + pd.Timedelta(days=1)
        if following in base.index:
            next_day.append(_max_abs(alt.loc[following], base.loc[following]))
    worst_same = max(same_day) if same_day else 0.0
    best_control = max(next_day) if next_day else 0.0
    return {
        "dias_comprobados": len(mondays),
        "max_diferencia_mismo_dia": float(worst_same),
        "max_diferencia_dia_siguiente": float(best_control),
        "pasa": bool(worst_same < 1e-12 and best_control > 1e-6),
    }


def _max_abs(left: pd.Series, right: pd.Series) -> float:
    a = left.to_numpy(dtype=float)
    b = right.to_numpy(dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    if not mask.any():
        return 0.0
    return float(np.max(np.abs(a[mask] - b[mask])))


def shuffled_payoff(rate: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Baraja cada columna en el tiempo: misma marginal, cero timing."""
    arr = rate.to_numpy(dtype=float, copy=True)
    for column in range(arr.shape[1]):
        values = arr[:, column]
        mask = ~np.isnan(values)
        block = values[mask]
        rng.shuffle(block)
        values[mask] = block
        arr[:, column] = values
    return pd.DataFrame(arr, index=rate.index, columns=rate.columns)


def noise_payoff(rate: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Ruido de 5 pb alrededor de cero, con la forma del panel."""
    shape = rate.shape
    return pd.DataFrame(rng.normal(0.0, 5e-4, size=shape),
                        index=rate.index, columns=rate.columns)


def median_of(rate, close, quote, cap, start, end, payoff) -> float:
    result = screen_mod.screen(rate, close, quote, cap, start, end, payoff=payoff)
    return float(result["median_bp"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Canarios y baseline nulo")
    parser.add_argument("--panel-dir", default=str(ROOT / "data" / "h10"))
    parser.add_argument("--permutations", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20261127)
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    rate, close, quote = load_panels(Path(args.panel_dir))
    cap = screen_mod.DEFAULT_MAX_PER_SIDE
    rng = np.random.default_rng(args.seed)

    observed = median_of(rate, close, quote, cap, args.start, args.end, None)
    print(f"observado: mediana {observed:.2f} pb")

    canary_a = canary_signal(rate)
    print(f"canario de señal: {canary_a['dias_comprobados']} lunes, "
          f"mismo día {canary_a['max_diferencia_mismo_dia']:.2e}, "
          f"día siguiente {canary_a['max_diferencia_dia_siguiente']:.2e} → "
          f"{'PASA' if canary_a['pasa'] else 'FALLA'}")

    noise = median_of(rate, close, quote, cap, args.start, args.end,
                      noise_payoff(rate, rng))
    print(f"canario de ruido: mediana {noise:.2f} pb → "
          f"{'PASA' if abs(noise) < 5 else 'FALLA'}")

    nulls = []
    for index in range(args.permutations):
        value = median_of(rate, close, quote, cap, args.start, args.end,
                          shuffled_payoff(rate, rng))
        nulls.append(value)
        if (index + 1) % 10 == 0:
            print(f"  permutación {index + 1}/{args.permutations}", flush=True)

    null = np.array(nulls)
    p_value = (1 + int((null >= observed).sum())) / (len(null) + 1)
    percentile = float((null < observed).mean() * 100)
    summary = {
        "observado_bp": round(observed, 2),
        "nulidad": {
            "permutaciones": len(null),
            "media_bp": round(float(null.mean()), 2),
            "p50_bp": round(float(np.median(null)), 2),
            "p95_bp": round(float(np.percentile(null, 95)), 2),
            "p99_bp": round(float(np.percentile(null, 99)), 2),
            "max_bp": round(float(null.max()), 2),
        },
        "percentil_observado": round(percentile, 1),
        "p_valor": round(p_value, 4),
        "canario_senal": canary_a,
        "canario_ruido": {"mediana_bp": round(noise, 2),
                          "pasa": bool(abs(noise) < 5)},
        "panel": str(args.panel_dir),
        "ventana": {"start": args.start, "end": args.end},
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    target = Path(args.json) if args.json else Path(args.panel_dir) / "validation.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"escrito {target}")

    failed = not canary_a["pasa"] or abs(noise) >= 5
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
