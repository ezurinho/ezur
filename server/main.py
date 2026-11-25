"""FastAPI application: API plus the compiled frontend, in one process."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import __version__
from .alerts import build_notifier
from .api import EventHub, router
from .config import load_settings
from .db import Store
from .engine import TradingEngine
from .env import env
from .market.feed import CSVFeed, LiveFeed, MarketFeed, SimulatedFeed
from .market.okx import OKXFeed
from .strategy.registry import resolve_strategy
from .timeutil import session_open_utc

DEFAULT_CONFIG = Path("data/config.json")
DEFAULT_DB = Path("data/terminal.db")

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
logger = logging.getLogger(__name__)


class LocalOriginMiddleware:
    """Loopback no evita CSRF/CSWSH: una web puede llamar a localhost.

    Se acepta cualquier petición sin Origin (curl, health checks), pero una web
    solo puede hablar con el mismo Host que sirvió la aplicación. El Host
    `testserver` se admite únicamente desde el cliente sintético de TestClient.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope["headers"]}
        host = headers.get("host", "")
        hostname = urlsplit(f"//{host}").hostname
        client_host = (scope.get("client") or ("", 0))[0]
        host_allowed = hostname in LOCAL_HOSTS or (
            hostname == "testserver" and client_host == "testclient"
        )
        origin = headers.get("origin")
        fetch_site = headers.get("sec-fetch-site", "")
        allowed = host_allowed and fetch_site != "cross-site"
        if allowed and origin:
            parsed = urlsplit(origin)
            allowed = parsed.scheme in {"http", "https"} and parsed.netloc.lower() == host.lower()
        if allowed and scope["type"] == "http":
            try:
                allowed = int(headers.get("content-length") or 0) <= 1_048_576
            except ValueError:
                allowed = False
        if allowed:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008, "reason": "origin not allowed"})
        else:
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [(b"content-type", b"text/plain; charset=utf-8")],
                }
            )
            await send({"type": "http.response.body", "body": b"origin not allowed"})


def resolve_paths() -> tuple[Path, Path]:
    profile = env("PROFILE_DIR")
    if profile:
        base = Path(profile)
        return base / "config.json", base / "terminal.db"
    config = env("CONFIG_PATH")
    database = env("DB_PATH")
    return (
        Path(config) if config else DEFAULT_CONFIG,
        Path(database) if database else DEFAULT_DB,
    )


def default_session_date(settings) -> str:
    """Most recent trading day for the primary instrument's session template."""
    template = settings.instruments.template_for(settings.instruments.primary)
    day = date.today()
    for _ in range(10):
        if day.weekday() in template.weekdays:
            return day.isoformat()
        day -= timedelta(days=1)
    return date.today().isoformat()


def build_feed(settings) -> MarketFeed:
    symbols = settings.instruments.symbols
    provider = settings.feed.provider
    if provider == "csv":
        return CSVFeed(settings.feed.csv_path, symbols)
    if provider == "live":
        return LiveFeed()
    if provider == "okx":
        return OKXFeed(
            {
                item.symbol: item.venue_symbol or item.symbol
                for item in settings.instruments.enabled
            },
            bars=settings.feed.backfill_bars,
            poll_interval_s=settings.feed.poll_interval_s,
        )
    seed = settings.feed.start_date or default_session_date(settings)
    template = settings.instruments.template_for(settings.instruments.primary)
    start = session_open_utc(template, date.fromisoformat(seed))
    return SimulatedFeed(
        seed,
        symbols,
        start=start,
        tick_size=settings.instruments.by_symbol(settings.instruments.primary).tick_size,
        tick_sizes={item.symbol: item.tick_size for item in settings.instruments.items},
        reference_prices={
            item.symbol: item.reference_price
            for item in settings.instruments.items
            if item.reference_price is not None
        },
    )


