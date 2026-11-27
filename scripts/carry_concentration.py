"""¿Cuántos nombres capturan el carry y cuánto capital absorbe?

El top-5 es lo que tumbó a H5 raw y a H10 con k = 4: el resultado depende de
cuatro operaciones. Este script mide si esa concentración es estructural o
episódica, y añade la capacidad —el nocional que cabe sin mover el libro— porque
un edge que no escala tampoco es desplegable.

Para cada ventana de 7 días replica la cartera del cribado y reparte el
diferencial capturado entre sus miembros: contribución de un corto = su funding
menos la media de los largos; de un largo, la media de los cortos menos el suyo.
La suma de las contribuciones dividida por k es el `captured_bp` del cribado.

Uso:
    python scripts/carry_concentration.py --start 2025-01-01
    python scripts/carry_concentration.py --panel-dir data/h10
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

import screen_h10_dispersion as screen_mod  # noqa: E402

PARTICIPATION = 0.01  # 1 % del volumen mediano diario por posición


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Concentración y capacidad del carry")
    parser.add_argument("--panel-dir", default=str(ROOT / "data" / "h10ext"))
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default="2026-11-01")
    parser.add_argument("--json", default=None)
    args = parser.parse_args()

    funding, perp, _freeze = screen_mod.load(Path(args.panel_dir))
    rate, close, quote = screen_mod.panels(funding, perp)
    zscore = screen_mod.signal_frame(rate)
    adv = quote.rolling(30, min_periods=20).median().shift(1)
    history = close.notna().cumsum().shift(1)
    funding_days = rate.notna().cumsum().shift(1)

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    mondays = [d for d in close.index if d.weekday() == 0 and start <= d < end]

    rows: list[dict] = []
    for date in mondays:
        tradable = (
            (history.loc[date] >= screen_mod.MIN_HISTORY)
            & (funding_days.loc[date] >= screen_mod.MIN_HISTORY)
            & (adv.loc[date] >= screen_mod.MIN_ADV_USD)
            & (close.loc[date] > 0)
            & (quote.loc[date] > 0)
            & zscore.loc[date].notna()
        )
        members = [s for s in zscore.columns if bool(tradable.get(s, False))]
        if len(members) < screen_mod.MIN_ELIGIBLE:
            continue
        ranked = zscore.loc[date, members].sort_values()
        count = min(max(2, int(round(len(members) * 0.2))),
                    screen_mod.DEFAULT_MAX_PER_SIDE)
        longs = list(ranked.index[:count])
        shorts = list(ranked.index[-count:])
        horizon = close.index[(close.index >= date) & (close.index < date + pd.Timedelta(days=7))]
        if len(horizon) < 6:
            continue

        block = rate.loc[horizon]
        short_mean = block[shorts].mean(axis=1).mean()
        long_mean = block[longs].mean(axis=1).mean()
        contributions = {}
        for name in shorts:
            contributions[name] = float(block[name].mean() - long_mean)
        for name in longs:
            contributions[name] = float(short_mean - block[name].mean())

        values = np.array([abs(v) for v in contributions.values()])
        total = values.sum()
        if total <= 0:
            continue
        ordered = np.sort(values)[::-1]
        top1 = float(ordered[0] / total)
        top3 = float(ordered[:3].sum() / total)
        top5 = float(ordered[:5].sum() / total)
        hhi = float(((values / total) ** 2).sum())
        count80 = int(np.searchsorted(np.cumsum(ordered) / total, 0.8) + 1)

        capacities = []
        for name in list(contributions):
            volume = adv.loc[date, name]
            if pd.notna(volume) and volume > 0:
                capacities.append(float(volume) * PARTICIPATION)
        gross = 2 * count * float(np.median(capacities)) if capacities else float("nan")

        rows.append({
            "date": date.strftime("%Y-%m-%d"),
            "k": count,
            "captured_bp": round((short_mean - long_mean) * 1e4, 2),
            "top1": round(top1, 3),
            "top3": round(top3, 3),
            "top5": round(top5, 3),
            "hhi": round(hhi, 4),
            "n_para_80": count80,
            "gross_capacity_usd": round(gross, 0) if gross == gross else None,
        })

    if not rows:
        raise SystemExit("sin ventanas: revisa la ventana o el panel")

    frame = pd.DataFrame(rows)
    summary = {
        "ventana": {"start": args.start, "end": args.end},
        "semanas": int(len(frame)),
        "top1_mediana": round(float(frame["top1"].median()), 3),
        "top3_mediana": round(float(frame["top3"].median()), 3),
        "top5_mediana": round(float(frame["top5"].median()), 3),
        "hhi_mediana": round(float(frame["hhi"].median()), 4),
        "nombres_para_80pct_mediana": float(frame["n_para_80"].median()),
        "semanas_un_nombre_mas_de_50pct": int((frame["top1"] >= 0.5).sum()),
        "gross_capacity_usd_mediana": float(frame["gross_capacity_usd"].median()),
        "captured_bp_mediana": round(float(frame["captured_bp"].median()), 2),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    target = Path(args.json) if args.json else Path(args.panel_dir) / "concentration.json"
    target.write_text(json.dumps({"summary": summary, "weeks": rows}, indent=2) + "\n",
                      encoding="utf-8")
    print(f"escrito {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
