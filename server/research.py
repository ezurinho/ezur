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
import itertools
import json
import os
import re
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
GENERATED = Path("data/research/specs")
SPECS_DIR = Path("runner") / "specs"
RUNNER = Path("runner") / "run_strategy.py"

# Rejillas por parámetro. Solo se barre lo que la spec declara en `params`, así
# que una spec sin `N` no recibe un `N` inventado. `fast`/`slow` no se barren:
# cualquier combinación desordenada rompería la regla de entrada.
GRIDS: dict[str, list[float | int]] = {
    "N": [20, 40, 60],
    "z": [1.5, 2.0, 2.5],
    "atr_k": [1.2, 2.0, 3.0],
    "tp_r": [2.0, 4.0],
    "range_bars": [2, 4, 6],
}
SWEEPABLE = ("N", "z", "atr_k", "tp_r", "range_bars")


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


def spec_paths(home: Path, generated: Path | None = None) -> list[Path]:
    """Semillas del motor + variantes que ha escrito el bot."""
    paths: list[Path] = []
    for directory in (home / SPECS_DIR, GENERATED if generated is None else generated):
        if directory.is_dir():
            paths.extend(directory.glob("*.json"))
    return sorted(paths, key=lambda path: path.stat().st_mtime)


def _slug(value: float | int) -> str:
    return str(value).replace(".", "-")


_TOKENS = {"N": "N", "z": "Z", "atr_k": "K", "tp_r": "TP", "range_bars": "R"}
ID_PATTERN = re.compile(r"^BTC-[A-Z0-9]+(-[A-Z0-9]+)*$")
LABEL_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,48}$")


# Familias que el motor ya implementa y que este bot nunca ha medido. El lado
# de tendencia lleva seis semillas y noventa y seis variantes sin pasar el
# filtro; probar el contrario y otro patrón de sesión es lo que falta.
# `orb_session` cierra la sesión a 96 barras fijas, así que su marco natural es
# 15m; pero el esquema del motor solo acepta "15m"/"30m" y pandas 3 rechaza esos
# alias ("'m' is no longer supported"), así que todo marco de minutos salvo el
# 5m nativo revienta al resamplear. Se mide en 5m: rango de la primera hora y
# ventana de 8 h, que es la sesión que `_orb` sabe cerrar en ese marco.
SEED_BLUEPRINTS: list[dict[str, Any]] = [
    {
        "id": "BTC-ZREV-1H",
        "label": "zrev_1h_96",
        "name": "Reversion z-score 1h",
        "family": "mean_reversion",
        "timeframe_signal": "1h",
        "rule": "zscore_fade",
        "hypothesis": (
            "Las seis semillas del motor prueban tendencia y todas fueron rechazadas. "
            "El lado contrario no está medido: una desviacion grande respecto a la "
            "media de 96 barras de hora revierte antes de que el stop de 2 ATR se "
            "toque. A 96 barras la media cubre cuatro dias, que es el horizonte donde "
            "la reversión de BTC ya no la come el coste de 5 pb por lado."
        ),
        "long": "z[t] <= -z (cierre muy por debajo de la media)",
        "short": "z[t] >= z (cierre muy por encima de la media)",
        "params": {"N": 96, "z": 2.0, "atr_k": 2.0, "tp_r": 2.0},
        "exit": {"stop": "2.0 * ATR(14)[t]", "target": "2.0 * R", "time_stop_bars": 48, "trailing": None},
        "failure_modes": [
            "tendencia sostenida: el precio no vuelve a la media y el stop corta",
            "el z-score se dispara con el hueco, sin entrada posible al precio teorico",
        ],
    },
    {
        "id": "BTC-ZREV-4H",
        "label": "zrev_4h_60",
        "name": "Reversion z-score 4h",
        "family": "mean_reversion",
        "timeframe_signal": "4h",
        "rule": "zscore_fade",
        "hypothesis": (
            "La misma reversión que en 1h, medida en barras de 4h: 60 barras son diez "
            "días de media y el coste por operación baja a la mitad. Si la reversión "
            "existe en BTC, debería verse mejor cuanto menos se paga por operar."
        ),
        "long": "z[t] <= -z (cierre muy por debajo de la media)",
        "short": "z[t] >= z (cierre muy por encima de la media)",
        "params": {"N": 60, "z": 2.0, "atr_k": 2.0, "tp_r": 2.0},
        "exit": {"stop": "2.0 * ATR(14)[t]", "target": "2.0 * R", "time_stop_bars": 30, "trailing": None},
        "failure_modes": [
            "tendencia sostenida: el precio no vuelve a la media y el stop corta",
            "con 60 barras la media reacciona tarde y el z-score llega agotado",
        ],
    },
    {
        "id": "BTC-ORB-5M",
        "label": "orb_5m_12",
        "name": "Opening range breakout 5m",
        "family": "orb",  # el esquema solo admite trend/breakout/orb/mean_reversion/regime/momentum
        "timeframe_signal": "5m",
        "rule": "orb_session",
        "hypothesis": (
            "La primera hora del dia UTC define un rango y el primer cierre fuera de "
            "el suele continuar durante las horas siguientes. En futuros con campana "
            "de apertura el patron esta documentado; en BTC el dia UTC no tiene "
            "campana, asi que la hipotesis es debil y por eso importa medirla en vez "
            "de citarla. Doce barras de 5m son esa primera hora."
        ),
        "long": "close[t] > max(high[apertura .. apertura+range_bars])",
        "short": "close[t] < min(low[apertura .. apertura+range_bars])",
        "params": {"range_bars": 12, "atr_k": 2.0, "tp_r": 2.0},
        "exit": {"stop": "2.0 * ATR(14)[t]", "target": "2.0 * R", "time_stop_bars": 96, "trailing": None},
        "failure_modes": [
            "falsas rupturas en un rango estrecho: el primer cierre fuera vuelve dentro",
            "el rango de la primera hora es tan ancho que el stop queda lejos",
        ],
    },
]


