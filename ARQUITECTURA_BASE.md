# Arquitectura base (agnóstica de estrategia)

**Plantilla:** terminal local de trading algorítmico, reutilizable para cualquier estrategia.
**Estado:** esqueleto. La lógica de estrategia no existe todavía; su único punto de entrada está reservado en el bloque final `# Aquí va la estrategia`.

**Invariante central:** todo lo descrito aquí funciona igual con cualquier estrategia, cualquier conjunto de instrumentos y cualquier temporalidad, porque ni el motor, ni el snapshot, ni React conocen nombres de activos, fases concretas ni reglas de entrada.

---

## 1. Alcance

| Dentro del alcance | Fuera del alcance |
|---|---|
| Motor determinista, riesgo, ejecución paper, persistencia, backtesting, API, dashboard | Reglas de entrada/salida, indicadores, filtros, gestión de señal |
| Contratos de datos (config, snapshot, estrategia) | Rentabilidad esperada, calibración de parámetros |
| Reglas de seguridad operativa y de promoción de modo | Adaptadores reales de broker/feed |

La plantilla **no** valida que una estrategia gane dinero. Verifica que el sistema que la ejecuta sea determinista, auditable y que ningún componente de infraestructura dependa de la estrategia concreta.

---

## 2. Principios de diseño (invariantes)

1. **Motor separado de la interfaz.** El motor no importa React; cerrar el navegador no detiene la operativa.
2. **Backend como única fuente de verdad.** La UI no calcula señales, P&L real, riesgo ni fases. Solo presenta y agrega velas para las temporalidades del gráfico.
3. **Estrategia como plugin puro.** `BaseStrategy.evaluate(market_data)` es una función determinista de velas cerradas más parámetros declarados. Sin estado oculto, sin I/O, sin red, sin acceso a la base.
4. **Contrato de snapshot genérico.** React renderiza por `kind` y por hints de formato enviados por el backend; nunca por nombre de símbolo, nombre de estrategia ni fase fija.
5. **Nada de lógica específica en la infraestructura.** El motor no conoce conceptos de estrategia (rangos, niveles, patrones, confirmaciones): solo conoce señales, fases, zonas, marcadores, órdenes y riesgo.
6. **Instrumentos como datos.** Todo símbolo, tick, valor por punto, moneda y plantilla de sesión vive en configuración; el código itera sobre la lista configurada.
7. **Determinismo total.** Mismo dataset + misma configuración + misma versión de estrategia ⇒ mismos resultados en live, paper y backtest.
8. **Interfaces estrechas y sustituibles.** `Store`, `MarketFeed`, `ExecutionEngine` y `BaseStrategy` se pueden reemplazar sin tocar el resto.
9. **LIVE bloqueado por defecto.** Requiere configuración, confirmación explícita y adaptador implementado; si falta cualquiera de las tres, el motor se niega a arrancar en LIVE.
10. **Degradación explícita.** Un `kind` de snapshot desconocido se ignora y se registra; nunca rompe la vista.

---

