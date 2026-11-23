# Plan de investigación y mejora continua — 23/11/2026

Objetivo de la noche: convertir ezur de «terminal que funciona» en «terminal que
se puede auditar y operar sin leer el código». Se trabaja por fases, cada una
con criterio de aceptación medible y verificación ejecutada antes de decir que
está hecha. Nada se marca hecho sin salida de comando que lo respalde.

## Reglas de la noche

1. Un commit por fase cerrada; el árbol queda limpio entre fases.
2. Toda función nueva entra con test. Si no se puede medir, se dice, no se estima.
3. El contrato snapshot v1 no se rompe: campos nuevos son aditivos.
4. Cero referencias a instrumentos concretos en `server/` (salvo `server/market/`).
5. La UI no inventa: si falta el dato, se enseña el hueco.

## Fase 0 — Investigación (2 h)

Preguntas:

| # | Pregunta | Fuente |
|---|---|---|
| R1 | ¿Qué hacen las terminales de trading open source mejor que ezur en interacción? | Freqtrade UI, Hummingbot, Jesse, OctoBot, Superalgos, Ghostfolio |
| R2 | ¿Qué patrones de «laboratorio» (probar estrategia sin tocar el bot vivo) existen y cuáles son falsos? | Nautilus, vectorbt, QuantConnect LEAN, backtesting.py |
| R3 | ¿Cómo presentan resultados para que un no experto entienda si algo sirve? | Informes de Freqtrade, QuantStats, OpenBB |
| R4 | ¿Qué telemetría de estrategia es útil y cuál es ruido? | Documentación de las anteriores |

Entregable: `docs/INVESTIGACION_UI_2026-11-23.md` con datos reales de GitHub
(estrellas, último push, licencia), tabla adoptar / evitar y destino en el repo.

## Fase 1 — Trazabilidad de ejecuciones (backend)

Problema: `run_id` era el prefijo del hash del dataset. Dos corridas del mismo
CSV con distinta estrategia compartían identificador: no se puede citar «la
corrida X» en una conversación.

- `run_id` único por ejecución (uuid corto), `dataset_id` sigue siendo el hash.
- `config_hash` (SHA-256 del JSON canónico de settings efectivos).
- `run_group` para comparaciones: N estrategias sobre el mismo dataset.
- El ledger guarda `run_id`, `config_hash` y `dataset_id`; `--verify` sigue ok.
- Aceptación: dos corridas del mismo CSV dan `dataset_id` igual y `run_id`
  distinto; el test lo fija.

## Fase 2 — Laboratorio de estrategias (backend + UI)

Problema: para comparar estrategias había que usar la CLI. Un operador debe
poder correr un backtest desde la terminal, ver el veredicto de puertas y
comparar tres estrategias sin salir del navegador.

Backend:

- `GET /api/backtest/strategies` — plugins instalados con versión y parámetros.
- `POST /api/backtest/compare` — mismas velas, N estrategias, un `run_group`,
  veredicto por estrategia, ranking explícito (no elige ganador: ordena por
  esperanza y dice qué puertas falla cada una).
- Aceptación: comparar 3 estrategias devuelve 3 filas con el mismo
  `dataset_id`, `run_id` distintos y veredicto por fila.

Frontend (vista nueva «Laboratorio», solo modo avanzado):

- Selector de dataset (`/api/datasets`), de estrategia y de modelo de fill.
- Botón Ejecutar con estado real (no spinner infinito), tarjetas de resultado,
  lista de puertas con ✓/✗ y motivo, y tabla comparativa.
- Historial de corridas (`/api/backtest/runs`) con veredicto.
- Aceptación: correr desde la UI devuelve métricas idénticas a la CLI para el
  mismo dataset y estrategia (comparación en el test de paridad).

## Fase 3 — Lectura de resultados para humanos (UI)

- Histograma de R con los buckets reales de `stats.r_distribution` (sin
  inventar rangos en el cliente) en Estadísticas.
- Curva de equidad con relleno y marca de máximo, para ver el drawdown.
- Semáforo de calidad del dato en el gráfico cuando `staleness_ms` alto.
- Aceptación: el histograma usa exactamente las claves del backend; test de
  contrato con un payload fijo.

## Fase 4 — Interacción (UI)

- Ayuda de atajos con `?` (teclas reales, leídas de una sola tabla).
- Paleta de comandos: acciones nuevas (laboratorio, probar alerta, reset).
- Aviso de alerta de prueba desde Configuración (`POST /api/alerts/test`).

## Fase 5 — Cierre

- `pytest`, `tsc`, `vitest`, `npm run build`, `experiments --verify`.
- Docs: `docs/API.md`, `docs/UI.md`, `docs/DECISIONES.md` (ADR nuevos),
  `README.md` y este plan con lo hecho y lo que quedó fuera.
- Capturas nuevas en `docs/img/`.

## Estado de ejecución

| Fase | Estado | Evidencia |
|---|---|---|
| 0 · Investigación | hecho | `docs/INVESTIGACION_UI_2026-11-23.md`, 15 repos con ★ y último push |
| 1 · Trazabilidad | hecho | `run_id` único, `config_hash`, `run_group`; `tests/test_traceability.py` (8) |
| 2 · Laboratorio | hecho | `GET /api/backtest/strategies`, `POST /api/backtest/compare`, vista `Lab`, `server/datasets.py` |
| 3 · Lectura de resultados | parcial | histograma de R ya existía; equidad con línea de inicio y tema |
| 4 · Interacción | hecho | atajos con `?`, paleta con acciones, alerta de prueba en Configuración |
| 5 · Cierre | hecho | 364 backend / 43 frontend, build 371 kB, ledger verificado |

### Lo que se encontró al ejecutar (no estaba en el plan)

| Fallo | Cómo se vio | Arreglo |
|---|---|---|
| Dos hilos escribían en la misma conexión SQLite | «cannot commit - no transaction is active» en `/api/bot/start` durante un replay | `_LockedConnection` con `RLock` + test de 4 hilos |
| El estado tras un control podía quedar viejo en pantalla | botón decía «running», la UI seguía en «stopped» | `publish_now()` tras cada acción y estado capturado antes de ceder |
| `/api/datasets` listaba junto al perfil | Laboratorio vacío con perfil `okx` | directorio `data/` + `EZUR_DATA_DIR` |
| `run_id` repetido entre estrategias | informe ambiguo | uuid por ejecución |
| `null` encabezaba el ranking con 0.00 R | lectura engañosa | las estrategias sin operaciones van al final |
| `"es-ES"` en el gráfico | el guardián agnóstico lo leía como el símbolo ES | locale del navegador |

## Fuera de alcance (declarado)

- Ejecución real contra broker (ADR 0.3 sigue abierto).
- Estrategia con edge: la noche mejora el instrumento de medida, no inventa alfa.
- Multi-usuario, autenticación y despliegue remoto.
