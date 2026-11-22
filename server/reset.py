"""Operational reset: archive the local state, then start clean.

Two steps always: move the database and configuration into a timestamped backup
directory, then leave the paths absent so the next start rebuilds them from
defaults. ``--dry-run`` prints the plan and touches nothing.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_DB = Path("data/terminal.db")
DEFAULT_CONFIG = Path("data/config.json")
DEFAULT_BACKUP_ROOT = Path("backups")

SUFFIXES = ("", "-wal", "-shm")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def plan_reset(
    db_path: str | Path = DEFAULT_DB,
    config_path: str | Path = DEFAULT_CONFIG,
    backup_root: str | Path = DEFAULT_BACKUP_ROOT,
) -> dict[str, Any]:
    database = Path(db_path)
    config = Path(config_path)
    targets: list[Path] = []
    for suffix in SUFFIXES:
        candidate = Path(str(database) + suffix)
        if candidate.exists():
            targets.append(candidate)
    if config.exists():
        targets.append(config)
    destination = Path(backup_root) / f"reset-{_timestamp()}"
    return {
        "files": [str(path) for path in targets],
        "destination": str(destination),
        "empty": not targets,
    }


def run_reset(
    db_path: str | Path = DEFAULT_DB,
    config_path: str | Path = DEFAULT_CONFIG,
    backup_root: str | Path = DEFAULT_BACKUP_ROOT,
    *,
    confirm: bool = False,
) -> dict[str, Any]:
    plan = plan_reset(db_path, config_path, backup_root)
    if plan["empty"] or not confirm:
        return {**plan, "executed": False}

    destination = Path(plan["destination"])
    destination.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for source in plan["files"]:
        origin = Path(source)
        shutil.move(str(origin), str(destination / origin.name))
        moved.append(str(destination / origin.name))
    return {**plan, "executed": True, "moved": moved}


def main() -> None:
    parser = argparse.ArgumentParser(description="Reinicio operativo con backup previo")
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--backups", default=str(DEFAULT_BACKUP_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if args.dry_run or not args.yes:
        plan = plan_reset(args.db, args.config, args.backups)
        print("Plan (nada modificado):")
        for item in plan["files"] or ["(sin archivos que archivar)"]:
            print(f"  - {item}")
        print(f"  destino: {plan['destination']}")
        if not args.dry_run:
            print("Ejecuta con --yes para aplicar.")
        return

    result = run_reset(args.db, args.config, args.backups, confirm=True)
    print(f"Archivado en {result['destination']}: {len(result.get('moved', []))} archivos")


if __name__ == "__main__":
    main()
