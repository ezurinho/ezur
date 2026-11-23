"""Environment lookups for ezur.

The product was renamed from a generic "terminal", so both prefixes are read:
``EZUR_*`` wins, ``TERMINAL_*`` still works. Dropping the old names immediately
would break every script and service file written before the rename, and a
broken start-up because of a name change is a worse bug than a long variable.
"""

from __future__ import annotations

import os

PREFIX = "EZUR"
LEGACY_PREFIX = "TERMINAL"


def env(name: str, default: str | None = None) -> str | None:
    """Read ``EZUR_<name>``, then ``TERMINAL_<name>``, then ``default``."""
    for prefix in (PREFIX, LEGACY_PREFIX):
        value = os.getenv(f"{prefix}_{name}")
        if value:
            return value
    return default


def env_flag(name: str, default: bool = False) -> bool:
    value = env(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}
