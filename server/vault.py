"""Vault de Markdown con la memoria de la investigación.

Un artefacto del motor, una nota: cifras, puertas y procedencia, enlazadas desde
un índice, su familia y su marco. El vault se genera desde los JSON del motor,
así que no inventa ninguna cifra y se puede borrar y volver a crear entero.

    python -m server.research --vault        # escribe data/research/vault
    python -m server.research --vault-lint   # enlaces rotos y notas huérfanas
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

VAULT = Path("data/research/vault")
ARTIFACTS = Path("data/research/artifacts")
LEDGER = Path("data/research/runs.jsonl")

_LINK = re.compile(r"\[\[([^\]|#]+)")
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")

_CALLOUT = {"APPROVED": "success", "REJECTED": "failure"}


def _name(text: Any) -> str:
    return _SAFE.sub("-", str(text)).strip("-") or "sin-nombre"


def _num(value: Any, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "sí" if value else "no"
    if isinstance(value, int):
        return f"{value:,}".replace(",", ".")
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.append("---")
    return "\n".join(lines)


def read_artifacts(directory: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(document, dict) and document.get("spec_id"):
            out.append(document)
    return out


def _read_ledger(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def spec_note(artifact: dict[str, Any]) -> tuple[str, str]:
    """La nota de un artefacto: qué midió, qué puertas falló y de dónde sale."""
    ident = _name(artifact.get("spec_id"))
    version = str(artifact.get("version") or "0.0.0")
    title = f"{ident}-v{version}"
    family = _name(artifact.get("family") or "desconocida")
    data = artifact.get("data") or {}
    timeframe = str(data.get("timeframe_signal") or "?")
    verdict = str(artifact.get("verdict") or "SIN VEREDICTO")
    metrics = (artifact.get("metrics") or {}).get("all") or {}
    oos = (artifact.get("metrics") or {}).get("oos") or {}
    gates = artifact.get("gates") or {}
    failed = {
        name: gate
        for name, gate in gates.items()
        if isinstance(gate, dict) and gate.get("pass") is False
    }

    if failed:
        summary = " · ".join(
            f"{name} {_num(gate.get('value'), 3)} {gate.get('op', '')} {_num(gate.get('threshold'), 3)}"
            for name, gate in failed.items()
        )
    else:
        summary = "todas las puertas que se midieron pasaron"

    lines = [
        _frontmatter(
            {
                "id": ident,
                "version": version,
                "family": family,
                "timeframe": timeframe,
                "verdict": verdict,
                "pf_net": _num(metrics.get("pf_net"), 3),
                "trades": metrics.get("n"),
                "tags": ["spec", f"verdict/{verdict}", f"familia/{family}", f"marco/{timeframe}"],
            }
        ),
        "",
        f"# {title}",
        "",
        f"{artifact.get('name') or ident} · familia [[Familia - {family}]] · "
        f"marco [[Marco - {timeframe}]]",
        "",
        f"> [!{_CALLOUT.get(verdict, 'warning')}] {verdict}",
        f"> {summary}",
        "",
        "## Números",
        "",
        "| métrica | todas | fuera de muestra |",
        "| --- | --- | --- |",
    ]
    for key, label in (
        ("n", "operaciones"),
        ("win", "acierto"),
        ("pf_net", "PF neto"),
        ("exp_net_r", "esperanza neta (R)"),
        ("sharpe", "Sharpe"),
        ("mdd", "DD máximo"),
        ("t_stat", "t"),
    ):
        lines.append(f"| {label} | {_num(metrics.get(key), 3)} | {_num(oos.get(key), 3)} |")

    costs = artifact.get("costs") or {}
    benchmark = artifact.get("benchmark") or {}
    stress = artifact.get("stress") or {}
    lines += [
        "",
        "## Coste y referencia",
        "",
        f"- coste ida y vuelta: {_num(costs.get('rt_bps'), 2)} pb "
        f"({_num(costs.get('cost_r_mean'), 4)} R por operación)",
        f"- CAGR de la estrategia: {_num(benchmark.get('strategy_cagr'), 4)} "
        f"frente a {_num(benchmark.get('bh_cagr'), 4)} de comprar y mantener",
        f"- alfa anual: {_num(benchmark.get('alpha_annual'), 4)}",
        f"- coste de equilibrio: {_num(stress.get('breakeven_rt_bps'), 2)} pb",
        "",
        "## Puertas",
        "",
        "| puerta | valor | umbral | pasa |",
        "| --- | --- | --- | --- |",
    ]
    for name in sorted(gates):
        gate = gates[name]
        if not isinstance(gate, dict):
            continue
        lines.append(
            f"| {name} | {_num(gate.get('value'), 3)} | "
            f"{gate.get('op', '')} {_num(gate.get('threshold'), 3)} | "
            f"{_num(gate.get('pass'))} |"
        )

    lines += [
        "",
        "## Procedencia",
        "",
        f"- barras: {_num(data.get('bars_signal'))} de {timeframe}, "
        f"{data.get('start')} → {data.get('end')}",
        f"- spec: `{identity_path(artifact)}`",
        f"- hora de la corrida: {artifact.get('generated_at') or '—'}",
    ]
    return title, "\n".join(lines) + "\n"


_SMALLER_BETTER = {"≤", "<=", "<"}
_LARGER_BETTER = {"≥", ">=", ">"}


def gate_margin(gate: dict[str, Any]) -> float | None:
    """Cuánto le faltó a una puerta para pasar, en fracción de su umbral.

    Positivo = se quedó corta. Cada puerta mide cosas distintas, así que esto
    sirve para ordenar dentro de una puerta, no para comparar su gravedad.
    """
    value, threshold = gate.get("value"), gate.get("threshold")
    op = str(gate.get("op") or "").strip()
    if value is None or threshold is None or isinstance(value, bool):
        return None
    try:
        value, threshold = float(value), float(threshold)
    except (TypeError, ValueError):
        return None
    scale = abs(threshold) if abs(threshold) > 1e-12 else 1.0
    if op in _SMALLER_BETTER:
        return (value - threshold) / scale
    if op in _LARGER_BETTER:
        return (threshold - value) / scale
    if op == "==":
        return abs(value - threshold) / scale
    return None


def constant_gates(artifacts: list[dict[str, Any]]) -> set[str]:
    """Puertas que dan el mismo valor en todas las specs: no ordenan nada."""
    return {entry["gate"] for entry in gate_audit(artifacts) if entry["constant"]}


def closeness(artifact: dict[str, Any], ignore: set[str] | None = None) -> dict[str, Any]:
    """Cuántas puertas pasó y cuál fue su obstáculo más pequeño."""
    ignored = ignore or set()
    gates = {
        name: gate
        for name, gate in (artifact.get("gates") or {}).items()
        if isinstance(gate, dict) and name not in ignored
    }
    failed = {
        name: margin
        for name, margin in (
            (name, gate_margin(gate)) for name, gate in gates.items() if gate.get("pass") is False
        )
    }
    margins = {name: margin for name, margin in failed.items() if margin is not None}
    blocker = min(margins, key=lambda name: abs(margins[name])) if margins else None
    return {
        "passed": sum(1 for gate in gates.values() if gate.get("pass") is True),
        "measured": len(gates),
        "failed": len(failed),
        "blocker": blocker,
        "margin": margins.get(blocker) if blocker else None,
    }


def gate_audit(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Puertas que no distinguen una spec de otra.

    Una puerta que da el mismo valor en todas las corridas —o que no la pasa
    ninguna— no informa: si además está en el camino crítico, ninguna spec
    puede aprobar jamás.
    """
    stats: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        for name, gate in (artifact.get("gates") or {}).items():
            if not isinstance(gate, dict):
                continue
            entry = stats.setdefault(name, {"values": set(), "passes": 0, "total": 0})
            entry["total"] += 1
            entry["passes"] += 1 if gate.get("pass") is True else 0
            entry["values"].add(json.dumps(gate.get("value")))
    audit: list[dict[str, Any]] = []
    for name, entry in sorted(stats.items()):
        constant = len(entry["values"]) == 1 and entry["total"] > 1
        never = entry["passes"] == 0
        if not (constant or never):
            continue
        audit.append(
            {
                "gate": name,
                "constant": constant,
                "never_passes": never,
                "value": next(iter(entry["values"])) if constant else None,
                "specs": entry["total"],
            }
        )
    return audit


