# Plan de construcción — terminal de trading agnóstica

> **For agentic workers:** REQUIRED SUB-SKILL: use `subagent-driven-development` (recommended) or `executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construir una terminal de trading local con motor determinista, riesgo, ejecución paper, persistencia y dashboard, cuya lógica de estrategia sea un plugin intercambiable que se valide con un protocolo que pueda rechazarla.

**Architecture:** Motor `TradingEngine` independiente de la UI, alimentado por un `MarketFeed` multi-serie; la estrategia es un plugin puro (`BaseStrategy.evaluate`) que devuelve señal, fases, métricas, zonas y marcadores; `RiskManager` y `ExecutionEngine` son los únicos autorizados a dimensionar y ejecutar; `SnapshotBuilder` compone un contrato v1 genérico que React renderiza sin conocer activos ni estrategia.

**Tech Stack:** Python 3.12 · FastAPI · Pydantic v2 · SQLite (WAL) · pytest · React 18 · TypeScript 5 · Vite 5 · Lightweight Charts 4.2 · vitest

**Spec:** `ARQUITECTURA_BASE.md` (contratos) + `CHECKLIST_ESQUELETO.md` (inventario de archivos)

---

## Global Constraints

- Contrato de snapshot `v: 1`; todo mapa de instrumentos usa `symbol` como clave.
- `strategy.phases[].status ∈ {pending, active, done, failed, skipped}`.
- `strategy.metrics.*.format ∈ {number, price, pct, ratio, text, duration, boolean}`.
- `strategy.metrics.*.tone ∈ {neutral, good, bad, warn}`.
- `chart.zones[].kind ∈ {band, line, box, region}`.
- `chart.markers[].kind ∈ {entry, exit, phase, note, warning}`.
- `chart.series[].mode ∈ {raw, normalized, percent}`, `axis ∈ {overlay, secondary}`.
- `chart.timeframes = ["1m", "5m", "15m", "30m"]`.
- Retención de `events`: 5.000 filas.
- Historial: páginas de 25 filas; periodos `today | week | month | 30d | all`.
- Defaults de riesgo: `risk_per_trade_pct = 1.0`, `max_daily_loss_pct = 3.0`, `max_daily_profit_pct = 0.0`, `max_trades_per_day = 3`, `max_units_per_trade = 5`, `max_stop_ticks = 200`, `cooldown_minutes = 5`, `close_at_session_end = true`.
- LIVE arranca solo si `adapter_implemented and live_enabled and live_confirmation`; si falta algo, `RuntimeError`.
- Ningún identificador de activo ni nombre de estrategia en `server/` (salvo `server/market/`) ni en `frontend/src/`.
- La estrategia no importa `db`, `engine`, `api` ni `execution`.
- Toda escritura de configuración es atómica; configuración corrupta se archiva como `.json.broken` y se arranca con defaults.
- Python: `ruff` + `mypy --strict` en `server/strategy`, `server/risk.py`, `server/schemas.py`. Frontend: `tsc --noEmit` sin `any` implícito.

## Review Focus

1. **Snapshot con instrumentos añadidos o quitados en caliente** — un símbolo nuevo en `InstrumentsConfig` aparece en `quotes`, `instruments` y `series` sin editar código; uno eliminado desaparece de las tres y no deja claves huérfanas.
2. **Estrategia que devuelve `phases` vacío, 12 fases o un `kind` de zona desconocido** — la UI no lanza, no colapsa el layout y registra el `kind` no soportado.
3. **Señal sin `stop_price`, con `units` calculadas < 1, o repetida con la misma `key`** — se rechaza con motivo explícito visible en `strategy.rejection` o `risk.block_reason`, nunca entra una segunda vez.
4. **Vela ambigua (high y low tocan SL y TP en la misma barra)** — se resuelve SL primero, se registra diagnóstico auditable y el P&L del trade refleja esa decisión.
5. **Reinicio con posición abierta y config corrupta a la vez** — la posición y su bracket se restauran desde `kv`, la config se archiva a `.broken`, el motor arranca con defaults y la equidad se reconstruye desde `trades` (nunca desde un saldo guardado).

---

# Parte A — Plan maestro por fases

Cada fase termina en una **puerta** verificable por comando. No se avanza sin la puerta verde.

| Fase | Entregable | Duración | Puerta |
|---|---|---:|---|
| 0 | Decisiones congeladas | 1-2 d | `docs/DECISIONES.md` con 7 ADR firmados |
| 1 | Esqueleto ejecutable | 5-7 d | 7 checks del checklist + `pytest -q` verde |
| 2 | Datos y costes realistas | 3-5 d | Dataset validado + reconciliación de costes |
| 3 | Estrategia v1 | 3-5 d | Determinismo + golden test |
| 4 | Validación estadística | 5-10 d | Puertas G1–G14 |
| 5 | DRY-RUN | 30 d calendario | Desviación vs backtest ≤ 10 % |
| 6 | LIVE mínimo | continuo | Kill switch probado |
| 7 | Operación y mejora | continuo | Re-validación completa por versión |

Total hasta la primera decisión de capital real: **~6-8 semanas de trabajo efectivo + 30 días de calendario de dry-run.**

## Fase 0 — Decisiones congeladas

Nada de código. Se decide y se firma; cambiar esto después invalida validaciones.

| ADR | Decisión | Criterio |
|---|---|---|
| 0.1 | Mercado e instrumentos (primario + contexto) | Al menos 12 meses de historia con volumen real |
| 0.2 | Fuente de datos y su coste | Tick o 1m, con contrato/vencimiento documentado |
| 0.3 | Broker o ejecución simulada | Si no hay adaptador, LIVE queda bloqueado por diseño |
| 0.4 | Capital de referencia y tolerancia a drawdown | Número, no adjetivo |
| 0.5 | Temporalidad de decisión y de contexto | Escritas en `FeedConfig` |
| 0.6 | Costes: comisión, slippage, funding | Valores reales del broker, no estimaciones |
| 0.7 | Horario operativo y zona horaria | Con feriados y cierres anticipados |

**Puerta P0:** los 7 ADR existen, cada uno con número, alternativa descartada y motivo. Sin esto, la Fase 4 no es válida: un holdout sobre criterios cambiantes no es un holdout.

## Fase 1 — Esqueleto ejecutable

Detalle task-by-task en la Parte B. Construye todo con `NullStrategy`: el motor arranca detenido, sin señal, y el panel de Estado de Estrategia aparece vacío.

**Puerta P1 — comando único:**

```bash
python -m pytest -q && cd frontend && npm run build && cd .. && python run.py
```

Verde si: `pytest` sin fallos, build sin errores de tipos, `GET /api/health` responde, `WS /api/ws` emite el primer snapshot con `strategy.signal = null`, y `tests/test_no_hardcoded_instruments.py` devuelve 0 coincidencias.

## Fase 2 — Datos y costes realistas

| Paso | Qué se hace | Verificación |
|---|---|---|
| 2.1 | Ingesta del proveedor elegido (ADR 0.2) | Mismo dataset descargado dos veces ⇒ hash idéntico |
| 2.2 | Validación: alineación de series, huecos, sesiones, rolls, warmup | `POST /api/data/validate` sobre el dataset real ⇒ `ok` |
| 2.3 | Calendario con feriados y cierres anticipados | Tests de DST y de sesión corta |
| 2.4 | Costes reales por instrumento en `ExecutionConfig` | Comisión del broker = valor configurado |
| 2.5 | Modelo de fill + slippage acotado + barras ambiguas | Reconciliación de 20 operaciones reales vs simuladas |

**Puerta P2:** sobre 20 operaciones ejecutadas (por el operador o tomadas del broker), la diferencia media de precio de fill simulada vs real es ≤ 1 tick y el P&L neto simulado está dentro de ±5 %. Si no se puede medir, se declara `[NO MEDIBLE]` y la Fase 6 no se autoriza.

## Fase 3 — Estrategia v1

Una sola hipótesis. Una. Nada de "probemos también".

| Paso | Entregable |
|---|---|
| 3.1 | `docs/ESTRATEGIA.md`: hipótesis económica, por qué existe la ineficiencia, qué la rompería |
| 3.2 | Reglas de entrada/salida en pseudocódigo con parámetros nombrados y valores por defecto |
| 3.3 | `server/strategy/<id>.py` con `params_model` y `evaluate()` |
| 3.4 | `warmup_requirements()` coherente con el dataset |
| 3.5 | Test unitario con fixture de velas congelado |
| 3.6 | Golden test de backtest con hash reproducible |

**Puerta P3:** mismo dataset ⇒ mismo hash en 3 ejecuciones; `evaluate()` no toca red, disco ni reloj del sistema (test con monkeypatch que lanza si se invoca); los 8 guardarraíles de la sección 16 del spec tienen test.

## Fase 4 — Validación estadística

Protocolo pre-registrado **antes** de mirar resultados. Lock en `.lock.json`, congelado.

| Etapa | Regla | Rechazo |
|---|---|---|
| Desarrollo | Ventanas W1–W6 sobre el periodo de diseño | — |
| Determinismo | W1 dos veces ⇒ mismo resultado | G2 falla |
| Integridad | Dataset, rolls y series coherentes | G1/G3/G14 fallan |
| Muestra | ≥ 80 operaciones, ≥ 20 por dirección | G4 falla |
| Edge | PF ≥ 1.25 y expectativa ≥ +0.10 R | G5 falla |
| Riesgo | DD ≤ 2 % del capital y peor racha ≤ 8 | G6 falla |
| Consistencia | ≥ 4/6 bloques con PF > 1.0 | G7 falla |
| Costes | PF ≥ 1.10 con costes duplicados | G8 falla |
| Concentración | P&L > 0 sin las 5 mejores; top-5 ≤ 50 % | G9/G10 fallan |
| Significancia | IC bootstrap 80 % > 0 (10.000 remuestras, semilla fija) | G11 falla |
| Simetría | Cortos con muestra y PF mínimos | G12 falla |
| Datos ambiguos | ≤ 5 % de barras ambiguas | G13 falla |
| Holdout | Sellado; ≥ 18 ops, PF ≥ 1.00, DD ≤ 2.5 % | H1–H5 fallan |

**Puerta P4:** las 14 puertas duras en verde **y** el holdout ejecutado una sola vez. Muestra insuficiente ⇒ `INCONCLUSO`, no aprobación. Un `pass` no autoriza LIVE.

## Fase 5 — DRY-RUN

30 días de calendario mínimo con datos reales y fills simulados.

| Métrica de control | Umbral |
|---|---|
| Desviación de slippage vs backtest | ≤ 10 % |
| Desviación de PF vs backtest | ≤ 10 % |
| Señales perdidas por errores de feed | 0 no justificadas |
| Divergencia de estado (snapshot vs `kv`) | 0 |
| Uptime del motor en horario operativo | ≥ 99 % |

**Puerta P5:** las cinco métricas en rango y una revisión manual de todas las operaciones simuladas contra el gráfico. Cualquier desviación > 10 % devuelve a Fase 3, no a Fase 6.

## Fase 6 — LIVE mínimo

- 1 unidad por operación, independientemente de lo que diga el sizing.
- Límite de pérdida diaria a la mitad del configurado.
- Kill switch probado en dry-run antes de usarlo en real.
- Revisión semanal obligatoria; dos semanas con degradación ⇒ vuelta a Fase 5.

**Puerta P6:** reconciliación diaria posición broker vs `kv` con diferencia 0, y un cierre de sesión completo sin intervención manual.

## Fase 7 — Operación y mejora

- Detección de degradación: PF rodante de 20 operaciones por debajo de 1.0 durante 2 semanas ⇒ alerta y revisión.
- Versionado semántico de la estrategia; ningún cambio de parámetros en caliente.
- Cada cambio re-ejecuta Fase 4 completa. Sin excepciones.

## Qué significa "super bueno" — y qué no

Lo que este plan **sí** garantiza, medible:

| Propiedad | Cómo se mide |
|---|---|
| Determinismo | Mismo input ⇒ mismo hash de salida, 3 ejecuciones |
| Ausencia de lookahead | Test que prohíbe indexar barras posteriores a `md.clock` |
| Costes realistas | Reconciliación contra fills reales, ±1 tick |
| Robustez fuera de muestra | Holdout sellado + walk-forward + Monte Carlo |
| Rechazo de sobreajuste | Sensibilidad ±10 %/±20 % y costes ×2 |
| Control de riesgo | Límites duros con test de cada uno |

Lo que este plan **no** garantiza: que la estrategia gane dinero. Ningún plan puede. Un sistema técnicamente perfecto sobre una hipótesis sin edge pierde dinero de forma muy ordenada. La Fase 4 existe para que se descubra antes de arriesgar capital.

## Criterios de muerte del proyecto

Se detiene y se replantea cuando:

1. Tres hipótesis distintas fallan G5 o G9 en la misma ventana de desarrollo.
2. El holdout, ejecutado una vez, falla H3.
3. El dry-run desvía > 10 % respecto al backtest en dos periodos consecutivos y la causa no es un bug reproducible.
4. No se puede medir la reconciliación de costes (P2 no medible) y se pretende pasar a LIVE igualmente.

## Riesgos

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Sobreajuste por iterar sobre el mismo periodo | Alta | Alto | Holdout sellado, protocolo con lock, criterios de muerte |
| Datos con huecos o rolls mal resueltos | Media | Alto | Validador en P2 + hash de dataset en cada ejecución |
| Costes subestimados | Media | Alto | P2 con fills reales; G8 con costes ×2 |
| Acoplamiento accidental UI↔estrategia | Media | Medio | `test_no_hardcoded_instruments.py` en CI |
| Recuperación tras reinicio inconsistente | Baja | Alto | Test de Fase 1 con posición abierta + config corrupta |
| Deriva de parámetros durante dry-run | Media | Alto | Sin cambios en caliente; cada cambio re-valida |

---

# Parte B — Implementación de la Fase 1 (task-by-task)

12 tareas. Cada una deja el repositorio verde y commiteable. Orden por dependencia de contratos.

## Ruta de trabajo

`C:\Users\Administrator\Downloads\bot-base` (repositorio nuevo). La vía "copiar y limpiar" sustituye T1–T4 por la limpieza descrita en `CHECKLIST_ESQUELETO.md` §2–§4 y mantiene el resto idéntico.

---

### Task 1: Arranque mínimo y healthcheck

**Files:**
- Create: `pyproject.toml`, `requirements.txt`, `.gitignore`, `run.py`, `server/__init__.py`, `server/main.py`, `tests/conftest.py`
- Test: `tests/test_api_contract.py`

**Interfaces:**
- Consumes: nada.
- Produces: `run.py:main()`, `server.main:app` (`FastAPI`), `GET /api/health → {"status": "ok", "version": str}`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_health_returns_ok(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

- [ ] **Step 2: Ejecutarlo y verlo fallar**

Run: `pytest tests/test_api_contract.py::test_health_returns_ok -v`
Expected: FAIL — `ModuleNotFoundError: server.main`

- [ ] **Step 3: Implementar `server/main.py` con `create_app() -> FastAPI` y montar `/api/health`**

`app = create_app()` a nivel de módulo. `conftest.py` define el fixture `client` con `TestClient(app)`.

- [ ] **Step 4: Ejecutarlo y verlo pasar**

Run: `pytest tests/test_api_contract.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml requirements.txt .gitignore run.py server/__init__.py server/main.py tests/
git commit -m "feat: bootstrap fastapi app with health endpoint"
```

---

### Task 2: Contratos de estrategia y NullStrategy

**Files:**
- Create: `server/strategy/__init__.py`, `server/strategy/base.py`, `server/strategy/null_strategy.py`, `server/strategy/registry.py`
- Test: `tests/test_strategy_interface.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `base.py`: `Warmup(bars: dict[str, int], session_ready: bool)`, `MarketData(session, clock, primary, bars, params, context)`, `Signal(key, side, strength, reason, ts, valid_until, stop_price, target_price)`, `Phase(key, label, status, ts, detail)`, `Zone(id, kind, label, from_ts, to_ts, price_low, price_high, style, active)`, `Marker(id, ts, price, kind, side, label)`, `Metric(label, value, format, unit, tone, group)`, `StrategyOutput(state, state_label, phases, signal, rejection, metrics, zones, markers, notes)`, `BaseStrategy` (Protocol con `id`, `name`, `version`, `params_model`, `warmup_requirements()`, `evaluate(md)`).
  - `null_strategy.py`: `class NullStrategy` con `id="null"`, `version="0.0.0"`, `params_model=NullParams`, `state="disabled"`, `signal=None`.
  - `registry.py`: `resolve_strategy(strategy_id: str, params: dict) -> BaseStrategy`, `strategy_schema(strategy_id: str) -> dict`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_null_strategy_satisfies_protocol():
    s = NullStrategy()
    assert isinstance(s, BaseStrategy)
    assert s.warmup_requirements() == Warmup(bars={}, session_ready=False)

