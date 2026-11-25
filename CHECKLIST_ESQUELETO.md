# Checklist del esqueleto — repositorio nuevo

Objetivo: dejar un repositorio que **arranca, persiste, sirve el dashboard y pasa los tests** con una estrategia nula (`NullStrategy`), listo para recibir la estrategia real en `server/strategy/`.

Criterio de aceptación del esqueleto:

| # | Criterio | Verificación |
|---|---|---|
| 1 | Arranca y sirve el dashboard | `python run.py` → `http://127.0.0.1:8765` responde |
| 2 | Arranque automático configurable | Con `auto_start: true` (por defecto) queda `running`; con `false`, `idle`/`stopped`. Sin señal, `strategy.signal = null` |
| 3 | Snapshot conforme al contrato v1 | `pytest -q` sobre test de contrato |
| 4 | Persistencia operativa | Iniciar, generar eventos, reiniciar, estado restaurado |
| 5 | Cero referencias a activos/estrategia en código de infra | `grep -rn` de tickers y nombres de estrategia = 0 resultados |
| 6 | Frontend compila | `npm run build` sin errores de tipos |
| 7 | Backtest determinista con estrategia nula | Golden test de hash |

---

## 1. Crear (nuevo)

### 1.1 Núcleo del motor

| Archivo | Nota |
|---|---|
| `run.py` | Arranque; `*_HOST`, `*_PORT`, `*_OPEN`, `*_PROFILE_DIR`, `*_CONFIG_PATH`, `*_DB_PATH` |
| `requirements.txt`, `pyproject.toml` | Dependencias fijadas |
| `server/__init__.py` | — |
| `server/main.py` | FastAPI, lifespan, estáticos de `frontend/dist` |
| `server/api.py` | REST + `WS /api/ws` |
| `server/engine.py` | `TradingEngine`: estado, control, emergencia, bucle |
| `server/snapshot.py` | **Nuevo**: `SnapshotBuilder` (contrato v1, todo dinámico) |
| `server/config.py` | `Settings` con los 7 grupos de la sección 11 |
| `server/models.py` | `Bar`, `Tick`, `Signal`, `Position`, `Order`, `TradeRecord` |
| `server/risk.py` | `RiskManager`, `RiskDecision` |
| `server/execution.py` | `ExecutionEngine` (fills, brackets, SL/TP) |
| `server/db.py` | `Store` sobre SQLite WAL |
| `server/migrations.py` | Esquema versionado desde v1 |
| `server/stats.py` | `compute_stats` |
| `server/schemas.py` | Contratos Pydantic del snapshot y del backtest |
| `server/timeutil.py` | Zonas horarias y sesión |
| `server/funnel.py` | Embudo de evaluación |
| `server/diagnostics.py` | Diagnóstico SQLite de solo lectura |
| `server/reset.py` | Reinicio con archivo de backups |

### 1.2 Bloque de estrategia (interfaz únicamente)

| Archivo | Nota |
|---|---|
| `server/strategy/__init__.py` | Exporta `BaseStrategy`, `MarketData`, `StrategyOutput` |
| `server/strategy/base.py` | **Contratos de la sección 16 del documento**: `Warmup`, `MarketData`, `Signal`, `Phase`, `Zone`, `Marker`, `Metric`, `StrategyOutput`, `BaseStrategy` |
| `server/strategy/registry.py` | `resolve_strategy(id)`, validación de `params` contra `params_model` |
| `server/strategy/null_strategy.py` | `NullStrategy`: sin señal, `state="disabled"`, `metrics={}`, `phases=[]`. Placeholder explícito |

### 1.3 Datos de mercado

| Archivo | Nota |
|---|---|
| `server/market/__init__.py` | — |
| `server/market/feed.py` | `MarketFeed`, `SimulatedFeed`, `CSVFeed`, `LiveFeed` (sin adaptador) |
| `server/market/csv_data.py` | Carga, alineación y validación multi-serie genérica |
| `server/market/sessions.py` | Calendario, feriados, cierres anticipados |
| `server/market/instruments.py` | Especificaciones, vencimientos y rolls (antes `contracts.py`) |
| `server/market/synthetic.py` | Generador sintético determinista |
| `server/market/providers/` | Adaptadores de descarga, uno por proveedor |

### 1.4 Backtesting y validación

| Archivo | Nota |
|---|---|
| `server/backtest.py` | `prepare_dataset`, `run_backtest`, `run_variants`, presets |
| `server/confirmatory.py` | Hashes, preflight, sello del holdout |
| `server/experiments.py` | Identidad de experimentos y ledger JSONL |
| `server/gates.py` | **Nuevo**: umbrales de validación como datos versionados (hoy dispersos) |
| `research/validacion_bloques.py` | Diseño de validación por bloques, agnóstico |
| `docs/PROTOCOLO_BACKTEST.md` + `.lock.json` | Protocolo y lock del proyecto nuevo |

