"""Watchdog del dashboard.

Comprueba ``/health`` cada pocos segundos. Si el proceso deja de responder,
mata solo el PID que ocupa el puerto 8765 y relanza ``run.py`` con el perfil
``okx``. El watchdog nunca llama a ``/api/bot/start``: el paper se reanuda o no
según el ``auto_start`` del perfil, que en ``okx`` está en ``true``.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "profiles" / "okx" / "config.json"
DATABASE = ROOT / "profiles" / "okx" / "terminal.db"
LOG_PATH = ROOT / "data" / "watchdog.log"
SERVER_LOG = ROOT / "data" / "paper-15m-server.log"
HOST = "127.0.0.1"
PORT = 8765
HEALTH_URL = f"http://{HOST}:{PORT}/health"
CHECK_INTERVAL = 5.0
FAILURES_BEFORE_RESTART = 3
RESTART_COOLDOWN = 30.0
START_TIMEOUT = 30.0


def health_ok() -> bool:
    """El servidor responde y su liveness dice ok."""
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, ValueError, urllib.error.URLError):
        return False
    return payload.get("status") == "ok"


def listening_pid() -> int | None:
    """PID que escucha en el puerto, solo si es el listener TCP."""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for line in result.stdout.splitlines():
        parts = line.split()
        if (
            len(parts) >= 5
            and parts[0].upper() == "TCP"
            and f":{PORT}" in parts[1]
            and parts[3].upper() == "LISTENING"
        ):
            try:
                return int(parts[-1])
            except ValueError:
                continue
    return None


def stop_listener(pid: int) -> None:
    logging.warning("matando el proceso %s que ocupa el puerto %s", pid, PORT)
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=10,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            logging.exception("no se pudo terminar el proceso %s", pid)


def start_server() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["EZUR_CONFIG_PATH"] = str(PROFILE)
    env["EZUR_DB_PATH"] = str(DATABASE)
    env["EZUR_HOST"] = HOST
    env["EZUR_PORT"] = str(PORT)
    env.pop("EZUR_OPEN", None)
    log = open(SERVER_LOG, "ab", buffering=0)
    try:
        return subprocess.Popen(
            [sys.executable, str(ROOT / "run.py")],
            cwd=str(ROOT),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    finally:
        log.close()


def wait_health(timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if health_ok():
            return True
        time.sleep(1)
    return False


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(LOG_PATH),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        encoding="utf-8",
    )
    logging.info("watchdog iniciado; health=%s", HEALTH_URL)
    failures = 0
    last_restart = 0.0
    try:
        while True:
            if health_ok():
                if failures:
                    logging.info("servidor recuperado")
                failures = 0
                time.sleep(CHECK_INTERVAL)
                continue
            failures += 1
            logging.warning(
                "healthcheck falló (%s/%s)", failures, FAILURES_BEFORE_RESTART
            )
            if failures < FAILURES_BEFORE_RESTART:
                time.sleep(CHECK_INTERVAL)
                continue
            now = time.monotonic()
            if now - last_restart < RESTART_COOLDOWN:
                time.sleep(CHECK_INTERVAL)
                continue
            last_restart = now
            failures = 0
            pid = listening_pid()
            if pid is not None:
                stop_listener(pid)
                time.sleep(1)
            process = start_server()
            logging.info("servidor relanzado (pid wrapper=%s)", process.pid)
            if wait_health(START_TIMEOUT):
                logging.info("servidor sano de nuevo")
            else:
                logging.error("el servidor no respondió tras %ss", START_TIMEOUT)
                if process.poll() is None:
                    process.terminate()
            time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logging.info("watchdog detenido")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
