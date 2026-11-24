"""Umbrales del motor de estrategias, leídos del contrato del bot.

No hay copia local a propósito. Una copia es exactamente cómo dos proyectos
acaban midiendo lo mismo con números distintos y ninguno sabe cuál creer: el
bot dice PF 1,25 y el laboratorio dice 1,00, y los dos tienen tests verdes.

Si el fichero no está, este módulo falla al importarse. Un error de arranque es
preferible a un umbral inventado.

    EZUR_GATES_FILE   ruta explícita al contrato
    EZUR_BOT_HOME     raíz del bot (por defecto, dos niveles sobre este fichero)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

# research_engine/runner/gates.py → la raíz del repo que contiene config/gates.json.
BOT_HOME = Path(os.getenv("EZUR_BOT_HOME") or Path(__file__).resolve().parents[2])
GATES_FILE = Path(os.getenv("EZUR_GATES_FILE") or (BOT_HOME / "config" / "gates.json"))


def load(path: Path | str | None = None) -> dict:
    target = Path(path) if path is not None else GATES_FILE
    if not target.is_file():
        raise FileNotFoundError(
            f"no encuentro el contrato de umbrales en {target}. "
            f"Apunta {os.environ.get('EZUR_GATES_FILE', 'EZUR_GATES_FILE')} al "
            f"config/gates.json del bot o define EZUR_BOT_HOME."
        )
    document = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{target}: el contrato debe ser un objeto JSON")
    return document


def research(path: Path | str | None = None) -> dict:
    section = load(path).get("research")
    if not isinstance(section, dict):
        raise ValueError(f"{GATES_FILE}: falta la sección 'research'")
    return section


_SECTION = research()

MAX_PBO = float(_SECTION["max_pbo"])
MIN_DSR = float(_SECTION["min_dsr"])
MIN_OOS_T_STAT = float(_SECTION["min_oos_t_stat"])
MIN_OOS_PF_CI_LOW = float(_SECTION["min_oos_pf_ci_low"])
MIN_TRADES = int(_SECTION["min_trades"])
MIN_WFA_TRADES_PER_FOLD = int(_SECTION["min_wfa_trades_per_fold"])
MIN_MINBTL_COVERAGE = float(_SECTION["min_minbtl_coverage"])
COST_STRESS_MULTIPLIER = float(_SECTION["cost_stress_multiplier"])
MIN_COST_STRESS_PF = float(_SECTION["min_cost_stress_pf"])
MIN_PLATEAU_PF = float(_SECTION["min_plateau_pf"])
MIN_BENCHMARK_ALPHA_CI_LOW = float(_SECTION["min_benchmark_alpha_ci_low"])
MAX_UNEXPLAINED_GAPS = int(_SECTION["max_unexplained_gaps"])
