# CONTINUACIÓN — ezur (bot de trading)

Pega este documento como primer mensaje del **segundo chat** del proyecto. El otro chat
("Motor IA para Estrategias BTC") es el motor de investigación; este es el bot.

## 1. Los dos proyectos no se mezclan

| Chat | Qué es | Dónde vive |
|---|---|---|
| Motor IA para Estrategias BTC | Investigación: specs, runner determinista, 12 puertas, PBO/DSR. No opera. | `…\.deepai-code\scratch\2026-11-22-motor-ia-…` · repo privado `motor-ia-estrategias-btc` |
| **ezur** (este) | Terminal de trading: motor determinista, riesgo, ejecución **paper**, SQLite WAL y dashboard. | `C:\Users\Administrator\Downloads\bot-base` · repo privado `ezur` |

No importes el runner de investigación dentro del bot ni al revés. Comparten filosofía —medir
antes de creer— pero son bases de código distintas.

## 2. Estado exacto, verificado hoy

- Rama **`master`**, 25+ commits, **sin remoto** hasta ahora.
- Último commit: `d2fa1bc docs: night report with the measured numbers`.
- **Árbol sucio a propósito**: el trabajo se cortó a mitad de la *barrera temporal* (que tras un
  reinicio el motor no pueda cerrar una posición con velas anteriores a su entrada).
  - Modificados: `server/db.py` (+43), `server/engine.py` (+21), `server/migrations.py` (+46),
    `tests/test_maintenance.py`, `tests/test_store.py`.
  - Sin trackear: `tests/test_replay_barrier.py`.
- Última verificación conocida: **349 tests backend · 28 frontend · `tsc` limpio · build 358 kB ·
  cobertura 96 %**.
- UI en `http://127.0.0.1:8765`, motor con `auto_start: true`.
- **18 experimentos, 0 aprobados.** 9 de 10 puertas medidas; falta el holdout, y por diseño.
- Las tres estrategias pierden y las **seis combinaciones** del walk-forward pierden en las tres
  ventanas. Con datos sintéticos sin estructura **eso es lo correcto**: si alguna aprobara, el
  problema sería el arnés.

## 3. Arquitectura que no se toca sin ADR

Motor (`TradingEngine`) totalmente separado de la UI · FastAPI con `/api/ws` (snapshots) y `/api/*`
(REST) · SQLite en **WAL** con `trades`, `events`, `equity`, `kv`, `backtests`, más ledger encadenado
· `RiskManager` con orden de comprobaciones y sizing · parada de emergencia persistente · triple
condición de LIVE · secuencia **BACKTEST → DRY-RUN → LIVE** · 7 vistas en Avanzado y 4 en Básico ·
contrato de snapshot **v1 agnóstico**: React no conoce activos ni estrategias, todo viene del backend
· estrategia como plugin `BaseStrategy.evaluate(market_data)`.

## 4. Comandos

| Comando | Qué hace |
|---|---|
| `python -m pytest` | Suite del backend |
| `cd frontend && npm run test` | Suite de componentes |
| `cd frontend && npm run build` | `tsc --noEmit` + build de Vite |
| `python run.py` | Servidor en `127.0.0.1:8765` |
| `python -m server.simulation --days 60 --bars 390 --out reports/backtest/sim-60d.json` | Simulación multi-sesión |
| `python -m server.funnel` | Embudo de evaluación del ledger |
| `python -m server.walkforward` | Ventanas W1–W6 sobre una rejilla |
| `python -m server.experiments` | Ledger de experimentos con veredictos |
| `python -m server.diagnostics` | Diagnóstico de SQLite en solo lectura |
| `python -m server.reset --dry-run` / `--yes` | Previsualiza / ejecuta el reinicio operativo |

El proyecto ya tiene su `.venv` con las dependencias (`requirements.txt`: fastapi, uvicorn, pydantic,
pytest, httpx, tzdata). Los docs que mandan: `docs/OPERACION.md`, `docs/PROTOCOLO_BACKTEST.md`,
`docs/DECISIONES.md`, `docs/COMO_ESCRIBIR_UNA_ESTRATEGIA.md`, `docs/API.md`.

## 5. Reglas de hierro

- **Determinismo**: solo velas cerradas, sin lookahead, sin estado oculto, sin I/O en la estrategia.
- El plugin **no manda órdenes ni gestiona riesgo**: devuelve `stop_price` obligatorio y el motor
  decide.
- **Nunca coronar una tabla perdedora.** Si el walk-forward pierde, se escribe que pierde.
- Los datos sintéticos **no validan rentabilidad**. No presentar una simulación como edge.
- Toda decisión de arquitectura va a `docs/DECISIONES.md` como ADR.
- Tests y build en verde antes de cada commit; commits pequeños y en español.
- **Paper only**: no hay ejecución real, no hay claves de exchange, no se añaden.
- Si un cambio puede alterar el veredicto de una estrategia, se avisa antes de aplicarlo.

## 6. Lo que estaba en curso (empieza por aquí)

La **barrera temporal** post-reinicio. Los cambios están sin commitear y `tests/test_replay_barrier.py`
no se ha ejecutado nunca. El primer trabajo es terminarla, correr la suite y commitear **solo si pasa**.

## 7. Pendientes conocidos

- Cerrar los ADR que quedaron abiertos en `docs/INFORME_NOCHE_2026-11-23.md`.
- El **holdout**, la única puerta sin medir.
- Comparación de variantes y curva contra buy & hold en la UI.

## 8. Primer paso que te pido

1. `git status` y `git diff` completos para ver el WIP.
2. Activa el `.venv` y corre `python -m pytest`.
3. Termina la barrera temporal y pasa la suite.
4. Pégame la salida real y dime qué falta antes de commitear.
