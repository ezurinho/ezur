"""La cuenta de papel, sin arrancar el servidor.

    python -m server.paper                          # data/terminal.db
    python -m server.paper --profile profiles/okx   # el perfil que opera
    python -m server.paper --json                   # para engancharlo a algo

Lee la base en solo lectura: si el bot está parado, la cuenta sigue ahí. Cada
operación cerrada se inserta una sola vez (`insert_trade_once`), así que un
reinicio con backfill no duplica el histórico ni falsea el resultado.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

from .db import row_to_trade
from .models import TradeRecord
from .stats import aggregate


def read_trades(db_path: Path) -> list[TradeRecord]:
    uri = f"file:{(db_path.resolve()).as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM trades ORDER BY closed_ts")]
    finally:
        conn.close()
    return [TradeRecord.model_validate(row_to_trade(row)) for row in rows]


def summary(db_path: Path, capital: float) -> dict[str, Any]:
    return aggregate(read_trades(db_path), capital)


def _money(value: Any) -> str:
    return f"{float(value or 0.0):,.2f}".replace(",", " ")


def render(summary: dict[str, Any], capital: float, label: str) -> str:
    closed = summary.get("closed") or {}
    trades = int(closed.get("trades") or 0)
    lines = [f"cuenta de papel · {label}", ""]
    if not trades:
        lines.append(f"capital {capital:,.2f} · sin operaciones cerradas todavía".replace(",", " "))
        return "\n".join(lines)

    pnl = float(closed.get("pnl_net") or 0.0)
    fees = float(closed.get("fees") or 0.0)
    gross = pnl + fees
    share = (fees / abs(gross) * 100) if gross else 0.0
    lines += [
        f"capital inicial {_money(capital)} · resultado {_money(pnl)} · "
        f"equity {_money(capital + pnl)}",
        f"{trades} cerradas · {int(closed.get('wins') or 0)} ganadas · "
        f"{int(closed.get('losses') or 0)} perdidas · "
        f"acierto {float(closed.get('win_rate') or 0) * 100:.1f} %",
        f"factor de beneficio {float(closed.get('profit_factor') or 0):.2f} · "
        f"esperanza {float(closed.get('expectancy_r') or 0):+.3f} R",
        f"bruto {_money(gross)} · comisiones {_money(fees)} "
        f"({share:.0f} % del bruto)",
        f"peor racha {int(closed.get('max_loss_streak') or 0)} · "
        f"mejor operación {_money(closed.get('best_trade'))} · "
        f"peor {_money(closed.get('worst_trade'))}",
    ]
    return "\n".join(lines)


def _profile_defaults(profile: Path) -> tuple[Path, float]:
    db = profile / "terminal.db"
    capital = 25_000.0
    config = profile / "config.json"
    if config.is_file():
        try:
            document = json.loads(config.read_text(encoding="utf-8"))
            capital = float((document.get("risk") or {}).get("initial_capital") or capital)
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            pass
    return db, capital


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumen de la cuenta de papel")
    parser.add_argument("--db", default=None, help="base SQLite a leer")
    parser.add_argument("--profile", default=None, help="carpeta del perfil")
    parser.add_argument("--capital", type=float, default=None, help="capital inicial")
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if args.profile:
        db, capital = _profile_defaults(Path(args.profile))
    else:
        db, capital = Path(args.db or "data/terminal.db"), 25_000.0
    if args.capital is not None:
        capital = args.capital

    if not db.is_file():
        print(f"no hay base en {db}: el bot no ha operado todavía", flush=True)
        return 1

    result = summary(db, capital)
    if args.json:
        print(json.dumps({"db": str(db), "capital": capital, "summary": result}, indent=2))
    else:
        print(render(result, capital, str(db)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