### 1.5 Frontend

| Archivo | Nota |
|---|---|
| `frontend/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html` | Base del proyecto |
| `frontend/src/main.tsx`, `App.tsx` | Rutas y las 7 vistas |
| `frontend/src/types.ts` | **Espejo tipado del contrato v1**; sin uniones de tickers |
| `frontend/src/api.ts` | Cliente REST + WebSocket con reconexión |
| `frontend/src/store.tsx` | Estado global tipado |
| `frontend/src/utils.ts` | Formato numérico por `format`/`decimals`/`currency` |
| `frontend/src/components/Sidebar.tsx`, `TopBar.tsx` | Navegación y cabecera |
| `frontend/src/components/KvPanel.tsx` | **Nuevo**: panel clave-valor genérico |
| `frontend/src/components/PhaseTimeline.tsx` | **Nuevo**: fases dinámicas |
| `frontend/src/components/ZoneLayer.tsx` | **Nuevo**: zonas (`band`/`line`/`box`/`region`) |
| `frontend/src/components/MarkerLayer.tsx` | **Nuevo**: marcadores |
| `frontend/src/components/SymbolsTable.tsx` | **Nuevo**: tabla de instrumentos desde `instruments[]` |
| `frontend/src/components/DynamicTable.tsx` | Tablas de operaciones/órdenes |
| `frontend/src/pages/Dashboard.tsx` | Inicio |
| `frontend/src/pages/Chart.tsx` | Gráfico |
| `frontend/src/pages/Operations.tsx` | Operaciones |
| `frontend/src/pages/History.tsx` | Historial |
| `frontend/src/pages/Stats.tsx` | Estadísticas |
| `frontend/src/pages/Config.tsx` | Configuración, incluida pestaña de estrategia generada desde `/api/strategy/schema` |
| `frontend/src/pages/Console.tsx` | Consola |

### 1.6 Tests del esqueleto

| Archivo | Cubre |
|---|---|
| `tests/conftest.py` | Fixtures de config, store temporal y dataset mínimo |
| `tests/test_snapshot_contract.py` | Snapshot válido contra el esquema v1 con `NullStrategy` |
| `tests/test_strategy_interface.py` | `NullStrategy` cumple el Protocol; params inválidos rechazados |
| `tests/test_dynamic_render_contract.py` | Zonas/marcadores/fases con `kind` desconocido no rompen |
| `tests/test_risk.py` | Orden de comprobaciones, sizing, ventanas, cooldown |
| `tests/test_execution.py` | Fills, brackets, slippage, barras ambiguas |
| `tests/test_store.py` | Esquema, migraciones, recuperación |
| `tests/test_engine.py` | Ciclo de vela, control start/pause/stop, emergencia |
| `tests/test_api_contract.py` | REST/OpenAPI y handshake WS |
| `tests/test_backtest_golden.py` | Determinismo con `NullStrategy` |
| `tests/test_no_hardcoded_instruments.py` | **Nuevo guardián**: el código de `server/` (salvo `market/`) y `frontend/src/` no contiene tickers ni nombres de estrategia |

### 1.7 Infraestructura de repositorio

| Archivo | Nota |
|---|---|
| `AGENTS.md` | Reglas del proyecto para agentes |
| `.gitignore` | `data/`, `backups/`, `frontend/node_modules`, `frontend/dist`, `__pycache__` |
| `start.bat` | Crea `.venv` e instala dependencias (Windows) |
| `data/.gitkeep`, `backups/.gitkeep`, `profiles/.gitkeep`, `reports/backtest/.gitkeep` | Estructura vacía versionada |
| `profiles/backtest/config.json`, `profiles/dryrun/config.json` | Perfiles aislados con símbolos de ejemplo genéricos |

---

## 2. Copiar desde el repo actual (sin cambios de lógica)

| Archivo | Ajuste |
|---|---|
| `server/models.py` | Renombrar `contracts` → `units` si aún dice `contracts` |
| `server/db.py` | Ninguno |
| `server/migrations.py` | Resetear versión a v1 creando solo las 5 tablas base + índice de backtests |
| `server/timeutil.py` | Ninguno |
| `server/diagnostics.py` | Ninguno |
| `server/reset.py` | Ninguno |
| `server/confirmatory.py` | Renombrar rutas de lock al proyecto nuevo |
| `server/experiments.py` | Renombrar prefijo de IDs de experimento |
| `research/validacion_bloques.py` | Ninguno (ya es genérico) |
| `tests/test_validacion_bloques.py` | Ninguno |

---

## 3. Reescribir (copiar estructura, eliminar acoplamiento)

