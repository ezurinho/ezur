"""La puerta de promoción del estudio, ejecutable y aplicable al arranque.

Ganar en un backtest no demuestra nada. Los cuatro criterios salen de
`docs/ESTUDIO-2026-11-24.md` y se aplican con la misma vara a toda
configuración que quiera operar:

- PF fuera de muestra > 1 con al menos 100 operaciones fuera de muestra;
- coste ponderado < 0,25 R por operación (fees totales / riesgo total);
- PF fuera de muestra > 1 con el coste duplicado;
- PBO del ciclo de selección de su universo <= 0,2;
- DSR del ciclo >= 0,95 (el Sharpe sobrevive a la multiplicidad de intentos).

El PBO y el DSR no se escriben aquí: salen de `config/gates.json`, el mismo
fichero que lee el motor de estrategias, para que la misma selección no se
mida con dos varas.

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
MIN_DSR = 0.95


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


def _limits() -> dict[str, float]:
    """Umbrales de selección del contrato compartido (`config/gates.json`).

    El PBO y el DSR son la misma vara en el laboratorio y en el arranque: si se
    escriben dos veces, acaban midiendo distinto. Manda el fichero; los valores
    de este módulo son el respaldo para cuando no está.
    """
    from . import gates

    try:
        research = gates.research_thresholds()
    except (OSError, ValueError):
        return {"max_pbo": MAX_PBO, "min_dsr": MIN_DSR}

    def pick(key: str, default: float) -> float:
        value = _number(research.get(key))
        return default if value is None else value

    return {"max_pbo": pick("max_pbo", MAX_PBO), "min_dsr": pick("min_dsr", MIN_DSR)}


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


def _stress_from_cycle(cycle: dict[str, Any] | None) -> dict[str, Any] | None:
    """El estrés 2x que ya midió el ciclo, con la forma del fichero aparte.

    El ciclo guarda una entrada por configuración. Si declara el candidato que
    opera el perfil (`candidate`), la puerta usa ese; si no, usa el que el
    propio ciclo selecciona (`stress.selected`). Así el estrés no puede quedar
    en una variante distinta a la del perfil cuando el ciclo ya la declara. La
    promoción no necesita una segunda corrida con costes duplicados. El alcance
    es el ciclo completo, no el tramo OOS del fichero: se reutiliza su forma
    para no duplicar el contrato de la puerta.
    """
    block = (cycle or {}).get("stress")
    if not isinstance(block, dict):
        return None
    configs = block.get("configs")
    if not isinstance(configs, list) or not configs:
        return None
    selected = str((cycle or {}).get("candidate") or "").strip() or block.get(
        "selected"
    )
    chosen = next(
        (
            item
            for item in configs
            if isinstance(item, dict) and item.get("name") == selected
        ),
        None,
    )
    if chosen is None:
        return None
    return {
        "split": {
            "out_of_sample": {
                "profit_factor": chosen.get("pf_net"),
                "trades": chosen.get("trades"),
                "expectancy_r": chosen.get("exp_r"),
            }
        },
        "multiplier": block.get("multiplier"),
        "source": "cycle",
    }


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


def _reprice_cost(
    cost: float, declared: dict[str, float], model: dict[str, float]
) -> float:
    """Reexpresa un coste en R con el modelo de ejecución del perfil."""
    return cost * (model["commission"] / model["tick_value"]) / (
        declared["commission"] / declared["tick_value"]
    )


def daily_cap_rejections(rejections: Any) -> int:
    """Señales rechazadas por el tope diario de operaciones.

    No confundir con `trades_at_cap`/`cap_rate`: esos cuentan operaciones cuyo
    **tamaño** tocó `max_units_per_trade`, no días que agotaron
    `max_trades_per_day`. El tope diario se ve en el rechazo
    `max_trades_reached`.
    """
    if not isinstance(rejections, dict):
        return 0
    value = rejections.get("max_trades_reached", 0)
    return int(value) if isinstance(value, (int, float)) else 0


def cost_metrics(
    trades: list[Any],
    execution: dict[str, Any] | None,
    budget: float | None = None,
    max_units: int | None = None,
) -> dict[str, Any]:
    """Coste en R con el riesgo real de cada operación.

    `cost_per_trade_r` es el **ponderado** (`fees totales / riesgo total`),
    comparable con el nominal (`fees / operaciones / presupuesto`). El **simple**
    (`media de fees/riesgo por operación`) se conserva aparte como distribución
    (mediana, p90, p99, cola >1R), no como métrica de aprobación: mezclar la
    media por operación con un nominal ponderado da un factor engañoso.
    """
    empty = {
        "trades": 0,
        "avg_risk_per_trade": None,
        "avg_stop_ticks": None,
        "cost_per_trade_r": None,
        "cost_per_trade_r_weighted": None,
        "cost_per_trade_r_simple": None,
        "cost_per_trade_r_median": None,
        "cost_per_trade_r_p90": None,
        "cost_per_trade_r_p99": None,
        "cost_above_1r": 0,
        "cost_above_1r_rate": None,
        "cost_min": None,
        "cost_max": None,
        "cost_per_trade_r_nominal": None,
        "risk_budget_utilization": None,
        "trades_at_cap": 0,
        "trades_at_units_cap": 0,
        "cap_rate": None,
    }
    model = _execution_model(execution)
    if model is None:
        return empty
    raw_execution = execution if isinstance(execution, dict) else {}
    tick_size = _number(raw_execution.get("tick_size"))
    if tick_size is None or tick_size <= 0:
        return empty
    rows: list[tuple[float, float, float]] = []
    at_cap = 0
    for trade in trades:
        entry = _number(getattr(trade, "entry_price", None))
        stop = _number(getattr(trade, "stop_price", None))
        units = _number(getattr(trade, "units", None))
        fees = _number(getattr(trade, "fees", None))
        if entry is None or stop is None or units is None or fees is None:
            continue
        if units <= 0:
            continue
        stop_ticks = abs(entry - stop) / tick_size
        risk = stop_ticks * model["tick_value"] * units
        if risk <= 0:
            continue
        rows.append((risk, fees, stop_ticks))
        if max_units is not None and units >= max_units:
            at_cap += 1
    if not rows:
        return empty
    n = len(rows)
    total_risk = sum(risk for risk, _, _ in rows)
    total_fees = sum(fees for _, fees, _ in rows)
    costs = [fees / risk for risk, fees, _ in rows]
    ordered = sorted(costs)

    def percentile(fraction: float) -> float:
        position = fraction * (len(ordered) - 1)
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        weight = position - lower
        return ordered[lower] * (1 - weight) + ordered[upper] * weight

    weighted = total_fees / total_risk
    simple = sum(costs) / n
    above_one = sum(1 for cost in costs if cost > 1.0)
    return {
        "trades": n,
        "avg_risk_per_trade": total_risk / n,
        "avg_stop_ticks": sum(ticks for _, _, ticks in rows) / n,
        # Ponderado: fees totales / riesgo total. Es el comparable con el
        # nominal (fees / operaciones / presupuesto) y el que usa la puerta.
        "cost_per_trade_r": weighted,
        "cost_per_trade_r_weighted": weighted,
        # Simple: media de fees/riesgo por operación. Es una distribución,
        # no la métrica de aprobación.
        "cost_per_trade_r_simple": simple,
        "cost_per_trade_r_median": percentile(0.5),
        "cost_per_trade_r_p90": percentile(0.9),
        "cost_per_trade_r_p99": percentile(0.99),
        "cost_above_1r": above_one,
        "cost_above_1r_rate": above_one / n,
        "cost_min": ordered[0],
        "cost_max": ordered[-1],
        "cost_per_trade_r_nominal": (
            total_fees / n / budget if budget and budget > 0 else None
        ),
        "risk_budget_utilization": (
            total_risk / n / budget if budget and budget > 0 else None
        ),
        # El tamaño tocó `max_units_per_trade`. El tope diario no se mide aquí:
        # se ve en `diagnostics.rejections["max_trades_reached"]`.
        "trades_at_cap": at_cap,
        "trades_at_units_cap": at_cap,
        "cap_rate": at_cap / n,
    }


def _measured_cost(
    evidence: dict[str, Any], execution: dict[str, Any] | None
) -> tuple[float | None, str, str]:
    """Coste por operación en R, método usado y motivo si no se puede medir.

    El número real es el **ponderado** (`fees totales / riesgo total`), que es
    el comparable con el nominal; el simple es una distribución y no se usa
    para aprobar. El coste en R de una operación es
    2·comisión/(stop·tick_value). El número que trae la evidencia se midió con
    la comisión y el tick_value de aquella corrida; si el perfil opera con otro
    modelo, ese número no vale. De la corrida se recupera el stop medio
    implícito (comisiones, operaciones y presupuesto de riesgo) y se recalcula
    con el modelo del perfil. Sin modelo declarado no hay número: una evidencia
    que no dice con qué costes se midió no puede aprobar el criterio, y sin el
    modelo del perfil tampoco se acepta el número heredado.
    """
    if execution is None:
        return None, "unknown", "falta el perfil que va a operar: coste no verificable"
    model = _execution_model(execution)
    if model is None:
        return (
            None,
            "unknown",
            "el perfil no declara comisión y tick_value: coste no verificable",
        )
    declared = _execution_model(evidence.get("execution"))
    if declared is None:
        return (
            None,
            "unknown",
            "la evidencia no declara su modelo de ejecución: coste no verificable",
        )

    real_cost = _number(evidence.get("cost_per_trade_r_weighted"))
    if real_cost is None:
        real_cost = _number(evidence.get("cost_per_trade_r"))
    if str(evidence.get("cost_method") or "") == "real_risk":
        if str(evidence.get("cost_scope") or "") != "out_of_sample":
            return (
                None,
                "unknown",
                "el coste real no declara el tramo fuera de muestra: coste no verificable",
            )
        if real_cost is None or real_cost <= 0:
            return (
                None,
                "unknown",
                "el coste real declarado no es válido: coste no verificable",
            )
        return _reprice_cost(real_cost, declared, model), "real_risk", ""

    avg_stop = _number(evidence.get("avg_stop_ticks"))
    if avg_stop is not None and avg_stop > 0:
        measured = 2 * declared["commission"] / (avg_stop * declared["tick_value"])
        return _reprice_cost(measured, declared, model), "avg_stop", ""

    # Compatibilidad con evidencias anteriores a la medición con riesgo real.
    metrics = evidence.get("metrics") or {}
    trades = _number(metrics.get("trades"))
    fees = _number(metrics.get("fees"))
    budget = _number(evidence.get("risk_budget"))
    if not trades or not fees or not budget or trades <= 0 or fees <= 0 or budget <= 0:
        return (
            None,
            "unknown",
            "la evidencia no declara operaciones, comisiones y presupuesto: "
            "coste no verificable",
        )
    stop_ticks = (
        2 * declared["commission"] * trades * budget / (fees * declared["tick_value"])
    )
    if stop_ticks <= 0:
        return (
            None,
            "unknown",
            "el stop implícito de la corrida no es válido: coste no verificable",
        )
    return 2 * model["commission"] / (stop_ticks * model["tick_value"]), "nominal", ""


def cost_per_trade_r(
    evidence: dict[str, Any], execution: dict[str, Any] | None
) -> tuple[float | None, str]:
    """Coste por operación y motivo; el método queda en `_measured_cost`."""
    cost, _method, reason = _measured_cost(evidence, execution)
    return cost, reason


def evaluate(
    evidence: dict[str, Any] | None,
    stress: dict[str, Any] | None = None,
    cycle: dict[str, Any] | None = None,
    strategy: dict[str, Any] | None = None,
    config_hash: str | None = None,
    execution: dict[str, Any] | None = None,
    research_hash: str | None = None,
    profile_hash: str | None = None,
    brakes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    if execution is None and config_hash:
        # La puerta por hash puede usar el modelo que declara la evidencia;
        # sin hash sigue siendo obligatorio el perfil que va a operar.
        execution = (evidence or {}).get("execution")

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

    evidence_doc = evidence or {}
    cost, cost_method, cost_reason = _measured_cost(evidence_doc, execution)
    if cost_reason:
        cost_failure = cost_reason
    elif cost is not None:
        kind = {
            "real_risk": "ponderado",
            "avg_stop": "estimado por stop medio",
            "nominal": "nominal",
        }.get(cost_method, cost_method)
        cost_failure = f"coste {kind} {cost:.3f} R ≥ {MAX_COST_R:g} R"
    else:
        cost_failure = "sin coste medido"
    cost_check = _check(
        "coste_por_operacion",
        cost,
        f"< {MAX_COST_R} R",
        (cost_value := _number(cost)) is not None and cost_value < MAX_COST_R,
        cost_failure,
    )
    cost_check["method"] = cost_method
    cost_check["metric"] = "weighted" if cost_method == "real_risk" else cost_method
    cost_check["simple"] = _number(evidence_doc.get("cost_per_trade_r_simple"))
    cost_check["scope"] = evidence_doc.get("cost_scope")
    checks.append(cost_check)

    cycle_stress = _stress_from_cycle(cycle)
    stress_source = (
        "ciclo"
        if cycle_stress is not None
        else ("fichero" if stress is not None else None)
    )
    if cycle_stress is not None:
        stress = cycle_stress
    stressed_oos = _oos(stress or {})
    stressed_pf = stressed_oos.get("profit_factor")
    stressed_value = _number(stressed_pf)
    stress_reason = "falta la corrida con coste duplicado"
    if stressed_value is not None:
        where = " (ciclo)" if stress_source == "ciclo" else ""
        stress_reason = f"PF con coste duplicado{where} {stressed_value:g} ≤ 1"
    stress_check = _check(
        "pf_con_coste_duplicado",
        stressed_pf,
        f"> {MIN_OOS_PF}",
        stressed_value is not None and stressed_value > MIN_OOS_PF,
        stress_reason,
    )
    stress_check["source"] = stress_source
    stress_check["scope"] = stress_source or "ninguno"
    stress_check["multiplier"] = (stress or {}).get("multiplier")
    checks.append(stress_check)

    pbo = ((cycle or {}).get("pbo") or {}).get("pbo")
    evidence_tf = str((evidence or {}).get("timeframe") or "") or _timeframe((evidence or {}).get("dataset"))
    cycle_tfs = {
        str(item.get("timeframe"))
        for item in ((cycle or {}).get("universe") or [])
        if isinstance(item, dict) and item.get("timeframe")
    }
    if (cycle or {}).get("timeframe"):
        cycle_tfs.add(str((cycle or {}).get("timeframe")))
    limits = _limits()
    max_pbo = limits["max_pbo"]
    min_dsr = limits["min_dsr"]
    comparable = True
    pbo_value = _number(pbo)
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
    elif pbo_value is None:
        pbo_reason = "el ciclo no declara PBO: no se puede medir la selección"
    elif pbo_value > max_pbo:
        pbo_reason = (
            f"PBO {pbo_value:.3f} > {max_pbo:g}: el mejor del universo no se "
            "distingue de la mediana"
        )
    checks.append(
        _check(
            "pbo_del_ciclo",
            pbo,
            f"<= {max_pbo:g}",
            comparable and pbo_value is not None and pbo_value <= max_pbo,
            pbo_reason,
        )
    )

    # El PBO dice si la selección es ruido; el DSR dice si el Sharpe que la
    # sostiene sobrevive a haber probado muchas configuraciones. Faltaba: el
    # ciclo lo medía y la puerta no lo miraba.
    dsr_block = (cycle or {}).get("dsr")
    dsr = dsr_block.get("dsr") if isinstance(dsr_block, dict) else None
    dsr_value = _number(dsr)
    if not comparable:
        dsr_reason = "sin ciclo comparable: DSR no verificable"
    elif dsr_value is None:
        dsr_reason = "el ciclo no declara DSR: no se puede medir la selección"
    else:
        dsr_reason = (
            f"DSR {dsr_value:.3f} < {min_dsr:g}: el Sharpe no sobrevive a los "
            "intentos de selección"
        )
    checks.append(
        _check(
            "dsr_del_ciclo",
            dsr,
            f">= {min_dsr:g}",
            comparable and dsr_value is not None and dsr_value >= min_dsr,
            dsr_reason,
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

    expected_hash = str(config_hash or "")
    expected_research = str(research_hash or "")
    if expected_research:
        found_research = str((evidence or {}).get("research_hash") or "")
        found_hash = str((evidence or {}).get("config_hash") or "")
        if found_research:
            matches = found_research == expected_research
            detail = (
                f"la evidencia se midió con otra configuración de investigación: "
                f"{found_research}, no {expected_research}"
            )
            found_value, expected_value = found_research, expected_research
        else:
            # Evidencia anterior a la separación de huellas: se compara como
            # antes en vez de darla por buena sin comprobar nada.
            matches = bool(expected_hash) and found_hash == expected_hash
            detail = (
                "la evidencia es anterior a la separación de huellas y declara "
                f"{found_hash or 'sin hash'}, no {expected_hash or expected_research}"
            )
            found_value = found_hash or "?"
            expected_value = expected_hash or expected_research
        checks.append(
            _check(
                "evidencia_de_la_configuracion",
                found_value,
                expected_value,
                matches,
                detail,
            )
        )
    elif expected_hash:
        found_hash = str((evidence or {}).get("config_hash") or "")
        checks.append(
            _check(
                "evidencia_de_la_configuracion",
                found_hash or "?",
                expected_hash,
                found_hash == expected_hash,
                f"la evidencia declara {found_hash or 'sin hash'}, no "
                f"{expected_hash}: se midio con otra configuracion",
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
        # Se publica junto a PBO/DSR, pero no es una puerta: mide si las entradas
        # del candidato baten a entradas aleatorias con su mismo riesgo.
        "random_entries": (cycle or {}).get("random_entries"),
        # De qué corrida sale el veredicto: sin esto, una tabla de criterios no
        # dice si se midió la estrategia, el marco temporal o la muestra buenos.
        "source": {
            "strategy": f"{found.get('id') or '?'}@{found.get('version') or '?'}",
            "dataset": (evidence or {}).get("dataset"),
            "split_at": ((evidence or {}).get("split") or {}).get("at"),
            "oos_trades": trades,
            # Con qué frenos se midió, no con los que opera el perfil ahora: la
            # puerta exige la huella de investigación, pero deja constancia del
            # perfil de medición para que la diferencia no sea invisible.
            "research_hash": (evidence or {}).get("research_hash"),
            "profile_hash": (evidence or {}).get("profile_hash"),
            "brakes": (evidence or {}).get("brakes"),
            "profile_hash_current": profile_hash,
            "brakes_current": brakes,
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
    config_hash: str | None = None,
    execution: dict[str, Any] | None = None,
    research_hash: str | None = None,
    profile_hash: str | None = None,
    brakes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return evaluate(
        load(evidence_path),
        load(stress_path),
        load(cycle_path),
        strategy,
        config_hash,
        execution,
        research_hash,
        profile_hash,
        brakes,
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
    config_hash: str | None = None,
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
    from .backtest import profile_fingerprint, research_fingerprint, risk_brakes

    execution = execution_model(settings)
    verdict = evaluate_paths(
        settings.promotion.evidence,
        settings.promotion.stress_evidence,
        settings.promotion.cycle,
        {"id": settings.strategy.id, "version": settings.strategy.version},
        config_hash=config_hash,
        execution=execution,
        research_hash=research_fingerprint(settings),
        profile_hash=profile_fingerprint(settings),
        brakes=risk_brakes(settings),
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
    random = verdict.get("random_entries") or {}
    if random.get("available"):
        lines.append("")
        lines.append(
            "entradas aleatorias "
            f"{random.get('config') or '':<26} "
            f"PF real {_shown(random.get('actual_pf'))} vs "
            f"mediana {_shown(random.get('random_pf_median'))} "
            f"(p={_shown(random.get('p_value'))}, n={random.get('trades')})"
        )
        lines.append(
            "  rango aleatorio "
            f"{_shown(random.get('random_pf_p05'))}..{_shown(random.get('random_pf_p95'))} "
            f"· percentil {_shown(random.get('percentile'))}"
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
    parser.add_argument(
        "--stress",
        default=None,
        help="backtest con coste duplicado; el ciclo con estrés tiene prioridad",
    )
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
    from .backtest import config_fingerprint

    config_hash = config_fingerprint(profile)
    verdict = evaluate_paths(
        args.evidence,
        args.stress,
        args.cycle,
        expected,
        config_hash=config_hash,
        execution=execution,
    )
    if args.json:
        print(json.dumps(verdict, indent=2, ensure_ascii=False))
    else:
        print(render(verdict))
    return 0 if verdict["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