## 3. Componentes

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              NAVEGADOR (local)                               │
│  React 18 + TypeScript + Lightweight Charts                                  │
│  Inicio · Gráfico · Operaciones · Historial · Estadísticas · Config · Consola │
│  Render declarativo: KvPanel · PhaseTimeline · ZoneLayer · MarkerLayer       │
└───────────────▲───────────────────────────────┬──────────────────────────────┘
                │ WebSocket /api/ws             │ REST /api/*
                │ snapshots + eventos           │ comandos y consultas
┌───────────────┴───────────────────────────────▼──────────────────────────────┐
│                           FastAPI (server/main.py)                           │
│  API + estáticos de frontend/dist + lifespan del motor                       │
└───────────────┬──────────────────────────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────────────────────┐
│                        TradingEngine (server/engine.py)                      │
│  estado · snapshot · control (start/pause/stop) · emergencia · config        │
│                                                                              │
│  ┌─────────────┐  ┌───────────────┐  ┌─────────────┐  ┌───────────────────┐  │
│  │ MarketFeed  │─►│ BaseStrategy  │─►│ RiskManager │─►│ ExecutionEngine   │  │
│  │ replay/CSV  │  │ evaluate()    │  │ sizing/lím. │  │ fills/SL/TP       │  │
│  │ N símbolos  │  │ plugin puro   │  │             │  │                   │  │
│  └─────────────┘  └───────────────┘  └─────────────┘  └─────────┬─────────┘  │
│         │                    │                                   │           │
│  ┌──────▼────────────────────▼───────────────────────────────────▼────────┐  │
│  │ EventHub (colas por cliente) · SnapshotBuilder (contrato v1)           │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────────────────────┐  │
│  │ Store SQLite (WAL): trades · events · equity · kv · backtests          │  │
│  └────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Estructura de módulos

```text
run.py                         arranque de API + motor + dashboard
server/
  main.py                      FastAPI, lifespan, estáticos
  api.py                       endpoints REST y WebSocket
  engine.py                    TradingEngine: orquestación, estado, control
  snapshot.py                  SnapshotBuilder: contrato v1 agnóstico
  config.py                    Settings + validación Pydantic + persistencia atómica
  models.py                    Bar, Tick, Signal, Position, Order, TradeRecord
  risk.py                      RiskManager y RiskDecision
  execution.py                 ExecutionEngine: fills, brackets, SL/TP
  db.py                        Store SQLite
  migrations.py                migraciones y esquema versionado
  stats.py                     compute_stats y métricas
  backtest.py                  motor de backtesting, datasets y presets
  confirmatory.py              hashes, preflight y sello del holdout
  experiments.py               identidad de experimentos y ledger JSONL
  schemas.py                   contratos Pydantic del snapshot y del backtest
  diagnostics.py               diagnóstico de solo lectura de SQLite
  reset.py                     reinicio operativo con archivo de backups
  timeutil.py                  utilidades de zona horaria y sesión
  funnel.py                    registro y resumen del embudo de evaluación
  strategy/                    ← ÚNICO punto donde vive la lógica de estrategia
    base.py                    BaseStrategy, MarketData, StrategyOutput, Signal,
                               Phase, Zone, Marker, Metric
    registry.py                resolve_strategy(id) + validación de params
    null_strategy.py           NullStrategy: no emite señal (placeholder del esqueleto)
  market/
    feed.py                    MarketFeed, SimulatedFeed, CSVFeed, LiveFeed
    csv_data.py                carga, alineación y validación multi-serie
    sessions.py                calendario, feriados y cierres anticipados
    instruments.py             especificaciones, vencimientos y rolls
    synthetic.py               generador sintético determinista
    providers/                 descarga de datos históricos (adaptadores)
frontend/src/
  App.tsx                      rutas/páginas
  types.ts                     tipos del contrato de snapshot (espejo de schemas.py)
  api.ts                       cliente REST + WebSocket
  store.tsx                    estado y suscripción
  components/
    Sidebar.tsx  TopBar.tsx
    KvPanel.tsx                panel clave-valor genérico (Estado de Estrategia)
    PhaseTimeline.tsx          fases dinámicas enviadas por el backend
    ZoneLayer.tsx              zonas del gráfico (bandas, líneas, cajas)
    MarkerLayer.tsx            marcadores del gráfico
    SymbolsTable.tsx           tabla de instrumentos configurados
    DynamicTable.tsx           tablas de operaciones/órdenes
  pages/                       siete pantallas
frontend/dist/                 build servido por FastAPI
research/                      diseños de validación
tests/                         pytest
docs/                          arquitectura, protocolo, proveedores, validación
profiles/                      perfiles aislados (backtest, dryrun)
reports/backtest/              ejecuciones y auditorías
data/                          configuración y SQLite locales
backups/                       copias operativas
```

**Regla de dependencias:** `strategy/*` no importa `db`, `engine`, `api` ni `execution`.
Solo consume `models` y utilidades puras (`timeutil`). El motor importa `strategy`, nunca al revés.

---

## 5. Flujo de un ciclo

1. `MarketFeed.next_tick()` entrega un `Tick` con las velas alineadas por timestamp de **todos** los instrumentos habilitados (`{symbol: Bar}`), sin nombres fijos.
2. `engine._process` detecta cambio de sesión según la plantilla del instrumento primario, reinicia el estado diario y registra un evento.
3. `ExecutionEngine.on_bar(bars)` llena la orden pendiente según el modelo de fill configurado y comprueba SL/TP de la posición abierta.
4. Si el motor está `running`, `strategy.evaluate(market_data)` recalcula el estado con **velas cerradas** y devuelve `StrategyOutput` (estado, fases, señal, rechazo, métricas, zonas, marcadores).
5. `RiskManager.evaluate(output, portfolio)` autoriza o rechaza la señal, con motivo explícito, y dimensiona la posición.
6. La orden se arma y se ejecuta en la vela siguiente; al cerrar se persiste el trade.
7. `SnapshotBuilder` compone el snapshot v1, se guarda el estado en `kv`, se emite el evento y se difunde por WebSocket.

La reconstrucción determinista de la estrategia (paso 4) es lo que permite que el backtest use exactamente las mismas reglas que el modo live: no hay estado oculto que replicar.

---

## 6. Contrato de estrategia (resumen)

Detalle completo, guardarraíles y checklist de integración en la sección 16.

```python
class BaseStrategy(Protocol):
    id: str
    name: str
    version: str
    params_model: type[BaseModel]        # esquema Pydantic de los parámetros

    def warmup_requirements(self) -> Warmup: ...
    def evaluate(self, md: MarketData) -> StrategyOutput: ...
```

- `MarketData`: sesión, reloj, instrumento primario, `bars: dict[symbol, Sequence[Bar]]` (solo velas cerradas), `params` validados y `context` opcional.
- `StrategyOutput`: `state` (string libre), `phases[]`, `signal | None`, `rejection | None`, `metrics{}`, `zones[]`, `markers[]`, `notes[]`.
- El motor **no interpreta** el contenido semántico: solo consume `signal` (para riesgo/ejecución) y reenvía el resto al snapshot.

---

## 7. Contrato del snapshot (v1)

El WebSocket envía `{type: "snapshot", data: {...}}` en cada vela y `{type: "event", data: {...}}` al registrar un evento.

### 7.1 Reglas

| Regla | Consecuencia |
|---|---|
| Todo mapa de instrumentos usa `symbol` como clave | Añadir o quitar activos es un cambio de configuración, no de código |
| `quotes` se genera iterando `settings.instruments` | La UI no conoce ningún ticker |
| `strategy.phases` es una lista de longitud variable | 0, 3 o 12 fases: la UI las pinta igual |
| `strategy.metrics` es un mapa clave-valor con hints de formato | El panel "Estado de Estrategia" no tiene campos fijos |
| Zonas y marcadores llegan con `kind` y `style` | La capa visual no interpreta semántica de estrategia |
| Campo `v` en la raíz | Cambios aditivos compatibles; campo desconocido se ignora |
| `null` explícito cuando no aplica | `signal`, `rejection`, `position` pueden ser `null` |

### 7.2 Estructura

```json
{
  "type": "snapshot",
  "v": 1,
  "ts": "2026-01-15T14:31:00Z",
  "data": {
    "status": "running",
    "mode": "paper",
    "session": {
      "id": "2026-01-15:PRIMARY",
      "label": "RTH",
      "is_open": true,
      "open_ts": "2026-01-15T14:30:00Z",
      "close_ts": "2026-01-15T21:00:00Z",
      "phase": "open"
    },
    "data": {
      "provider": "csv",
      "quality": "ok",
      "last_bar_ts": "2026-01-15T14:30:00Z",
      "staleness_ms": 1200,
      "bars_available": 412
    },
    "instruments": [
      {
        "symbol": "PRIMARY",
        "role": "primary",
        "enabled": true,
        "tick_size": 0.25,
        "tick_value": 0.5,
        "point_value": 2.0,
        "currency": "USD",
        "decimals": 2
      },
      {
        "symbol": "CTX_A",
        "role": "context",
        "enabled": true,
        "tick_size": 0.25,
        "tick_value": 5.0,
        "point_value": 50.0,
        "currency": "USD",
        "decimals": 2
      }
    ],
    "quotes": {
      "PRIMARY": {
        "last": 100.25, "bid": 100.25, "ask": 100.5,
        "change": 0.5, "change_pct": 0.5, "ts": "2026-01-15T14:30:59Z"
      },
      "CTX_A": {
        "last": 4210.75, "bid": 4210.5, "ask": 4211.0,
        "change": -3.25, "change_pct": -0.077, "ts": "2026-01-15T14:30:59Z"
      }
    },
    "chart": {
      "primary": "PRIMARY",
      "timeframe": "1m",
      "timeframes": ["1m", "5m", "15m", "30m"],
      "candles": [
        { "t": "2026-01-15T14:30:00Z", "o": 99.75, "h": 100.5, "l": 99.5, "c": 100.25, "v": 1832 }
      ],
      "series": [
        {
          "symbol": "CTX_A",
          "label": "CTX_A",
          "mode": "normalized",
          "axis": "overlay",
          "visible": true,
          "values": [{ "t": "2026-01-15T14:30:00Z", "v": 0.12 }]
        }
      ],
      "zones": [
        {
          "id": "zone-1",
          "kind": "band",
          "label": "Zona",
          "from_ts": "2026-01-15T14:30:00Z",
          "to_ts": null,
          "price_low": 99.5,
          "price_high": 101.0,
          "style": { "color": "#4c8dff", "opacity": 0.14, "line": "none" },
          "active": true,
          "source": "strategy",
          "meta": {}
        }
      ],
      "markers": [
        {
          "id": "mk-1",
          "ts": "2026-01-15T15:04:00Z",
          "price": 100.75,
          "kind": "entry",
          "side": "long",
          "label": "Entrada",
          "source": "strategy",
          "meta": {}
        }
      ]
    },
    "strategy": {
      "id": "template-default",
      "name": "Estrategia pendiente",
      "version": "0.0.0",
      "state": "warmup",
      "state_label": "Calentando",
      "phases": [
        { "key": "session_ready", "label": "Sesión lista", "status": "done", "ts": "2026-01-15T14:30:00Z", "detail": null },
        { "key": "setup", "label": "Setup", "status": "active", "ts": "2026-01-15T14:47:00Z", "detail": "3 de 5 condiciones" },
        { "key": "trigger", "label": "Disparo", "status": "pending", "ts": null, "detail": null }
      ],
      "metrics": {
        "atr_14":  { "label": "ATR(14)", "value": 12.5, "format": "price", "unit": "pts", "tone": "neutral" },
        "bias":    { "label": "Sesgo",   "value": "neutral", "format": "text", "tone": "warn" },
        "score":   { "label": "Score",   "value": 0.42, "format": "ratio", "tone": "neutral" }
      },
      "signal": {
        "key": "2026-01-15:long:15:04",
        "side": "long",
        "strength": 0.7,
        "reason": "texto libre del plugin",
        "ts": "2026-01-15T15:03:00Z",
        "valid_until": null,
        "stop_price": 99.75,
        "target_price": 102.25
      },
      "rejection": null
    },
    "position": {
      "symbol": "PRIMARY", "side": "long", "units": 2, "entry_price": 100.5,
      "stop_price": 99.75, "target_price": 102.25, "opened_ts": "2026-01-15T15:04:00Z",
      "unrealized": 41.0, "r_open": 0.55
    },
    "orders": [],
    "risk": {
      "equity": 25000.0,
      "open_risk": 150.0,
      "daily_pnl": 0.0,
      "daily_trades": 0,
      "blocked": false,
      "block_reason": null,
      "limits": {
        "risk_per_trade_pct": 1.0,
        "max_daily_loss_pct": 3.0,
        "max_trades_per_day": 3
      }
    },
    "stats": {},
    "day_stats": {},
    "settings": {},
    "ui": {
      "panels": ["strategy_state", "quotes", "position"],
      "theme": "dark"
    }
  }
}
```

### 7.3 Tipos del contrato

**`strategy.phases[]`**

| Campo | Tipo | Notas |
|---|---|---|
| `key` | string | Identificador estable para el plugin y para tests |
| `label` | string | Texto mostrado; traducible, sin lógica en el cliente |
| `status` | `pending \| active \| done \| failed \| skipped` | `PhaseTimeline` solo conoce estos cinco |
| `ts` | ISO-8601 \| null | Marca temporal del cambio de estado |
| `detail` | string \| null | Texto libre (contadores, motivo) |

**`strategy.metrics` (`KvEntry`)**

| Campo | Tipo | Notas |
|---|---|---|
| `label` | string | Etiqueta mostrada |
| `value` | number \| string \| boolean \| null | Valor |
| `format` | `number \| price \| pct \| ratio \| text \| duration \| boolean` | Hint de renderizado |
| `unit` | string \| null | Sufijo |
| `tone` | `neutral \| good \| bad \| warn` | Color semántico |
| `group` | string \| null | Agrupación opcional dentro del panel |

**`chart.zones[]`**

| Campo | Tipo | Notas |
|---|---|---|
| `id` | string | Único dentro del snapshot |
| `kind` | `band \| line \| box \| region` | Forma de dibujo |
| `label` | string \| null | Etiqueta opcional |
| `from_ts` / `to_ts` | ISO-8601 \| null | `to_ts: null` = extender hasta el borde derecho |
| `price_low` / `price_high` | number | Para `line`, ambos iguales |
| `style` | `{color, opacity, line}` | Paleta la decide el backend |
| `active` | boolean | Permite atenuar zonas consumidas |
| `source` | `strategy \| engine \| user` | Trazabilidad |
| `meta` | object | Libre; la UI lo ignora |

**`chart.markers[]`**: `{id, ts, price, kind: entry|exit|phase|note|warning, side: long|short|none, label, source, meta}`.

**`chart.series[]`**: `{symbol, label, mode: raw|normalized|percent, axis: overlay|secondary, visible, values: [{t, v}]}`.

`symbols` en `series` es siempre una clave de `instruments`; el eje y la normalización los decide el backend.

---

## 8. Reglas de render dinámico en React

| Vista / componente | Consume | Prohibido |
|---|---|---|
| `TopBar` | `status`, `mode`, `session`, `data.quality` | Conocer símbolos concretos |
| `SymbolsTable`, `quotes` | `instruments[]` + `quotes{}` | Listas fijas de tickers |
| `KvPanel` (Estado de Estrategia) | `strategy.metrics` + `strategy.phases` + `strategy.state_label` | Campos hardcodeados |
| `PhaseTimeline` | `strategy.phases[]` | Asumir número de fases |
| Gráfico | `chart.candles`, `chart.series`, `chart.zones`, `chart.markers` | Dibujar zonas con semántica propia |
| Operaciones | `position`, `orders`, `risk` | Mapear `side` a nombres de producto |
| Historial | `GET /api/trades` (+filtros) | Formatear importes con moneda fija |
| Estadísticas | `GET /api/stats` | Inventar métricas ausentes |
| Config | `GET /api/config` → grupos + `strategy.params_schema` | Formularios de estrategia hardcodeados |

Reglas adicionales:

- Formato numérico: `decimals` y `currency` por instrumento, nunca `toFixed(2)` global.
- Un `kind` desconocido en zonas/marcadores se omite y se anota en `console.debug`.
- Los textos visibles (`label`, `state_label`, `detail`) los envía el backend.
- El cliente puede reenviar `settings` al servidor solo mediante `PUT /api/config` validado.

---

## 9. Persistencia

SQLite en modo WAL, con interfaz `Store` aislada (migrable a PostgreSQL sin tocar llamantes).

| Tabla | Contenido |
|---|---|
| `trades` | Operaciones cerradas: símbolo, dirección, unidades, precios, SL, TP, P&L neto, R, fees, motivos y modo. |
| `events` | Log con nivel, categoría, mensaje y metadatos (retención máx. 5.000 filas). |
| `equity` | Puntos de equidad tras cada cierre. |
| `kv` | Estado del motor, posición abierta y estado de sesión para recuperación. |
| `backtests` | Resultado completo, métricas y diagnósticos. |
| `backtest_runs` / `backtest_results` | Índice y resultados normalizados, con paginación por cursor. |
| `backtest_ledger_outbox` | Cola de publicación al ledger de experimentos. |
| `schema_migrations` | Control de versiones del esquema. |

Reglas de recuperación:

- La posición y su bracket SL/TP se restauran desde `kv`.
- La equidad se reconstruye desde las operaciones reales; nunca se guarda un saldo inventado.
- Los contadores diarios se conservan si la sesión coincide.
- El replay se reinicia sin evaluar velas anteriores a la entrada de la posición restaurada.

---

## 10. Riesgo y seguridad operativa

`RiskManager` aplica, en este orden: emergencia → orden pendiente → posición abierta → operaciones del día → distancia de stop máxima → ventana horaria → ventana de exclusión → pérdida diaria → beneficio diario → pérdidas consecutivas → cooldown. Después dimensiona.

Sizing genérico (por instrumento, vía su especificación):

```text
riesgo_por_unidad = |entry - stop| / tick_size * tick_value
presupuesto       = equity * risk_per_trade_pct / 100
qty               = floor(presupuesto / riesgo_por_unidad)
qty               = min(qty, max_units_per_trade)
```

Si `qty < 1`, la señal se rechaza con motivo explícito y el rechazo queda visible en el snapshot (`strategy.rejection` o `risk.block_reason`).

Invariantes de seguridad:

- Una señal se identifica por su `key` estable y se ejecuta una sola vez.
- No se permite segunda entrada con posición abierta u orden pendiente.
- Los límites diarios se evalúan antes de cada entrada y se muestran como estado.
- La parada de emergencia bloquea entradas, cancela órdenes, permite cerrar y es persistente hasta desactivación explícita.
- LIVE exige adaptador implementado + `live_enabled` + confirmación; si falta algo, no arranca.
- Los errores de feed se registran y se reintenta la conexión; nunca se ocultan.

---

## 11. Configuración

`Settings` se compone de grupos independientes, todos validados con Pydantic antes de aplicarse:

| Grupo | Contenido | ¿Depende de la estrategia? |
|---|---|---|
| `InstrumentsConfig` | Símbolos, rol (`primary`/`context`), `tick_size`, `tick_value`, `point_value`, moneda, decimales, plantilla de sesión, vencimientos y rolls | No |
| `StrategyConfig` | `id`, `enabled`, `version`, `params` (validados contra `params_model` del plugin) | **Sí**, solo dentro de `params` |
| `RiskConfig` | Capital inicial, riesgo por operación, límites diarios, ventana horaria, cooldown, unidades máximas, stop máximo | No |
| `ExecutionConfig` | Comisión por unidad y lado, slippage y tope, modelo de fill, fills parciales | No |
| `FeedConfig` | Proveedor, ruta CSV, velocidad de replay, bucle, fecha inicial, latencia simulada | No |
| `LiveConfig` | Broker, entorno, cuenta, feed, `live_enabled`, confirmación | No |
| `UIConfig` | Paneles visibles y orden, tema, locale | No |

Reglas: defaults en código (`Settings()`), configuración viva en `data/config.json`, escritura atómica, backup `.json.broken` si está corrupta y arranque con defaults. Rutas sobreescribibles por entorno (`*_PROFILE_DIR`, `*_CONFIG_PATH`, `*_DB_PATH`).

---

## 12. Backtesting y validación

- `prepare_dataset` valida un dataset multi-serie; `run_backtest` ejecuta la configuración; `run_variants` corre variantes sobre el mismo dataset.
- El motor comparte exactamente las mismas clases de riesgo y ejecución que el modo paper: comisiones, slippage acotado, modelo de fill, diagnóstico de barras ambiguas.
- El dataset exige: timestamps alineados entre series, sesión completa según calendario, días hábiles, barras de calentamiento suficientes para la estrategia, contratos y vencimientos declarados, consistencia de rolls y ausencia de huecos injustificados.
- Cada ejecución guarda identidad de dataset (hash), identidad de serie, rango de sesiones, contratos, plan de rolls y configuración de feed/ejecución.
- El protocolo de validación es **configurable**, no específico: ventanas de desarrollo, ventanas rodantes y holdout sellado con `HoldoutAlreadySealed`. Las puertas (integridad, determinismo, muestra mínima, Profit Factor, expectativa R, drawdown, consistencia por bloques, sensibilidad a costes, concentración, bootstrap) viven en un archivo de umbrales versionado.
- Un `pass` no autoriza LIVE. La secuencia es BACKTEST → DRY-RUN → LIVE, y cada salto es una decisión explícita del operador.
- Muestra insuficiente ⇒ `INCONCLUSO`, nunca aprobación.

---

## 13. API

| Grupo | Endpoints |
|---|---|
| Salud y estado | `GET /api/health`, `GET /api/status` |
| Configuración | `GET /api/config`, `PUT /api/config`, `POST /api/config/reset`, `GET /api/strategy/schema` |
| Motor | `POST /api/bot/{action}` (`start`/`pause`/`stop`) |
| Posición y órdenes | `POST /api/position/close`, `POST /api/orders/cancel`, `GET /api/orders` |
| Emergencia | `POST /api/emergency`, `DELETE /api/emergency` |
| Historial | `GET /api/trades`, `GET /api/trades/export.csv`, `GET /api/events` |
| Estadísticas | `GET /api/stats`, `GET /api/stats/reset/preview`, `POST /api/stats/reset` |
| Gráfico | `GET /api/chart/history?tf=&symbol=` |
| Backtesting | `/api/backtest/*` (ejecución, variantes, presets, historial, detalle, comparación, ledger) |
| Datos | `GET /api/datasets`, `POST /api/data/validate` |
| Tiempo real | `WS /api/ws` |

`GET /api/strategy/schema` es el que permite a la pestaña **Configuración → Estrategia** construir el formulario desde `params_model` sin campos hardcodeados.

---

## 14. Vistas

| Vista | Contenido |
|---|---|
| **Inicio** | Estado operativo, equidad, P&L, riesgo abierto, mini-gráfico, posición, últimas operaciones, curva de equidad, panel de estado de estrategia. |
| **Gráfico** | Velas de 1/5/15/30 min, zoom y pan, volumen, indicadores opcionales, series de comparación normalizadas, zonas y marcadores del backend. |
| **Operaciones** | Posición, órdenes, brackets, riesgo actual, límites de sesión, controles de cierre/cancelación/pausa/emergencia. Pestañas `positions`, `orders`, `closed`. |
| **Historial** | Registro persistente con filtros (`today`, `week`, `month`, `30d`, `all`), detalle y exportación CSV, paginación de 25 filas. |
| **Estadísticas** | `resumen`, `rendimiento`, `direccion`, `hora`, `mes` + comparación de backtests. |
| **Configuración** | `instrumentos`, `estrategia` (formulario generado desde el esquema del plugin), `riesgo`, `horarios`, `avanzado`. |
| **Consola** | Eventos en tiempo real con nivel, categoría y estado de conexiones. |

---

## 15. Pruebas mínimas del esqueleto

Sin estrategia todavía, la suite debe pasar y cubrir:

| Área | Qué valida |
|---|---|
| Contrato de snapshot | `SnapshotBuilder` produce JSON válido contra el esquema Pydantic v1 con `NullStrategy`. |
| Interfaz de estrategia | `NullStrategy` cumple el Protocol; parámetros inválidos se rechazan. |
| Riesgo | Orden de comprobaciones, sizing, ventanas, cooldown, emergencia persistente. |
| Ejecución | Fills, brackets, slippage acotado, barras ambiguas, comisiones. |
| Store | Esquema, migraciones, WAL, recuperación de posición y equidad. |
| Backtest | Determinismo con `NullStrategy` (golden test) y dataset de fixture. |
| API | Contrato REST/OpenAPI y handshake del WebSocket. |
| Frontend | `tsc --noEmit`, build de Vite y tipos del snapshot alineados con `schemas.py`. |

---

## 16. Extensiones previstas

1. Adaptador real de datos (`MarketFeed`) para el proveedor elegido.
2. Adaptador de ejecución con reconciliación de posiciones del broker.
3. Migración de `Store` a PostgreSQL manteniendo la interfaz.
4. Walk-forward automático con ventanas configurables.
5. Alertas externas y exportación de métricas.
6. Segundo plugin de estrategia en paralelo (comparación A/B con el mismo motor).

---

# Aquí va la estrategia

<!--
BLOQUE RESERVADO. Es el único lugar del repositorio donde se describe lógica de
estrategia. Nada de lo anterior depende de este contenido.
-->

## Contrato que debe cumplir cualquier estrategia

### Firma

```python
# server/strategy/base.py  (contratos; la implementación vive en el plugin)

class Warmup(BaseModel):
    bars: dict[str, int]          # velas mínimas por símbolo antes de evaluar
    session_ready: bool           # requiere sesión iniciada

class MarketData(BaseModel):
    session: SessionInfo          # id, label, is_open, open_ts, close_ts, phase
    clock: datetime               # instante de la vela cerrada evaluada
    primary: str                  # símbolo primario (de InstrumentsConfig)
    bars: dict[str, list[Bar]]    # SOLO velas cerradas, ordenadas, por símbolo
    params: BaseModel             # params validados del plugin
    context: dict[str, Any]       # datos auxiliares inyectados por el motor (opcional)

class Signal(BaseModel):
    key: str                      # identidad estable: session + side + instante disparador
    side: Literal["long", "short"]
    strength: float | None        # 0..1, informativo
    reason: str
    ts: datetime
    valid_until: datetime | None
    stop_price: float             # OBLIGATORIO: sin stop no hay señal
    target_price: float | None

class Phase(BaseModel):
    key: str
    label: str
    status: Literal["pending", "active", "done", "failed", "skipped"]
    ts: datetime | None = None
    detail: str | None = None

class Zone(BaseModel):
    id: str
    kind: Literal["band", "line", "box", "region"]
    label: str | None
    from_ts: datetime
    to_ts: datetime | None
    price_low: float
    price_high: float
    style: dict[str, Any] = {}
    active: bool = True

class Marker(BaseModel):
    id: str
    ts: datetime
    price: float
    kind: Literal["entry", "exit", "phase", "note", "warning"]
    side: Literal["long", "short", "none"] = "none"
    label: str | None = None

class Metric(BaseModel):
    label: str
    value: float | str | bool | None
    format: Literal["number", "price", "pct", "ratio", "text", "duration", "boolean"] = "number"
    unit: str | None = None
    tone: Literal["neutral", "good", "bad", "warn"] = "neutral"
    group: str | None = None

class StrategyOutput(BaseModel):
    state: str                                  # libre; el motor no lo interpreta
    state_label: str
    phases: list[Phase] = []
    signal: Signal | None = None
    rejection: dict[str, str] | None = None     # {"code": ..., "message": ...}
    metrics: dict[str, Metric] = {}
    zones: list[Zone] = []
    markers: list[Marker] = []
    notes: list[str] = []

class BaseStrategy(Protocol):
    id: str
    name: str
    version: str
    params_model: type[BaseModel]

    def warmup_requirements(self) -> Warmup: ...
    def evaluate(self, md: MarketData) -> StrategyOutput: ...
```

### Mapa de consumo por el motor

| Campo de `StrategyOutput` | Destino |
|---|---|
| `signal.key` | Identidad para deduplicar (una ejecución por señal) |
| `signal.side` / `stop_price` / `target_price` | `RiskManager` → sizing → `ExecutionEngine` (bracket) |
| `signal.reason`, `strength`, `valid_until` | Trazabilidad en `trades`/`events` y snapshot |
| `state`, `state_label`, `phases` | Panel de Estado de Estrategia |
| `metrics` | Panel clave-valor |
| `zones`, `markers` | Capa visual del gráfico |
| `rejection` | Se muestra como motivo de no-entrada; no bloquea el motor |
| `notes` | Eventos de nivel `info` (no se persisten en `trades`) |

### Guardarraíles (violarlos invalida la integración)

1. **Solo velas cerradas.** Nunca la vela en formación ni `bars[-1]` si no está cerrada.
2. **Sin lookahead.** Prohibido indexar barras futuras o usar `md.clock` para leer datos posteriores.
3. **Sin estado oculto.** El resultado debe depender solo de `md`. Cachés permitidas únicamente si son puras y reiniciables por sesión.
4. **Sin I/O.** Prohibido acceder a base de datos, red, disco, reloj del sistema o aleatoriedad no sembrada.
5. **Sin órdenes.** La estrategia no envía, modifica ni cierra órdenes: solo devuelve `Signal`.
6. **Sin riesgo propio.** La estrategia propone `stop_price`; el tamaño y los límites los impone `RiskManager`.
7. **Determinismo.** Mismo `MarketData` ⇒ mismo `StrategyOutput`, byte a byte en los campos numéricos.
8. **Sin nombres de activos en el plugin.** Los símbolos se leen de `md.primary` y `md.bars.keys()`.

### Checklist de integración (cuando exista la estrategia)

- [ ] `server/strategy/<id>.py` implementa `BaseStrategy` con `params_model` propio.
- [ ] Registrado en `registry.py` y seleccionado por `StrategyConfig.id`.
- [ ] `warmup_requirements()` coherente con el backtest (mismo mínimo de velas).
- [ ] Fases declaradas como lista fija y documentada (orden y `key` estables).
- [ ] Zonas y marcadores con `id` determinista y `label` descriptivo.
- [ ] `signal.key` estable y único por sesión/dirección/disparo.
- [ ] `stop_price` siempre presente y compatible con `max_stop_ticks`.
- [ ] Test unitario de `evaluate()` con fixture de velas congelado.
- [ ] Golden test de backtest con hash reproducible.
- [ ] Ningún campo nuevo en `schemas.py` fuera del bloque `strategy`/`chart`.
- [ ] Reglas, parámetros y limitaciones documentadas en `docs/ESTRATEGIA.md`.
