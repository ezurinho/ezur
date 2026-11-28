"""Vigilancia AFK de solo lectura para el bot en paper.

No decide, no opera y no toca la base: consulta los endpoints, comprueba el lock
del watchdog y deja un snapshot JSONL + un resumen Markdown en `data/afk/`.
Se puede ejecutar una vez (`--once`, para Task Scheduler) o en bucle
(`--loop --interval 600`).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.instance_lock import InstanceAlreadyRunning, InstanceLock  # noqa: E402

BASE_URL = "http://127.0.0.1:8765"
HEALTH_URL = f"{BASE_URL}/api/health"
READY_URL = f"{BASE_URL}/api/ready"
STATUS_URL = f"{BASE_URL}/api/status"
TIMEOUT = 3.0
DEFAULT_INTERVAL = 600.0
LOG_LINES = 12


def _fetch(url: str) -> dict[str, Any]:
    """Devuelve status, payload y error sin lanzar por un 503 o una caída."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
            raw = response.read()
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                return {
                    "http": response.status,
                    "payload": None,
                    "error": f"json inválido: {error}",
                }
            return {"http": response.status, "payload": payload, "error": None}
    except urllib.error.HTTPError as error:
        raw = error.read()
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        return {"http": error.code, "payload": payload, "error": None}
    except (OSError, urllib.error.URLError) as error:
        return {"http": None, "payload": None, "error": str(error)}


def _get(payload: Any, *keys: str) -> Any:
    current = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def watchdog_state() -> dict[str, Any]:
    """El lock es la verdad: un PID en un fichero puede quedar pegado."""
    lock = InstanceLock(ROOT / "data" / "watchdog.lock")
    try:
        lock.acquire()
    except InstanceAlreadyRunning as error:
        return {"running": True, "pid": error.pid, "since": error.since}
    except OSError as error:
        return {"running": None, "pid": None, "since": None, "error": str(error)}
    else:
        lock.release()
        return {"running": False, "pid": None, "since": None}


def _tail(path: Path, lines: int = LOG_LINES) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return text.splitlines()[-lines:]


def collect() -> dict[str, Any]:
    health = _fetch(HEALTH_URL)
    ready = _fetch(READY_URL)
    status = _fetch(STATUS_URL)
    snapshot = _get(status.get("payload"), "data") or {}
    ready_payload = ready.get("payload")
    health_payload = health.get("payload")
    if not isinstance(ready_payload, dict):
        ready_payload = {}
    if not isinstance(health_payload, dict):
        health_payload = {}

    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ok": bool(ready_payload.get("ready")),
        "health": {
            "http": health.get("http"),
            "error": health.get("error"),
            "version": health_payload.get("version"),
            "readiness": health_payload.get("readiness"),
            "engine": health_payload.get("engine"),
        },
        "ready": ready,
        "bot": {
            "http": status.get("http"),
            "error": status.get("error"),
            "status": _get(snapshot, "status"),
            "mode": _get(snapshot, "mode"),
            "session": _get(snapshot, "session", "label"),
            "quality": _get(snapshot, "data", "quality"),
            "provider": _get(snapshot, "data", "provider"),
            "last_bar_ts": _get(snapshot, "data", "last_bar_ts"),
            "staleness_ms": _get(snapshot, "data", "staleness_ms"),
            "block_reason": _get(snapshot, "risk", "block_reason"),
            "position": _get(snapshot, "position"),
            "orders": len(_get(snapshot, "orders") or []),
        },
        "watchdog": watchdog_state(),
        "logs": {
            "watchdog": _tail(ROOT / "data" / "watchdog.log"),
            "engine": _tail(ROOT / "data" / "run" / "engine.log", 8),
            "server": _tail(ROOT / "data" / "paper-15m-server.log", 8),
        },
    }


def _markdown(snapshot: dict[str, Any]) -> str:
    bot = snapshot["bot"]
    watchdog = snapshot["watchdog"]
    health = snapshot["health"]
    engine = health.get("engine") or {}
    ready = snapshot["ready"].get("payload") or {}
    reasons = ", ".join(ready.get("reasons") or []) or "ninguno"
    position = bot.get("position")
    position_text = "sin posición" if not position else json.dumps(position, ensure_ascii=False)

    lines = [
        f"# Vigilancia AFK — {snapshot['ts']}",
        "",
        "| Comprobación | Valor |",
        "|---|---|",
        f"| `/api/ready` | `{snapshot['ok']}` |",
        f"| Razones | {reasons} |",
        f"| Motor | `{engine.get('status')}` / `{engine.get('mode')}` |",
        f"| Feed | `{bot.get('provider')}` / `{bot.get('quality')}` |",
        f"| Última vela | `{bot.get('last_bar_ts')}` (hace {bot.get('staleness_ms')} ms) |",
        f"| Bloqueo | `{bot.get('block_reason')}` |",
        f"| Posición | {position_text} |",
        f"| Órdenes | {bot.get('orders')} |",
        f"| Watchdog | `{watchdog.get('running')}` (pid {watchdog.get('pid')}) |",
        "",
        "## Watchdog (últimas líneas)",
        "",
        "```text",
        *snapshot["logs"]["watchdog"],
        "```",
        "",
        "## Motor (últimas líneas)",
        "",
        "```text",
        *snapshot["logs"]["engine"],
        "```",
        "",
    ]
    return "\n".join(lines)


def write_report(snapshot: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = out_dir / f"afk-{stamp}.json"
    json_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    with (out_dir / "monitor.jsonl").open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    (out_dir / "latest.md").write_text(_markdown(snapshot), encoding="utf-8")
    return json_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vigilancia AFK de solo lectura")
    parser.add_argument("--once", action="store_true", help="un snapshot y sale")
    parser.add_argument("--loop", action="store_true", help="repite hasta Ctrl+C")
    parser.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL,
        help="segundos entre snapshots en modo bucle (mínimo 30)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "afk",
        help="directorio del reporte",
    )
    args = parser.parse_args(argv)

    if not args.once and not args.loop:
        parser.error("usa --once o --loop")
    if args.interval < 30:
        parser.error("--interval no puede ser menor de 30 segundos")

    while True:
        snapshot = collect()
        path = write_report(snapshot, args.out)
        state = "ok" if snapshot["ok"] else "revisar"
        print(f"{snapshot['ts']} {state} -> {path}", flush=True)
        if args.once:
            return 0
        try:
            time.sleep(args.interval)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