def test_null_strategy_emits_no_signal(md_fixture):
    out = NullStrategy().evaluate(md_fixture)
    assert out.signal is None
    assert out.state == "disabled"
    assert out.phases == []

def test_registry_rejects_unknown_id():
    with pytest.raises(KeyError):
        resolve_strategy("does-not-exist", {})

def test_registry_rejects_invalid_params():
    with pytest.raises(ValidationError):
        resolve_strategy("null", {"unexpected": 1})
```

- [ ] **Step 2: Ejecutarlo y verlo fallar**

Run: `pytest tests/test_strategy_interface.py -v`
Expected: FAIL — `ImportError: server.strategy.base`

- [ ] **Step 3: Implementar los cuatro archivos con las firmas exactas del bloque Interfaces**

`BaseStrategy` como `Protocol` con `@runtime_checkable`. `null_strategy.py` no importa nada de `server/` salvo `base`.

- [ ] **Step 4: Ejecutarlo y verlo pasar**

Run: `pytest tests/test_strategy_interface.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add server/strategy/ tests/test_strategy_interface.py
git commit -m "feat: add strategy protocol, null strategy and registry"
```

---

### Task 3: Modelos, Settings y persistencia atómica

**Files:**
- Create: `server/models.py`, `server/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: `Warmup` de Task 2 (solo para defaults de `warmup_bars`).
- Produces:
  - `models.py`: `Bar(t, o, h, l, c, v)`, `Tick(ts, bars: dict[str, Bar])`, `Position(symbol, side, units, entry_price, stop_price, target_price, opened_ts)`, `Order(id, symbol, side, units, kind, price, status)`, `TradeRecord(...)`.
  - `config.py`: `InstrumentsConfig`, `StrategyConfig`, `RiskConfig`, `ExecutionConfig`, `FeedConfig`, `LiveConfig`, `UIConfig`, `Settings`, `load_settings(path) -> Settings`, `save_settings(settings, path)`, `apply_settings(settings, patch) -> Settings`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_defaults_match_spec():
    s = Settings()
    assert s.risk.risk_per_trade_pct == 1.0
    assert s.risk.max_daily_loss_pct == 3.0
    assert s.risk.max_trades_per_day == 3
    assert s.risk.cooldown_minutes == 5
    assert s.execution.fill_model == "next_open"
    assert s.live.live_enabled is False

