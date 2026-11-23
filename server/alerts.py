"""External alerts: the events that matter when nobody is looking at the screen.

A stop that only appears on the screen you are not watching is not a stop. The
engine keeps working without it (the notifier is optional and disabled by
default) and a broken webhook never blocks a tick: deliveries are queued and a
daemon thread does the HTTP work.

Design rules:

* ``enqueue`` never raises and never blocks. A full queue drops and counts.
* Failures are counted (``failed``, ``dropped``) instead of logged per attempt:
  a webhook down for an hour must not fill the console with the same line.
* Identical messages inside ``dedupe_window_s`` are sent once. A blocked engine
  emits the same rejection hundreds of times per minute.
* The payload is JSON with a stable shape: ``level``, ``category``, ``message``,
  ``meta``, ``ts`` and ``source``. Whoever receives it can filter without
  knowing this codebase.
"""

from __future__ import annotations

import json
import queue
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

LEVELS: dict[str, int] = {"debug": 10, "info": 20, "warn": 30, "error": 40}
SOURCE = "ezur"


@dataclass(slots=True)
class Alert:
    """One event worth waking a human for."""

    level: str
    category: str
    message: str
    meta: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)

    def payload(self) -> dict[str, Any]:
        return {
            "source": SOURCE,
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "meta": self.meta,
            "ts": round(self.ts, 3),
        }


class WebhookNotifier:
    """Queue plus worker thread that POSTs alerts as JSON.

    ``transport`` exists so tests can capture deliveries without a socket. When
    it is ``None`` the worker uses ``urllib``; that is the only place in the
    codebase that speaks HTTP as a client.
    """

    def __init__(
        self,
        url: str | None,
        *,
        min_level: str = "warn",
        timeout_s: float = 5.0,
        max_retries: int = 3,
        retry_backoff_s: float = 0.5,
        dedupe_window_s: float = 60.0,
        queue_size: int = 256,
        transport: Callable[[dict[str, Any]], None] | None = None,
        on_failure: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_level not in LEVELS:
            raise ValueError(f"min_level inválido: {min_level!r}")
        self.url = url
        self.min_level = min_level
        self.timeout_s = timeout_s
        self.max_retries = max(1, int(max_retries))
        self.retry_backoff_s = max(0.0, retry_backoff_s)
        self.dedupe_window_s = max(0.0, dedupe_window_s)
        self._transport = transport or self._post
        self._on_failure = on_failure
        self._clock = clock
        self._queue: queue.Queue[Alert] = queue.Queue(maxsize=max(1, queue_size))
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.enabled = bool(url)
        self.stats: dict[str, int] = {
            "queued": 0,
            "sent": 0,
            "failed": 0,
            "dropped": 0,
            "deduped": 0,
            "filtered": 0,
        }

    # --- public API -------------------------------------------------------
    def enqueue(
        self,
        level: str,
        category: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> bool:
        """Queue an alert. Returns True when it was accepted."""
        if not self.enabled:
            return False
        if LEVELS.get(level, 0) < LEVELS[self.min_level]:
            self.stats["filtered"] += 1
            return False
        key = f"{level}|{category}|{message}"
        if self._is_duplicate(key):
            self.stats["deduped"] += 1
            return False
        self._start()
        try:
            self._queue.put_nowait(Alert(level, category, message, dict(meta or {})))
        except queue.Full:
            self.stats["dropped"] += 1
            self._fail("cola de alertas llena")
            return False
        self.stats["queued"] += 1
        return True

    def send_now(
        self,
        level: str,
        category: str,
        message: str,
        meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deliver one alert on the calling thread and say whether it arrived.

        `enqueue` is right for the engine (never block a tick). A test button is
        the opposite case: the operator is waiting for an answer, so the answer
        must be «entregada» or the reason it was not. `min_level` does not filter
        an explicit test.
        """
        if not self.enabled:
            return {"sent": False, "reason": "alertas desactivadas", "stats": self.snapshot()}
        delivered = self._deliver(Alert(level, category, message, dict(meta or {})))
        return {
            "sent": delivered,
            "reason": None if delivered else "el webhook no respondió correctamente",
            "stats": self.snapshot(),
        }

    def close(self, timeout_s: float = 2.0) -> None:
        """Stop the worker. Pending alerts are dropped, and the count says so."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None
        self.stats["dropped"] += self._queue.qsize()

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "min_level": self.min_level,
            "url_configured": bool(self.url),
            "dedupe_window_s": self.dedupe_window_s,
            **self.stats,
        }

    # --- internals --------------------------------------------------------
    def _is_duplicate(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            last = self._seen.get(key)
            if last is not None and now - last < self.dedupe_window_s:
                return True
            self._seen[key] = now
            if len(self._seen) > 512:
                horizon = now - self.dedupe_window_s
                self._seen = {k: v for k, v in self._seen.items() if v >= horizon}
            return False

    def _fail(self, reason: str) -> None:
        if self._on_failure is not None:
            try:
                self._on_failure(reason)
            except Exception:  # noqa: BLE001 - a broken callback must not kill the worker
                pass

    def _start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._worker, name="alerts", daemon=True
            )
            self._thread.start()

    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                alert = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            self._deliver(alert)

    def _deliver(self, alert: Alert) -> bool:
        for attempt in range(1, self.max_retries + 1):
            try:
                self._transport(alert.payload())
            except Exception:  # noqa: BLE001 - any transport error means "not delivered"
                if attempt < self.max_retries:
                    time.sleep(self.retry_backoff_s * attempt)
                    continue
                self.stats["failed"] += 1
                self._fail(f"alerta no entregada tras {attempt} intentos")
                return False
            self.stats["sent"] += 1
            return True
        return False

    def _post(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.url or "",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": SOURCE},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise urllib.error.HTTPError(
                    self.url or "", status, "webhook rechazó la alerta", None, None
                )


def build_notifier(
    config: Any,
    *,
    url_override: str | None = None,
    on_failure: Callable[[str], None] | None = None,
) -> WebhookNotifier | None:
    """Return a started notifier, or ``None`` when alerts are off.

    ``None`` is the honest answer for "disabled": the engine then does not even
    pay the cost of a dictionary lookup per event.
    """
    url = url_override or getattr(config, "webhook_url", None)
    # An explicit URL in the environment is an operator decision: it enables
    # alerts even when the file says otherwise, so a secret never needs to be
    # written into config.json just to turn the feature on.
    if not (getattr(config, "enabled", False) or url_override):
        return None
    if not url:
        return None
    return WebhookNotifier(
        url,
        min_level=getattr(config, "min_level", "warn"),
        timeout_s=getattr(config, "timeout_s", 5.0),
        max_retries=getattr(config, "max_retries", 3),
        dedupe_window_s=getattr(config, "dedupe_window_s", 60.0),
        on_failure=on_failure,
    )
