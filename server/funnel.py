"""Evaluation funnel: how many ideas entered the process and how many survived.

The funnel exists to make attrition visible. A ledger with 40 experiments and no
approval is not a failure of the process, it is the process working; a funnel
that only reports the winner is how research gets p-hacked.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Sequence

from server.experiments import load

STAGES: tuple[str, ...] = (
    "experiments",
    "strategies",
    "datasets",
    "rejected",
    "inconclusive",
    "approved",
)

PASSING_VERDICTS = {"APROBADA"}


def build_funnel(entries: Sequence[dict[str, Any]]) -> dict[str, Any]:
    verdicts = Counter(str(entry.get("verdict", "")) for entry in entries)
    strategies = {_strategy_key(entry) for entry in entries}
    datasets = {str(entry.get("dataset_id", "")) for entry in entries if entry.get("dataset_id")}
    by_strategy: dict[str, dict[str, Any]] = {}
    for entry in entries:
        key = _strategy_key(entry)
        node = by_strategy.setdefault(key, {"experiments": 0, "verdicts": Counter()})
        node["experiments"] += 1
        node["verdicts"][str(entry.get("verdict", ""))] += 1

    return {
        "stages": {
            "experiments": len(entries),
            "strategies": len(strategies),
            "datasets": len(datasets),
            "rejected": verdicts.get("RECHAZADA", 0),
            "inconclusive": verdicts.get("INCONCLUSO", 0),
            "approved": verdicts.get("APROBADA", 0),
        },
        "verdicts": dict(verdicts),
        "survival_rate": _ratio(verdicts.get("APROBADA", 0), len(entries)),
        "by_strategy": {
            key: {
                "experiments": node["experiments"],
                "verdicts": dict(node["verdicts"]),
            }
            for key, node in sorted(by_strategy.items())
        },
    }


def load_funnel(path: Path | str) -> dict[str, Any]:
    return build_funnel(load(path))


def format_funnel(report: dict[str, Any]) -> str:
    lines = ["Embudo de evaluación", ""]
    labels = {
        "experiments": "Experimentos registrados",
        "strategies": "Estrategias distintas",
        "datasets": "Datasets distintos",
        "rejected": "Rechazadas",
        "inconclusive": "Inconclusas",
        "approved": "Aprobadas",
    }
    for stage in STAGES:
        lines.append(f"  {labels[stage]:<26}{report['stages'][stage]:>5}")
    lines.append(f"  {'Tasa de supervivencia':<26}{report['survival_rate']:>5.1%}")
    for key, node in report["by_strategy"].items():
        lines.append(f"  - {key}: {node['experiments']} experimento(s) {node['verdicts']}")
    return "\n".join(lines)


def _strategy_key(entry: dict[str, Any]) -> str:
    strategy = entry.get("strategy") or {}
    if isinstance(strategy, dict):
        return f"{strategy.get('id', '?')}@{strategy.get('version', '?')}"
    return str(strategy)


def _ratio(part: int, total: int) -> float:
    return float(part) / float(total) if total else 0.0


def _force_utf8_stdout() -> None:
    """Windows consoles default to cp1252 and mangle the accents in the report."""
    stream = getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resumen del embudo de evaluación")
    parser.add_argument("--ledger", default="reports/experiments.jsonl")
    parser.add_argument("--json", action="store_true", help="salida JSON")
    args = parser.parse_args(list(argv) if argv is not None else None)

    _force_utf8_stdout()
    report = load_funnel(args.ledger)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(format_funnel(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