def _base_template(home: Path) -> dict[str, Any]:
    """Una spec real del motor, para heredar riesgo, costes y validacion."""
    preferred = home / SPECS_DIR / "btc-trend-1d-donchian-40.json"
    candidates = [preferred] if preferred.is_file() else sorted((home / SPECS_DIR).glob("*.json"))
    if not candidates:
        raise ResearchUnavailable(f"no hay specs en {home / SPECS_DIR}")
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def seed_documents(template: dict[str, Any]) -> list[dict[str, Any]]:
    """Semillas nuevas a partir de una spec real: nada de inventar campos."""
    documents: list[dict[str, Any]] = []
    for blueprint in SEED_BLUEPRINTS:
        document = json.loads(json.dumps(template))
        document.update(
            id=blueprint["id"],
            name=blueprint["name"],
            label=blueprint["label"],
            family=blueprint["family"],
            hypothesis=blueprint["hypothesis"],
            timeframe_signal=blueprint["timeframe_signal"],
            version="1.0.0",
        )
        document.pop("parent_version", None)
        document.pop("expected", None)  # no se inventan cifras de rendimiento
        document["entry"] = {
            "rule": blueprint["rule"],
            "long": blueprint["long"],
            "short": blueprint["short"],
            "cooldown_bars": 0,
        }
        if blueprint["rule"] == "orb_session":
            document["entry"]["sessions"] = ["00:00"]
        document["exit"] = blueprint["exit"]
        document["params"] = blueprint["params"]
        document["failure_modes"] = blueprint["failure_modes"]
        document["validation"] = {**document.get("validation", {}), "trials_declared": 1}
        documents.append(document)
    return documents


