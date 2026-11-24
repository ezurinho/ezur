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

    python -m server.promotion --config profiles/okx/config.json \
        --evidence bt.json --stress bt-2x.json --cycle ciclo.json

Sale con 1 si la configuración no está promovida. Es una decisión, no un aviso.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings

MIN_OOS_PF = 1.0
MIN_OOS_TRADES = 100
MAX_COST_R = 0.25
MAX_PBO = 0.20


def _number(value: Any) -> float | None:
    """Número o None. Una evidencia con texto no debe tumbar la puerta."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _instant(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


_TIMEFRAME = re.compile(r"_(1m|3m|5m|15m|30m|1h|2h|4h|6h|8h|12h|1d|1w)(?:_|\.|$)")


def _timeframe(dataset: Any) -> str:
    match = _TIMEFRAME.search(str(dataset or ""))
    return match.group(1) if match else ""


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


def _execution_model(block: Any) -> dict[str, float] | None:
    """Comisión y tick_value de un modelo de ejecución, si están completos."""
    if not isinstance(block, dict):
        return None
    commission = _number(block.get("commission_per_unit_side"))
    tick_value = _number(block.get("tick_value"))
    if commission is None or tick_value is None:
        return None
    if commission <= 0 or tick_value <= 0:
        return None
    return {"commission": commission, "tick_value": tick_value}


def cost_per_trade_r(
    evidence: dict[str, Any], execution: dict[str, Any] | None
) -> tuple[float | None, str]:
    """Coste por operación en R medido con la ejecución que se va a usar.

    El coste en R de una operación es 2·comisión/(stop·tick_value). El número
    que trae la evidencia se midió con la comisión y el tick_value de aquella
    corrida; si el perfil opera con otro modelo, ese número no vale. De la
    corrida se recupera el stop medio implícito (comisiones, operaciones y
    presupuesto de riesgo) y se recalcula con el modelo del perfil. Sin modelo
    declarado no hay número: una evidencia que no dice con qué costes se midió
    no puede aprobar el criterio, y sin el modelo del perfil tampoco se acepta
    el número heredado.
    """
    if execution is None:
        return None, "falta el perfil que va a operar: coste no verificable"
    model = _execution_model(execution)
    if model is None:
        return None, "el perfil no declara comisión y tick_value: coste no verificable"
    declared = _execution_model(evidence.get("execution"))
    if declared is None:
        return None, "la evidencia no declara su modelo de ejecución: coste no verificable"
    metrics = evidence.get("metrics") or {}
    trades = _number(metrics.get("trades"))
    fees = _number(metrics.get("fees"))
    budget = _number(evidence.get("risk_budget"))
    if not trades or not fees or not budget or trades <= 0 or fees <= 0 or budget <= 0:
        return None, (
            "la evidencia no declara operaciones, comisiones y presupuesto: "
            "coste no verificable"
        )
    stop_ticks = (
        2 * declared["commission"] * trades * budget / (fees * declared["tick_value"])
    )
    if stop_ticks <= 0:
        return None, "el stop implícito de la corrida no es válido: coste no verificable"
    return 2 * model["commission"] / (stop_ticks * model["tick_value"]), ""


def evaluate(
    evidence: dict[str, Any] | None,
    stress: dict[str, Any] | None = None,
    cycle: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    metrics = (evidence or {}).get("metrics") or {}
    split = (evidence or {}).get("split") or {}
    last_ts = str(metrics.get("last_ts") or "")
    cut_at = str(split.get("at") or "")
    last = _instant(last_ts)
    cut = _instant(cut_at)
    if last is not None and cut is not None:
        checks.append(
            _check(
                "corrida_completa_hasta_el_corte",
                last_ts,
                f"≥ {cut_at}",
                last >= cut,
                f"la corrida terminó en {last_ts}, antes del corte {cut_at}: "
                "no hay periodo fuera de muestra",
            )
        )

    oos = _oos(evidence or {})
    pf = oos.get("profit_factor")
    trades = oos.get("trades")
    checks.append(
        _check(
            "pf_fuera_de_muestra",
            pf,
            f"> {MIN_OOS_PF}",
            (pf_value := _number(pf)) is not None and pf_value > MIN_OOS_PF,
            "sin PF fuera de muestra, o por debajo de 1",
        )
    )
    checks.append(
        _check(
            "operaciones_fuera_de_muestra",
            trades,
            f">= {MIN_OOS_TRADES}",
            (trades_value := _number(trades)) is not None
            and trades_value >= MIN_OOS_TRADES,
            "muestra fuera de muestra insuficiente",
        )
    )

    cost, cost_reason = cost_per_trade_r(evidence or {}, execution)
    checks.append(
        _check(
            "coste_por_operacion",
            cost,
            f"< {MAX_COST_R} R",
            (cost_value := _number(cost)) is not None and cost_value < MAX_COST_R,
            cost_reason or "sin coste medido, o demasiado alto para dejar margen",
        )
    )

    stressed_oos = _oos(stress or {})
    stressed_pf = stressed_oos.get("profit_factor")
    stressed_value = _number(stressed_pf)
    stress_reason = "falta la corrida con coste duplicado"
    if stressed_value is not None:
        stress_reason = f"PF con coste duplicado {stressed_value:g} ≤ 1"
    checks.append(
        _check(
            "pf_con_coste_duplicado",
            stressed_pf,
            f"> {MIN_OOS_PF}",
            stressed_value is not None and stressed_value > MIN_OOS_PF,
            stress_reason,
        )
    )

    pbo = ((cycle or {}).get("pbo") or {}).get("pbo")
    evidence_tf = str((evidence or {}).get("timeframe") or "") or _timeframe((evidence or {}).get("dataset"))
    cycle_tfs = {
        str(item.get("timeframe"))
        for item in ((cycle or {}).get("universe") or [])
        if isinstance(item, dict) and item.get("timeframe")
    }
    if (cycle or {}).get("timeframe"):
        cycle_tfs.add(str((cycle or {}).get("timeframe")))
    comparable = True
    pbo_reason = "sin ciclo de selección, o el universo es indistinguible del ruido"
    if not evidence_tf:
        comparable = False
        pbo_reason = (
            "la evidencia no declara dataset: no se puede verificar el marco del PBO"
        )
    elif not cycle_tfs:
        comparable = False
        pbo_reason = "el ciclo no declara marco: no se puede verificar el PBO"
    elif evidence_tf not in cycle_tfs:
        comparable = False
        pbo_reason = (
            f"el ciclo mide {'/'.join(sorted(cycle_tfs))}, no {evidence_tf}: "
            "PBO no comparable"
        )
    checks.append(
        _check(
            "pbo_del_ciclo",
            pbo,
            f"<= {MAX_PBO}",
            comparable
            and (pbo_value := _number(pbo)) is not None
            and pbo_value <= MAX_PBO,
            pbo_reason,
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
    reason = failed[0]["reason"] if failed else ""
    if (
        failed
        and failed[0]["name"] == "pf_fuera_de_muestra"
        and any(check["name"] == "operaciones_fuera_de_muestra" for check in failed)
    ):
        trades_value = _number(trades)
        if trades_value is not None:
            reason = (
                "muestra fuera de muestra insuficiente: "
                f"{trades_value:g} < {MIN_OOS_TRADES}"
            )
    found = (evidence or {}).get("strategy") or {}
    return {
        "passed": not failed,
        "checks": checks,
        "reason": reason,
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
    execution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate(
        load(evidence_path), load(stress_path), load(cycle_path), strategy, execution
    )


def execution_model(settings: Settings) -> dict[str, float] | None:
    """Modelo de ejecución del instrumento primario del perfil."""
    primary = next(
        (
            item
            for item in settings.instruments.items
            if item.symbol == settings.instruments.primary
        ),
        None,
    )
    if primary is None:
        return None
    return {
        "commission_per_unit_side": settings.execution.commission_per_unit_side,
        "tick_size": primary.tick_size,
        "tick_value": primary.tick_value,
    }


def effective_settings_and_verdict(
    settings: Settings,
) -> tuple[Settings, dict[str, Any] | None]:
    """Configuración que debe usar el motor y el veredicto que la explica.

    La reducción por falta de promoción es una decisión de arranque: no puede
    escribirse en `risk_per_trade_pct` porque el siguiente guardado la tomaría
    como valor configurado y volvería a reducirla. El archivo conserva el valor
    que eligió el operador; el motor recibe una copia efectiva.

    Devuelve el veredicto para que el arranque pueda dejar constancia del motivo
    sin volver a evaluar la evidencia. Si la puerta está apagada, el veredicto
    es `None`; si pasa o el modo es `block`, la configuración vuelve intacta.
    """
    if not settings.promotion.required:
        return settings, None
    execution = execution_model(settings)
    verdict = evaluate_paths(
        settings.promotion.evidence,
        settings.promotion.stress_evidence,
        settings.promotion.cycle,
        {"id": settings.strategy.id, "version": settings.strategy.version},
        execution,
    )
    if verdict["passed"] or settings.promotion.mode != "reduce":
        return settings, verdict
    effective = settings.model_copy(deep=True)
    effective.risk.risk_per_trade_pct = round(
        settings.risk.risk_per_trade_pct * settings.promotion.size_factor, 4
    )
    return effective, verdict


def effective_settings(settings: Settings) -> Settings:
    """Atajo para quien solo necesita la configuración efectiva."""
    return effective_settings_and_verdict(settings)[0]


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
        shown = _shown(check["value"])
        if check["name"] == "pbo_del_ciclo" and any(
            marker in check["reason"]
            for marker in ("no comparable", "no declara", "no se puede")
        ):
            shown = "—"
        lines.append(
            f"{check['name']:<26} {shown:>10} "
            f"{check['threshold']:>14}  {'si' if check['pass'] else 'NO'}"
        )
    lines.append("")
    lines.append("promovida" if verdict["passed"] else f"no promovida: {verdict['reason']}")
    failed = [check for check in verdict["checks"] if not check["pass"]]
    if failed:
        lines.append("motivos:")
        for check in failed:
            lines.append(f"  · {check['name']}: {check['reason']}")
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
    parser.add_argument(
        "--config",
        required=True,
        help="perfil con el que se va a operar; el coste se recalcula con su ejecución",
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
    profile_path = Path(args.config)
    if not profile_path.is_file():
        print(f"no hay perfil en {args.config}", flush=True)
        return 1
    try:
        profile = Settings.model_validate(
            json.loads(profile_path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"perfil inválido en {args.config}: {error}", flush=True)
        return 1
    execution = execution_model(profile)
    verdict = evaluate_paths(
        args.evidence, args.stress, args.cycle, expected, execution
    )
    if args.json:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
    else:
        print(render(verdict))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
