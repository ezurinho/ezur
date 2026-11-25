"""FastAPI application: API plus the compiled frontend, in one process."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path
from typing import AsyncIterator

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
    return SimulatedFeed(seed, symbols, start=start)


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
    hub = EventHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = Store(db_path)
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
        app.state.settings = settings
        app.state.store = store
        app.state.engine = engine
        app.state.hub = hub
        app.state.config_path = config_path
        app.state.experiment_ledger = ledger_path
        app.state.notifier = notifier
        promoted = True
        if settings.promotion.required:
            from .backtest import config_fingerprint
            from .promotion import evaluate_paths

            verdict = evaluate_paths(
                settings.promotion.evidence,
                settings.promotion.stress_evidence,
                settings.promotion.cycle,
                {"id": settings.strategy.id, "version": settings.strategy.version},
                config_fingerprint(settings),
            )
            promoted = bool(verdict["passed"])
            if not promoted:
                if settings.promotion.mode == "reduce":
                    before = settings.risk.risk_per_trade_pct
                    settings.risk.risk_per_trade_pct = round(
                        before * settings.promotion.size_factor, 4
                    )
                    store.insert_event(
                        "warn",
                        "promotion",
                        f"sin promoción: riesgo {before:.2f} % -> "
                        f"{settings.risk.risk_per_trade_pct:.2f} % ({verdict['reason']})",
                    )
                    promoted = True  # arranca, pero a menor tamaño
                else:
                    store.insert_event(
                        "warn",
                        "promotion",
                        f"auto_start bloqueado: {verdict['reason']}",
                    )
        if settings.auto_start and promoted and engine.state.status in {"idle", "stopped"}:
            try:
                engine.start()
                engine.start_task()
            except RuntimeError as error:  # a bad profile must not block the UI
                store.insert_event("warn", "engine", f"auto_start falló: {error}")
        try:
            yield
        finally:
            await engine.stop_task()
            if notifier is not None:
                notifier.close()
            store.close()

    app = FastAPI(title="ezur", version=__version__, lifespan=lifespan)
    app.include_router(router)

    dist = Path("frontend/dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    return app


app = create_app()
