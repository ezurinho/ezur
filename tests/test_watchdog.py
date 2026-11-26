"""El watchdog no puede correr dos veces sobre el mismo perfil."""

import importlib.util
from pathlib import Path

import pytest

from server.instance_lock import InstanceAlreadyRunning

ROOT = Path(__file__).resolve().parents[1]


def _watchdog():
    spec = importlib.util.spec_from_file_location(
        "ezur_watchdog", ROOT / "scripts" / "watchdog.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_el_lock_del_watchdog_rechaza_una_segunda_instancia(tmp_path):
    watchdog = _watchdog()
    path = tmp_path / "watchdog.lock"

    first = watchdog.instance_lock(path)
    try:
        with pytest.raises(InstanceAlreadyRunning):
            watchdog.instance_lock(path)
    finally:
        first.release()