def test_corrupt_config_is_archived_and_defaults_restored(tmp_path):
    p = tmp_path / "config.json"
    p.write_text("{not json")
    s = load_settings(p)
    assert s.risk.risk_per_trade_pct == 1.0
    assert (tmp_path / "config.json.broken").exists()

def test_save_is_atomic(tmp_path):
    p = tmp_path / "config.json"
    save_settings(Settings(), p)
    assert json.loads(p.read_text())["risk"]["risk_per_trade_pct"] == 1.0
    assert not (tmp_path / "config.json.tmp").exists()

def test_apply_rejects_invalid_patch():
    with pytest.raises(ValidationError):
        apply_settings(Settings(), {"risk": {"risk_per_trade_pct": 150}})
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_config.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `models.py` y `config.py`**

Escritura atómica vía `tmp` + `os.replace`. `model_config = ConfigDict(extra="forbid")` en todos los grupos.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_config.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add server/models.py server/config.py tests/test_config.py
git commit -m "feat: add domain models and validated settings with atomic persistence"
```

---

### Task 4: Store SQLite WAL y migraciones v1

**Files:**
- Create: `server/db.py`, `server/migrations.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `Bar`, `TradeRecord` de Task 3.
- Produces:
  - `db.py`: `Store(db_path)` con `insert_trade`, `list_trades(limit, offset, filters)`, `insert_event`, `list_events(limit, level)`, `count_events()`, `append_equity`, `equity_curve`, `kv_get(key)`, `kv_set(key, value)`, `save_backtest`, `list_backtest_runs(cursor, limit)`, `schema_version()`, `close()`, `SCHEMA_VERSION`.
  - `migrations.py`: `apply_migrations(conn)`, `CURRENT_VERSION = 1`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_store_creates_v1_schema(store):
    tables = {r[0] for r in store.conn.execute("select name from sqlite_master where type='table'")}
    assert {"trades", "events", "equity", "kv", "backtests", "schema_migrations"} <= tables

