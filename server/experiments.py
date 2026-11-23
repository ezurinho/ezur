"""Experiment ledger.

Every backtest or simulation that claims a result gets a line here: identity,
hashes, configuration and verdict. Append-only JSONL, so the file is diffable,
greppable and cheap to keep in version control.

Each entry also carries ``prev_hash`` and ``chain_hash``: a SHA-256 chain over
the previous entry and this one's canonical payload. Append-only is a promise;
the chain turns it into something a reader can check. Editing a line in the
middle, inserting one, or deleting one breaks ``verify_chain`` and says exactly
where.
"""

from __future__ import annotations

import argparse
import hashlib
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


def _chain_hash(prev_hash: str, entry: dict[str, Any]) -> str:
    body = {key: value for key, value in entry.items() if key != "chain_hash"}
    return hashlib.sha256(
        (prev_hash + json.dumps(body, sort_keys=True, default=str)).encode("utf-8")
    ).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists():
        return ""
    for line in reversed(path.read_text(encoding="utf-8").splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return str(json.loads(line).get("chain_hash", ""))
        except json.JSONDecodeError:
            continue
    return ""


def record(path: str | Path = DEFAULT_LEDGER, **kwargs: Any) -> dict[str, Any]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    entry = build_record(**kwargs)
    entry["prev_hash"] = _last_hash(target)
    entry["chain_hash"] = _chain_hash(entry["prev_hash"], entry)
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


def verify_chain(path: str | Path = DEFAULT_LEDGER) -> dict[str, Any]:
    """Walk the ledger and prove (or disprove) that nobody edited the middle.

    Returns the first broken position instead of a boolean: a ledger that says
    "broken" without saying where is not useful for forensics.
    """
    target = Path(path)
    entries = load(target)
    previous = ""
    for index, entry in enumerate(entries):
        expected_prev = entry.get("prev_hash", "")
        if expected_prev != previous:
            return {
                "ok": False,
                "entries": len(entries),
                "broken_at": index,
                "reason": "prev_hash no coincide con la entrada anterior",
            }
        stored = entry.get("chain_hash")
        if stored is None:
            # Ledgers written before the chain existed are honest about it.
            previous = ""
            continue
        if _chain_hash(previous, entry) != stored:
            return {
                "ok": False,
                "entries": len(entries),
                "broken_at": index,
                "reason": "chain_hash no corresponde al contenido",
            }
        previous = stored
    return {"ok": True, "entries": len(entries), "broken_at": None, "reason": ""}


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
        "chain": verify_chain(path),
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
    parser.add_argument(
        "--verify", action="store_true", help="verificar la cadena de hashes"
    )
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

    if args.verify:
        result = verify_chain(args.ledger)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result["ok"] else 1

    entries = load(args.ledger)
    if args.json:
        print(json.dumps(summary(args.ledger), indent=2, ensure_ascii=False))
        return 0
    print(format_table(list(reversed(entries))[: args.limit]))
    report = summary(args.ledger)
    print()
    chain = report["chain"]
    print(f"{report['experiments']} experimento(s), veredictos: {report['verdicts']}")
    print(
        "cadena: íntegra"
        if chain["ok"]
        else f"cadena: ROTA en la entrada {chain['broken_at']} ({chain['reason']})"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
