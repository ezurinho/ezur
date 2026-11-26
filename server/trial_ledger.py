"""Trial ledger for a selection cycle, with an exact PBO/DSR reconstruction.

The selection artifact stores one summary row per surviving configuration.
That is enough to report PF, but not enough to audit the selection: PBO and
DSR are properties of the whole search space, and discarded specs are part of
that space. This module writes an append-only JSONL ledger with one line per
spec (the executed document, dataset hash and window, seed, status, metrics
and daily R series), plus one final decision line.

The chain hash makes edits in the middle detectable. ``reconstruct_ledger``
rebuilds the daily matrix from the recorded series and applies the same
``cscv_pbo`` and ``deflated_sharpe`` functions used by the selection. It never
reads or writes gates: a reconstructed number is evidence, not a new threshold.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .selection import cscv_pbo, deflated_sharpe, sharpe_daily


class TrialLedgerError(RuntimeError):
    """The ledger is missing, incomplete or its chain does not verify."""


def _chain_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    body = {key: value for key, value in entry.items() if key != "chain_hash"}
    return hashlib.sha256(
        (prev_hash + json.dumps(body, sort_keys=True, default=str)).encode("utf-8")
    ).hexdigest()


class TrialLedger:
    """Append-only, hash-chained JSONL writer.

    The file is created exclusively: reusing a cycle id would mix two searches
    under one name and make the reconstruction ambiguous. Use a new cycle id
    for a new run.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        cycle_id: str,
        blocks: int,
        dataset: dict[str, Any],
        specs_hash: str | None = None,
    ) -> None:
        self.path = Path(path)
        self.cycle_id = cycle_id
        self._prev = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise TrialLedgerError(
                f"el ledger {self.path} ya existe; usa otro cycle_id o bórralo "
                "conscientemente antes de repetir la búsqueda"
            )
        # Se crea en modo exclusivo y se cierra: cada línea se añade después
        # con un append atómico, sin dejar un descriptor abierto durante los
        # backtests. Así una excepción no deja el fichero bloqueado en Windows.
        with self.path.open("x", encoding="utf-8"):
            pass
        self._write(
            {
                "kind": "ledger",
                "version": 1,
                "cycle_id": cycle_id,
                "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
                "blocks": int(blocks),
                "dataset": dataset,
                "specs_hash": specs_hash,
                "method": (
                    "un trial por spec; serie diaria de R para reconstruir "
                    "CSCV PBO y DSR con las mismas funciones del ciclo"
                ),
            }
        )

    def _write(self, entry: dict[str, Any]) -> dict[str, Any]:
        entry["prev_hash"] = self._prev
        entry["chain_hash"] = _chain_hash(self._prev, entry)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(entry, sort_keys=True, ensure_ascii=False, default=str)
                + "\n"
            )
        self._prev = str(entry["chain_hash"])
        return entry

    def record_trial(
        self,
        *,
        spec: dict[str, Any],
        dataset: dict[str, Any],
        status: str,
        seed: int | None,
        daily_returns: list[dict[str, Any]],
        metrics: dict[str, Any] | None,
        discard_reason: str | None = None,
        error: str | None = None,
        stress: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if status not in {"evaluated", "discarded"}:
            raise ValueError(f"estado de trial inválido: {status}")
        return self._write(
            {
                "kind": "trial",
                "cycle_id": self.cycle_id,
                "spec": spec,
                "dataset": dataset,
                "seed": seed,
                "status": status,
                "discard_reason": discard_reason,
                "error": error,
                "daily_returns": daily_returns,
                "metrics": metrics,
                "stress": stress,
            }
        )

    def record_selection(
        self,
        *,
        selected: str | None,
        not_selected: Iterable[str],
        discarded: Iterable[dict[str, Any]],
        pbo: dict[str, Any],
        dsr: dict[str, Any],
        dsr_config: str | None,
    ) -> dict[str, Any]:
        return self._write(
            {
                "kind": "selection",
                "cycle_id": self.cycle_id,
                "selected": selected,
                "not_selected": list(not_selected),
                "discarded": list(discarded),
                "pbo": pbo,
                "dsr": dsr,
                "dsr_config": dsr_config,
            }
        )

    def close(self) -> None:
        """Compatibilidad: cada escritura abre y cierra su propio fichero."""

    def __enter__(self) -> "TrialLedger":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def _read_entries(path: str | Path, *, verify: bool = True) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        raise TrialLedgerError(f"no existe el ledger {target}")
    entries: list[dict[str, Any]] = []
    for index, raw in enumerate(target.read_text(encoding="utf-8").splitlines()):
        line = raw.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as error:
            raise TrialLedgerError(f"línea {index + 1} no es JSON válido: {error}") from error
        if not isinstance(entry, dict):
            raise TrialLedgerError(f"línea {index + 1} no contiene un objeto JSON")
        entries.append(entry)
    if not entries:
        raise TrialLedgerError(f"el ledger {target} está vacío")
    if entries[0].get("kind") != "ledger":
        raise TrialLedgerError("el ledger no empieza por la cabecera")
    if verify:
        result = verify_chain(entries)
        if not result["ok"]:
            raise TrialLedgerError(
                f"cadena rota en la entrada {result['broken_at']}: {result['reason']}"
            )
    return entries


def verify_chain(entries: list[dict[str, Any]]) -> dict[str, Any]:
    previous = ""
    for index, entry in enumerate(entries):
        if entry.get("prev_hash", "") != previous:
            return {
                "ok": False,
                "entries": len(entries),
                "broken_at": index,
                "reason": "prev_hash no coincide con la entrada anterior",
            }
        stored = entry.get("chain_hash")
        if not isinstance(stored, str) or _chain_hash(previous, entry) != stored:
            return {
                "ok": False,
                "entries": len(entries),
                "broken_at": index,
                "reason": "chain_hash no corresponde al contenido",
            }
        previous = stored
    return {"ok": True, "entries": len(entries), "broken_at": None, "reason": ""}


def _trial_label(trial: dict[str, Any]) -> str:
    spec = trial.get("spec")
    label = spec.get("label") if isinstance(spec, dict) else None
    if not isinstance(label, str) or not label:
        raise TrialLedgerError("un trial no declara spec.label")
    return label


def _trial_group(trial: dict[str, Any]) -> str:
    spec = trial.get("spec")
    if not isinstance(spec, dict):
        raise TrialLedgerError("un trial no declara spec")
    group = spec.get("group") or spec.get("id") or spec.get("label")
    if not isinstance(group, str) or not group:
        raise TrialLedgerError("un trial no declara grupo")
    return group


def _matrix_from_trials(
    trials: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[str]]:
    labels: list[str] = []
    points: dict[str, dict[date, float]] = {}
    for trial in trials:
        label = _trial_label(trial)
        status = trial.get("status")
        daily = trial.get("daily_returns")
        if status == "discarded":
            if daily:
                raise TrialLedgerError(
                    f"{label}: un trial descartado no puede tener serie diaria"
                )
            continue
        if status != "evaluated":
            raise TrialLedgerError(f"{label}: estado de trial desconocido {status!r}")
        if not isinstance(daily, list) or not daily:
            raise TrialLedgerError(f"{label}: trial evaluado sin serie diaria")
        if label in points:
            raise TrialLedgerError(f"label duplicado en el ledger: {label}")
        labels.append(label)
        series: dict[date, float] = {}
        for point in daily:
            if not isinstance(point, dict):
                raise TrialLedgerError(f"{label}: punto diario inválido")
            try:
                day = date.fromisoformat(str(point["date"]))
                value = float(point["r_net"])
            except (KeyError, TypeError, ValueError) as error:
                raise TrialLedgerError(f"{label}: punto diario inválido: {error}") from error
            if day in series:
                raise TrialLedgerError(f"{label}: fecha diaria duplicada {day}")
            series[day] = value
        points[label] = series

    if not labels:
        raise TrialLedgerError("no hay trials evaluados para reconstruir PBO/DSR")
    days = sorted({day for series in points.values() for day in series})
    matrix = pd.DataFrame(
        {
            label: [points[label].get(day, 0.0) for day in days]
            for label in labels
        },
        index=pd.Index(days),
    )
    return matrix, labels


def reconstruct_ledger(
    path: str | Path,
    *,
    verify: bool = True,
) -> dict[str, Any]:
    """Rebuild the daily matrix and rerun the selection's PBO/DSR functions."""
    entries = _read_entries(path, verify=verify)
    manifest = entries[0]
    trials = [entry for entry in entries if entry.get("kind") == "trial"]
    selection = next(
        (entry for entry in entries if entry.get("kind") == "selection"), None
    )
    if not trials:
        raise TrialLedgerError("el ledger no tiene trials")

    matrix, labels = _matrix_from_trials(trials)
    blocks = int(manifest.get("blocks") or 10)
    if blocks < 2:
        raise TrialLedgerError(f"bloques inválidos en la cabecera: {blocks}")

    pbo = cscv_pbo(matrix, blocks=blocks)
    sr_daily = {column: sharpe_daily(matrix[column].to_numpy()) for column in matrix.columns}
    best = max(sr_daily, key=sr_daily.get)
    groups: dict[str, list[str]] = {}
    for trial in trials:
        groups.setdefault(_trial_group(trial), []).append(_trial_label(trial))

    dsr_by_group: dict[str, Any] = {}
    for group, names in groups.items():
        present = [name for name in names if name in matrix.columns]
        if len(present) < 2:
            continue
        sharpes = np.array([sr_daily[name] for name in present])
        top = present[int(np.argmax(sharpes))]
        value = deflated_sharpe(matrix[top].to_numpy(), sharpes)
        value["config"] = top
        value["trials"] = len(present)
        dsr_by_group[group] = value

    dsr_pooled = deflated_sharpe(
        matrix[best].to_numpy(), np.array(list(sr_daily.values()))
    )
    dsr = dict(dsr_pooled)
    best_group = next(
        (_trial_group(trial) for trial in trials if _trial_label(trial) == best), None
    )
    if best_group and best_group in dsr_by_group:
        dsr = dict(dsr_by_group[best_group])
        dsr["source"] = f"grupo {best_group}"
    else:
        dsr["source"] = "universo completo"

    discarded = [
        {
            "label": _trial_label(trial),
            "reason": trial.get("discard_reason"),
            "error": trial.get("error"),
        }
        for trial in trials
        if trial.get("status") == "discarded"
    ]
    return {
        "cycle_id": manifest.get("cycle_id"),
        "blocks": blocks,
        "dataset": manifest.get("dataset"),
        "trials": len(trials),
        "evaluated": len(labels),
        "discarded": discarded,
        "matrix": {"days": int(matrix.shape[0]), "columns": int(matrix.shape[1])},
        "pbo": pbo,
        "dsr": dsr,
        "dsr_pooled": dsr_pooled,
        "dsr_by_group": dsr_by_group,
        "dsr_config": best,
        "selected": best,
        "not_selected": [label for label in labels if label != best],
        "selection": selection,
    }


def _compare_artifact(report: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    pbo = (artifact.get("pbo") or {}).get("pbo")
    dsr = (artifact.get("dsr") or {}).get("dsr")
    config = artifact.get("dsr_config")
    return {
        "pbo": pbo,
        "dsr": dsr,
        "dsr_config": config,
        "matches": (
            pbo == report["pbo"].get("pbo")
            and dsr == report["dsr"].get("dsr")
            and config == report["dsr_config"]
        ),
    }


def format_report(report: dict[str, Any]) -> str:
    dataset = report.get("dataset") or {}
    pbo = report.get("pbo") or {}
    dsr = report.get("dsr") or {}
    lines = [
        f"Ciclo {report.get('cycle_id')}",
        f"Dataset {dataset.get('path')} · {dataset.get('rows')} velas · "
        f"{dataset.get('sha256')}",
        f"Trials {report['trials']} · evaluados {report['evaluated']} · "
        f"descartados {len(report['discarded'])}",
        f"PBO {pbo.get('pbo')} · {pbo.get('n_splits')} particiones",
        f"DSR {dsr.get('dsr')} · config {report['dsr_config']} · {dsr.get('source')}",
        f"Seleccionado {report['selected']}",
    ]
    if report["discarded"]:
        lines.append(
            "Descartados: "
            + ", ".join(
                f"{item['label']} ({item['reason'] or 'sin motivo'})"
                for item in report["discarded"]
            )
        )
    if report["not_selected"]:
        lines.append("No seleccionados: " + ", ".join(report["not_selected"]))
    artifact = report.get("artifact")
    if artifact:
        lines.append(
            f"Contraste con artefacto: "
            f"{'coincide' if artifact['matches'] else 'NO coincide'} "
            f"(PBO {artifact['pbo']}, DSR {artifact['dsr']}, "
            f"config {artifact['dsr_config']})"
        )
    return "\n".join(lines)


def _force_utf8_stdout() -> None:
    stream = getattr(sys, "stdout", None)
    if stream is not None and hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Reconstruye PBO/DSR desde el trial ledger de una selección"
    )
    parser.add_argument("--ledger", required=True)
    parser.add_argument("--artifact", default=None, help="artefacto del ciclo para contrastar")
    parser.add_argument("--out", default=None, help="escribe el informe JSON en esta ruta")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    _force_utf8_stdout()
    report = reconstruct_ledger(args.ledger)
    if args.artifact:
        with Path(args.artifact).open(encoding="utf-8") as handle:
            report["artifact"] = _compare_artifact(report, json.load(handle))
    text = json.dumps(report, indent=2, ensure_ascii=False, default=str)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text + "\n", encoding="utf-8")
    print(text if args.json else format_report(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