def test_wal_enabled(store):
    assert store.conn.execute("pragma journal_mode").fetchone()[0].lower() == "wal"

def test_events_capped_at_5000(store):
    for i in range(5010):
        store.insert_event(level="info", category="t", message=str(i))
    assert store.count_events() == 5000

def test_migrations_are_idempotent(store):
    apply_migrations(store.conn)
    apply_migrations(store.conn)
    assert store.schema_version() == 1
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `db.py` y `migrations.py`**

`PRAGMA journal_mode=WAL`, `synchronous=NORMAL`. Retención de `events` con `DELETE ... WHERE id NOT IN (SELECT id ORDER BY id DESC LIMIT 5000)` dentro de la misma transacción.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_store.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add server/db.py server/migrations.py tests/test_store.py
git commit -m "feat: add sqlite wal store with versioned migrations"
```

---

### Task 5: SnapshotBuilder (contrato v1)

**Files:**
- Create: `server/schemas.py`, `server/snapshot.py`
- Test: `tests/test_snapshot_contract.py`, `tests/test_dynamic_render_contract.py`

**Interfaces:**
- Consumes: `Settings` (T3), `Store` (T4), `StrategyOutput` (T2).
- Produces: `SnapshotBuilder(settings, store).build(state: EngineState) -> dict`, y los modelos Pydantic `Snapshot`, `SnapshotData`, `StrategyBlock`, `PhaseModel`, `KvEntryModel`, `ZoneModel`, `MarkerModel`, `SeriesModel`, `QuoteModel`, `InstrumentModel`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_snapshot_validates_against_schema(builder_with_null):
    snap = builder_with_null.build(engine_state_stopped)
    Snapshot.model_validate(snap)
    assert snap["v"] == 1
    assert snap["data"]["strategy"]["signal"] is None
    assert snap["data"]["strategy"]["phases"] == []

def test_quotes_follow_configured_instruments(builder):
    builder.settings.instruments.items = [mk_instrument("AAA"), mk_instrument("BBB")]
    snap = builder.build(engine_state_stopped)
    assert set(snap["data"]["quotes"]) == {"AAA", "BBB"}
    assert {i["symbol"] for i in snap["data"]["instruments"]} == {"AAA", "BBB"}

def test_removed_instrument_leaves_no_orphan_quote(builder):
    builder.settings.instruments.items = [mk_instrument("AAA")]
    snap = builder.build(engine_state_stopped)
    assert set(snap["data"]["quotes"]) == {"AAA"}

def test_unknown_zone_kind_is_dropped_and_logged(builder, caplog):
    snap = builder.build(state_with_zone_kind("hexagon"))
    assert all(z["kind"] != "hexagon" for z in snap["data"]["chart"]["zones"])
    assert "unsupported zone kind" in caplog.text

def test_phases_arbitrary_length(builder):
    for n in (0, 3, 12):
        snap = builder.build(state_with_phases(n))
        assert len(snap["data"]["strategy"]["phases"]) == n
        Snapshot.model_validate(snap)
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_snapshot_contract.py tests/test_dynamic_render_contract.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `schemas.py` y `snapshot.py`**

`schemas.py` usa `Literal` para todos los enums del bloque Global Constraints. `snapshot.py` itera `settings.instruments.items` para `quotes` e `instruments`; descarta y registra `kind` desconocidos.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_snapshot_contract.py tests/test_dynamic_render_contract.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add server/schemas.py server/snapshot.py tests/test_snapshot_contract.py tests/test_dynamic_render_contract.py
git commit -m "feat: add agnostic snapshot contract v1"
```

