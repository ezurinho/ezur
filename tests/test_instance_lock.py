from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from server.instance_lock import InstanceAlreadyRunning, InstanceLock

ROOT = Path(__file__).resolve().parents[1]

HOLDER = """
import sys, time
from pathlib import Path
from server.instance_lock import InstanceLock

lock = InstanceLock(Path(sys.argv[1])).acquire()
Path(sys.argv[2]).write_text("listo", encoding="utf-8")
time.sleep(60)
"""


def test_el_mismo_fichero_no_se_puede_bloquear_dos_veces(tmp_path):
    path = tmp_path / "cuenta.lock"
    first = InstanceLock(path).acquire()
    try:
        with pytest.raises(InstanceAlreadyRunning) as error:
            InstanceLock(path).acquire()
        assert "otra instancia ya usa esta cuenta" in str(error.value)
        assert str(path) in str(error.value)
    finally:
        first.release()


def test_al_liberar_se_puede_volver_a_bloquear(tmp_path):
    path = tmp_path / "cuenta.lock"
    lock = InstanceLock(path)
    lock.acquire()
    lock.release()
    assert not lock.held
    again = InstanceLock(path).acquire()
    try:
        assert again.held
    finally:
        again.release()


def test_dos_cuentas_distintas_no_se_estorbran(tmp_path):
    one = InstanceLock(tmp_path / "a.lock").acquire()
    other = InstanceLock(tmp_path / "b.lock").acquire()
    try:
        assert one.held and other.held
    finally:
        one.release()
        other.release()


def test_el_dueno_queda_escrito_para_poder_decir_quien_lo_tiene(tmp_path):
    path = tmp_path / "cuenta.lock"
    lock = InstanceLock(path).acquire()
    try:
        owner = path.with_name(path.name + ".owner").read_text(encoding="utf-8")
        assert owner.splitlines()[0] == str(os.getpid())
    finally:
        lock.release()


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    """En Windows el python del venv puede ser un lanzador con un hijo real."""
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        process.terminate()
    process.wait(timeout=10)


def test_otro_proceso_del_sistema_no_puede_compartir_la_cuenta(tmp_path):
    path = tmp_path / "cuenta.lock"
    ready = tmp_path / "ready"
    holder = subprocess.Popen(
        [sys.executable, "-c", HOLDER, str(path), str(ready)],
        cwd=str(ROOT),
    )
    try:
        deadline = time.monotonic() + 15
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert ready.exists(), "el proceso que sostiene el lock no arranco"

        owner = path.with_name(path.name + ".owner")
        owner_pid = int(owner.read_text(encoding="utf-8").splitlines()[0])
        with pytest.raises(InstanceAlreadyRunning) as error:
            InstanceLock(path).acquire()
        assert error.value.pid == owner_pid
        assert error.value.pid != os.getpid()
    finally:
        _kill_tree(holder)

    # Al morir el dueño, el sistema libera el lock: el watchdog puede recuperar.
    lock = InstanceLock(path).acquire()
    lock.release()
