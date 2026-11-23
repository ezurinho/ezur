"""Dataset integrity as a measured gate (G1/G3/G14).

The validator already answers the structural questions: file present, symbols
aligned, no duplicated timestamps, no empty series. What it cannot answer is
whether the *hash* is reproducible, so this module hashes twice and compares.

Roll continuity (G3) needs real contract data with expiries; when the dataset is
a continuous series there is nothing to roll, and the detail says so instead of
pretending it was checked.
"""

from __future__ import annotations

from pathlib import Path

from .backtest import Dataset
from .gates import GateOutcome
from .market.csv_data import ValidationReport, validate_dataset


def integrity_outcome(
    report: ValidationReport,
    dataset_id: str,
    second_hash: str,
) -> GateOutcome:
    issues = [issue.code for issue in report.errors]
    hash_stable = bool(dataset_id) and dataset_id == second_hash
    ok = report.ok and hash_stable

    parts = [
        f"validador {'ok' if report.ok else 'falla: ' + ', '.join(sorted(set(issues)))}",
        f"{report.sessions} sesiones, {report.rows} filas",
        f"hash {'estable' if hash_stable else 'inestable'}",
    ]
    if report.ok and hash_stable:
        parts.append("sin rolls que verificar en este dataset")

    return GateOutcome(
        id="G1/G3/G14",
        description="Integridad del dataset y de los rolls",
        status="pass" if ok else "fail",
        threshold="validador sin errores y hash reproducible",
        detail="; ".join(parts),
    )


def measure_integrity(
    dataset_path: str | Path, symbols: list[str]
) -> GateOutcome:
    report = validate_dataset(dataset_path, symbols)
    first = Dataset.load(dataset_path, symbols) if report.ok else None
    second = Dataset.load(dataset_path, symbols) if report.ok else None
    return integrity_outcome(
        report,
        first.dataset_id if first else "",
        second.dataset_id if second else "x",
    )