---

### Task 6: RiskManager

**Files:**
- Create: `server/risk.py`
- Test: `tests/test_risk.py`

**Interfaces:**
- Consumes: `Signal` (T2), `RiskConfig`/`InstrumentsConfig` (T3), `Position` (T3).
- Produces: `RiskManager(config).evaluate(signal: Signal, portfolio: PortfolioState) -> RiskDecision`, `RiskDecision(approved: bool, code: str, message: str, units: int, risk_per_unit: float)`.

- [ ] **Step 1: Escribir el test que falla**

```python
@pytest.mark.parametrize("setup,expected_code", [
    ("emergency", "emergency_active"),
    ("open_position", "position_open"),
    ("pending_order", "order_pending"),
    ("max_trades", "max_trades_reached"),
    ("outside_window", "outside_window"),
    ("daily_loss", "daily_loss_limit"),
    ("cooldown", "cooldown_active"),
])
def test_rejection_order_and_codes(rm_factory, setup, expected_code):
    d = rm_factory(setup).evaluate(signal_long_2ticks, portfolio_for(setup))
    assert d.approved is False and d.code == expected_code

def test_sizing_uses_instrument_spec(rm_factory):
    d = rm_factory("clean").evaluate(signal_long_2ticks, portfolio_equity_25000)
    # 25000 * 1% = 250 presupuesto; riesgo/unidad = 2 ticks * 0.5 = 1.0
    assert d.units == 5          # capado por max_units_per_trade
    assert d.risk_per_unit == 1.0

def test_size_below_one_is_rejected(rm_factory):
    d = rm_factory("clean", max_stop_ticks=200).evaluate(signal_with_huge_stop, portfolio_equity_50)
    assert d.approved is False and d.code == "size_below_minimum"

def test_signal_without_stop_is_rejected():
    with pytest.raises(ValidationError):
        Signal(key="k", side="long", reason="r", ts=now(), stop_price=None)
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_risk.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `risk.py` en el orden exacto del spec (sección 10)**

`sizing = floor(equity * pct / 100 / risk_per_unit)`, capado por `max_units_per_trade`. Ventana semiabierta `[start, end)`.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_risk.py -v`
Expected: 10 PASS

