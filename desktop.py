"""Lanzador de escritorio de ezur: servidor local + ventana nativa.

No reimplementa nada. Arranca exactamente el mismo `server.main:app` que `run.py`
en `127.0.0.1` con un puerto libre, espera a que responda y lo muestra en una
ventana (WebView2 en Windows). El motor, el riesgo, las estrategias y la base de
datos siguen siendo los mismos objetos: esto es solo otro envoltorio.

Dos detalles que sí importan para un ejecutable:

* El servidor resuelve `frontend/dist`, `data/` y `profiles/` **relativo al
  directorio de trabajo**, así que el lanzador se coloca en la carpeta del
  ejecutable antes de importar `server.main`.
* En modo ventana no hay consola: si algo falla, el motivo va a
  `%LOCALAPPDATA%\\ezur\\logs\\desktop.log`. Un cierre silencioso sin rastro es
  el peor fallo posible en una app de escritorio.

Uso:

    python desktop.py                 # ventana
    python desktop.py --self-test     # arranca, comprueba la API y sale
    python desktop.py --no-window     # servidor sin ventana (para depurar)
    python desktop.py --port 8790     # puerto fijo
    python desktop.py --check-update  # ¿hay versión nueva publicada?
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_NAME = "ezur"
WINDOW_TITLE = "ezur · trading terminal"
LOGGER = logging.getLogger("ezur.desktop")


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Carpeta del ejecutable si está empaquetado, la del repo si no."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def state_dir() -> Path:
    base = os.getenv("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def setup_logging(debug: bool) -> Path:
    log_file = state_dir() / "logs" / "desktop.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if is_frozen():
        # Sin consola, `sys.stdout`/`sys.stderr` son None: se redirigen al log
        # para que un traceback de uvicorn o de webview no se pierda.
        stream = open(log_file, "a", buffering=1, encoding="utf-8")
        if sys.stdout is None:
            sys.stdout = stream
        if sys.stderr is None:
            sys.stderr = stream
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8", errors="replace")],
    )
    return log_file


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def fetch(url: str, timeout: float = 2.0) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.status, response.read()


def wait_ready(base_url: str, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _ = fetch(f"{base_url}/api/status", timeout=1.5)
            if status == 200:
                return True
        except (urllib.error.URLError, OSError, TimeoutError):
            time.sleep(0.25)
    return False


def start_server(port: int) -> tuple[object, threading.Thread]:
    """`uvicorn.Server` en un hilo daemon; se para con `should_exit`."""
    import uvicorn

    config = uvicorn.Config(
        "server.main:app",
        host="127.0.0.1",
        port=port,
        log_level="info",
        access_log=False,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="ezur-uvicorn", daemon=True)
    thread.start()
    return server, thread


def self_test(base_url: str) -> int:
    """Arranque real sin ventana: API, snapshot y assets de la UI."""
    status, body = fetch(f"{base_url}/api/status")
    payload = json.loads(body.decode("utf-8"))
    data = payload.get("data", payload)
    html_status, html = fetch(f"{base_url}/")
    html_text = html.decode("utf-8", "replace")
    report = {
        "url": base_url,
        "api_status": status,
        "engine_status": data.get("status"),
        "strategy": (data.get("strategy") or {}).get("id"),
        "feed": (data.get("data") or {}).get("provider"),
        "ui_status": html_status,
        "ui_has_root": 'id="root"' in html_text,
        "ui_bytes": len(html),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    ok = status == 200 and html_status == 200 and report["ui_has_root"]
    return 0 if ok else 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog=APP_NAME, description=__doc__)
    parser.add_argument("--port", type=int, default=0, help="puerto fijo (0 = libre)")
    parser.add_argument("--self-test", action="store_true", help="arranca, comprueba y sale")
    parser.add_argument("--no-window", action="store_true", help="servidor sin ventana")
    parser.add_argument("--check-update", action="store_true", help="comprueba si hay versión nueva y sale")
    parser.add_argument("--auto-close", type=float, default=0.0, help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args(argv)

    root = app_dir()
    # Antes de importar `server.main`: resuelve dist/, data/ y profiles/ desde aquí.
    os.chdir(root)
    log_file = setup_logging(args.debug)
    LOGGER.info("arranque dir=%s frozen=%s log=%s", root, is_frozen(), log_file)

    if args.check_update:
        from server import __version__
        from server.update import DEFAULT_URL, current_status

        url = os.getenv("EZUR_UPDATE_URL") or DEFAULT_URL
        status = current_status(url, __version__)
        print(json.dumps(status, ensure_ascii=False, indent=2))
        return 0

    if not (root / "frontend" / "dist" / "index.html").is_file():
        LOGGER.error("falta frontend/dist/index.html en %s", root)
        print(f"falta la interfaz compilada en {root / 'frontend' / 'dist'}", file=sys.stderr)
        return 3

    port = args.port or free_port()
    base_url = f"http://127.0.0.1:{port}"
    server, thread = start_server(port)

    if not wait_ready(base_url):
        LOGGER.error("el servidor no respondió en %s", base_url)
        print(f"el servidor no respondió en {base_url}", file=sys.stderr)
        return 2

    LOGGER.info("servidor listo en %s", base_url)

    if args.self_test:
        return self_test(base_url)

    if args.no_window:
        print(base_url, flush=True)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        return 0

    import webview

    window = webview.create_window(
        WINDOW_TITLE,
        base_url,
        width=1440,
        height=900,
        min_size=(1024, 640),
        background_color="#070b11",
    )

    def closer() -> None:
        time.sleep(args.auto_close)
        LOGGER.info("cierre automático tras %.1fs", args.auto_close)
        window.destroy()

    try:
        webview.start(
            closer if args.auto_close > 0 else None,
            private_mode=False,
            storage_path=str(state_dir() / "webview"),
        )
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        LOGGER.info("ventana cerrada, servidor parado")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
