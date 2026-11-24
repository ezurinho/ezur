"""La puerta de promoción del estudio, ejecutable y aplicable al arranque.

Ganar en un backtest no demuestra nada. Los cuatro criterios salen de
`docs/ESTUDIO-2026-11-24.md` y se aplican con la misma vara a toda
configuración que quiera operar:

- PF fuera de muestra > 1 con al menos 100 operaciones fuera de muestra;
- coste medio < 0,25 R por operación;
- PF fuera de muestra > 1 con el coste duplicado;
- PBO del ciclo de selección de su universo <= 0,2.

Y la evidencia tiene que ser de la estrategia que se va a operar: un backtest
de otra estrategia no dice nada de esta, por bien que puntúe.

    python -m server.promotion --evidence bt.json --stress bt-2x.json --cycle ciclo.json

Sale con 1 si la configuración no está promovida. Es una decisión, no un aviso.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

MIN_OOS_PF = 1.0
MIN_OOS_TRADES = 100
MAX_COST_R = 0.25
MAX_PBO = 0.20


def _check(name: str, value: Any, threshold: str, passed: bool, reason: str) -> dict[str, Any]:
    return {
        "name": name,
        "value": value,
        "threshold": threshold,
        "pass": bool(passed),
        "reason": "" if passed else reason,
    }


def _oos(evidence: dict[str, Any]) -> dict[str, Any]:
    return (evidence.get("split") or {}).get("out_of_sample") or {}


def evaluate(
    evidence: dict[str, Any] | None,
    stress: dict[str, Any] | None = None,
    cycle: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    oos = _oos(evidence or {})
    pf = oos.get("profit_factor")
    trades = oos.get("trades")
    checks.append(
        _check(
            "pf_fuera_de_muestra",
            pf,
            f"> {MIN_OOS_PF}",
            pf is not None and float(pf) > MIN_OOS_PF,
            "sin PF fuera de muestra, o por debajo de 1",
        )
    )
    checks.append(
        _check(
            "operaciones_fuera_de_muestra",
            trades,
            f">= {MIN_OOS_TRADES}",
            trades is not None and int(trades) >= MIN_OOS_TRADES,
            "muestra fuera de muestra insuficiente",
        )
    )

    cost = (evidence or {}).get("cost_per_trade_r")
    checks.append(
        _check(
            "coste_por_operacion",
            cost,
            f"< {MAX_COST_R} R",
            cost is not None and float(cost) < MAX_COST_R,
            "sin coste medido, o demasiado alto para dejar margen",
        )
    )

    stressed_oos = _oos(stress or {})
    stressed_pf = stressed_oos.get("profit_factor")
    checks.append(
        _check(
            "pf_con_coste_duplicado",
            stressed_pf,
            f"> {MIN_OOS_PF}",
            stressed_pf is not None and float(stressed_pf) > MIN_OOS_PF,
            "falta la corrida con coste duplicado, o su PF no llega a 1",
        )
    )

    pbo = ((cycle or {}).get("pbo") or {}).get("pbo")
    checks.append(
        _check(
            "pbo_del_ciclo",
            pbo,
            f"<= {MAX_PBO}",
            pbo is not None and float(pbo) <= MAX_PBO,
            "sin ciclo de selección, o el universo es indistinguible del ruido",
        )
    )

    expected_id = str((strategy or {}).get("id") or "")
    expected_version = str((strategy or {}).get("version") or "")
    if expected_id:
        found = (evidence or {}).get("strategy") or {}
        found_id = str(found.get("id") or "")
        found_version = str(found.get("version") or "")
        matches = found_id == expected_id and (
            not expected_version or found_version == expected_version
        )
        expected = f"{expected_id}@{expected_version or '?'}"
        # Primero la procedencia: si la evidencia es de otra estrategia, los
        # demás criterios no dicen nada de esta configuración.
        checks.insert(
            0,
            _check(
                "evidencia_de_la_estrategia",
                f"{found_id or '?'}@{found_version or '?'}",
                expected,
                matches,
                f"la evidencia es de {found_id or '?'}@{found_version or '?'}, "
                f"no de {expected}",
            )
        )

    failed = [check for check in checks if not check["pass"]]
    found = (evidence or {}).get("strategy") or {}
    return {
        "passed": not failed,
        "checks": checks,
        "reason": failed[0]["reason"] if failed else "",
        "failed": [check["name"] for check in failed],
        # De qué corrida sale el veredicto: sin esto, una tabla de criterios no
        # dice si se midió la estrategia, el marco temporal o la muestra buenos.
        "source": {
            "strategy": f"{found.get('id') or '?'}@{found.get('version') or '?'}",
            "dataset": (evidence or {}).get("dataset"),
            "split_at": ((evidence or {}).get("split") or {}).get("at"),
            "oos_trades": trades,
        },
    }


def load(path: str | Path | None) -> dict[str, Any] | None:
    if not path:
        return None
    target = Path(path)
    if not target.is_file():
        return None
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return document if isinstance(document, dict) else None


def evaluate_paths(
    evidence_path: str | None,
    stress_path: str | None,
    cycle_path: str | None,
    strategy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate(load(evidence_path), load(stress_path), load(cycle_path), strategy)


def _shown(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render(verdict: dict[str, Any]) -> str:
    source = verdict.get("source") or {}
    parts = [
        str(part)
        for part in (
            source.get("strategy"),
            source.get("dataset"),
            f"corte {source['split_at']}" if source.get("split_at") else None,
            f"{source['oos_trades']} ops OOS" if source.get("oos_trades") is not None else None,
        )
        if part
    ]
    lines: list[str] = [f"evidencia: {' · '.join(parts)}", ""] if parts else []
    lines.append(f"{'criterio':<26} {'valor':>10} {'umbral':>14}  pasa")
    for check in verdict["checks"]:
        lines.append(
            f"{check['name']:<26} {_shown(check['value']):>10} "
            f"{check['threshold']:>14}  {'si' if check['pass'] else 'NO'}"
        )
    lines.append("")
    lines.append("promovida" if verdict["passed"] else f"no promovida: {verdict['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regla de promoción antes de operar")
    parser.add_argument("--evidence", required=True, help="backtest con split IS/OOS")
    parser.add_argument("--stress", default=None, help="el mismo backtest con coste duplicado")
    parser.add_argument("--cycle", default=None, help="ciclo de selección (PBO)")
    parser.add_argument(
        "--strategy",
        default=None,
        help="id@version que debe haber producido la evidencia; sin esto no se comprueba la procedencia",
    )
    parser.add_argument("--json", action="store_true", help="salida en JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not Path(args.evidence).is_file():
        print(f"no hay evidencia en {args.evidence}", flush=True)
        return 1

    expected = None
    if args.strategy:
        identifier, _, version = args.strategy.partition("@")
        expected = {"id": identifier, "version": version or None}
    verdict = evaluate_paths(args.evidence, args.stress, args.cycle, expected)
    if args.json:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
    else:
        print(render(verdict))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