- [ ] **Step 5: Commit**

```bash
git add server/risk.py tests/test_risk.py
git commit -m "feat: add risk manager with ordered checks and instrument-based sizing"
```

---

### Task 7: ExecutionEngine

**Files:**
- Create: `server/execution.py`
- Test: `tests/test_execution.py`

**Interfaces:**
- Consumes: `RiskDecision` (T6), `Bar`/`Position`/`Order`/`TradeRecord` (T3), `ExecutionConfig` (T3).
- Produces: `ExecutionEngine(config).arm(decision, signal)`, `.on_bar(bars: dict[str, Bar]) -> list[ExecutionEvent]`, `.close(reason)`, `.cancel_all()`, `.position`, `.orders`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_fill_at_next_open_with_bounded_slippage(engine):
    engine.arm(decision_long, signal_long)
    engine.on_bar({"AAA": bar(o=100.0, h=101.0, l=99.8)})
    assert engine.position.entry_price == pytest.approx(100.0 + 1 * 0.25)  # slippage 1 tick

def test_stop_and_target_placed_from_signal(engine):
    engine.arm(decision_long, signal_long)
    engine.on_bar({"AAA": bar(o=100.0)})
    assert engine.position.stop_price == signal_long.stop_price
    assert engine.position.target_price == signal_long.target_price

def test_ambiguous_bar_resolves_stop_first(engine):
    engine.arm(decision_long, signal_long)
    events = engine.on_bar({"AAA": bar(o=100.0, h=102.5, l=99.5)})
    assert events[-1].exit_reason == "stop"
    assert events[-1].diagnostics["ambiguous_bar"] is True

def test_commission_applied_per_side(engine):
    engine.arm(decision_long, signal_long)
    engine.on_bar({"AAA": bar(o=100.0)})
    trade = engine.close("manual")
    assert trade.fees == pytest.approx(2 * 0.62 * decision_long.units)
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_execution.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `execution.py`**

Convención conservadora ante ambigüedad: SL primero, con `diagnostics["ambiguous_bar"] = True`.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_execution.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add server/execution.py tests/test_execution.py
git commit -m "feat: add execution engine with brackets and ambiguous bar diagnostics"
```

---

### Task 8: TradingEngine

**Files:**
- Create: `server/engine.py`, `server/timeutil.py`
- Test: `tests/test_engine.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `TradingEngine(settings, store, feed, strategy)`, `EngineState(status, mode, session, strategy_output, position, orders, risk, day_stats)`, métodos `start()`, `pause()`, `stop()`, `emergency_on()`, `emergency_off()`, `_process(tick)`, `snapshot() -> dict`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_engine_starts_stopped(engine):
    assert engine.state.status == "stopped"
    assert engine.snapshot()["data"]["strategy"]["signal"] is None

def test_session_change_resets_daily_counters(engine):
    engine.start()
    engine._process(tick_on_day(1))
    engine._process(tick_on_day(2))
    assert engine.state.day_stats.trades == 0
    assert any(e.category == "session" for e in engine.store.list_events(10))

def test_strategy_not_evaluated_when_paused(engine, spy_strategy):
    engine.start(); engine.pause()
    engine._process(tick_on_day(1))
    assert spy_strategy.calls == 0

def test_emergency_persists_across_restart(store, settings):
    e1 = TradingEngine(settings, store, feed_stub, NullStrategy()); e1.emergency_on()
    e2 = TradingEngine(settings, store, feed_stub, NullStrategy())
    assert e2.snapshot()["data"]["risk"]["blocked"] is True

def test_restart_restores_position_and_bracket(store, settings):
    seed_open_position(store, entry=100.5, stop=99.75, target=102.25)
    e = TradingEngine(settings, store, feed_stub, NullStrategy())
    assert e.state.position.stop_price == 99.75
    assert e.state.position.target_price == 102.25
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_engine.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `timeutil.py` (sesión, DST) y `engine.py` con el ciclo de 7 pasos del spec (sección 5)**

