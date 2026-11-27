"""Strategy registry — plugins + spec-driven strategies.

Adding a strategy is one entry here (plugin) OR a JSON spec file (spec-driven).
The rest of the application resolves strategies by id and never imports them directly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .base import BaseStrategy
from .donchian import DonchianStrategy
from .fade import FadeStrategy
from .null_strategy import NullStrategy
from .reference import ReferenceStrategy
from .trend import TrendStrategy
from .spec_schema import StrategySpec, load_spec, validate_spec

# --------------------------------------------------------------------------- #
# Plugin strategies (existing)
# --------------------------------------------------------------------------- #

_PLUGIN_BUILDERS: dict[str, Callable[[dict[str, Any]], BaseStrategy]] = {
    "null": lambda params: NullStrategy(),
    "reference": lambda params: ReferenceStrategy(params),
    "donchian": lambda params: DonchianStrategy(params),
    "fade": lambda params: FadeStrategy(params),
    "trend": lambda params: TrendStrategy(params),
}

# --------------------------------------------------------------------------- #
# Spec-driven strategies (new)
# --------------------------------------------------------------------------- #

_SPEC_BUILDERS: dict[str, Callable[[dict[str, Any]], BaseStrategy]] = {}
_SPEC_CACHE: dict[str, StrategySpec] = {}
_SPECS_LOADED = False


def _ensure_specs_loaded() -> None:
    """Auto-load all spec files from the spec directory on first use."""
    global _SPECS_LOADED
    if _SPECS_LOADED:
        return
    _SPECS_LOADED = True

    from ..env import env
    spec_dir = Path(env("SPEC_DIR", "data/specs"))

    if not spec_dir.exists():
        return

    for spec_path in spec_dir.glob("*.json"):
        try:
            spec = load_spec(spec_path)
            _SPEC_CACHE[spec.id] = spec
            # Create a builder that closes over the spec_id
            _SPEC_BUILDERS[spec.id] = lambda p, sid=spec.id: _load_spec_strategy(sid, p)
        except Exception as e:
            # Log but don't crash — invalid specs shouldn't break the registry
            import logging
            logging.getLogger(__name__).warning("failed to load spec %s: %s", spec_path, e)


def _load_spec_strategy(spec_id: str, params: dict[str, Any] | None = None) -> BaseStrategy:
    """Load a spec-driven strategy from the registry's spec directory."""
    # The spec directory is configurable via env or defaults to data/specs/
    from ..env import env
    spec_dir = Path(env("SPEC_DIR", "data/specs"))
    spec_path = spec_dir / f"{spec_id}.json"

    if not spec_path.exists():
        raise KeyError(f"spec {spec_id!r} not found in {spec_dir}")

    spec = load_spec(spec_path)
    _SPEC_CACHE[spec_id] = spec

    # Build the actual strategy from the spec
    return _build_strategy_from_spec(spec, params)


def _build_strategy_from_spec(spec: StrategySpec, params: dict[str, Any] | None = None) -> BaseStrategy:
    """Create a strategy instance from a validated spec.

    This maps the spec's entry.rule to the corresponding runner implementation.
    """
    from . import spec_driven

    rule = spec.entry.rule
    merged_params = {**spec.params.model_dump(exclude_none=True), **(params or {})}

    if rule == "donchian_breakout":
        return spec_driven.DonchianBreakoutStrategy(merged_params)
    if rule == "donchian_trend":
        return spec_driven.DonchianTrendStrategy(merged_params)
    if rule == "ema_state":
        return spec_driven.EMAStateStrategy(merged_params)
    if rule == "sma_state":
        return spec_driven.SMAStateStrategy(merged_params)
    if rule == "orb_session":
        return spec_driven.ORBSessionStrategy(merged_params)
    if rule == "zscore_fade":
        return spec_driven.ZScoreFadeStrategy(merged_params)

    raise KeyError(f"spec-driven rule {rule!r} not implemented")


def register_spec(spec_id: str, spec_path: Path) -> None:
    """Register a spec file at runtime (for dynamic loading).

    El constructor se queda con la ruta: dar por hecho que el fichero se llama
    como el id obligaba a renombrar specs que ya estaban validadas.
    """
    spec = load_spec(spec_path)
    path = Path(spec_path)
    _SPEC_CACHE[spec_id] = spec
    _SPEC_BUILDERS[spec_id] = lambda p, file=path: _build_strategy_from_spec(
        load_spec(file), p
    )


def available() -> list[str]:
    _ensure_specs_loaded()
    return sorted(set(_PLUGIN_BUILDERS) | set(_SPEC_BUILDERS) | set(_SPEC_CACHE))


def resolve_strategy(strategy_id: str, params: dict[str, Any] | None = None) -> BaseStrategy:
    _ensure_specs_loaded()
    # 1. Check spec-driven builders (dynamic specs)
    if strategy_id in _SPEC_BUILDERS:
        return _SPEC_BUILDERS[strategy_id](params or {})

    # 2. Check cached specs (loaded via register_spec)
    if strategy_id in _SPEC_CACHE:
        return _build_strategy_from_spec(_SPEC_CACHE[strategy_id], params)

    # 3. Check plugin builders
    try:
        builder = _PLUGIN_BUILDERS[strategy_id]
    except KeyError:
        raise KeyError(f"unknown strategy {strategy_id!r}") from None

    strategy = builder(params or {})
    # Validate declared params against the plugin's own schema.
    strategy.params_model.model_validate(params or {})
    return strategy


def strategy_schema(strategy_id: str) -> dict[str, Any]:
    """Return the params schema for a strategy (plugin or spec)."""
    _ensure_specs_loaded()

    # Spec-driven
    if strategy_id in _SPEC_CACHE:
        spec = _SPEC_CACHE[strategy_id]
        return {
            "id": strategy_id,
            "type": "spec",
            "rule": spec.entry.rule,
            "params_schema": spec.params.model_json_schema(),
            "full_spec": spec.model_dump(mode="json"),
        }

    # Plugin
    try:
        builder = _PLUGIN_BUILDERS[strategy_id]
    except KeyError:
        raise KeyError(f"unknown strategy {strategy_id!r}") from None

    model = builder({}).params_model
    return {
        "id": strategy_id,
        "type": "plugin",
        "params_schema": model.model_json_schema(),
    }


def load_spec_file(path: str | Path) -> StrategySpec:
    """Load and validate a spec file — re-export for convenience."""
    return load_spec(path)


def validate_spec_file(path: str | Path) -> list[str]:
    """Validate a spec file without constructing the Pydantic model."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return validate_spec(data)