| Archivo | Qué eliminar | Qué conservar |
|---|---|---|
| `server/config.py` | `ORBConfig`, `SMTConfig` y cualquier grupo con nombre de estrategia | Estructura de grupos, validación Pydantic, guardado atómico, backup `.broken` |
| `server/engine.py` | Llamadas a lógica de fases concretas; referencias a símbolos fijos | Ciclo de vela, cambio de sesión, control, emergencia, `kv` |
| `server/api.py` | Endpoints con nombres de estrategia; payloads con campos fijos | Grupos de endpoints de la sección 13 + `GET /api/strategy/schema` |
| `server/risk.py` | Umbrales con nombre de setup; supuestos de un solo instrumento | Orden de comprobaciones, sizing por especificación de instrumento, motivos de rechazo |
| `server/execution.py` | `tick_size`/`tick_value` hardcodeados | Fills, brackets, comisiones, slippage acotado, barras ambiguas |
| `server/stats.py` | Agrupaciones por "tipo de señal" con valores fijos | Métricas de la sección 12; agrupación por `signal.key` como string |
| `server/backtest.py` | Alineación de tres series fijas; presets con nombre de estrategia | `prepare_dataset`, `run_backtest`, `run_variants`, comparación |
| `server/market/feed.py` | `{SYM_A, SYM_B, SYM_C}` en el tick | `bars: dict[symbol, Bar]` |
| `server/market/csv_data.py` | Validación de columnas por ticker; exigencias de barras de apertura | Alineación por timestamp, huecos, sesiones, rolls, warmup configurable |
| `server/market/instruments.py` | Wrappers por producto | Tabla de especificaciones dirigida por config |
| `server/schemas.py` | `OpeningRange`, `Assessment` con campos de estrategia | Contrato v1 de la sección 7 |
| `server/snapshot.py` | — | Construir todo iterando `settings.instruments` |
| `frontend/src/types.ts` | Uniones con tickers; interfaces `OpeningRange`/`Assessment` | Tipos del contrato v1 |
| `frontend/src/pages/Chart.tsx` | Capas dibujadas con lógica propia; colores por activo | Velas, series, `ZoneLayer`, `MarkerLayer`, timeframes |
| `frontend/src/pages/Dashboard.tsx` | Widgets con nombres de fase fijos | KPIs, curva de equidad, `KvPanel`, posición |
| `frontend/src/pages/Config.tsx` | Formulario de estrategia con campos hardcodeados | Pestañas y formulario generado desde `params_schema` |
| `frontend/src/pages/Operations.tsx` | Supuestos de un solo contrato | Posición/órdenes/brackets genéricos |
| `docs/ARQUITECTURA.md` | Contenido específico | Reemplazar por `ARQUITECTURA_BASE.md` |

---

## 4. Eliminar del repo nuevo

| Elemento | Motivo |
|---|---|
| Todo módulo concreto en `server/strategy/` (fases, niveles, confirmaciones y cualquier regla propia del proyecto anterior) | Es la estrategia; se reemplaza por el bloque `# Aquí va la estrategia` |
| `server/gates` o umbrales embebidos con criterios atados a la estrategia anterior | Pasan a `server/gates.py` como datos |
| Datasets y CSV con tickers del proyecto anterior (`data/bars*.csv`, `data/real/*`) | Datos del proyecto viejo |
| `reports/backtest/*` del proyecto anterior | Resultados no trasladables |
| `profiles/backtest_real/` y `profiles/dryrun/` con configuración vieja | Se regeneran |
| `docs/PROTOCOLO_BACKTEST.md`, `.lock.json`, informes de desarrollo, auditorías | Específicos de la estrategia anterior |
| `frontend/dist/` | Se regenera con `npm run build` |
| `data/*.db`, `data/config.json`, `backups/*` | Estado local, nunca versionado |
| `tests/*` que aserten fases, motivos o números de la estrategia anterior | Se sustituyen por los tests del esqueleto |
| Scripts de descarga con tickers fijos | Parametrizar o eliminar |
| Cualquier `AGENTS.md`/`CLAUDE.md` heredado | Se escribe uno nuevo |

---

## 5. Verificación final del esqueleto

```bash
# 1. Backend
python -m pip install -r requirements.txt
python -m pytest -q

# 2. Guardián de agnosticismo (debe devolver 0 líneas)
python -m pytest -q tests/test_no_hardcoded_instruments.py

# 3. Frontend
cd frontend
npm install
npm run build
cd ..

# 4. Arranque real
python run.py
# → http://127.0.0.1:8765 : dashboard, WebSocket conectado,
#   panel "Estado de Estrategia" vacío, sin señales, motor detenido

# 5. Persistencia
#    iniciar motor, generar eventos, reiniciar, comprobar restauración
```

Criterio de "esqueleto listo": los 7 criterios de la tabla inicial pasan y `server/strategy/` contiene únicamente contratos, registro y `NullStrategy`.