El estado de emergencia se persiste en `kv["emergency"]`; la posición en `kv["position"]`.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_engine.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add server/engine.py server/timeutil.py tests/test_engine.py
git commit -m "feat: add trading engine with session handling and crash recovery"
```

---

### Task 9: API REST y WebSocket

**Files:**
- Create: `server/api.py`
- Modify: `server/main.py` (montar router y lifespan del motor)
- Test: `tests/test_api_contract.py`

**Interfaces:**
- Consumes: `TradingEngine` (T8), `Settings` (T3), `Store` (T4), `Snapshot` (T5).
- Produces: router `/api` con los grupos de la sección 13 del spec, `WS /api/ws` con `{"type": "snapshot"|"event", "data": {...}}`, `GET /api/strategy/schema`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_openapi_exposes_all_groups(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ["/api/health", "/api/status", "/api/config", "/api/bot/{action}",
              "/api/position/close", "/api/orders/cancel", "/api/emergency",
              "/api/trades", "/api/events", "/api/stats", "/api/chart/history",
              "/api/strategy/schema"]:
        assert p in paths

def test_config_put_rejects_invalid(client):
    assert client.put("/api/config", json={"risk": {"risk_per_trade_pct": 150}}).status_code == 422

def test_ws_sends_snapshot_on_connect(client):
    with client.websocket_connect("/api/ws") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "snapshot"
        Snapshot.model_validate(msg["data"])

def test_ws_snapshot_has_no_strategy_specific_keys(client):
    with client.websocket_connect("/api/ws") as ws:
        data = ws.receive_json()["data"]
        assert set(data["strategy"]) == {"id", "name", "version", "state", "state_label",
                                         "phases", "metrics", "signal", "rejection"}
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_api_contract.py -v`
Expected: FAIL — 404 en rutas

- [ ] **Step 3: Implementar `api.py` con `EventHub` (una `asyncio.Queue` por cliente) y el lifespan que arranca/detiene el motor**

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_api_contract.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
git add server/api.py server/main.py tests/test_api_contract.py
git commit -m "feat: add rest and websocket api with snapshot contract"
```

---

### Task 10: Backtest determinista y guardián de agnosticismo

**Files:**
- Create: `server/backtest.py`, `tests/fixtures/dataset_min.csv`, `tests/test_backtest_golden.py`, `tests/test_no_hardcoded_instruments.py`
- Test: los dos anteriores

**Interfaces:**
- Consumes: `TradingEngine` (T8), `CSVFeed` mínimo (T11, adelantado como stub en `tests/conftest.py`).
- Produces: `run_backtest(settings, dataset, strategy) -> BacktestResult`, con `.metrics: dict`, `.equity: list[float]`, `.trades: list[TradeRecord]`, `.dataset_id: str`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_backtest_is_deterministic():
    h = {sha256_of(run_backtest(settings_fixture, dataset_fixture, NullStrategy()))
         for _ in range(3)}
    assert len(h) == 1

def test_backtest_with_null_strategy_produces_no_trades():
    r = run_backtest(settings_fixture, dataset_fixture, NullStrategy())
    assert r.trades == []
    assert r.metrics["trades"] == 0

def test_no_hardcoded_instruments_in_source():
    banned = re.compile(r"\b(MNQ|NQ|ES|ORB|SMT)\b")
    offenders = [p for p in SOURCE_PATHS if banned.search(p.read_text())]
    assert offenders == []
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_backtest_golden.py tests/test_no_hardcoded_instruments.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar `backtest.py` reutilizando `TradingEngine` en modo `backtest` (mismo riesgo y ejecución, sin `asyncio`)**

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_backtest_golden.py tests/test_no_hardcoded_instruments.py -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
git add server/backtest.py tests/fixtures/ tests/test_backtest_golden.py tests/test_no_hardcoded_instruments.py
git commit -m "feat: add deterministic backtest and agnosticism guard"
```

---

### Task 11: Feed multi-serie y datos sintéticos

**Files:**
- Create: `server/market/__init__.py`, `server/market/feed.py`, `server/market/csv_data.py`, `server/market/sessions.py`, `server/market/instruments.py`, `server/market/synthetic.py`
- Test: `tests/test_feed.py`, `tests/test_csv_data.py`

**Interfaces:**
- Consumes: `Bar`/`Tick` (T3), `FeedConfig`/`InstrumentsConfig` (T3).
- Produces: `MarketFeed.iter_ticks() -> Iterator[Tick]`, `SimulatedFeed(seed_date, instruments)`, `CSVFeed(path, instruments)`, `LiveFeed` (lanza `NotImplementedError`), `validate_dataset(path, instruments) -> ValidationReport`, `next_active(symbol, date)`.

- [ ] **Step 1: Escribir el test que falla**

```python
def test_synthetic_feed_is_deterministic_for_same_date():
    a = list(islice(SimulatedFeed(seed_date="2026-01-15", instruments=three).iter_ticks(), 50))
    b = list(islice(SimulatedFeed(seed_date="2026-01-15", instruments=three).iter_ticks(), 50))
    assert a == b

def test_feed_emits_tick_keyed_by_configured_symbols():
    tick = next(SimulatedFeed(seed_date="2026-01-15", instruments=["AAA", "BBB"]).iter_ticks())
    assert set(tick.bars) == {"AAA", "BBB"}

def test_csv_validation_flags_misaligned_timestamps(tmp_path):
    rep = validate_dataset(write_csv(tmp_path, misaligned=True), instruments=["AAA", "BBB"])
    assert rep.ok is False
    assert "misaligned" in rep.errors[0].code

def test_live_feed_without_adapter_raises():
    with pytest.raises(NotImplementedError):
        next(LiveFeed().iter_ticks())
```