def create_app(
    config_path: Path | str | None = None,
    db_path: Path | str | None = None,
    experiment_ledger: Path | str | None = None,
) -> FastAPI:
    default_config, default_db = resolve_paths()
    config_path = Path(config_path) if config_path else default_config
    db_path = Path(db_path) if db_path else default_db
    ledger_path = Path(
        experiment_ledger or env("EXPERIMENT_LEDGER", "reports/experiments.jsonl")
    )
    db_existed = db_path.exists() and db_path.stat().st_size > 0
    hub = EventHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(db_path)
        backup_dir = db_path.parent / "backups"

        def make_backup() -> Path:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            target = store.backup(backup_dir / f"terminal-{stamp}.db")
            if config_path.is_file():
                shutil.copy2(config_path, backup_dir / f"config-{stamp}.json")
            return target

        async def backup_loop() -> None:
            while True:
                await asyncio.sleep(86_400)
                try:
                    make_backup()
                except Exception:
                    logger.exception("no se pudo crear el respaldo programado")

        if db_existed:
            try:
                make_backup()
            except Exception:
                logger.exception("no se pudo crear el respaldo de arranque")
        backup_task = asyncio.create_task(backup_loop())
        config_failed = False

        def _config_error(message: str) -> None:
            nonlocal config_failed
            config_failed = True
            store.insert_event("error", "config", f"{message}; usando valores por defecto")

        settings = load_settings(config_path, on_error=_config_error)
        if config_failed:
            # Un perfil ilegible no puede acabar operando con los valores por
            # defecto sobre el libro vivo: se queda esperando a que lo arreglen.
            settings.auto_start = False
        # La reducción por promoción se aplica antes de construir el motor, a
        # una copia efectiva. La configuración guardada conserva el porcentaje
        # que eligió el operador; así un guardado posterior no lo reduce otra
        # vez y el RiskManager nace ya con el tamaño correcto.
        configured_settings = settings.model_copy(deep=True)
        from .promotion import effective_settings_and_verdict

        settings, promotion_verdict = effective_settings_and_verdict(configured_settings)
        notifier = build_notifier(
            settings.alerts,
            url_override=env("ALERT_WEBHOOK_URL"),
            on_failure=lambda reason: store.insert_event("warn", "alerts", reason),
        )
        engine = TradingEngine(
            settings,
            store,
            feed=build_feed(settings),
            strategy=resolve_strategy(settings.strategy.id, settings.strategy.params),
            feed_factory=build_feed,
            strategy_factory=lambda cfg: resolve_strategy(cfg.strategy.id, cfg.strategy.params),
            notifier=notifier,
        )
        engine.subscribe(hub.broadcast)
        if not engine.equity_audit["ok"]:
            # El motor también se niega a arrancar; dejar constancia aquí evita
            # que un auto_start silencioso oculte el motivo en el panel.
            store.insert_event(
                "error",
                "accounting",
                "arranque bloqueado: la equity no cuadra con el libro",
                {
                    "issues": engine.equity_audit["issues"],
                    "differences": engine.equity_audit["differences"],
                },
            )
            settings.auto_start = False
            configured_settings.auto_start = False
        app.state.settings = settings
        app.state.configured_settings = configured_settings
        app.state.promotion_verdict = promotion_verdict
        app.state.store = store
        app.state.engine = engine
        app.state.hub = hub
        app.state.config_path = config_path
        app.state.experiment_ledger = ledger_path
        app.state.notifier = notifier
        promoted = True
        if promotion_verdict is not None and not promotion_verdict["passed"]:
            if settings.promotion.mode == "reduce":
                before = configured_settings.risk.risk_per_trade_pct
                store.insert_event(
                    "warn",
                    "promotion",
                    f"sin promoción: riesgo {before:.2f} % -> "
                    f"{settings.risk.risk_per_trade_pct:.2f} % "
                    f"({promotion_verdict['reason']})",
                )
            else:
                store.insert_event(
                    "warn",
                    "promotion",
                    f"auto_start bloqueado: {promotion_verdict['reason']}",
                )
                promoted = False
        if settings.auto_start and promoted and engine.state.status in {"idle", "stopped"}:
            try:
                engine.start()
                await engine.start_task()
            except RuntimeError as error:  # a bad profile must not block the UI
                store.insert_event("warn", "engine", f"auto_start falló: {error}")
        try:
            yield
        finally:
            backup_task.cancel()
            try:
                await backup_task
            except asyncio.CancelledError:
                pass
            await engine.stop_task()
            if notifier is not None:
                notifier.close()
            store.close()

    app = FastAPI(title="ezur", version=__version__, lifespan=lifespan)
    app.state.backtest_lock = asyncio.Lock()
    app.add_middleware(LocalOriginMiddleware)
    app.include_router(router)

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        """Liveness del proceso: no depende del motor ni del paper."""
        return {"status": "ok", "service": "ezur"}

    dist = Path("frontend/dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    return app


app = create_app()