def ranking(
    artifacts: list[dict[str, Any]], ignore: set[str] | None = None
) -> list[dict[str, Any]]:
    """Ordena por cercanía a pasar: menos puertas falladas y obstáculo menor."""
    rows: list[dict[str, Any]] = []
    for artifact in artifacts:
        metrics = (artifact.get("metrics") or {}).get("all") or {}
        row = {
            "id": _name(artifact.get("spec_id")),
            "version": str(artifact.get("version") or "0.0.0"),
            "family": _name(artifact.get("family") or "desconocida"),
            "timeframe": str((artifact.get("data") or {}).get("timeframe_signal") or "?"),
            "verdict": str(artifact.get("verdict") or "SIN VEREDICTO"),
            "pf_net": metrics.get("pf_net"),
            "trades": metrics.get("n"),
            **closeness(artifact, ignore),
        }
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["failed"],
            abs(row["margin"]) if row.get("margin") is not None else 9e9,
            -(row.get("pf_net") or 0.0),
        )
    )
    return rows


def grouped_ranking(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Una fila por familia y marco: cuántas specs y cuál es la mejor de ellas.

    Sin agrupar, el podio lo copan veinte variantes del mismo barrido, que son
    la misma hipótesis contada veinte veces.
    """
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["family"], row["timeframe"])
        group = groups.setdefault(
            key,
            {
                "family": row["family"],
                "timeframe": row["timeframe"],
                "specs": 0,
                "best": row,
            },
        )
        group["specs"] += 1
        best = group["best"]
        candidate = (row["failed"], abs(row["margin"]) if row.get("margin") is not None else 9e9)
        current = (best["failed"], abs(best["margin"]) if best.get("margin") is not None else 9e9)
        if candidate < current:
            group["best"] = row
    return sorted(
        groups.values(),
        key=lambda group: (
            group["best"]["failed"],
            abs(group["best"]["margin"]) if group["best"].get("margin") is not None else 9e9,
        ),
    )


def ranking_note(artifacts: list[dict[str, Any]]) -> str:
    ignored = constant_gates(artifacts)
    rows = ranking(artifacts, ignored)
    lines = [
        _frontmatter({"tipo": "ranking", "specs": len(rows), "tags": ["ranking"]}),
        "",
        "# Ranking por cercanía",
        "",
        "> [!warning] Es una heurística de triaje, no una probabilidad",
        "> Ordena por puertas superadas y, a igualdad, por lo que le faltó a la más",
        "> cercana en fracción de su umbral. Cada puerta mide cosas distintas: que",
        "> una quede a un 5 % no significa que sea más fácil de arreglar que otra al",
        "> 40 %. Sirve para decidir qué mirar primero. Índice: [[index]].",
    ]
    if ignored:
        lines += [
            "",
            f"> [!note] Fuera del margen: {', '.join(sorted(ignored))}",
            "> Valen lo mismo en todas las specs, así que no ordenan ninguna: se",
            "> cuentan arriba como sospechosas y no como obstáculo.",
        ]
    audit = gate_audit(artifacts)
    if audit:
        lines += ["", "> [!danger] Puertas que no discriminan"]
        for entry in audit:
            if entry["constant"]:
                lines.append(
                    f"> `{entry['gate']}` da el mismo valor ({entry['value']}) en las "
                    f"{entry['specs']} specs: no distingue nada."
                )
            else:
                lines.append(
                    f"> `{entry['gate']}` no la pasó ninguna de las {entry['specs']} specs."
                )
    lines += [
        "",
        "## Por familia y marco",
        "",
        "| familia | marco | specs | mejor pasó | obstáculo | margen | la mejor |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for group in grouped_ranking(rows):
        best = group["best"]
        note = f"{best['id']}-v{best['version']}"
        lines.append(
            f"| {group['family']} | {group['timeframe']} | {group['specs']} | "
            f"{best['passed']}/{best['measured']} | {best['blocker'] or '—'} | "
            f"{_num(best['margin'], 3)} | [[{note}]] |"
        )
    lines += [
        "",
        "## Las veinte más cercanas",
        "",
        "| # | spec | marco | veredicto | pasó | falló | obstáculo | margen |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for position, row in enumerate(rows[:20], start=1):
        note = f"{row['id']}-v{row['version']}"
        verdict = row["verdict"] or "SIN VEREDICTO"
        lines.append(
            f"| {position} | [[{note}]] | {row['timeframe']} | {verdict} | "
            f"{row['passed']}/{row['measured']} | {row['failed']} | "
            f"{row['blocker'] or '—'} | {_num(row['margin'], 3)} |"
        )
    return "\n".join(lines) + "\n"


def identity_path(artifact: dict[str, Any]) -> str:
    artifacts = artifact.get("artifacts") or {}
    return str(artifacts.get("spec_path") or "—")


def family_note(family: str, artifacts: list[dict[str, Any]]) -> tuple[str, str]:
    title = f"Familia - {family}"
    lines = [
        _frontmatter({"tipo": "familia", "family": family, "specs": len(artifacts), "tags": ["familia"]}),
        "",
        f"# {title}",
        "",
        f"{len(artifacts)} especificaciones medidas. Índice: [[index]].",
        "",
        "| spec | marco | veredicto | PF neto | operaciones |",
        "| --- | --- | --- | --- | --- |",
    ]
    for artifact in artifacts:
        note = f"{_name(artifact.get('spec_id'))}-v{artifact.get('version') or '0.0.0'}"
        metrics = (artifact.get("metrics") or {}).get("all") or {}
        lines.append(
            f"| [[{note}]] | {(artifact.get('data') or {}).get('timeframe_signal')} | "
            f"{artifact.get('verdict')} | {_num(metrics.get('pf_net'), 3)} | "
            f"{_num(metrics.get('n'))} |"
        )
    return title, "\n".join(lines) + "\n"


def frame_note(frame: str, artifacts: list[dict[str, Any]]) -> tuple[str, str]:
    title = f"Marco - {frame}"
    lines = [
        _frontmatter({"tipo": "marco", "timeframe": frame, "specs": len(artifacts), "tags": ["marco"]}),
        "",
        f"# {title}",
        "",
        f"{len(artifacts)} especificaciones medidas en este marco. Índice: [[index]].",
        "",
        "| spec | familia | veredicto | PF neto |",
        "| --- | --- | --- | --- |",
    ]
    for artifact in artifacts:
        note = f"{_name(artifact.get('spec_id'))}-v{artifact.get('version') or '0.0.0'}"
        metrics = (artifact.get("metrics") or {}).get("all") or {}
        lines.append(
            f"| [[{note}]] | {artifact.get('family')} | {artifact.get('verdict')} | "
            f"{_num(metrics.get('pf_net'), 3)} |"
        )
    return title, "\n".join(lines) + "\n"


def index_note(
    artifacts: list[dict[str, Any]],
    records: list[dict[str, Any]],
    days: list[str] | None = None,
) -> str:
    verdicts = Counter(str(artifact.get("verdict") or "SIN VEREDICTO") for artifact in artifacts)
    families = Counter(_name(artifact.get("family") or "desconocida") for artifact in artifacts)
    frames = Counter(str((artifact.get("data") or {}).get("timeframe_signal") or "?") for artifact in artifacts)
    lines = [
        _frontmatter({"tipo": "indice", "specs": len(artifacts), "corridas": len(records), "tags": ["indice"]}),
        "",
        "# Memoria de la investigación",
        "",
        "Una nota por artefacto del motor, agrupada por familia y por marco. "
        "Las cifras salen de los JSON del motor: este vault no calcula nada.",
        "",
        "## Veredictos",
        "",
        "| veredicto | specs |",
        "| --- | --- |",
    ]
    for verdict, count in sorted(verdicts.items()):
        lines.append(f"| {verdict} | {count} |")
    lines += ["", "## Familias", ""]
    for family, count in sorted(families.items()):
        lines.append(f"- [[Familia - {family}]] — {count} specs")
    lines += ["", "## Marcos", ""]
    for frame, count in sorted(frames.items()):
        lines.append(f"- [[Marco - {frame}]] — {count} specs")
    if artifacts:
        lines += ["", "## Ranking", "", "- [[Ranking]] — qué spec está más cerca de pasar y en qué puerta"]
    if days:
        lines += ["", "## Bitácora", ""]
        for day in days[-10:]:
            lines.append(f"- [[Bitacora - {day}]] — {len([r for r in records if str(r.get('ts') or '')[:10] == day])} corridas")
    lines += [
        "",
        "## Corridas",
        "",
        f"{len(records)} corridas en el ledger, "
        f"{sum(float(record.get('seconds') or 0) for record in records) / 60:.1f} min de motor.",
        "",
    ]
    return "\n".join(lines)


def bitacora_note(day: str, records: list[dict[str, Any]]) -> tuple[str, str]:
    title = f"Bitacora - {day}"
    lines = [
        _frontmatter({"tipo": "bitacora", "dia": day, "corridas": len(records), "tags": ["bitacora"]}),
        "",
        f"# {title}",
        "",
        "| spec | marco | veredicto | segundos |",
        "| --- | --- | --- | --- |",
    ]
    for record in records:
        lines.append(
            f"| {record.get('id')} | {record.get('timeframe')} | "
            f"{record.get('verdict') or 'sin veredicto'} | {_num(record.get('seconds'), 1)} |"
        )
    return title, "\n".join(lines) + "\n"


def _bitacora_days(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    days: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        stamp = str(record.get("ts") or "")
        day = stamp[:10] if len(stamp) >= 10 else "sin-fecha"
        days.setdefault(day, []).append(record)
    return days


def write_vault(
    artifacts_dir: Path = ARTIFACTS,
    ledger: Path = LEDGER,
    out_dir: Path = VAULT,
) -> dict[str, int]:
    artifacts = read_artifacts(artifacts_dir)
    records = _read_ledger(ledger)
    files: dict[str, str] = {}

    by_family: dict[str, list[dict[str, Any]]] = {}
    by_frame: dict[str, list[dict[str, Any]]] = {}
    for artifact in artifacts:
        family = _name(artifact.get("family") or "desconocida")
        frame = str((artifact.get("data") or {}).get("timeframe_signal") or "?")
        by_family.setdefault(family, []).append(artifact)
        by_frame.setdefault(frame, []).append(artifact)
        title, body = spec_note(artifact)
        files[f"specs/{title}.md"] = body

    for family, group in by_family.items():
        title, body = family_note(family, group)
        files[f"Familias/{title}.md"] = body
    for frame, group in by_frame.items():
        title, body = frame_note(frame, group)
        files[f"Marcos/{title}.md"] = body
    days = _bitacora_days(records)
    for day, group in sorted(days.items()):
        title, body = bitacora_note(day, group)
        files[f"Bitacora/{title}.md"] = body
    if artifacts:
        files["Ranking.md"] = ranking_note(artifacts)
    files["index.md"] = index_note(artifacts, records, sorted(days))

    # El vault se regenera entero: una nota de un artefacto que ya no existe
    # quedaría huérfana y el índice no la enlazaría. Se borran solo las .md que
    # esta corrida no escribió; lo demás (adjuntos) se respeta.
    for path in out_dir.rglob("*.md"):
        if path.relative_to(out_dir).as_posix() not in files:
            path.unlink(missing_ok=True)

    for relative, body in files.items():
        path = out_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")

    links = sum(len(_LINK.findall(body)) for body in files.values())
    return {
        "notes": len(files),
        "specs": len(artifacts),
        "families": len(by_family),
        "frames": len(by_frame),
        "links": links,
    }


def lint_vault(out_dir: Path = VAULT) -> list[str]:
    """Lo que rompe un wiki cuando crece: enlaces muertos y notas sueltas."""
    notes = {path.stem.lower(): path for path in out_dir.rglob("*.md")}
    if not notes:
        return [f"vault vacío: {out_dir}"]
    linked: set[str] = set()
    problems: list[str] = []
    for _stem, path in notes.items():
        text = path.read_text(encoding="utf-8")
        for target in _LINK.findall(text):
            key = target.strip().lower()
            if key not in notes:
                problems.append(f"enlace roto: [[{target}]] en {path.relative_to(out_dir)}")
            else:
                linked.add(key)
    for stem, path in notes.items():
        if stem != "index" and stem not in linked:
            problems.append(f"nota huérfana: {path.relative_to(out_dir)}")
    return problems
