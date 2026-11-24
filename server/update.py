"""¿Hay una versión más nueva que la que corre?

Comprobar sí, instalar no. Este módulo no descarga ni ejecuta nada: lee un
manifiesto JSON (o el endpoint de releases de GitHub) y dice qué versión hay
publicada, dónde se bajaría y con qué notas. Reemplazar un ejecutable en
caliente sin firma es exactamente la comodidad que un antivirus marca con razón,
así que el paso de instalar sigue siendo del usuario.

El canal se elige con `EZUR_UPDATE_URL` (https o file). Sin canal configurado no
se sale a la red: la app solo muestra su versión. Formato mínimo del manifiesto:

    {"version": "0.2.0", "url": "https://.../ezur-setup-0.2.0.exe", "notes": "..."}

El fallo nunca es una excepción: si no hay red, el manifiesto está roto o la URL
no existe, se devuelve `error` y la app sigue funcionando.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

# Sin canal por defecto: el repositorio es privado y una URL que siempre da 404
# solo genera ruido. Quien quiera avisos apunta EZUR_UPDATE_URL a su manifiesto.
DEFAULT_URL = ""
USER_AGENT = "ezur-update-check"

_VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")

UNCONFIGURED = "sin canal de actualizaciones configurado (EZUR_UPDATE_URL)"

_CACHE: dict[str, Any] = {"key": None, "at": 0.0, "payload": None}
_LOCK = threading.Lock()


def empty_status(current: str, error: str | None = None) -> dict[str, Any]:
    """Respuesta sin comprobación: la misma forma que `check`, sin red."""
    return {
        "current": current,
        "latest": None,
        "available": False,
        "url": None,
        "notes": None,
        "checked_at": None,
        "error": error,
    }


def parse_version(text: str) -> tuple[int, int, int]:
    """`v0.2.0` → (0, 2, 0). Acepta prefijo y sufijo; rechaza lo que no sea semver."""
    match = _VERSION_RE.search(text or "")
    if not match:
        raise ValueError(f"versión no reconocida: {text!r}")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def is_newer(latest: str, current: str) -> bool:
    """Compara numéricamente: 0.10.0 es más nuevo que 0.9.0, que el texto no ve."""
    try:
        return parse_version(latest) > parse_version(current)
    except ValueError:
        return False


def _manifest(payload: dict[str, Any] | list[Any]) -> dict[str, str]:
    """Acepta el manifiesto propio, un release de GitHub o una lista de ellos."""
    if isinstance(payload, list):
        payload = payload[0] if payload and isinstance(payload[0], dict) else {}
    if not isinstance(payload, dict):
        return {"version": "", "url": "", "notes": ""}
    version = str(payload.get("version") or payload.get("tag_name") or "")
    url = str(payload.get("url") or payload.get("html_url") or "")
    notes = str(payload.get("notes") or payload.get("body") or "")
    return {"version": version.lstrip("vV").strip(), "url": url, "notes": notes}


def _fetch(url: str, timeout: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def check(
    url: str,
    current: str,
    timeout: float = 3.0,
    fetch: Callable[[str, float], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Una comprobación, sin caché y sin excepciones."""
    result: dict[str, Any] = {
        "current": current,
        "latest": None,
        "available": False,
        "url": None,
        "notes": None,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "error": None,
    }
    try:
        manifest = _manifest((fetch or _fetch)(url, timeout))
        if not manifest["version"]:
            raise ValueError("el manifiesto no trae versión")
    except Exception as error:  # red, 404, JSON roto: la app no se entera
        result["error"] = f"{type(error).__name__}: {error}"[:200]
        return result

    result["latest"] = manifest["version"]
    result["url"] = manifest["url"] or None
    result["notes"] = manifest["notes"] or None
    result["available"] = is_newer(manifest["version"], current)
    return result


def check_cached(
    url: str,
    current: str,
    ttl: float = 6 * 3600,
    error_ttl: float = 120,
    timeout: float = 3.0,
    clock: Callable[[], float] | None = None,
    fetch: Callable[[str, float], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Igual que `check`, pero sin golpear la red en cada carga de la UI.

    Los fallos se cachean poco (dos minutos): un error de red no debe dejar la
    app diciendo «sin actualizaciones» durante seis horas.
    """
    now = (clock or time.time)()
    key = f"{url}|{current}"
    with _LOCK:
        cached = _CACHE["payload"]
        if cached and _CACHE["key"] == key:
            window = error_ttl if cached["error"] else ttl
            if now - _CACHE["at"] < window:
                return cached

    payload = check(url, current, timeout=timeout, fetch=fetch)
    with _LOCK:
        _CACHE.update(key=key, at=now, payload=payload)
    return payload


def current_status(url: str, current: str, **kwargs: Any) -> dict[str, Any]:
    """El único punto de entrada: sin canal no se sale a la red."""
    if not url:
        return empty_status(current, UNCONFIGURED)
    return check_cached(url, current, **kwargs)


def reset_cache() -> None:
    """Para los tests: cada caso parte de cero."""
    with _LOCK:
        _CACHE.update(key=None, at=0.0, payload=None)
