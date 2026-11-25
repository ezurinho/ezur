"""Bloqueo de instancia única por cuenta.

El bloqueo lo sostiene el sistema operativo, no un fichero con un PID: si el
proceso muere, el watchdog lo mata o la máquina se reinicia, el lock se libera
solo. Un PID escrito en disco se quedaría pegado tras una caída y el watchdog
no podría recuperar el motor. El `.owner` es solo para poder decir quién lo
tenía, nunca para decidir si está libre.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path


class InstanceAlreadyRunning(RuntimeError):
    """Otra instancia tiene el lock de esta cuenta."""

    def __init__(self, path: Path, pid: int | None, since: str | None) -> None:
        self.path = path
        self.pid = pid
        self.since = since
        holder = f"pid {pid}" if pid else "proceso desconocido"
        if since:
            holder += f" desde {since}"
        super().__init__(
            f"otra instancia ya usa esta cuenta ({holder}): {path}. "
            "Detenla antes de arrancar otra."
        )


class InstanceLock:
    """Lock exclusivo y no bloqueante sobre un fichero, por cuenta."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.owner_path = self.path.with_name(self.path.name + ".owner")
        self._fd: int | None = None

    @property
    def held(self) -> bool:
        return self._fd is not None

    def _holder(self) -> tuple[int | None, str | None]:
        try:
            lines = self.owner_path.read_text(encoding="utf-8").splitlines()
            pid = int(lines[0])
            since = lines[1] if len(lines) > 1 else None
        except (OSError, ValueError, IndexError):
            return None, None
        return pid, since

    def acquire(self) -> InstanceLock:
        if self._fd is not None:
            return self
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            pid, since = self._holder()
            raise InstanceAlreadyRunning(self.path, pid, since) from None
        self._fd = fd
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        try:
            self.owner_path.write_text(f"{os.getpid()}\n{stamp}\n", encoding="utf-8")
        except OSError:
            pass
        return self

    def release(self) -> None:
        if self._fd is None:
            return
        fd, self._fd = self._fd, None
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        finally:
            os.close(fd)
            try:
                self.owner_path.unlink()
            except OSError:
                pass

    def __enter__(self) -> InstanceLock:
        return self.acquire()

    def __exit__(self, *exc_info: object) -> bool:
        self.release()
        return False
