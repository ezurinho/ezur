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
import math
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from .config import Settings
from .db import row_to_trade
from .models import TradeRecord
from .promotion import evaluate_paths, execution_model, load
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


def _instant(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def exposure(
    trades: list[TradeRecord], capital: float, contract_size: float | None = None
) -> dict[str, Any]:
    """Cuántas veces el capital se movió en cada operación (nocional).

    El tamaño de contrato sale de `tick_value / tick_size` del perfil. Sin ese
    dato no se inventa la escala BTC: los múltiplos quedan sin medir.
    """
    if not trades:
        return {"trades": 0, "max_multiple": None, "median_multiple": None, "max_notional": None}
    if contract_size is None or not math.isfinite(contract_size) or contract_size <= 0:
        return {
            "trades": len(trades),
            "max_multiple": None,
            "median_multiple": None,
            "max_notional": None,
            "contract_size": None,
        }
    running = float(capital)
    multiples: list[float] = []
    max_notional = 0.0
    for trade in trades:
        notional = float(trade.units) * float(contract_size) * float(trade.entry_price)
        base = running if running > 0 else float(capital)
        multiples.append(notional / base if base else 0.0)
        max_notional = max(max_notional, notional)
        running += float(trade.pnl_net or 0.0)
    return {
        "trades": len(multiples),
        "max_multiple": round(max(multiples), 2),
        "median_multiple": round(median(multiples), 2),
        "max_notional": round(max_notional, 2),
    }


def impossible(trades: list[TradeRecord], capital: float) -> dict[str, Any]:
    """Operaciones que salieron antes de entrar: el libro las cuenta igual.

    No se corrigen desde aquí —una fila del libro solo se toca con una decisión
    explícita—, pero el informe tiene que decir cuánto pesan y cuál sería la
    equity sin ellas, para que la diferencia no se descubra por sorpresa.
    """
    broken = [
        trade for trade in trades if _instant(trade.closed_ts) < _instant(trade.opened_ts)
    ]
    pnl = sum(float(trade.pnl_net or 0.0) for trade in broken)
    total = sum(float(trade.pnl_net or 0.0) for trade in trades)
    valid = [
        trade for trade in trades if _instant(trade.closed_ts) >= _instant(trade.opened_ts)
    ]
    wins = sum(
        float(trade.pnl_net or 0.0) for trade in valid if float(trade.pnl_net or 0.0) > 0
    )
    losses = sum(
        float(trade.pnl_net or 0.0) for trade in valid if float(trade.pnl_net or 0.0) < 0
    )
    return {
        "trades": len(broken),
        "pnl_net": round(pnl, 8),
        "equity_without": round(float(capital) + total - pnl, 8),
        "trades_without": len(valid),
        "pf_without": round(wins / abs(losses), 4) if losses else None,
    }


def promotion_state(profile: Path) -> dict[str, Any] | None:
    """La puerta tal como la aplica el arranque, sin arrancar el servidor."""
    config = profile / "config.json"
    if not config.is_file():
        return None
    try:
        document = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    block = document.get("promotion")
    if not isinstance(block, dict) or not block.get("required"):
        return None
    strategy = document.get("strategy") or {}
    try:
        execution = execution_model(Settings.model_validate(document))
    except ValueError:
        execution = None
    verdict = evaluate_paths(
        block.get("evidence"),
        block.get("stress_evidence"),
        block.get("cycle"),
        {"id": strategy.get("id"), "version": strategy.get("version")}
        if strategy.get("id")
        else None,
        execution=execution,
    )
    cycle = load(block.get("cycle"))
    checks: list[dict[str, Any]] = []
    for check in verdict["checks"]:
        checks.append(
            {
                "name": str(check.get("name") or ""),
                "passed": bool(check.get("pass")),
                "value": check.get("value"),
                "threshold": check.get("threshold"),
                "reason": check.get("reason") or "",
            }
        )
    failed = [check for check in checks if not check["passed"]]
    blocking = failed[0] if failed else None
    by_name = {check["name"]: check for check in checks}
    pbo_check = by_name.get("pbo_del_ciclo") or {}
    dsr_check = by_name.get("dsr_del_ciclo") or {}
    stress_check = by_name.get("pf_con_coste_duplicado") or {}
    pbo_block = (cycle or {}).get("pbo") or {}
    dsr_block = (cycle or {}).get("dsr") or {}
    wfa = (cycle or {}).get("wfa") or {}
    if not isinstance(pbo_block, dict):
        pbo_block = {}
    if not isinstance(dsr_block, dict):
        dsr_block = {}
    if not isinstance(wfa, dict):
        wfa = {}
    folds = wfa.get("folds") or []
    if not isinstance(folds, list):
        folds = []
    wfa_trades = wfa.get("total_oos_trades")
    if wfa_trades is None:
        wfa_trades = sum(
            int(fold.get("oos_trades") or 0)
            for fold in folds
            if isinstance(fold, dict)
        )
    risk_pct = (document.get("risk") or {}).get("risk_per_trade_pct")
    size_factor = block.get("size_factor")
    mode = block.get("mode") or "block"
    effective_risk_pct = risk_pct
    if (
        not verdict["passed"]
        and mode == "reduce"
        and isinstance(risk_pct, (int, float))
        and isinstance(size_factor, (int, float))
    ):
        effective_risk_pct = round(float(risk_pct) * float(size_factor), 6)
    return {
        "required": True,
        "passed": bool(verdict["passed"]),
        "reason": verdict["reason"],
        "mode": mode,
        "size_factor": size_factor,
        "configured_risk_pct": risk_pct,
        "effective_risk_pct": effective_risk_pct,
        "pbo": pbo_block.get("pbo"),
        "pbo_threshold": pbo_check.get("threshold"),
        "dsr": dsr_block.get("dsr"),
        "dsr_threshold": dsr_check.get("threshold"),
        "wfa_oos_trades": wfa_trades,
        "wfa_folds": wfa.get("evaluated_folds", len(folds)),
        "wfa_pf": wfa.get("oos_pf_aggregate"),
        "stress_pf": stress_check.get("value"),
        "blocking_gate": blocking["name"] if blocking else None,
        "blocking_detail": blocking["reason"] if blocking else None,
        "blocking_value": blocking["value"] if blocking else None,
        "blocking_threshold": blocking["threshold"] if blocking else None,
        "checks": checks,
        "cycle_path": block.get("cycle"),
        "cycle_generated_at": (cycle or {}).get("generated_at"),
        "cycle_id": (cycle or {}).get("cycle_id"),
    }


def _kv(connection: sqlite3.Connection, key: str) -> Any:
    try:
        row = connection.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    try:
        return json.loads(row["value"])
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _profile_risk(profile: Path) -> dict[str, Any]:
    config = profile / "config.json"
    try:
        document = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return document.get("risk") or {}


def _heartbeat_age(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds()


def health_state(
    profile: Path, capital: float, pnl: float, books_state: dict[str, Any]
) -> dict[str, Any]:
    """Salud operativa: drawdown, parada dura, latido y emergencia."""
    risk = _profile_risk(profile)
    peak = _number(books_state.get("peak"))
    equity = float(capital) + float(pnl)
    drawdown = (peak - equity) / peak * 100 if peak and peak > 0 else None
    halt_at = None
    if risk.get("soft_brakes") and risk.get("max_drawdown_pct"):
        halt_at = float(risk["max_drawdown_pct"]) * float(
            risk.get("soft_brake_halt_multiple") or 1.0
        )
    age = _heartbeat_age(books_state.get("heartbeat"))
    loss_pct = _number(risk.get("max_daily_loss_pct"))
    max_trades = _number(risk.get("max_trades_per_day"))
    return {
        "drawdown_pct": drawdown,
        "daily_loss_limit": (
            -abs(float(capital) * loss_pct / 100) if loss_pct else None
        ),
        "max_daily_trades": int(max_trades) if max_trades else None,
        "halt_at_pct": halt_at,
        "halted": bool(
            halt_at is not None and drawdown is not None and drawdown >= halt_at
        ),
        "heartbeat_s": age,
        "emergency": bool(books_state.get("emergency") or False),
    }


# Un latido más viejo que esto ya no es una pausa normal del mercado.
STALE_SECONDS = 600.0


def alarms(
    health: dict[str, Any] | None,
    promotion: dict[str, Any] | None,
    stored: dict[str, Any],
) -> list[str]:
    """Lo que un operador debe mirar sin leer el informe entero."""
    problems: list[str] = []
    if health:
        if health.get("halted"):
            problems.append("parada dura")
        if health.get("emergency"):
            problems.append("emergencia")
        age = health.get("heartbeat_s")
    else:
        age = _heartbeat_age(stored.get("heartbeat"))
    if age is None:
        problems.append("sin latido")
    elif float(age) > STALE_SECONDS:
        problems.append("latido viejo")
    if promotion is not None and not promotion.get("passed"):
        if (promotion.get("mode") or "block") == "block":
            problems.append("sin promoción")
    return problems


def books(db_path: Path) -> dict[str, Any]:
    """Lo guardado aparte del libro: última fila de la curva y equity del estado.

    Si estos números y el libro no coinciden, el panel enseña una cifra y la
    cuenta de papel otra. Se leen aquí para poder avisar sin abrir el servidor.
    """
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        # Una base a medio crear puede no tener aún curva ni estado: se avisa
        # con `None`, no se rompe la lectura del libro.
        try:
            row = conn.execute("SELECT equity FROM equity ORDER BY id DESC LIMIT 1").fetchone()
            curve_rows = int(conn.execute("SELECT COUNT(*) FROM equity").fetchone()[0])
        except sqlite3.OperationalError:
            row = None
            curve_rows = None
        state = _kv(conn, "equity")
        peak = _kv(conn, "peak_equity")
        heartbeat = _kv(conn, "heartbeat")
        emergency = _kv(conn, "emergency")
        day = _kv(conn, "day_stats")
        session = _kv(conn, "session_id")
    finally:
        conn.close()
    return {
        "curve": float(row["equity"]) if row else None,
        "rows": curve_rows,
        "state": _number(state),
        "peak": _number(peak),
        "heartbeat": heartbeat,
        "emergency": bool(emergency) if emergency is not None else None,
        "day": day if isinstance(day, dict) else None,
        "session": session if isinstance(session, str) else None,
    }


def _money(value: Any) -> str:
    return f"{float(value or 0.0):,.2f}".replace(",", " ")


def _times(value: Any) -> str:
    number = float(value)
    return f"{number:,.0f}".replace(",", " ") if abs(number) >= 10 else f"{number:,.1f}"


def render(
    summary: dict[str, Any],
    capital: float,
    label: str,
    books_state: dict[str, Any] | None = None,
    exposure_info: dict[str, Any] | None = None,
    anomalies: dict[str, Any] | None = None,
    promotion: dict[str, Any] | None = None,
    health: dict[str, Any] | None = None,
) -> str:
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
    if exposure_info and exposure_info.get("max_multiple") is not None:
        lines.append(
            f"exposición: nocional máximo {_money(exposure_info.get('max_notional'))} "
            f"({_times(exposure_info['max_multiple'])}× el capital) · "
            f"mediana {_times(exposure_info.get('median_multiple') or 0)}×"
        )
    if anomalies and int(anomalies.get("trades") or 0):
        pf_without = anomalies.get("pf_without")
        pf_text = "—" if pf_without is None else f"{float(pf_without):.3f}"
        lines.append(
            f"libro: {int(anomalies['trades'])} cierres anteriores a la apertura · "
            f"P&L {_money(anomalies.get('pnl_net'))} incluido · "
            f"equity sin ellas {_money(anomalies.get('equity_without'))} · "
            f"PF sin ellas {pf_text}"
        )
    if promotion is not None:
        if promotion.get("passed"):
            lines.append("puerta: promovida · riesgo completo")
        else:
            size = promotion.get("size_factor")
            brake = (
                f" · modo {promotion.get('mode')} al {float(size) * 100:.0f} %"
                if size is not None and float(size) < 1
                else f" · modo {promotion.get('mode')}"
            )
            lines.append(f"puerta: no promovida ({promotion.get('reason')}){brake}")
    if health is not None and health.get("drawdown_pct") is not None:
        parts = [f"drawdown {float(health['drawdown_pct']):.2f} %"]
        if health.get("halt_at_pct") is not None:
            parts.append(
                f"parada dura al {float(health['halt_at_pct']):.2f} %"
                + (" ACTIVA" if health.get("halted") else "")
            )
        age = health.get("heartbeat_s")
        parts.append(f"latido hace {_ago(age)}" if age is not None else "sin latido")
        if health.get("emergency"):
            parts.append("emergencia activa")
        lines.append("estado: " + " · ".join(parts))
    day = (books_state or {}).get("day")
    if isinstance(day, dict) and day.get("trades") is not None:
        session = (books_state or {}).get("session")
        limit = health.get("daily_loss_limit") if health else None
        max_trades = health.get("max_daily_trades") if health else None
        trades = int(day.get("trades") or 0)
        ops = f"{trades}/{max_trades} ops" if max_trades else f"{trades} ops"
        pnl_text = f"P&L {_money(day.get('pnl'))}"
        if limit is not None:
            pnl_text += f" de {_money(limit)}"
        detail = (
            f"día: {ops} · {pnl_text} · "
            f"racha {int(day.get('consecutive_losses') or 0)}"
        )
        if session:
            detail += f" · sesión {session}"
        lines.append(detail)
    if books_state:
        expected = capital + pnl
        curve = books_state.get("curve")
        state = books_state.get("state")
        rows = books_state.get("rows")
        closed_trades = int(closed.get("trades") or 0)
        agree = (
            curve is not None
            and abs(float(curve) - expected) < 0.01
            and (state is None or abs(float(state) - expected) < 0.01)
            and (rows is None or int(rows) == closed_trades)
        )
        lines.append(
            f"curva {_money(curve)} · estado {_money(state)} · "
            + ("cuadra con el libro" if agree else "NO cuadra con el libro")
        )
        if rows is not None and int(rows) != closed_trades:
            lines.append(
                f"filas de curva: {int(rows)} para {closed_trades} operaciones cerradas"
            )
    return "\n".join(lines)


def _ago(seconds: float) -> str:
    if seconds < 90:
        return f"{seconds:.0f} s"
    if seconds < 5400:
        return f"{seconds / 60:.0f} min"
    return f"{seconds / 3600:.1f} h"


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


def _profile_contract_size(profile: Path | None) -> float | None:
    if profile is None:
        return None
    try:
        document = json.loads((profile / "config.json").read_text(encoding="utf-8"))
        items = (document.get("instruments") or {}).get("items") or []
        primary = (document.get("instruments") or {}).get("primary")
        item = next((row for row in items if row.get("symbol") == primary), None)
        if not item:
            return None
        size = float(item["contract_size"])
        return size if math.isfinite(size) and size > 0 else None
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError, ZeroDivisionError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumen de la cuenta de papel")
    parser.add_argument("--db", default=None, help="base SQLite a leer")
    parser.add_argument("--profile", default=None, help="carpeta del perfil")
    parser.add_argument("--capital", type=float, default=None, help="capital inicial")
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="sale 1 si hay parada, emergencia, latido viejo o puerta bloqueada",
    )
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    profile = Path(args.profile) if args.profile else None
    if profile:
        db, capital = _profile_defaults(profile)
    else:
        db, capital = Path(args.db or "data/terminal.db"), 25_000.0
    if args.capital is not None:
        capital = args.capital

    if not db.is_file():
        print(f"no hay base en {db}: el bot no ha operado todavía", flush=True)
        return 1

    trades = read_trades(db)
    result = aggregate(trades, capital)
    stored = books(db)
    leaked = exposure(trades, capital, _profile_contract_size(profile))
    broken = impossible(trades, capital)
    gate = promotion_state(profile) if profile else None
    health = (
        health_state(
            profile, capital, float(result["closed"].get("pnl_net") or 0.0), stored
        )
        if profile
        else None
    )
    problems = alarms(health, gate, stored) if args.strict else []
    if args.json:
        print(
            json.dumps(
                {
                    "db": str(db),
                    "capital": capital,
                    "summary": result,
                    "books": stored,
                    "exposure": leaked,
                    "anomalies": broken,
                    "promotion": gate,
                    "alarms": problems,
                },
                indent=2,
            )
        )
    else:
        print(render(result, capital, str(db), stored, leaked, broken, gate, health))
    if problems:
        print("revisar: " + ", ".join(problems), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
