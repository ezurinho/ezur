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


def load_trades(db_path: Path) -> list[dict[str, Any]]:
    conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            "SELECT id, opened_ts, closed_ts, pnl_net FROM trades ORDER BY closed_ts, id"
        ).fetchall()
    finally:
        conn.close()
    return [dict(row) for row in rows]


def curve(trades: list[dict[str, Any]], initial: float) -> list[dict[str, Any]]:
    """Un punto por operación cerrada, en orden de cierre, acumulando el P&L neto."""
    running = float(initial)
    points: list[dict[str, Any]] = []
    for trade in trades:
        running += float(trade["pnl_net"] or 0.0)
        points.append({"ts": trade["closed_ts"], "equity": round(running, 8)})
    return points


def day_stats(trades: list[dict[str, Any]]) -> dict[str, Any]:
    """El resumen del último día con operaciones, como lo lleva el motor."""
    if not trades:
        return {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0, "consecutive_losses": 0}
    session = str(trades[-1]["closed_ts"])[:10]
    same_day = [t for t in trades if str(t["closed_ts"])[:10] == session]
    wins = sum(1 for t in same_day if float(t["pnl_net"] or 0) > 0)
    streak = 0
    for trade in reversed(same_day):
        if float(trade["pnl_net"] or 0) > 0:
            break
        streak += 1
    return {
        "trades": len(same_day),
        "wins": wins,
        "losses": len(same_day) - wins,
        "pnl": round(sum(float(t["pnl_net"] or 0) for t in same_day), 8),
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
        last = conn.execute("SELECT ts, equity FROM equity ORDER BY ts DESC LIMIT 1").fetchone()
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


def plan(db_path: Path, initial: float) -> dict[str, Any]:
    trades = load_trades(db_path)
    points = curve(trades, initial)
    return {
        "trades": len(trades),
        "curve": points,
        "last_equity": points[-1]["equity"] if points else float(initial),
        # El pico es lo que mide el drawdown: también se reconstruye.
        "peak_equity": max([float(initial)] + [p["equity"] for p in points]),
        "day_stats": day_stats(trades),
        "last_exit_ts": trades[-1]["closed_ts"] if trades else None,
    }


def apply(db_path: Path, initial: float, backup_dir: Path | None = None) -> Path:
    """Reescribe `equity` y el estado de `kv` desde el libro. Devuelve la copia."""
    planned = plan(db_path, initial)
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
    finally:
        conn.close()
    return backup


def reset_peak(db_path: Path, initial: float, backup_dir: Path | None = None) -> dict[str, Any]:
    """Pone el pico en la equity del libro: la salida de una parada dura.

    El freno duro bloquea para siempre porque, sin operar, la equity no puede
    volver al pico. Esto no cambia el riesgo: deja constancia —evento y copia—
    de que alguien aceptó la pérdida y vuelve a medir el drawdown desde aquí.
    """
    planned = plan(db_path, initial)
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

    if args.reset_peak:
        result = reset_peak(db_path, args.capital)
        print(f"pico reiniciado: {result['before']} -> {result['after']}", flush=True)
        print(f"copia: {result['backup']}", flush=True)
        return 0

    planned = plan(db_path, args.capital)
    before = current(db_path)
    effective_peak = max(planned["peak_equity"], float(before["kv_peak"] or 0.0))
    report = {
        "db": str(db_path),
        "trades": planned["trades"],
        "before": before,
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
        report["backup"] = str(apply(db_path, args.capital))

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"base: {db_path}")
        print(f"operaciones en el libro: {planned['trades']}")
        print(
            f"antes: curva {before['rows']} filas, última {before['last_equity']}, "
            f"estado {before['kv_equity']}, día {before['kv_day_stats']}"
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
        else:
            print("modo seco: nada escrito (usa --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
