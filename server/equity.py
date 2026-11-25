"""Reconstruye la curva de equity desde el libro, que es la única verdad.

La curva se escribía al cerrar cada operación con el equity que había en
memoria. Un tick viejo podía cerrar dos veces la misma operación: el libro
quedaba con una sola fila —`insert_trade_once` rechaza la repetida— pero la
memoria sumaba el P&L dos veces, y esa desviación se guardaba en la curva y en
el estado del motor. Resultado: el panel enseñaba 24.210,09 y el libro decía
24.356,41.

Reconstruir desde las operaciones devuelve las tres cosas a la misma cifra:

    python -m server.equity --profile profiles/okx           # enseña, no toca
    python -m server.equity --profile profiles/okx --apply   # reescribe con copia

`--apply` hace una copia de la base antes de tocar nada y es idempotente: dos
pasadas seguidas dejan exactamente la misma tabla.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .migrations import apply_migrations

EQUITY_TOLERANCE = 0.01


def _instant(value: Any) -> datetime:
    """Texto ISO a instante: ordenar por texto miente si hay desfases distintos."""
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    stamp = datetime.fromisoformat(text)
    return stamp if stamp.tzinfo is not None else stamp.replace(tzinfo=timezone.utc)


def load_trades(db_path: Path, mode: str | None = "paper") -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(trades)")}
        funding = "funding" if "funding" in columns else "0.0 AS funding"
        where = "WHERE mode = ?" if mode else ""
        params: tuple[Any, ...] = (mode,) if mode else ()
        rows = conn.execute(
            "SELECT id, opened_ts, closed_ts, pnl_gross, fees, "
            f"{funding}, pnl_net FROM trades {where}",
            params,
        ).fetchall()
    finally:
        conn.close()
    trades = [dict(row) for row in rows]
    trades.sort(key=lambda trade: (_instant(trade["closed_ts"]), trade["id"]))
    return trades


def _net(trade: dict[str, Any]) -> float:
    """P&L neto desde sus componentes, no desde la copia que se pueda haber
    quedado atrás. Las filas anteriores a la columna `funding` no tienen
    componentes y conservan su `pnl_net` guardado; no se inventa nada."""
    gross = float(trade.get("pnl_gross") or 0.0)
    fees = float(trade.get("fees") or 0.0)
    funding = float(trade.get("funding") or 0.0)
    stored = float(trade.get("pnl_net") or 0.0)
    if gross == 0.0 and fees == 0.0 and funding == 0.0 and stored != 0.0:
        return stored
    return gross - fees + funding


def curve(trades: list[dict[str, Any]], initial: float) -> list[dict[str, Any]]:
    """Un punto por operación cerrada, en orden de cierre, acumulando el P&L neto."""
    running = float(initial)
    points: list[dict[str, Any]] = []
    for trade in trades:
        running += _net(trade)
        points.append({"ts": trade["closed_ts"], "equity": round(running, 8)})
    return points


def day_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """El resumen del último día con operaciones, como lo lleva el motor."""
    if not trades:
        return {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "consecutive_losses": 0}
    session = str(trades[-1]["closed_ts"])[:10]
    same_day = [t for t in trades if str(t["closed_ts"])[:10] == session]
    wins = sum(1 for t in same_day if _net(t) > 0)
    streak = 0
    for trade in reversed(same_day):
        if _net(trade) > 0:
            break
        streak += 1
    return {
        "trades": len(same_day),
        "wins": wins,
        "losses": len(same_day) - wins,
        "pnl": round(sum(_net(t) for t in same_day), 8),
        "consecutive_losses": streak,
    }


def engine_alive(db_path: Path, *, window_s: float = 120.0) -> bool:
    """¿Hay un motor escribiendo en esta base ahora mismo?

    Se apoya en el latido que deja `_persist` en cada vela. Reescribir la curva
    con el motor vivo es una carrera perdida: la siguiente vela vuelve a
    escribir desde su memoria y deshace el trabajo.
    """
    try:
        conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            row = conn.execute("SELECT value FROM kv WHERE key = 'heartbeat'").fetchone()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return False
    if not row:
        return False
    try:
        stamp = datetime.fromisoformat(json.loads(row[0]))
    except (TypeError, ValueError):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamp).total_seconds() < window_s


def current(db_path: Path) -> dict[str, Any]:
    """Lo que hay guardado ahora: última fila de la curva y equity del estado."""
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = int(conn.execute("SELECT COUNT(*) AS c FROM equity").fetchone()["c"])
        last = conn.execute("SELECT ts, equity FROM equity ORDER BY id DESC LIMIT 1").fetchone()
        kv = conn.execute("SELECT value FROM kv WHERE key = 'equity'").fetchone()
        stats = conn.execute("SELECT value FROM kv WHERE key = 'day_stats'").fetchone()
        peak = conn.execute("SELECT value FROM kv WHERE key = 'peak_equity'").fetchone()
    finally:
        conn.close()
    return {
        "rows": rows,
        "last_ts": last["ts"] if last else None,
        "last_equity": float(last["equity"]) if last else None,
        "kv_equity": float(json.loads(kv["value"])) if kv else None,
        "kv_peak": float(json.loads(peak["value"])) if peak else None,
        "kv_day_stats": json.loads(stats["value"]) if stats else None,
    }


def stored_curve(db_path: Path) -> list[dict[str, Any]]:
    """La curva guardada completa, en el orden en que se escribió."""
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT ts, equity FROM equity ORDER BY id").fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def audit(db_path: Path, initial: float, mode: str | None = "paper") -> dict[str, Any]:
    """¿Coinciden libro, curva y estado guardados?

    No solo la última cifra: una curva desplazada puede terminar en el número
    correcto y aun así contar operaciones que ya no están en el libro. Se
    comparan todos los puntos, el número de filas y el estado de `kv`.
    """
    planned = plan(db_path, initial, mode)
    stored = current(db_path)
    points = stored_curve(db_path)
    issues: list[str] = []
    differences: dict[str, Any] = {}
    expected = float(planned["last_equity"])
    state = stored["kv_equity"]
    last = stored["last_equity"]

    # Una base recién creada no tiene copias guardadas: el libro es la verdad y
    # no hay contradicción que bloquear.
    if state is None and not points:
        return {
            "ok": True,
            "uninitialized": True,
            "trades": planned["trades"],
            "expected_equity": expected,
            "stored_state": None,
            "stored_last": None,
            "stored_peak": stored["kv_peak"],
            "curve_rows": 0,
            "expected_rows": 0,
            "issues": [],
            "differences": {},
        }

    if state is None:
        issues.append("missing_state")
    if not points and planned["trades"]:
        issues.append("missing_curve")
    if len(points) != len(planned["curve"]):
        differences["curve_rows"] = len(points) - len(planned["curve"])
        issues.append("curve_rows")
    for index, (got, want) in enumerate(zip(points, planned["curve"], strict=False)):
        if _instant(got["ts"]) != _instant(want["ts"]):
            differences[f"curve_ts_{index}"] = {
                "stored": str(got["ts"]),
                "ledger": str(want["ts"]),
            }
            issues.append("curve_timestamp")
            break
        delta = float(got["equity"]) - float(want["equity"])
        if abs(delta) > EQUITY_TOLERANCE:
            differences[f"curve_equity_{index}"] = round(delta, 8)
            issues.append("curve_equity")
            break
    if state is not None and abs(float(state) - expected) > EQUITY_TOLERANCE:
        differences["state_vs_ledger"] = round(float(state) - expected, 8)
        issues.append("state")
    if last is not None and abs(float(last) - expected) > EQUITY_TOLERANCE:
        differences["curve_vs_ledger"] = round(float(last) - expected, 8)
        issues.append("curve")
    peak = stored["kv_peak"]
    if peak is not None:
        required = max(float(initial), float(planned["peak_equity"]), expected)
        if float(peak) < required - EQUITY_TOLERANCE:
            differences["peak_below_equity"] = round(float(peak) - required, 8)
            issues.append("peak")

    return {
        "ok": not issues,
        "uninitialized": False,
        "trades": planned["trades"],
        "expected_equity": expected,
        "stored_state": state,
        "stored_last": last,
        "stored_peak": peak,
        "curve_rows": len(points),
        "expected_rows": len(planned["curve"]),
        "issues": issues,
        "differences": differences,
    }


def plan(db_path: Path, initial: float, mode: str | None = "paper") -> dict[str, Any]:
    trades = load_trades(db_path, mode)
    points = curve(trades, initial)
    return {
        "mode": mode,
        "trades": len(trades),
        "curve": points,
        "last_equity": points[-1]["equity"] if points else float(initial),
        # El pico es lo que mide el drawdown: también se reconstruye.
        "peak_equity": max([float(initial)] + [p["equity"] for p in points]),
        "gross": round(sum(float(t.get("pnl_gross") or 0.0) for t in trades), 8),
        "fees": round(sum(float(t.get("fees") or 0.0) for t in trades), 8),
        "funding": round(sum(float(t.get("funding") or 0.0) for t in trades), 8),
        "net": round(sum(_net(t) for t in trades), 8),
        "day_stats": day_stats(trades),
        "last_exit_ts": trades[-1]["closed_ts"] if trades else None,
    }


def ensure_schema(db_path: Path) -> None:
    """Aplica migraciones antes de escribir; `load_trades` tolera bases viejas."""
    conn = sqlite3.connect(db_path)
    try:
        apply_migrations(conn)
    finally:
        conn.close()


def apply(
    db_path: Path,
    initial: float,
    backup_dir: Path | None = None,
    mode: str | None = "paper",
) -> Path:
    """Reescribe `equity`, `kv` y el `pnl_net` derivado desde el libro.

    Es idempotente: dos pasadas dejan exactamente la misma curva, el mismo
    estado y el mismo pico. La copia se hace antes de tocar nada.
    """
    ensure_schema(db_path)
    planned = plan(db_path, initial, mode)
    trades = load_trades(db_path, mode)
    stored_peak = current(db_path)["kv_peak"]
    # El pico guardado puede ser más alto que la curva (se escribe por vela):
    # bajarlo sin más debilitaría el freno duro. Para bajarlo está --reset-peak.
    peak = max(planned["peak_equity"], float(stored_peak or 0.0))
    backup_dir = backup_dir or Path(".build") / "books-backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{db_path.stem}-{stamp}.db"
    shutil.copy2(db_path, backup)

    conn = sqlite3.connect(db_path)
    repaired = 0
    try:
        with conn:
            conn.execute("DELETE FROM equity")
            conn.executemany(
                "INSERT INTO equity (ts, equity) VALUES (?, ?)",
                [(p["ts"], p["equity"]) for p in planned["curve"]],
            )
            conn.execute(
                "INSERT INTO kv (key, value) VALUES ('equity', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(planned["last_equity"]),),
            )
            conn.execute(
                "INSERT INTO kv (key, value) VALUES ('peak_equity', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(peak),),
            )
            conn.execute(
                "INSERT INTO kv (key, value) VALUES ('day_stats', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(planned["day_stats"]),),
            )
            if planned["last_exit_ts"] is not None:
                conn.execute(
                    "INSERT INTO kv (key, value) VALUES ('last_exit_ts', ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (json.dumps(planned["last_exit_ts"]),),
                )
            # `pnl_net` es una copia derivada: si no coincide con sus
            # componentes, se corrige en la misma transacción. No se toca
            # `r_multiple` porque no se puede reconstruir sin el riesgo original.
            for trade in trades:
                net = _net(trade)
                if abs(net - float(trade.get("pnl_net") or 0.0)) > 1e-9:
                    conn.execute(
                        "UPDATE trades SET pnl_net=? WHERE id=?", (net, trade["id"])
                    )
                    repaired += 1
            if repaired:
                conn.execute(
                    "INSERT INTO events (ts, level, category, message, meta) "
                    "VALUES (?,?,?,?,?)",
                    (
                        datetime.now(timezone.utc).isoformat(),
                        "warn",
                        "maintenance",
                        f"{repaired} operación(es): pnl_net corregido desde gross - fees + funding",
                        json.dumps({"repaired": repaired}),
                    ),
                )
    finally:
        conn.close()
    return backup


def reset_peak(
    db_path: Path,
    initial: float,
    backup_dir: Path | None = None,
    mode: str | None = "paper",
) -> dict[str, Any]:
    """Pone el pico en la equity del libro: la salida de una parada dura.

    El freno duro bloquea para siempre porque, sin operar, la equity no puede
    volver al pico. Esto no cambia el riesgo: deja constancia —evento y copia—
    de que alguien aceptó la pérdida y vuelve a medir el drawdown desde aquí.
    """
    planned = plan(db_path, initial, mode)
    before = current(db_path)
    backup_dir = backup_dir or Path(".build") / "books-backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = backup_dir / f"{db_path.stem}-{stamp}.db"
    shutil.copy2(db_path, backup)
    now = datetime.now(timezone.utc).isoformat()
    conn = sqlite3.connect(db_path)
    try:
        with conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES ('peak_equity', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (json.dumps(planned["last_equity"]),),
            )
            conn.execute(
                "INSERT INTO events (ts, level, category, message, meta) VALUES (?,?,?,?,?)",
                (
                    now,
                    "warn",
                    "risk",
                    "pico reiniciado a la equity del libro: "
                    f"{before['kv_peak']} -> {planned['last_equity']}",
                    json.dumps(
                        {
                            "before": before["kv_peak"],
                            "after": planned["last_equity"],
                            "reason": "manual",
                        }
                    ),
                ),
            )
    finally:
        conn.close()
    return {"backup": str(backup), "before": before["kv_peak"], "after": planned["last_equity"]}


def _resolve(args: argparse.Namespace) -> Path:
    if args.db:
        return Path(args.db)
    return Path(args.profile) / "terminal.db"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconstruye la equity desde el libro")
    parser.add_argument("--db", default=None, help="base de datos (por defecto data/terminal.db)")
    parser.add_argument("--profile", default=None, help="perfil, p. ej. profiles/okx")
    parser.add_argument("--capital", type=float, default=25000.0, help="capital inicial")
    parser.add_argument(
        "--mode",
        default="paper",
        help="modo del libro a reconstruir (paper por defecto; 'all' para todos)",
    )
    parser.add_argument("--apply", action="store_true", help="reescribe la base (con copia)")
    parser.add_argument(
        "--force",
        action="store_true",
        help="reescribe aunque el motor siga vivo (se deshace en la próxima vela)",
    )
    parser.add_argument(
        "--reset-peak",
        action="store_true",
        help="pone el pico en la equity del libro (salida explícita de una parada dura)",
    )
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    db_path = _resolve(args) if (args.db or args.profile) else Path("data/terminal.db")
    if not db_path.is_file():
        print(f"no existe {db_path}", flush=True)
        return 1

    if (args.apply or args.reset_peak) and not args.force and engine_alive(db_path):
        print(
            "el motor está vivo en esta base: páralo o usa --force "
            "(la próxima vela desharía el cambio)",
            flush=True,
        )
        return 2

    mode = None if args.mode == "all" else args.mode
    if args.reset_peak:
        result = reset_peak(db_path, args.capital, mode=mode)
        print(f"pico reiniciado: {result['before']} -> {result['after']}", flush=True)
        print(f"copia: {result['backup']}", flush=True)
        return 0

    planned = plan(db_path, args.capital, mode)
    before = current(db_path)
    audit_before = audit(db_path, args.capital, mode)
    effective_peak = max(planned["peak_equity"], float(before["kv_peak"] or 0.0))
    report = {
        "db": str(db_path),
        "mode": args.mode,
        "trades": planned["trades"],
        "components": {
            "gross": planned["gross"],
            "fees": planned["fees"],
            "funding": planned["funding"],
            "net": planned["net"],
        },
        "before": before,
        "audit_before": audit_before,
        "after": {
            "rows": len(planned["curve"]),
            "last_equity": planned["last_equity"],
            "peak_equity": effective_peak,
            "peak_kept": effective_peak > planned["peak_equity"],
            "day_stats": planned["day_stats"],
        },
        "apply": bool(args.apply),
    }

    if args.apply:
        report["backup"] = str(apply(db_path, args.capital, mode=mode))
        report["audit_after"] = audit(db_path, args.capital, mode)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"base: {db_path} · modo: {args.mode}")
        print(f"operaciones en el libro: {planned['trades']}")
        print(
            f"componentes: bruto {planned['gross']}, fees {planned['fees']}, "
            f"funding {planned['funding']}, neto {planned['net']}"
        )
        print(
            f"antes: curva {before['rows']} filas, última {before['last_equity']}, "
            f"estado {before['kv_equity']}, día {before['kv_day_stats']}"
        )
        print(
            "auditoría antes: "
            + ("cuadra" if audit_before["ok"] else "NO cuadra")
            + (f" · {', '.join(audit_before['issues'])}" if audit_before["issues"] else "")
        )
        print(
            f"después: curva {len(planned['curve'])} filas, última {planned['last_equity']}, "
            f"estado {planned['last_equity']}, pico {effective_peak}, "
            f"día {planned['day_stats']}"
        )
        if report["after"]["peak_kept"]:
            print(
                f"pico conservado en {effective_peak}: la curva no lo supera "
                "(para bajarlo, --reset-peak)"
            )
        if args.apply:
            print(f"copia: {report['backup']}")
            after_audit = report["audit_after"]
            print(
                "auditoría después: "
                + ("cuadra" if after_audit["ok"] else "NO cuadra")
                + (f" · {', '.join(after_audit['issues'])}" if after_audit["issues"] else "")
            )
        else:
            print("modo seco: nada escrito (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
