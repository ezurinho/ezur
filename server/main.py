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
from .api import EventHub, router
from .config import load_settings
from .db import Store
from .engine import TradingEngine
from .market.feed import CSVFeed, LiveFeed, MarketFeed, SimulatedFeed
from .strategy.registry import resolve_strategy
from .timeutil import session_open_utc

DEFAULT_CONFIG = Path("data/config.json")
DEFAULT_DB = Path("data/terminal.db")


def resolve_paths() -> tuple[Path, Path]:
    profile = os.getenv("TERMINAL_PROFILE_DIR")
    if profile:
        base = Path(profile)
        return base / "config.json", base / "terminal.db"
    config = os.getenv("TERMINAL_CONFIG_PATH")
    database = os.getenv("TERMINAL_DB_PATH")
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
        experiment_ledger or os.getenv("TERMINAL_EXPERIMENT_LEDGER", "reports/experiments.jsonl")
    )
    hub = EventHub()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings = load_settings(config_path)
        store = Store(db_path)
        engine = TradingEngine(
            settings,
            store,
            feed=build_feed(settings),
            strategy=resolve_strategy(settings.strategy.id, settings.strategy.params),
            feed_factory=build_feed,
        )
        engine.subscribe(hub.broadcast)
        app.state.settings = settings
        app.state.store = store
        app.state.engine = engine
        app.state.hub = hub
        app.state.config_path = config_path
        app.state.experiment_ledger = ledger_path
        try:
            yield
        finally:
            await engine.stop_task()
            store.close()

    app = FastAPI(title="Trading Terminal", version=__version__, lifespan=lifespan)
    app.include_router(router)

    dist = Path("frontend/dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    return app


app = create_app()
