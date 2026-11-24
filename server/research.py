"""El mando único del bot sobre el motor de estrategias.

El motor vive en su propio árbol porque necesita pandas y su propio récord: dos
dependencias que no deben entrar en el .exe. Lo que se une aquí es el mando —
un solo comando, un solo ledger, un solo contrato de umbrales:

    python -m server.research --once      # la siguiente especificación pendiente
    python -m server.research --loop      # sigue buscando mientras el bot corre
    python -m server.research --list      # qué hay y qué ya se midió

Cada corrida queda en `data/research/runs.jsonl` con la huella de la spec, así
que reiniciar el bucle no repite lo ya medido.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_HOME = (
    Path.home()
    / ".deepai-code"
    / "scratch"
    / "2026-11-22-motor-ia-para-estrategias-btc-a2100b36"
)
LEDGER = Path("data/research/runs.jsonl")
SPECS_DIR = Path("runner") / "specs"
RUNNER = Path("runner") / "run_strategy.py"


class ResearchUnavailable(RuntimeError):
    """El motor no está donde se esperaba, o le falta el intérprete."""


def research_home(explicit: str | Path | None = None) -> Path:
    candidates = [explicit, os.getenv("EZUR_RESEARCH_HOME"), DEFAULT_HOME]
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate).expanduser()
        if (path / RUNNER).is_file():
            return path
    raise ResearchUnavailable(
        "no encuentro runner/run_strategy.py; define EZUR_RESEARCH_HOME"
    )


def interpreter(home: Path) -> str:
    """El del venv del motor si existe: es el único con pandas."""
    override = os.getenv("EZUR_RESEARCH_PYTHON")
    if override:
        return override
    candidates = [
        home / ".venv" / "Scripts" / "python.exe",
        home / ".venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return sys.executable


def spec_paths(home: Path) -> list[Path]:
    directory = home / SPECS_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"), key=lambda path: path.stat().st_mtime)


def fingerprint(spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def load_ledger(path: Path | str = LEDGER) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def measured(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Huella → última corrida buena. Un fallo no marca la spec como medida."""
    done: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("verdict"):
            done[str(record.get("fingerprint"))] = record
    return done


def _append(record: dict[str, Any], path: Path | str = LEDGER) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def pending(home: Path, records: list[dict[str, Any]]) -> list[Path]:
    done = measured(records)
    queue = []
    for path in spec_paths(home):
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if fingerprint(spec) not in done:
            queue.append(path)
    return queue


def _parse_verdict(output: str) -> str | None:
    for line in reversed(output.splitlines()):
        line = line.strip()
        if line.startswith("VERDICT "):
            return line.split(" ", 1)[1].strip() or None
    return None


def run_spec(
    home: Path,
    python: str,
    spec: Path,
    *,
    out_dir: Path,
    timeout: float = 3600.0,
) -> dict[str, Any]:
    """Ejecuta una spec con el motor y devuelve el registro para el ledger."""
    started = time.time()
    spec_doc = json.loads(Path(spec).read_text(encoding="utf-8"))
    command = [
        python,
        str(RUNNER),
        "--spec",
        str(Path(spec)),
        "--out",
        str(out_dir),
    ]
    try:
        done = subprocess.run(
            command, cwd=home, capture_output=True, text=True, timeout=timeout
        )
        output, error, code = done.stdout, done.stderr, done.returncode
    except subprocess.TimeoutExpired as expired:
        output = (expired.stdout or "") if isinstance(expired.stdout, str) else ""
        error = f"timeout tras {timeout:.0f}s"
        code = -9

    verdict = _parse_verdict(output) if code == 0 else None
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "spec": str(Path(spec).relative_to(home)) if Path(spec).is_relative_to(home) else str(spec),
        "id": spec_doc.get("id"),
        "family": spec_doc.get("family"),
        "timeframe": spec_doc.get("timeframe_signal"),
        "fingerprint": fingerprint(spec_doc),
        "verdict": verdict,
        "returncode": code,
        "seconds": round(time.time() - started, 1),
        "error": (error or "").strip()[-800:] or None,
        "output": (output or "").strip()[-800:] or None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Puente único con el motor de estrategias"
    )
    parser.add_argument("--home", default=None, help="raíz del motor (o EZUR_RESEARCH_HOME)")
    parser.add_argument("--list", action="store_true", help="specs y estado, sin ejecutar")
    parser.add_argument("--once", action="store_true", help="ejecuta la siguiente pendiente")
    parser.add_argument("--loop", action="store_true", help="sigue buscando hasta --max-runs")
    parser.add_argument("--max-runs", type=int, default=0, help="0 = sin límite")
    parser.add_argument("--cooldown", type=float, default=5.0, help="segundos entre corridas")
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--force", action="store_true", help="repite specs ya medidas")
    parser.add_argument("--ledger", default=str(LEDGER))
    args = parser.parse_args(argv)

    try:
        home = research_home(args.home)
    except ResearchUnavailable as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    python = interpreter(home)
    ledger = Path(args.ledger)
    records = load_ledger(ledger)

    if args.list:
        done = measured(records)
        for path in spec_paths(home):
            spec = json.loads(path.read_text(encoding="utf-8"))
            record = done.get(fingerprint(spec))
            state = record["verdict"] if record else "pendiente"
            print(f"{spec.get('id', path.stem):<28} {spec.get('timeframe_signal', ''):<4} {state}")
        print(f"\nmotor    {home}\npython   {python}\nledger   {ledger} ({len(records)} corridas)")
        return 0

    if not (args.once or args.loop):
        parser.print_help()
        return 0

    out_dir = Path("data/research/artifacts")
    runs = 0
    failures = 0
    while True:
        queue = spec_paths(home) if args.force else pending(home, load_ledger(ledger))
        if not queue:
            print("nada pendiente: todas las specs están medidas")
            return 0
        record = run_spec(
            home, python, queue[0], out_dir=out_dir, timeout=args.timeout
        )
        _append(record, ledger)
        runs += 1
        if record["verdict"]:
            failures = 0
            print(
                f"{record['id']} {record['timeframe']} -> {record['verdict']}"
                f" ({record['seconds']:.0f}s)"
            )
        else:
            failures += 1
            detail = (record["error"] or record["output"] or "").splitlines()
            print(
                f"{record['id']} falló (rc {record['returncode']}): "
                f"{detail[-1] if detail else 'sin salida'}",
                file=sys.stderr,
            )
            if failures >= 3:
                print("tres fallos seguidos: paro para no quemar tiempo en bucle", file=sys.stderr)
                return 1
        if args.once:
            return 0 if record["verdict"] else 1
        if args.max_runs and runs >= args.max_runs:
            return 0
        time.sleep(max(args.cooldown, 0.0))


if __name__ == "__main__":
    raise SystemExit(main())