def variants(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Producto cartesiano de los parámetros que la spec declara.

    La combinación igual a la semilla se descarta: ya está medida por definición.
    """
    params = spec.get("params") or {}
    keys = [key for key in SWEEPABLE if key in params]
    if not keys:
        return []
    base_id = str(spec.get("id") or "SPEC")
    tag = fingerprint(spec)[:4]
    out: list[dict[str, Any]] = []
    for combo in itertools.product(*(GRIDS[key] for key in keys)):
        if all(params[key] == value for key, value in zip(keys, combo)):
            continue
        suffix = "-".join(
            f"{_TOKENS.get(key, key)}{_slug(value)}" for key, value in zip(keys, combo)
        ).upper()
        document = json.loads(json.dumps(spec))
        document["params"] = {**params, **dict(zip(keys, combo))}
        document["id"] = f"{base_id}-{suffix}-{tag.upper()}"
        document["label"] = f"{spec.get('label', base_id)}-{suffix}".lower()[:49]
        # `parent_version` es el único campo de linaje que admite el esquema;
        # un campo inventado hace que el motor rechace la spec entera.
        version = str(spec.get("version") or "1.0.0")
        document["parent_version"] = version if re.fullmatch(r"\d+\.\d+\.\d+", version) else "1.0.0"
        out.append(document)
    # Cuantas mas combinaciones se prueban, mas se selecciona por azar: declarar
    # solo las de la semilla seria contar la mitad de la historia.
    for document in out:
        validation = document.get("validation")
        if isinstance(validation, dict):
            declared = int(validation.get("trials_declared") or 0)
            validation["trials_declared"] = max(declared, len(out) + 1)
    return out


def write_variants(
    specs: list[dict[str, Any]], directory: Path | str = GENERATED
) -> tuple[int, int]:
    """Escribe variantes nuevas; devuelve (escritas, ya existentes)."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    written = skipped = 0
    for spec in specs:
        name = f"{str(spec['id']).lower()}.json"
        path = target / name
        document = json.dumps(spec, indent=2, ensure_ascii=False)
        if path.exists():
            if path.read_text(encoding="utf-8") == document:
                skipped += 1
                continue
            # Una spec vieja con un campo que el esquema ya no admite se corrige.
            path.write_text(document, encoding="utf-8")
            written += 1
            continue
        path.write_text(document, encoding="utf-8")
        written += 1
    return written, skipped


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


def summarize(records: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, int]]:
    """Cuenta veredictos por familia y marco: lo que el bucle ha averiguado."""
    groups: dict[tuple[str, str], dict[str, int]] = {}
    for record in records:
        key = (str(record.get("family") or "?"), str(record.get("timeframe") or "?"))
        group = groups.setdefault(
            key,
            {"total": 0, "APPROVED": 0, "REJECTED": 0, "INCONCLUSIVE": 0, "sin veredicto": 0},
        )
        group["total"] += 1
        verdict = record.get("verdict")
        if verdict in ("APPROVED", "REJECTED", "INCONCLUSIVE"):
            group[verdict] += 1
        else:
            group["sin veredicto"] += 1
    return groups


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
    # El runner corre con cwd en su árbol: una ruta relativa al bot no existe allí.
    spec = Path(spec).resolve()
    spec_doc = json.loads(spec.read_text(encoding="utf-8"))
    command = [
        python,
        str(RUNNER),
        "--spec",
        str(spec),
        "--out",
        str(Path(out_dir).resolve()),
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
        "spec": str(spec.relative_to(home)) if spec.is_relative_to(home) else str(spec),
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
    parser.add_argument("--seeds", action="store_true", help="crea semillas de familias sin medir")
    parser.add_argument("--generate", action="store_true", help="crea variantes de las specs semilla")
    parser.add_argument("--report", action="store_true", help="resume el ledger por familia y marco")
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

    if args.seeds:
        documents = seed_documents(_base_template(home))
        written, skipped = write_variants(documents, home / SPECS_DIR)
        print(
            f"semillas: {written} nuevas, {skipped} ya existían ({len(documents)} propuestas)",
            flush=True,
        )
        return 0

    if args.generate:
        seeds = sorted((home / SPECS_DIR).glob("*.json"))
        created: list[dict[str, Any]] = []
        for path in seeds:
            try:
                created.extend(variants(json.loads(path.read_text(encoding="utf-8"))))
            except (OSError, json.JSONDecodeError):
                continue
        written, skipped = write_variants(created)
        print(
            f"variantes: {written} nuevas, {skipped} ya existían "
            f"({len(created)} calculadas de {len(seeds)} semillas)"
        )
        return 0

    if args.report:
        if not records:
            print(f"ledger vacío: {ledger}")
            return 0
        groups = summarize(records)
        print(f"{'familia':<12} {'marco':<5} {'total':>6} {'APPROVED':>9} {'REJECTED':>9} "
              f"{'INCONCLUSO':>11} {'fallos':>7}")
        for (family, frame), group in sorted(groups.items()):
            print(
                f"{family:<12} {frame:<5} {group['total']:>6} {group['APPROVED']:>9} "
                f"{group['REJECTED']:>9} {group['INCONCLUSIVE']:>11} {group['sin veredicto']:>7}"
            )
        interesting = [
            record for record in records
            if record.get("verdict") in ("APPROVED", "INCONCLUSIVE")
        ]
        if interesting:
            print("\nno rechazadas:")
            for record in interesting:
                print(f"  {record.get('id')} {record.get('timeframe')} -> {record.get('verdict')}")
        else:
            print("\nninguna spec ha pasado el filtro todavía")
        seconds = sum(float(record.get("seconds") or 0) for record in records)
        print(f"\n{len(records)} corridas · {seconds/60:.1f} min de motor")
        return 0

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
                f" ({record['seconds']:.0f}s)",
                flush=True,
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
