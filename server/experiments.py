"""Experiment ledger.

Every backtest or simulation that claims a result gets a line here: identity,
hashes, configuration and verdict. Append-only JSONL, so the file is diffable,
greppable and cheap to keep in version control.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

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


def format_table(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "Sin experimentos registrados."
    lines = ["ID                ESTRATEGIA           VEREDICTO   DATASET     FECHA"]
    for entry in entries:
        strategy = entry.get("strategy") or {}
        lines.append(
            "  ".join(
                [
                    str(entry.get("experiment_id", "?"))[:16].ljust(16),
                    f"{strategy.get('id', '?')}@{strategy.get('version', '?')}"[:20].ljust(20),
                    str(entry.get("verdict", "?"))[:11].ljust(11),
                    str(entry.get("dataset_id", ""))[:10].ljust(10),
                    str(entry.get("ts", ""))[:19],
                ]
            )
        )
    return "\n".join(lines)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ledger de experimentos")
    parser.add_argument("--ledger", default=str(DEFAULT_LEDGER))
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument("--find", default=None, help="buscar por experiment_id")
    args = parser.parse_args(list(argv) if argv is not None else None)

    stream = getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

    if args.find:
        entry = find(args.find, args.ledger)
        if entry is None:
            print(f"No existe el experimento {args.find}")
            return 1
        print(json.dumps(entry, indent=2, sort_keys=True, ensure_ascii=False))
        return 0

    entries = load(args.ledger)
    if args.json:
        print(json.dumps(summary(args.ledger), indent=2, ensure_ascii=False))
        return 0
    print(format_table(list(reversed(entries))[: args.limit]))
    report = summary(args.ledger)
    print()
    print(f"{report['experiments']} experimento(s), veredictos: {report['verdicts']}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
