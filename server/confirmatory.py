"""Holdout sealing.

A holdout is evidence only once. This module makes the second run impossible
without an explicit, recorded incident: sealing writes a lock file with the
dataset hash, configuration hash and timestamp, and refuses to overwrite it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HoldoutAlreadySealed(RuntimeError):
    """Raised when a holdout is opened twice."""


def canonical_hash(payload: Any) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def file_hash(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal_holdout(
    lock_path: str | Path,
    *,
    dataset_path: str | Path,
    config: dict[str, Any],
    strategy: dict[str, Any],
    protocol: str,
) -> dict[str, Any]:
    """Create the lock. Raises if it already exists."""
    target = Path(lock_path)
    if target.exists():
        raise HoldoutAlreadySealed(
            f"holdout already sealed at {target}; a new protocol is required"
        )
    payload = {
        "sealed_ts": datetime.now(timezone.utc).isoformat(),
        "protocol": protocol,
        "dataset_sha256": file_hash(dataset_path),
        "config_sha256": canonical_hash(config),
        "strategy_sha256": canonical_hash(strategy),
    }
    payload["seal_sha256"] = canonical_hash(payload)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return payload


def read_seal(lock_path: str | Path) -> dict[str, Any]:
    return json.loads(Path(lock_path).read_text(encoding="utf-8"))


def verify_seal(
    lock_path: str | Path,
    *,
    dataset_path: str | Path,
    config: dict[str, Any],
    strategy: dict[str, Any],
) -> dict[str, Any]:
    """Check that the inputs still match the sealed hashes."""
    seal = read_seal(lock_path)
    expected = {key: value for key, value in seal.items() if key != "seal_sha256"}
    if canonical_hash(expected) != seal.get("seal_sha256"):
        return {"ok": False, "reasons": ["seal hash mismatch: file was edited"]}

    reasons: list[str] = []
    if file_hash(dataset_path) != seal["dataset_sha256"]:
        reasons.append("dataset changed since sealing")
    if canonical_hash(config) != seal["config_sha256"]:
        reasons.append("configuration changed since sealing")
    if canonical_hash(strategy) != seal["strategy_sha256"]:
        reasons.append("strategy changed since sealing")
    return {"ok": not reasons, "reasons": reasons, "sealed_ts": seal["sealed_ts"]}