- [ ] **Step 2: Verlo fallar**

Run: `pytest tests/test_feed.py tests/test_csv_data.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implementar los seis módulos**

`synthetic.py` usa RNG sembrado por fecha. `LiveFeed` sin adaptador lanza siempre.

- [ ] **Step 4: Verlo pasar**

Run: `pytest tests/test_feed.py tests/test_csv_data.py -v`
Expected: 4 PASS

- [ ] **Step 5: Commit**

```bash
git add server/market/ tests/test_feed.py tests/test_csv_data.py
git commit -m "feat: add multi-symbol feed, dataset validation and synthetic generator"
```

---

### Task 12: Frontend — 7 vistas y render dinámico

**Files:**
- Create: `frontend/package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/types.ts`, `src/api.ts`, `src/store.tsx`, `src/utils.ts`, `src/components/{Sidebar,TopBar,KvPanel,PhaseTimeline,ZoneLayer,MarkerLayer,SymbolsTable,DynamicTable}.tsx`, `src/pages/{Dashboard,Chart,Operations,History,Stats,Config,Console}.tsx`
- Test: `frontend/src/__tests__/render-contract.test.tsx`

**Interfaces:**
- Consumes: contrato v1 del snapshot (T5, T9).
- Produces: componentes con estas props exactas:
  - `KvPanel({ entries: Record<string, KvEntry> })`
  - `PhaseTimeline({ phases: Phase[] })`
  - `ZoneLayer({ zones: Zone[] })`, `MarkerLayer({ markers: Marker[] })`
  - `SymbolsTable({ instruments: Instrument[], quotes: Record<string, Quote> })`
  - `DynamicTable<T>({ rows, columns, emptyLabel })`

- [ ] **Step 1: Escribir el test que falla**

```tsx
it('renders PhaseTimeline with 0, 3 and 12 phases', () => {
  for (const n of [0, 3, 12]) {
    const { container } = render(<PhaseTimeline phases={mkPhases(n)} />);
    expect(container.querySelectorAll('[data-phase]').length).toBe(n);
  }
});

it('renders KvPanel without knowing entry names', () => {
  render(<KvPanel entries={{ any_key: { label: 'X', value: 1, format: 'number', tone: 'neutral' } }} />);
  expect(screen.getByText('X')).toBeInTheDocument();
});

it('skips unsupported zone kind without crashing', () => {
  const { container } = render(<ZoneLayer zones={[{ ...zone, kind: 'hexagon' as never }]} />);
  expect(container.querySelectorAll('[data-zone]').length).toBe(0);
});

it('renders SymbolsTable from instruments array', () => {
  render(<SymbolsTable instruments={[mkInstrument('AAA')]} quotes={{ AAA: mkQuote(100) }} />);
  expect(screen.getByText('AAA')).toBeInTheDocument();
});
```

- [ ] **Step 2: Verlo fallar**

Run: `npm run test -- --run`
Expected: FAIL — módulos no encontrados

- [ ] **Step 3: Implementar `types.ts` como espejo exacto de `schemas.py` y los componentes genéricos**

`types.ts` declara los `Literal` del bloque Global Constraints. Ningún componente recibe un nombre de activo como prop.

- [ ] **Step 4: Verlo pasar**

Run: `npm run test -- --run`
Expected: 4 PASS

- [ ] **Step 5: Verificar el build**

Run: `npm run build`
Expected: `tsc --noEmit` sin errores y bundle generado en `frontend/dist/`

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: add frontend shell with dynamic snapshot rendering"
```

---

## Verificación de la Fase 1

```bash
python -m pytest -q                    # todo verde
cd frontend ; npm run build ; cd ..    # build limpio
python run.py                          # dashboard en http://127.0.0.1:8765
python -m pytest -q tests/test_no_hardcoded_instruments.py   # 0 ofensores
```

Manual, en el navegador: las 7 vistas cargan; el panel de Estado de Estrategia aparece vacío con `NullStrategy`; el gráfico no dibuja zonas; añadir un símbolo en Configuración lo hace aparecer en la tabla de cotizaciones sin tocar código.

---

## Handoff

Tras `Task 12`, el repositorio es el esqueleto completo de la Fase 1. Lo siguiente es la Fase 0 (ADR) si no está hecha, y después la Fase 2 (datos y costes). La Fase 3 no empieza hasta que P2 esté verde: construir la estrategia sobre costes no reconciliados produce un backtest que miente.

Método de ejecución recomendado: **subagent-driven**. Las 12 tareas comparten contratos (`schemas.py` → `snapshot.py` → `types.ts`), así que un error de interfaz se propaga a tres capas y el coste de un fallo silencioso en riesgo o ejecución es capital real. Un revisor fresco por tarea sale más barato que depurar esa propagación después.
