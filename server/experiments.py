"""Experiment ledger.

Every backtest or simulation that claims a result gets a line here: identity,
hashes, configuration and verdict. Append-only JSONL, so the file is diffable,
greppable and cheap to keep in version control.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .confirmatory import canonical_hash

DEFAULT_LEDGER = Path("reports/experiments.jsonl")


def build_record(
    *,
    kind: str,
    strategy_id: str,
    strategy_version: str,
    dataset_id: str,
    config: dict[str, Any],
    metrics: dict[str, Any],
    verdict: str,
    notes: str = "",
) -> dict[str, Any]:
    payload = {
        "kind": kind,
        "strategy": {"id": strategy_id, "version": strategy_version},
        "dataset_id": dataset_id,
        "config_sha256": canonical_hash(config),
        "metrics_sha256": canonical_hash(metrics),
        "verdict": verdict,
        "notes": notes,
    }
    payload["experiment_id"] = canonical_hash(payload)[:16]
    payload["ts"] = datetime.now(timezone.utc).isoformat()
    return payload


def record(path: str | Path = DEFAULT_LEDGER, **kwargs: Any) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = build_record(**kwargs)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")
    return entry


def load(path: str | Path = DEFAULT_LEDGER) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def find(experiment_id: str, path: str | Path = DEFAULT_LEDGER) -> dict[str, Any] | None:
    for entry in load(path):
        if entry.get("experiment_id") == experiment_id:
            return entry
    return None


def summary(path: str | Path = DEFAULT_LEDGER) -> dict[str, Any]:
    entries = load(path)
    verdicts: dict[str, int] = {}
    for entry in entries:
        verdict = entry.get("verdict", "UNKNOWN")
        verdicts[verdict] = verdicts.get(verdict, 0) + 1
    return {
        "experiments": len(entries),
        "verdicts": verdicts,
        "latest": entries[-1] if entries else None,
        "unique_ids": len({entry.get("experiment_id") for entry in entries}),
    }
