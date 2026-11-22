# Trading Terminal

Terminal local de trading algorítmico: motor determinista, gestión de riesgo,
ejecución paper, persistencia SQLite en WAL y dashboard web. La lógica de
estrategia es un plugin intercambiable: la infraestructura no conoce ni activos
ni reglas de entrada.

**Estado:** esqueleto completo y operativo (Fase 1) con simulación multi-sesión y
veredicto de validación automático. La estrategia incluida es una referencia sin
validar, no una ventaja de mercado.

## Arranque rápido

```bash
python -m pip install -r requirements.txt
cd frontend ; npm install ; npm run build ; cd ..
python run.py
```

Panel en `http://127.0.0.1:8765`. El motor arranca **detenido**: hay que pulsar
*Iniciar* en la vista de Inicio o llamar `POST /api/bot/start`.

Con datos sintéticos y la estrategia de referencia:

```bash
TERMINAL_PROFILE_DIR=profiles/demo python run.py      # Windows: set TERMINAL_PROFILE_DIR=profiles/demo
```

## Simulación multi-sesión

```bash
python -m server.simulation --days 60 --bars 390 --out reports/backtest/simulation-60d.json
```

Ejecuta el motor real sobre sesiones sintéticas deterministas y escribe
estadísticas completas: global, por dirección, por hora, por día de la semana,
por mes y curva de equidad. Sirve para verificar la infraestructura; los datos
sintéticos no validan rentabilidad.

## Comandos

| Comando | Qué hace |
|---|---|
| `python -m pytest` | Suite del backend |
| `cd frontend && npm run test` | Suite de componentes |
| `cd frontend && npm run build` | `tsc --noEmit` + build de Vite |
| `python -m server.simulation --days 20` | Simulación multi-sesión |
| `python -m server.diagnostics` | Diagnóstico de SQLite en solo lectura |
| `python -m server.reset --dry-run` | Previsualiza el reinicio operativo |
| `python -m server.reset --yes` | Archiva estado y deja todo limpio |

## Estructura

```text
server/
  engine.py        ciclo de vela, sesión, control, recuperación
  snapshot.py      contrato v1 agnóstico
  schemas.py       contrato Pydantic del snapshot
  risk.py          autorización y dimensionado
  execution.py     fills, brackets, barras ambiguas
  db.py            Store SQLite WAL
  simulation.py    simulación multi-sesión
  stats.py         métricas descriptivas
  gates.py         puertas de validación como datos + veredicto
  confirmatory.py  sellado del holdout (una sola vez)
  experiments.py   ledger JSONL de experimentos
  diagnostics.py   inspección SQLite de solo lectura
  reset.py         reinicio operativo con backup
  strategy/        ← único lugar con lógica de estrategia
    base.py        contrato BaseStrategy
    registry.py    resolución por id
    null_strategy.py
    reference.py   referencia sin validar
  market/          feeds, CSV, sesiones, instrumentos, sintético
frontend/src/      React 18 + TypeScript + Lightweight Charts
docs/              arquitectura, estrategia de referencia, decisiones
```

## Reglas que el código hace cumplir

- Ningún nombre de activo en `server/` (salvo `server/market/`) ni en
  `frontend/src/`: lo verifica `tests/test_no_hardcoded_instruments.py`.
- La estrategia no importa base de datos, motor, API ni ejecución.
- Una señal se ejecuta una sola vez; no hay segunda entrada con posición abierta.
- El stop es obligatorio: sin `stop_price` no hay señal válida.
- Ante una vela que toca stop y objetivo, gana el stop, con diagnóstico auditable.
- LIVE exige adaptador implementado + `live_enabled` + confirmación explícita.
- Un `kind` de zona o marcador desconocido se descarta y se registra.

## Qué está medido y qué no

| Hecho | Evidencia |
|---|---|
| Motor determinista | Mismo dataset ⇒ mismo hash de backtest |
| Snapshot conforme al contrato | 195 tests de backend, 12 de frontend |
| Pipeline completo con trades reales | `reports/backtest/simulation-180d.json` |
| Estrategia de referencia rentable | **No.** Veredicto automático: RECHAZADA |
| Veredicto reproducible | `GET /api/validation` evalúa G4–G13 y nombra lo no medible |

Ver `docs/ESTRATEGIA_REFERENCIA.md` para los números y por qué no cuenta como
ventaja, y `docs/DECISIONES.md` para lo que falta decidir antes de la Fase 4.

## Siguiente

1. Cerrar los 7 ADR de `docs/DECISIONES.md`.
2. Datos reales y reconciliación de costes (Fase 2).
3. Escribir la estrategia candidata en `server/strategy/` y validarla con el
   protocolo de puertas antes de arriesgar capital.
