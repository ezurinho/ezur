# Deep Research: Ezur — revisión, calificación y comparación

> Generado 2026-11-24 | Profundidad: deep | Fuentes: 73 | Corte: 19:15 UTC

## TL;DR

Ezur es un terminal de paper trading local con una disciplina de honestidad de datos poco común: no convierte ausencias en ceros, declara truncamiento y antigüedad, separa loading de empty y explica cada veto con datos trazables. La revisión independiente encontró cuatro fallos capaces de falsear resultados —gaps de ejecución, look-ahead en dimensionado, mezcla de modos contables y configuración fail-open— y los cuatro fueron reproducidos, corregidos y cubiertos por regresiones.

La calificación de ingeniería queda en **8,4/10**, pero la aptitud para **live desatendido** es solo **2,5/10** y la **ventaja demostrada** **3,0/10**. El producto está listo para seguir operando como demo paper supervisada; no está listo para dinero real. La estrategia actual tiene 13 cierres paper, P&L neto negativo y veredicto de validación RECHAZADA. Ninguna mejora de interfaz convierte ese historial en evidencia de edge.

La comparación ampliada a **27 plataformas adicionales** confirma el mismo patrón: Jesse y QuantRocket son los peers técnicos más serios; 3Commas, Cryptohopper y HaasOnline ganan en amplitud operativa; MetaTrader 5 y NinjaTrader en madurez de tester/ejecución; Trade Ideas, Composer y Capitalise en automatización expresiva. Ezur no gana en mercados ni en ecosistema: gana en **honestidad de datos, trazabilidad local y gates de evidencia explícitos**.

## Resumen ejecutivo

La arquitectura de Ezur combina FastAPI, SQLite WAL, un motor de ejecución propio, React y un motor de investigación separado con pandas. El punto fuerte no es la cantidad de funciones, sino la coherencia entre motor, API y pantalla: el snapshot es el contrato, el libro es la fuente de equity, las métricas se derivan del ledger y la UI evita presentar estados inventados. Los backtests conducen el mismo `TradingEngine` que el modo paper, lo que reduce la divergencia entre señal, riesgo y fills.

La revisión de código fue deliberadamente escéptica. Dos agentes independientes leyeron el working tree completo, incluido `research_engine`, sin modificar archivos. El primero se centró en motor, riesgo, ejecución, backtest, persistencia y pruebas; el segundo en API, seguridad, concurrencia, recuperación y operación. Ambos identificaron fortalezas reales y problemas concretos con `file:line`. Los hallazgos críticos se verificaron antes de implementar, siguiendo el principio de que una revisión externa también puede equivocarse.

El fallo más grave estaba en `server/execution.py`: una entrada larga cuyo open ya atravesaba el stop podía rellenarse por debajo del stop y cerrarse “en el stop”, por encima de la entrada, produciendo un beneficio artificial. El modelo `signal_price` además podía usar un mínimo o máximo de la vela ocurrido antes del fill. La corrección rechaza entradas ya atravesadas por el stop en todos los modelos, ejecuta stops con gap a la apertura más deslizamiento adverso y degrada `signal_price` cuando OHLC no puede establecer el orden post-fill.

El segundo fallo estaba en `research_engine/runner/run_strategy.py`: la volatilidad usada para dimensionar incluía el retorno de la vela de entrada, que utiliza su cierre futuro. Una prueba de perturbación cambió el factor de 1,536 a 0,5 antes del arreglo. Ahora la ventana termina en el retorno anterior a la entrada y la prueba exige invariancia.

El tercer fallo era contable: `realized_pnl`, estadísticas y reconstrucción diaria no filtraban por modo. Una fila backtest de +100 podía elevar una cuenta paper nueva. `Store` ahora acepta filtros por modo y motor, snapshot y API los aplican. El cuarto fallo era de configuración: versiones futuras, NaN, comisiones negativas y metadatos de tick inválidos podían llegar al motor; ahora el modelo es fail-closed y un perfil ausente o corrupto no arranca solo.

La pasada de corrección no se detuvo ahí. Se endurecieron admisión de sesión, caducidad de bloqueos, slippage de salidas, fills parciales, migraciones, reconfiguración atómica, límites de capital, reset, semántica de stop, serialización de comandos, reconstrucción de estadísticas diarias, notifier, Host/Origin, redacción de webhooks, límites de recursos, backups online, escala de contrato, profit factor sin pérdidas, warmup y metadatos de instrumento. También se corrigió el runner de investigación para no aceptar artefactos viejos o de otra spec.

El resultado sigue siendo paper-only por diseño. No existe adapter de broker, reconciliación de venue ni camino de promoción validado. Freqtrade, NautilusTrader y Lean son más fuertes en ejecución live; Ezur es más fuerte en transparencia local, validación explícita y UI que no maquilla la falta de datos. La comparación correcta no es “¿cuál tiene más features?”, sino “¿qué capa necesita todavía Ezur para que sus números sean independientemente defendibles?”.

## 1. Estado actual y método

### 1.1 Alcance

La revisión cubrió:

- Motor, ciclo de ticks, sesiones, orden monotónico y replay.
- Riesgo, dimensionado, stops, objetivos, slippage, comisiones y fills.
- Persistencia, migraciones, equity, deduplicación y reconstrucción.
- Backtest, simulación, estrés, gates, holdout y artefactos de investigación.
- API REST/WebSocket, configuración, alertas y actualización.
- Frontend: snapshots, estado de carga, stale data, tablas, historial, estadísticas y laboratorio.
- Operación local: loopback, Host/Origin, backups, recuperación y stop.

No se evaluó una estrategia como inversión, no se operó dinero real y no se modificó el libro vivo. Durante la auditoría apareció un artefacto externo de cuarentena para las operaciones #3/#5 (`profiles/okx/backups/quarantine-trades-3-5-20261124T171737Z.json` y una base previa). No se restauró, borró ni reescribió nada relacionado; la calificación usa el estado actual del libro.

### 1.2 Evidencia ejecutada

- Backend: **746 tests passed**.
- Frontend: TypeScript limpio, **220 tests passed**, build Vite correcto.
- Motor de investigación: **79 unittests passed**.
- API viva: `health` OK, motor `running`, modo `paper`, feed OKX, WebSocket abierto.
- Equity viva reconciliada con el ledger paper del corte: **24.280,12**.
- Ledger paper del corte: **13 cierres**, P&L neto **−719,88**.
- Backup online restaurado en una base desechable: `PRAGMA integrity_check = ok`; la copia contenía 12 cierres y −644,96, coherente con ser anterior al último cierre.
- Guardia Host/Origin probada en vivo: origen cruzado 403, mismo origen 200.

### 1.3 Rúbrica

La nota de ingeniería pondera: integridad y contabilidad 20; riesgo y ejecución 20; backtest e investigación 20; fiabilidad y recuperación 15; UI y verdad 10; seguridad 10; pruebas y mantenibilidad 5. La nota de producto se separa de la de readiness live y de la de edge porque mezclarlas sería engañoso.

## 2. Calificación

| Dimensión | Puntos | Nota | Justificación |
|---|---:|---:|---|
| Integridad de datos y contabilidad | 18/20 | 9,0 | Ledger como fuente, modos separados, migraciones con archivo y reconciliación diaria desde el libro. Falta journal inmutable de comandos. |
| Riesgo y ejecución | 17/20 | 8,5 | Gates, gaps, slippage, sesión, kill switch y deduplicación corregidos. No hay adapter ni reconciliación live. |
| Backtest e investigación | 15/20 | 7,5 | Gates, DSR/PBO, holdout y artefactos con hash. Falta validador independiente y trial ledger completo. |
| Fiabilidad y recuperación | 13/15 | 8,7 | WAL, serialización, backups online, restore drill y tareas cancelables. Falta retención/verificación automática de backups. |
| UI y verdad | 10/10 | 10,0 | Loading/stale/empty separados; `—` para ausencias; truncamiento, UTC y exposición final declarados. |
| Seguridad | 7/10 | 7,0 | Loopback, Host/Origin, body cap y redacción. Falta token de sesión y allowlist de raíces de dataset. |
| Pruebas y mantenibilidad | 4/5 | 8,0 | 1045 tests verdes y contratos amplios. CI y dependencias no reflejan Python 3.14. |
| **Total ingeniería** | **84/100** | **8,4/10** | Sólido para paper supervisado; no es un certificado de producción. |
| Aptitud live desatendida | 25/100 | 2,5/10 | Paper-only, sin venue, sin reconciliación y sin piloto. |
| Ventaja demostrada | 30/100 | 3,0/10 | Muestra corta, P&L negativo y validación rechazada. |

## 3. Backtest e integridad de ejecución

### 3.1 Lo que estaba mal

Un backtest no es una reproducción del pasado: es una simulación de decisiones con información disponible en cada momento. La literatura sobre DSR y PBO muestra que una búsqueda amplia de parámetros puede producir resultados in-sample excelentes y resultados out-of-sample negativos; el problema no es solo “hacer trampa”, sino no contabilizar cuántas estrategias se probaron [1][2]. El protocolo de Arnott, Harvey y Markowitz exige registrar todos los modelos y variables intentados, incluidos los fallidos, y advierte que reutilizar un holdout después de ajustar lo convierte en in-sample [23].

Ezur ya tenía elementos valiosos: gates versionados, verdict INCONCLUSO cuando faltan mediciones, hashes de dataset, semillas fijas, stop-first en barras ambiguas y un ledger de experimentos. Pero el motor de ejecución tenía dos errores que invalidaban esos controles. Un gap podía crear P&L positivo artificial y el dimensionado por volatilidad usaba el cierre de la vela de entrada. Corregir solo la UI no habría bastado: el libro y los veredictos dependían de esos cálculos.

### 3.2 Correcciones aplicadas

**Gaps de entrada y salida.** `ExecutionEngine._fill_plan` ahora calcula el fill con slippage y rechaza cualquier modelo cuyo open ya esté al otro lado del stop. `_bracket_hit` detecta primero un gap de stop y sale a `bar.open` con deslizamiento adverso; no al precio de stop ya sobrepasado. Un gap favorable de objetivo sale al mejor open. Esto elimina el caso largo entrada 97,25 / stop 99,50 / beneficio +22,50 que reprodujo la revisión.

**Orden post-fill.** En `signal_price`, si el rango OHLC toca el stop pero no permite saber si ocurrió antes o después de un fill intrabar, el motor degrada a `next_open` y registra `fill_fallback=pre_entry_stop_unknown`. No afirma un orden que los datos no contienen. La documentación de Backtrader también distingue órdenes de mercado, limit y stop y muestra que la configuración de slippage puede no alterar ciertos fills; una opción que no cambia comportamiento es una opción que miente [3].

**Look-ahead de dimensionado.** `vol_factors` usa ahora `ret[lo:entry_i]`, excluyendo el retorno que incorpora el cierre de la vela de entrada. La regresión perturba únicamente ese cierre y exige el mismo factor. La documentación de SciPy bootstrap recuerda que sus intervalos asumen muestras aleatorias; aplicarlo sin preservar dependencia puede dar intervalos demasiado estrechos [4]. Ezur debe seguir usando bloques o bootstrap estacionario para drawdown y métricas dependientes del camino [24].

**Exposición al final del backtest.** El resultado incluye `open_position`, `pending_orders` y `marked_to_market=false`. El laboratorio muestra una nota cuando la corrida termina con exposición: esa operación no está incluida en la curva ni en las métricas. Antes, el último cierre podía leerse como el final completo de la simulación.

### 3.3 Ampliación posterior: frescura, oráculo y escala sintética

Una segunda revisión independiente encontró cuatro huecos adicionales y se cerraron con TDD. El motor ahora autoriza entradas usando también el reloj de pared cuando el provider es OKX/live: un backfill de recuperación con velas de hace 19 minutos no puede rellenar una orden pendiente aunque el hueco entre velas sea de un minuto. Las posiciones abiertas siguen gestionando stops y objetivos. El snapshot reporta la misma antigüedad de pared en `quality` y `staleness_ms`, evitando la contradicción “stale · último dato hace 1 min”.

Se añadió un oráculo de ejecución con 13 casos calculados a mano: largos y cortos, gaps de stop y objetivo, slippage, comisiones, cierre manual, barra ambigua, `signal_price`, `intrabar`, objetivo antes de la entrada y salida en la misma vela. No reutiliza los helpers de P&L del motor. El modelo `signal_price` degrada cuando OHLC no puede establecer el orden post-fill de stop u objetivo, y todos los modelos rechazan una entrada cuya apertura ya atravesó el stop o alcanzó el objetivo.

La simulación sintética también se corrigió. `reference_price` es un campo opcional y validado por instrumento; la volatilidad y las mechas escalan con el precio cuando se declara, mientras la serie legacy conserva exactamente sus dos draws independientes. El redondeo depende del tick y ya no genera ceros con ticks pequeños. Con el perfil OKX y referencia 60.000, una simulación de cinco días pasó de una expectativa absurda de −506 R a **−0,17 R**, con 18 operaciones. Sigue siendo sintética y no demuestra edge, pero sus métricas son internamente coherentes.

La identidad del dataset sintético ahora hashea timestamps y OHLCV generados, no la estrategia. Dos estrategias sobre las mismas velas comparten `dataset_id`; cambiar referencia, tick, calendario o símbolos lo cambia. La reconfiguración runtime sincroniza `state.provider`, de modo que cambiar de simulated a OKX activa la frescura de pared y cambiar a CSV no marca el replay histórico como obsoleto.

La revisión final confirmó el cierre de los hallazgos importantes y mantuvo la calificación de ingeniería en **8,4/10**. Queda como mejora operativa menor un watchdog que cancele órdenes pendientes durante un silencio total del feed; hoy no pueden rellenarse sin un tick y el primer tick stale las cancela antes de ejecutar.

### 3.4 Lo que falta

La validación más importante que falta es un **validador independiente**. Hoy backtest y paper comparten el mismo motor; esa paridad detecta divergencia de configuración, pero no un error común de semántica. La literatura de implement risk compara motores y recomienda diversidad de validadores precisamente porque motores populares pueden divergir en costes, orden de fills y escalado [21]. Ezur necesita fixtures pequeños con resultados esperados calculados a mano o por un motor distinto: gap de entrada, stop y objetivo en la misma vela, target gap, slippage, comisiones, cierre manual, session close y varios modos contables.

Tampoco existe un trial ledger completo que registre automáticamente cada parámetro, dataset, semilla y configuración abandonada. El ledger de experimentos actual es una buena base, pero no demuestra que la búsqueda completa esté contabilizada. TimeSeriesSplit ofrece una base cronológica con `gap`, pero no purga información solapada ni sustituye un protocolo financiero [22][25].

### 3.5 Watchdog de frescura y ciclo de vida

La última revisión detectó que un feed completamente silencioso dejaba órdenes pendientes y calidad `ok` hasta el siguiente tick. La documentación de exchanges distingue tres controles que no deben confundirse: liveness de transporte, frescura de datos y continuidad de secuencia. OKX exige ping si no hay mensajes durante 30 segundos y reconexión si no hay pong [62]; Binance envía ping cada 20 segundos y desconecta tras un minuto sin pong [63]. Esas reglas no definen la antigüedad máxima de una vela. NautilusTrader documenta timers independientes de `on_quote()`/`on_bar()` y distingue `CONNECTED` de adapter listo [64]. Freqtrade separa `/pause`/`stopentry`, cancelación de órdenes y `/forceexit` [65].

Ezur implementa ahora un watchdog cada 30 segundos que corre fuera del callback de velas. Su umbral de `stale` sigue siendo el ya configurado por el motor —15 minutos desde la última vela, con degradado desde 3— y se considera una decisión de diseño, no una regla universal del exchange. El watchdog:

- Actualiza `quality` y `staleness_ms` con el reloj de pared.
- Cancela órdenes pendientes de entrada sin inventar un precio de salida.
- Mantiene stops y objetivos de posiciones abiertas.
- Publica el snapshot aunque no lleguen ticks.
- Contiene excepciones para no morir silenciosamente.
- No afecta backtests ni replays históricos.

El ciclo de vida se serializó con `_lifecycle_lock`. `start_task`, `refresh_task` y `stop_task` comprueban el estado antes y después del teardown, siempre bajo el lock. Un reinicio directo limpia las velas para no duplicar historia. La regresión forzada inyecta `stop()` durante el teardown y exige que el contador de consumidores no aumente. La revisión focalizada calificó esta capa en **9,5/10**, sin hallazgos críticos o importantes en su alcance; la nota global se mantiene en **8,4/10** por las deudas de auditoría, autenticación y live que siguen fuera de esta capa.

Pendiente para una siguiente iteración: incorporar heartbeat de transporte y continuidad de secuencia cuando el adapter OKX exponga esos eventos. El watchdog actual protege frescura de velas, no integridad de order book.

### 3.6 Expiración de órdenes y señales antiguas

El watchdog de frescura no bastaba: si el feed volvía con una vela actual, una orden armada hacía 16 minutos podía rellenarse porque los datos nuevos ya eran frescos. La literatura operativa separa **vigencia de la señal**, **validez de la orden** y **reconciliación**. Freqtrade expone `ignore_buying_expired_candle_after` y `unfilledtimeout.entry` [33]; Binance documenta IOC/FOK como reglas de ejecución, no como garantía de señal fresca [66]; NautilusTrader distingue `SUBMITTED`, `PENDING_CANCEL` y outcomes desconocidos [67][7].

Ezur añadió un TTL de **120 segundos** para órdenes pendientes live. `ExecutionEngine.expire_pending` cancela antes de `on_bar`; el watchdog también lo comprueba durante el silencio. El reloj usa un `armed_at` runtime separado de `created_ts`, porque la vela OKX ya tiene aproximadamente un minuto al procesarse. Así el TTL empieza al armar, no al abrir la vela. Los backtests y replays quedan fuera de esta política.

`stale_data` tiene prioridad: si el feed está obsoleto, la orden se cancela por datos, no por edad. Si los datos están frescos pero la orden es vieja, el bloqueo es `stale_order`, presentado como retención neutral y no como alarma de riesgo. Una señal duplicada conserva el aviso; una señal única y aprobada lo limpia y arma una orden nueva. La revisión focalizada calificó esta capa en **9,3/10**, sin hallazgos críticos o importantes.

Queda como deuda menor que el TTL se comprueba por polling —cada tick y cada 30 segundos—, no por un deadline exacto. Es seguro para fills porque toda vela vuelve a comprobar antes de ejecutar. La persistencia de eventos ya registra la cancelación, pero el detalle de IDs de orden y el journal immutable siguen pendientes.

### 3.7 Caducidad declarada de la señal

`Signal.valid_until` existía en el contrato, pero el motor lo ignoraba. Freqtrade separa `ignore_buying_expired_candle_after` de `unfilledtimeout.entry` y del time-in-force de la orden [33]; NautilusTrader define TIF como validez de la orden, no de la señal [67]; Jesse documenta correcciones para evitar operar con velas no terminadas o actualizaciones de fill tardías [68].

Ezur evalúa ahora el estado duro de riesgo y después aplica `valid_until` antes de `execution.arm`. Así una señal vencida no crea una orden, pero tampoco sustituye un bloqueo activo de emergencia, pérdida diaria o drawdown. El reloj es `tick.ts` en backtest/replay y `now_utc()` en paper/live con OKX. La comparación es inclusiva: en el instante exacto de expiración la señal sigue siendo válida; un microsegundo después se rechaza como `stale_signal`. Los timestamps naïve se interpretan como UTC.

`stale_signal` se presenta como retención neutral, no como alarma de riesgo. La política es deliberadamente **pre-arm**: una orden ya armada conserva su propio TTL de 120 segundos; `valid_until` no se reinterpreta como deadline absoluto del fill. La revisión verificó además prioridad con emergencia, pérdida diaria y drawdown, y no encontró hallazgos críticos o importantes en este alcance. La nota global permanece en **8,4/10**.

### 3.8 Precisión por instrumento en el feed simulado

El feed simulado usaba el `tick_size` del instrumento primario para todos los símbolos. Eso viola el contrato agnóstico y puede generar precios fuera de la rejilla de un contexto. OKX publica `tickSz`, `lotSz` y `minSz` por instrumento [69]; Binance separa `PRICE_FILTER.tickSize` de `LOT_SIZE.stepSize` y `MARKET_LOT_SIZE` [70]; NautilusTrader separa precisión decimal de incrementos ejecutables [71]; Lean guarda tick, lote y mínimo por `SymbolProperties` [72].

`SimulatedFeed` acepta ahora `tick_sizes` por símbolo y `build_feed` propaga el mapa completo desde configuración. El `tick_size` global queda como fallback para callers que no declaran mapa. La validación ocurre en el constructor: rechaza booleanos, strings, NaN, infinitos, negativos y valores menores de `1e-12`. Ese mínimo documentado evita precios sintéticos que redondean a cero; el caso límite inclusivo pasa.

Las pruebas cubren propagación desde `build_feed`, fallback, dos referencias distintas, alineación de opens, timestamps, determinismo y paridad exacta de la serie legacy. Una sonda independiente comprobó 11.700 velas en el límite y 36 sesiones completas de 390 velas sin cambios respecto al comportamiento anterior. La revisión focalizada calificó esta capa en **9,5/10**, sin hallazgos críticos o importantes. La nota global sigue en **8,4/10**.

Queda fuera de esta pasada la validación de incrementos de cantidad y mínimos de notional. Ezur ya dimensiona unidades enteras, pero no declara `lot_size` ni `min_notional`; esos campos deben añadirse antes de cualquier adapter live.

### 3.9 Lotes, notional mínimo y limpieza de modelos de fill

La investigación de lotes confirma que el orden correcto es **redondear a la baja y después validar**. OKX exige múltiplos de `lotSz` y `sz ≥ minSz` [69]; Binance exige `quantity % stepSize == 0` y `price × quantity ≥ minNotional` [70]; Nautilus separa incremento de tamaño, lote y notional [71]; Lean usa `AdjustByLotSize` y validación de mínimo por brokerage [72][73].

Ezur añadió `lot_size` entero —las unidades internas del motor son enteras— y `min_notional` opcional. El riesgo aplica presupuesto, tope, freno suave, redondeo por lote y finalmente notional. Nunca redondea hacia arriba para rescatar una orden. `contract_size` es explícito y obligatorio cuando se declara `min_notional`; el motor ya no infiere un multiplicador BTC desde `tick_value / tick_size`. El perfil operativo no declara esos metadatos porque su semántica de unidad sigue pendiente: el informe de exposición muestra desconocido en vez de inventar una escala.

El notional se valida dos veces: con el último precio en riesgo y con el **fill real** antes de abrir exposición. Esto cubre `next_open` y `signal_price`, largo y corto, incluidos los fallbacks. Los rechazos por notional o gaps quedan contabilizados una sola vez por tick y se persisten con modelo de fill, precio candidato, stop, objetivo, notional, umbral, `contract_size`, orden y señal. El bloqueo de ejecución permanece visible durante ese tick y se limpia en el siguiente tick limpio, incluso durante warmup o sin señal.

También se eliminó `intrabar`: tras universalizar el rechazo de gaps, el modelo había quedado como alias exacto de `next_open`. Los perfiles enviados usan ahora `next_open` y `load_settings` normaliza perfiles legacy con `intrabar` sin desactivar el arranque. La validación directa sigue estricta.

La revisión final de esta capa no encontró hallazgos críticos. La nota global se mantiene en **8,4/10**; la deuda principal sigue siendo autenticación, journal immutable y preparación live.

## 4. Riesgo, ejecución y promoción

### 4.1 Controles actuales

El `RiskManager` aplica una secuencia determinista: emergencia, orden pendiente, posición abierta, máximo diario, racha, drawdown, precio, geometría de stop/objetivo, ancho de stop, ventana horaria, pérdida diaria, beneficio diario, cooldown y dimensionado. Cada rechazo lleva código y mensaje; la UI traduce el código y el snapshot conserva totales por motivo.

La revisión confirmó que el motor no tiene ruta real de broker. `LiveFeed` no está implementado y `live_enabled=false`. `TradingEngine` rechaza `mode="live"` si el adapter, confirmación y broker no cumplen `can_start()`. Esta es una mitigación fuerte: el producto no puede confundir un fill simulado con una orden de venue por un simple cambio de etiqueta.

### 4.2 Endurecimiento aplicado

- **Sesión:** una señal con `session.is_open=False` ya no arma orden, aunque el reloj de riesgo permita la hora.
- **Bloqueos:** un veto de geometría o tamaño deja de presentarse cuando no hay señal nueva; cooldown, ventana y drawdown caducan cuando su condición deja de cumplirse.
- **Salidas:** manual y session close aplican slippage adverso cuando hay último precio; un precio explícito de bracket no se vuelve a deslizar.
- **Fills parciales:** activarlos devuelve error de validación en lugar de ignorarlos silenciosamente.
- **Comandos:** close/cancel/emergency pasan a ejecutarse en el event loop; `on_bar` vuelve a comprobar `status=="pending"` justo antes del fill.
- **Stop:** además de cambiar el estado, cancela y espera la tarea del feed. Al reiniciar con posición, la barrera de replay evita procesar velas anteriores a su apertura.
- **Reset:** exige motor parado, sin posición ni órdenes pendientes; reconstruye equity, pico, día, órdenes y caché de estadísticas.
- **Reconfiguración:** feed y estrategia se construyen antes de mutar estado; no se puede retirar el instrumento expuesto ni cambiar el primario; el capital inicial no se cambia con operaciones registradas.

### 4.3 Promoción y riesgo residual

FINRA recomienda mecanismos para desactivar rápidamente algoritmos, pilotos de tamaño limitado, monitoreo reforzado y conciliación posterior [8]. La SEC describe controles pre-trade automáticos para todos los órdenes generados por computadora y rechaza estrategias de “scrambling” o “chase and cancel” como sustituto de bloqueos previos al enrutamiento [30]. Ezur tiene parada de emergencia y promoción reduce/block, pero carece de adapter y de un piloto live. NautilusTrader documenta que un resultado desconocido debe permanecer in-flight para stream, consulta o reconciliación, y que los fills se deduplican por `trade_id` [7]. OKX documenta que `clOrdId` es único solo entre órdenes pendientes y que una cancelización aceptada no equivale a estado terminal [6]; Binance también documenta que el client order ID no es idempotencia histórica permanente [29].

Por eso el veredicto correcto es: **conservar paper-only**. No activar live no es una deficiencia de UX; es el control que evita que una simulación se convierta en orden real sin reconciliación.

La semántica de halt también es específica del venue. Las reglas EBS para FX Spot+ cancelan Day Orders durante una pausa, rechazan órdenes nuevas y permiten cancelaciones [31]. Un stop protector no puede darse por superviviente sin modelar time-in-force y estado de mercado. Binance exige además buffer de profundidad, snapshot REST y continuidad estricta de `pu`/`u`; si hay un salto de secuencia, el cliente debe reiniciar desde un snapshot nuevo [32]. La frescura de cotización y el desfase de reloj siguen siendo controles separados. Freqtrade dry-run documenta sus propias aproximaciones —fills por volumen, slippage máximo del 5 %, límites que pueden convertirse en mercado y órdenes abiertas asumidas sin fill tras reinicio— y por eso sirve para ensayo, no como prueba de acknowledgments reales [33].

## 5. Fiabilidad, recuperación y seguridad

### 5.1 Persistencia y recuperación

SQLite WAL aporta recuperación tras crash, pero el WAL es estado transaccional usado para recuperación, no un journal inmutable de auditoría [10]. Ezur serializa escrituras con un lock, ejecuta migraciones transaccionales y reconstruye equity desde el ledger. La revisión encontró que `day_stats` podía quedar a medias si el proceso moría entre el cierre y `_persist`; ahora siempre se reconstruye desde las operaciones de la sesión y se reescribe la caché.

Las migraciones v2/v3 antes borraban duplicados. Ahora los mueven a `trade_archive` y crean los índices únicos después. El archivo no participa en equity ni estadísticas, pero conserva evidencia. Esto respeta el principio de que una operación histórica no desaparece sin rastro.

Se añadió `Store.backup`, que usa la API online de SQLite. La documentación indica que produce una copia consistente y que las escrituras concurrentes pueden reiniciar la copia [26]. La aplicación crea un backup al arrancar cuando ya existe base y otro cada 24 horas; también copia la configuración. El drill en una base desechable pasó `integrity_check`. Falta automatizar ese drill en CI y definir retención, alertas de fallo y verificación de hashes.

### 5.2 Observabilidad

La consola de eventos es útil, pero no es telemetía completa ni evidencia inmutable. OpenTelemetry recomienda logs estructurados con esquema estable y correlación log–trace [11]; NIST SP 800-92 recomienda acceso append-only cuando sea posible, archivos protegidos con digests y pruebas activas de los eventos esperados [28]. Ezur retiene 5.000 eventos y no tiene trazas, métricas de latencia ni journal de comandos. Para paper local es suficiente; para producción no.

La respuesta a incidentes también debe ensayarse. Google SRE separa roles de mando, operaciones, comunicación y planificación, y recomienda preservar evidencia [12]. Ezur no necesita un equipo grande, pero sí una runbook de tres pasos: detener, preservar libro/config/logs y restaurar una copia verificada.

### 5.3 Seguridad local

Loopback no impide que una web maliciosa llame a `localhost`. FastAPI documenta `TrustedHostMiddleware` como defensa contra Host Header attacks [27]; su alcance documentado es validar Host, no autenticación, CSRF ni Origin. ASVS proporciona requisitos versionados para diseñar, desarrollar y probar aplicaciones y servicios [13]. Ezur añadió una guardia ASGI que:

- Acepta Host solo loopback; `testserver` únicamente desde el cliente sintético de tests.
- Exige que Origin, si existe, tenga el mismo host que la petición.
- Rechaza `Sec-Fetch-Site: cross-site`.
- Limita cuerpos HTTP a 1 MiB.
- Redacta `alerts.webhook_url` en snapshots WebSocket.

La API sigue sin token de sesión. Un proceso local malicioso puede llamar directamente; un token tampoco lo detiene si puede leer memoria, pero sí evita control casual y refuerza el modelo de mutaciones. La recomendación pendiente es token por sesión más journal append-only de comandos con ID, hash del payload, estado, resultado y timestamps.

### 5.4 Recursos

Se acotaron paginación, exportación, eventos, historia, experimentos y corridas de laboratorio. Los backtests y comparaciones comparten un `asyncio.Lock`, de modo que solo una corrida CPU pesada se ejecuta a la vez. Los datasets deben ser CSV y están limitados a 250 MiB; el hash se calcula por chunks. Falta una allowlist de directorios autorizados: el límite de tamaño evita agotamiento, pero no autorización de rutas.

## 6. UI: la fortaleza diferencial

La regla “la UI nunca miente” se aplica de forma consistente:

- Antes del primer snapshot, equity, P&L, estado, modo y sesión muestran `—`; no se afirma “stopped” o “paper”.
- Un `NaN` o infinito se muestra como dato ausente, no como número medido.
- Historial y estadísticas muestran fecha de lectura y refrescan al cambiar el total de cierres, incluso al cruzar medianoche.
- “7 días” y “30 días” se anclan a medianoche UTC y avanzan al cambiar de día.
- La tabla de 200 filas dice que **puede** haber anteriores, no que definitivamente las hay.
- El desglose por hora, día, semana y mes declara el reloj de la sesión.
- Un backtest con posición abierta al final lo dice.
- Una posición o marker sin etiqueta recibe un nombre por tipo; no desaparece en un hueco invisible.
- Un cierre de posición normal se presenta como “sin entradas nuevas por ahora”, no como alarma de riesgo.

React recomienda que los Effects que hacen fetch cancelen o ignoren resultados irrelevantes [14]. Ezur usa banderas `cancelled/alive` y evita que una respuesta vieja sobrescriba otra nueva. La revisión básica de accesibilidad en las ocho vistas avanzadas no encontró botones/enlaces sin nombre, IDs duplicados, inputs sin etiqueta ni overflow horizontal.

La deuda es menor: faltan pruebas automatizadas de contraste WCAG, foco visible en todos los overlays y un modelo explícito `loading/current/stale/error/unavailable` compartido por todas las vistas. El estado actual ya lo aproxima; formalizarlo reduciría regresiones futuras.

## 7. Comparación con otros sistemas

### 7.1 NautilusTrader

NautilusTrader es más fuerte en ejecución: comparte estrategia y algoritmo entre backtest/live, cubre semántica de venue, reconciliación, caché y estados de ejecución. Su documentación también reconoce límites: colas no acotadas, monitoreo apagado por defecto y el runner no limita automáticamente el feed ni detiene trading al cruzar un umbral [7][19]. Ezur es más simple, transparente y honesto en la UI; no tiene su máquina de estados ni adapters. Es un terminal de investigación local, no un sustituto de Nautilus.

### 7.2 Freqtrade

Freqtrade es el peer operativo más cercano: estrategias configurables, persistencia, stoploss/ROI, límites de operaciones, hooks, freqUI, Telegram y API. Su propia documentación advierte que los callbacks live ocurren aproximadamente cada cinco segundos mientras el backtest es vela a vela, lo que puede producir divergencias [15]. Ezur gana en razonamiento determinista, gates de promoción y una UI que no promete datos inexistentes; Freqtrade gana en ecosistema, exchanges y experiencia live.

### 7.3 QuantConnect Lean

Lean es una plataforma event-driven modular para backtest y live en múltiples mercados, con CLI local y contenedores. Su README exige tests para contribuciones [18]. Ezur es más estrecho y fácil de auditar; su motor propio necesita un validador independiente. Lean no es automáticamente “más realista”: el paper trading por defecto de QuantConnect no modela slippage y no conserva el estado del algoritmo tras reinicios [9], justo dos riesgos que Ezur sí aborda.

### 7.4 Backtrader y vectorbt

Backtrader y vectorbt son principalmente capas de investigación. Backtrader documenta fills de mercado, limit, stop y stop-limit, gaps y slippage; su guía live con Interactive Brokers recomienda probar en paper antes de producción [3][16]. VectorBT community consume sobre todo arrays históricos; cross-validation, stop ladders y optimización de portfolios son funciones PRO [17]. Ezur integra motor, API, ledger y terminal, pero esa integración no garantiza corrección: la diversidad de motores sigue siendo necesaria [21].

### 7.5 Hummingbot

Hummingbot está orientado a CLOB/AMM, market making y control remoto multi-bot. Su documentación muestra paper trading, dashboard/API/Telegram y un `make doctor`, pero también advierte que una versión anterior publicaba el puerto 8000 en todas las interfaces [20]. Es un caso de uso distinto. Ezur no debería imitar su amplitad; debería conservar su foco direccional y su disciplina de validación.

### 7.6 Conclusión comparativa

Ezur compite bien en **honestidad, trazabilidad y validación local**. Pierde en **ejecución live, reconciliación, ecosistema y validación independiente**. La estrategia correcta es cerrar la brecha de evidencia antes de añadir venues: primero un motor de referencia, journal y trial ledger; después, si el edge resiste, un adapter y un piloto limitado.

## 8. Estrategia actual: qué dicen los datos

En el corte, el libro paper tiene 13 cierres y P&L neto −719,88. La validación de la UI muestra RECHAZADA y varios gates no medibles. Una muestra de 13 operaciones no permite concluir edge; el sistema lo dice y mantiene el veredicto conservador. El P&L diario puede ser positivo mientras el histórico total es negativo, y la UI lo muestra sin borrar uno para favorecer al otro.

El bootstrap y el IC80 pueden reducir ruido de simulación, pero no crean muestra independiente [4]. Más iteraciones no convierten 13 operaciones en 300. Tampoco un profit factor infinito sin pérdidas prueba una ventaja: significa que el denominador aún no existe. El gate G5 ahora trata ese caso como ilimitado, pero el resto de gates y el tamaño de muestra siguen aplicando.

La hoja de ruta de estrategia debe ser: registrar todos los trials, sellar holdout, ejecutar walk-forward con purga/embargo, probar costes y determinismo, y solo entonces considerar paper extendido o live. El preprint de walk-forward de 2025 es un ejemplo útil: 140 operaciones y resultado agregado no significativo se reporta como inconcluso en lugar de ajustarse hasta encontrar significación [5].

## 9. Plan de acción priorizado

### P0 — antes de cualquier promoción

- [ ] Construir un validador de ejecución independiente con fixtures de gaps, intrabar ambiguity, slippage, comisiones, cierre manual, session close y exposición final.
- [ ] Automatizar el drill de restauración: backup online, restauración desechable, `integrity_check`, conteos, equity y comparación de hashes.
- [ ] Mantener `live_enabled=false` y sin adapter hasta que P0 y P1 estén completos.

### P1 — defensibilidad y operación

- [ ] Token de sesión para mutaciones y WebSocket; mantener Host/Origin como defensa en profundidad.
- [ ] Journal append-only de comandos con ID, hash, actor, resultado, timestamps y correlación con orden/fill.
- [ ] Allowlist de directorios de datasets y límite de filas además del límite de bytes.
- [ ] Trial ledger completo: parámetros, datasets, semillas, features, runs abandonados y veredictos.
- [ ] Atar cada veredicto a hash de spec, config, dataset, código y dependencias; rechazar artefactos obsoletos.
- [ ] Walk-forward cronológico con purga/embargo y bootstrap de bloques para drawdown/exposición.
- [ ] Métricas y trazas: latencia de tick, snapshots por segundo, profundud de cola WS, rechazos por código y backups fallidos.

### P2 — mantenimiento

- [ ] CI con Python 3.14 y frontend; fijar dependencias/lockfile.
- [ ] Tick size por instrumento en feeds simuláticos multi-símbolo.
- [ ] Retención y verificación automática de backups; alertas de fallo.
- [ ] Pruebas WCAG de contraste, foco y overlays.
- [ ] Runbook de incidente y ensayo de kill switch/restore.

## 10. Preguntas abiertas y caveats

1. **¿Quién autorizó la cuarentena externa de #3/#5?** No se tocó durante esta pasada. El backup previo permite investigarlo sin modificar el libro actual.
2. **¿Qué adapter live se usaría?** Sin respuesta, el sistema debe seguir paper-only.
3. **¿Qué motor independiente validará fills y costes?** La paridad del mismo motor no basta.
4. **¿Cuál es el RPO/RTO aceptable?** El backup diario/arranque es un punto de partida; el drill manual no define un objetivo operativo.
5. **¿El histórico de trials está completo?** El ledger actual no demuestra que todas las búsquedas fallidas estén registradas.
6. **¿Las dependencias están reproducibles?** Hay lower bounds, no un lock completo; CI no cubre Python 3.14.
7. **¿El edge sobrevivirá fuera de muestra?** Hoy no hay evidencia; el veredicto RECHAZADA es correcto.

## 11. Cómo interpretar la calificación

Hay tres preguntas distintas detrás de cualquier sistema de trading y Ezur debe responderlas por separado. La primera es **¿el código calcula lo que dice?** La segunda es **¿puede operar y recuperarse sin intervención?** La tercera es **¿la estrategia produce una ventaja neta fuera de muestra?** Una nota alta en la primera no responde la segunda, y ninguna de las dos responde la tercera. La calificación 8,4/10 corresponde a la primera con apoyo de la segunda; el 2,5/10 de live y el 3,0/10 de edge evitan que se confundan.

La escalera de evidencia debe subirse en orden. Los tests unitarios prueban reglas locales; los tests de integración prueban contrato entre motor, store y API; el backtest prueba comportamiento sobre datos históricos; un validador independiente prueba que la semántica de fills y costes no es un error compartido; el paper con datos en vivo prueba operación y persistencia; un piloto live limitado prueba acknowledgments, latencia, parciales y reconciliación. Ezur ha avanzado bastante en los tres primeros escalones y tiene cimientos para el cuarto, pero no debe saltarse los últimos.

La paridad entre backtest y paper es útil, pero limitada. Si ambos usan el mismo `ExecutionEngine`, un error de gap aparece idéntico en los dos y la paridad lo celebra. Por eso el validador independiente no es un lujo académé: es la única forma de detectar errores de semántica que viven en el núcleo. Los fixtures deben ser pequeños, legibles y con resultados esperados escritos antes de ejecutar. Un motor distinto no tiene que ser una plataforma completa; puede ser una referencia event-driven para veinte casos canónicos.

La recuperación también debe medirse, no presumirse. Un backup existe, pero si nadie lo ha restaurado no se conoce su RTO ni su cobertura. El drill manual de esta pasada es una buena señal: la base restaurada abre, pasa `integrity_check` y conserva operaciones y P&L. Falta convertirlo en prueba automática y añadir verificación de hashes, alertas de fallo y retención. Una copia que no se restaura es un archivo, no una estrategia de recuperación.

La seguridad local tiene un modelo de amenaza distinto al de un servicio público. El enemigo principal no es solo un atacante remoto: es una web maliciosa que llama a `localhost`, un DNS rebinding, un proceso local curioso o un operador que pulsa reset sin entender el alcance. Host/Origin y loopback bloquean el primer vector; el token y el journal endurecen los siguientes; el reset con motor parado y reconstrucción de estado reduce el error humano. Ninguno de estos controles convierte la aplicación en un servicio multiusuario, y no debería presentarse como tal.

La complejidad tiene coste. Cada opción de configuración que no cambia comportamiento es una promesa falsa; cada adapter añade estados desconocidos; cada métrica sin fuente invita a optimizar el número equivocado. Ezur ya mostró que puede eliminar opciones muertas o hacerlas fallar visibles. La mejora futura debe medirse por evidencia que añade, no por superficie que crece. Un trial ledger completo vale más que diez indicadores nuevos; un validador independiente vale más que otro broker simulado; una alarma de backup fallido vale más que otro tema visual.

¿Qué elevaría la nota? Un validador independiente y un drill automático acercarían ingeniería a 9/10. Token, journal, allowlist de datasets, trial ledger y CI reproducible acercarían fiabilidad y seguridad a producción de laboratorio. La nota live solo subiría con un adapter real, reconciliación, piloto limitado y observabilidad de venue. La nota de edge solo subiría con una muestra suficiente, veredicto fuera de muestra positivo después de costes y estrés, y resultados que no dependan de unas pocas operaciones. Hasta entonces, la decisión correcta es seguir en paper, preservar el libro y no promocionar la estrategia.

## 12. Metodología

Investigación deep con dos revisores de código independientes, cuatro agentes de recuperación en la primera ola, tres agentes de ampliación de huecos, un agente de verificación de citas, tres revisiones focalizadas posteriores a las correcciones, cinco agentes adicionales para comparar 27 plataformas, un agente de investigación de watchdog/frescura, un agente de investigación de TTL/validez de órdenes y un agente de investigación de caducidad de señales y un agente de investigación de precisión por instrumento. Se priorizaron documentación oficial, papers y guías primarias; los preprints se marcan como tales. Las fuentes se accedieron el 2026-11-24. Los hallazgos de código se verificaron contra el working tree y cada corrección se probó antes de dar el veredicto. Ocho claims de alto impacto de la comparación ampliada se comprobaron de nuevo contra fuentes oficiales y todos resultaron soportados, con matices de alcance registrados en los extractos.

La calificación no es una nota de estrategia ni una recomendación de inversión. Es una medida de madureza técnica después de la pasada de corrección, separada explícitamente de readiness live y de evidencia de ventaja. Ningún resultado paper garantiza rentabilidad futura, y ninguna calificación de software sustituye una decisión de riesgo del operador.

## 13. Comparación ampliada con 27 plataformas adicionales

La muestra incluye bots crypto comerciales, proyectos open source, plataformas retail, servicios cuantitativos con API y plataformas de IA/alertas. Las capacidades se marcan **Verified** cuando la documentación oficial las confirma; la comparación relativa es **Inferred**. Los claims de rendimiento de IA son **Unverified** sin metodología pública. MultiCharts queda **Unverified** por bloqueo de su documentación, y Qraft se interpreta como Qraft Technologies porque `qrafts.ai` ya no es un producto de trading.

| Plataforma | Modelo | Fortaleza documentada | Límite relevante | Posición frente a Ezur |
|---|---|---|---|---|
| QuantRocket | Python, Docker local/cloud | Lifecycle completo: datos, Zipline/Pipeline, backtest, IB/Alpaca, revisión de order-files, riesgo cross-strategy y shortfall [34] | Infraestructura y secretos operados por el usuario; sin estándar de auditoría inmutable documentado | QuantRocket gana en live multi-broker; Ezur en UI honesta y gates explícitos |
| Blueshift | Python event-driven | API consistente backtest/live, pipelines, órdenes y APIs de riesgo [35] | Excluye HFT; hosting y cobertura de datos no quedaron claros | Blueshift gana en abstracción de broker; Ezur en producto local integrado |
| Alpaca | API brokerage alojada | Paper con la misma especificación live, IEX y fills parciales aleatorios [36] | Paper omite impacto, latencia, cola, borrow y fees; no valida tamaño contra liquidez | Alpaca gana en broker real; Ezur en control y transparencia del modelo |
| Interactive Brokers | API/FIX/TWS multi-activo | 175 mercados en 40 países, órdenes avanzadas y drop copy [37] | Paper usa top-of-book y tiene órdenes no soportadas; no es un backtester integrado [38] | IB gana en amplitud; Ezur en validación y razonamiento visible |
| NinjaTrader | Desktop de futuros | Strategy Builder genera NinjaScript; backtest, optimización y simulated forward [39] | La propia guía advierte overfitting y diferencias sim/live; no documenta API externa ni auditoría completa | NinjaTrader gana en ecosistema de futuros; Ezur en protocolo de promoción |
| TradeStation | Desktop/API multi-activo | EasyLanguage, backtesting, sandbox y API de acciones/opciones/futures [40] | Onboarding y posibles demoras/fallos; riesgo y auditoría no detallados | TradeStation gana en broker retail; Ezur en código y datos propios |
| MetaTrader 5 | EA multi-activo vía broker | Tester con ticks reales/generados, delay, requotes, márgenes, forward y Journal [41] | Órdenes pendientes no reciben delay de red; margen desactivado en modo pip; no es broker | MT5 gana en realismo de tester; Ezur en PBO/holdout y UI contextual |
| cTrader | cBots C#/Python local/cloud | FX/CFD, backtesting/optimización, OpenAPI y FIX [42] | Riesgo y auditoría no detallados en la guía recuperada | cTrader gana en brokers FX; Ezur en investigación direccional auditable |
| MultiCharts | Plataforma retail | Solo se verificó su uso de la API de TradeStation [40] | Documentación oficial 403; resto **Unverified** [43] | No se puede calificar con evidencia suficiente |
| OctoBot | Python self-hosted | 15+ exchanges CCXT, grid/DCA/AI/TradingView, backtest en instancias manuales, paper y live [44] | La versión 3.0 beta es WIP; mecanismos muy complejos pueden no encajar | OctoBot gana en exchanges y UI visual; Ezur en gates y auditoría de decisión |
| Jesse | Python/Rust, dashboard | Multi-símbolo/timeframe, optimización, Monte Carlo, significancia, `risk_to_qty` y muchas rutas live [45] | Varios exchanges premium, sin backtest en algunas rutas y Alpaca beta | Jesse es el peer técnico más cercano; Ezur gana en honestidad UI, Jesse en amplitud live |
| Superalgos | Visual Node/browser | Data mining, backtesting, paper/live, multi-servidor y nodos de stop [46] | Curva de aprendizaje alta; release 1.6.1 de 2024 pese a actividad reciente | Superalgos gana en flexibilidad visual; Ezur en simplicidad y foco |
| Gekko | Node.js legacy | Plugins de estrategia, paper/live y backtest con fees/slippage [47] | Archivado y no mantenido desde 2020 | No es candidato de producción en 2026 |
| Zenbot | Node.js/MongoDB legacy | Simulación, paper/live y stops configurables [48] | Archivado desde 2022; el README exige supervisión y no detiene pérdidas excesivas | No es candidato de producción en 2026 |
| Tribeca | TypeScript market making | Backtester, API, web y controles de quoting/posición [49] | Master de 2018, stack Node 7.8 y TODOs; mantenimiento no confirmado | No compite con el foco direccional de Ezur |
| 3Commas | SaaS crypto | DCA con safety orders, TP/SL/trailing y optimizador; Stop puede mantener o cerrar posiciones [50] | Backtest limitado a 30 días; semántica de halt distinta de flatten | 3Commas gana en facilidad/exchanges; Ezur en validación profunda |
| Cryptohopper | SaaS crypto | Paper con datos reales y fondos simulados [51] | La página recuperada no establece backtest, riesgo ni kill switch | Cryptohopper gana en producto cloud; Ezur en transparencia local |
| Gunbot | Motor local + browser | Backtest spot/futures con trades, drawdown, fees, exposición y ledger [52] | No reproduce latencia, outages, liquidez futura ni slippage | Gunbot gana en mercados; Ezur en declarar límites del modelo |
| HaasOnline | SaaS/local | Clonar paper a live, tests históricos, Deactivate y Cancel All Orders [53] | Capacidad por licencia; no documenta liquidate-all global | HaasOnline gana en operación multi-bot; Ezur en código propio |
| ProfitTrader | GUI local | Test Mode visible, Stop ProfitTrailer y Sell Only Mode [54] | La guía no confirma backtest, API ni fecha de mantenimiento | ProfitTrader gana en simplicidad de consola; Ezur en investigación |
| Autoview | Alertas/webhook | Convierte alertas en órdenes Deribit, `d=1` log-only y Testnet [55] | Sin backtester nativo; `c=all` y `b=flat` no soportados en Deribit | Autoview gana en ejecución de alertas; Ezur integra señal, riesgo y validación |
| Trade Ideas | Scanner IA + broker | Holly genera señales; Brokerage Plus envía órdenes a brokers [56] | Money Machine sigue en simulated mode; muchos signals fallan y no hay metodología IA pública | Trade Ideas gana en discovery; Ezur no finge edge ni ejecución IA |
| Composer | Brokerage no-code US | Lenguaje natural, backtest con fees/slippage y ejecución automática [57] | Sin paper workflow ni event log documentados; ventana de ejecución limitada | Composer gana en accesibilidad; Ezur en auditoría local |
| Qraft Technologies | Institucional | Ejecución, monitoring, post-trade y TCA con algoritmos IA [58] | Sin self-serve retail, paper o controls de riesgo documentados | No es un peer retail directo |
| Capitalise.ai | Escenarios en lenguaje natural | Backtest, simulación y ejecución con sizing/stops; brokers partner [59] | Fidelity solo señales; sin exportación de auditoría documentada | Capitalise gana en UX expresiva; Ezur en control del pipeline |
| Alertatron | Ejecución de alertas | Muchos exchanges, Testnet, logs/PnL, stops y sizing [60] | Historial limitado a 7/30/45 días; latencia “<1 s” es claim del vendor | Alertatron gana en conectividad; Ezur en investigación y procedencia |
| TradingView Webhooks | Transporte de alertas | POST con status de entrega y logging [61] | No ejecuta órdenes ni hace backtest; timeout de 3 s y puede fallar | TradingView es una capa de entrada, no un bot completo |

### 13.1 Patrones que aparecen en la muestra

**Los bots crypto comerciales optimizan amplitud y facilidad.** 3Commas, Cryptohopper, Gunbot, HaasOnline, ProfitTrader y Autoview cubren muchos exchanges y flujos paper/live, pero la documentación revisada no confirma un marco equivalente de holdout sellado, walk-forward, Monte Carlo y promoción. Esto no prueba que no exista; sí prueba que no se puede asumir.

**Open source no es sinónimo de mantenido.** OctoBot y Jesse tienen actividad de noviembre de 2026; Superalgos tiene actividad reciente pero un release estable antiguo. Gekko y Zenbot están archivados y Tribeca lleva años sin moverse. Ezur no tiene la comunidad de Jesse u OctoBot, pero su código y su roadmap son locales y auditables.

**Las plataformas retail tienen ejecución madura, no validación automática.** NinjaTrader, TradeStation, MT5 y cTrader ofrecen backtest, optimización y conexión a brokers. La calidad del backtest y la disciplina del usuario siguen separadas. MT5 documenta controles de realismo especialmente ricos; Ezur documenta gates de evidencia especialmente ricos.

**Las APIs cuantitativas delegan operaciones en el usuario.** QuantRocket es el lifecycle más completo de la muestra, pero requiere operar Docker, datos, secretas y brokers. Alpaca e IB ofrecen paper/live real con limitaciones explícitas. Ezur no las reemplaza; puede ser una capa de investigación y control más transparente.

**La IA suele ser señal o composición, no ejecución verificable.** Trade Ideas separa Holly de Money Machine, que aún es simulado; Composer y Capitalise automatizan reglas del usuario; Alertatron ejecuta alertas externas. Ninguna fuente recuperada publica una metodología independiente que convierta sus claims de IA en evidencia de edge.

### 13.2 Dónde queda Ezur

Ezur no es el bot con más exchanges, ni el más fácil, ni el más maduro en ejecución real. Su posición es distinta: **terminal local de investigación y paper con contrato de datos explícito, razón determinista, libro auditable, gates de promoción y UI que no maquilla ausencias**. Jesse y QuantRocket son los peers técnicos más serios; 3Commas/Cryptohopper/Haas son los operativos; MT5/NinjaTrader/TradeStation son los de ejecución retail; Trade Ideas/Composer/Capitalise son los de automatización expresiva.

La recomendación sigue siendo no imitar el recuento de features. La próxima brecha que conviene cerrar es la que los peers sí tienen y Ezur no: **validador independiente, journal de comandos, reconciliación y, solo si el edge resiste, un adapter limitado con piloto**. La amplitud de mercado viene después.

## Bibliografía

1. Bailey, David H.; López de Prado, Marcos. *The Deflated Sharpe Ratio*. 2014. https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf — Tier 1.
2. Bailey, David H.; Borwein, Jonathan M.; López de Prado, Marcos; Zhu, Qiji Jim. *The Probability of Backtest Overfitting*. 2015/2017. https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf — Tier 1.
3. Backtrader / Daniel Rodriguez. *Broker – Slippage*. https://www.backtrader.com/docu/slippage/slippage/ — Tier 1.
4. SciPy developers. *scipy.stats.bootstrap*. https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.bootstrap.html — Tier 1.
5. Deep, Gagan; Deep, Akash; Lamptey, William. *Interpretable Hypothesis-Driven Trading*. arXiv:2512.12924, 2025. https://arxiv.org/html/2512.12924v1 — Tier 2, preprint.
6. OKX. *OKX API guide*. https://www.okx.com/docs-v5/en/ — Tier 1.
7. NautilusTrader. *Execution*. https://nautilustrader.io/docs/latest/concepts/execution/ — Tier 1.
8. FINRA. *Regulatory Notice 15-09*. 2015. https://www.finra.org/rules-guidance/notices/15-09 — Tier 1.
9. QuantConnect. *Paper Trading*. https://www.quantconnect.com/docs/v2/cloud-platform/live-trading/brokerages/quantconnect-paper-trading — Tier 1.
10. SQLite. *Write-Ahead Logging*. https://www.sqlite.org/wal.html — Tier 1.
11. OpenTelemetry / CNCF. *Logs*. https://opentelemetry.io/docs/concepts/signals/logs/ — Tier 1.
12. Google SRE. *Managing Incidents*. https://sre.google/sre-book/managing-incidents/ — Tier 1.
13. OWASP. *ASVS Overview v5.0.0*. https://asvs.owasp.org/ — Tier 1.
14. React. *Synchronizing with Effects*. https://react.dev/learn/synchronizing-with-effects — Tier 1.
15. Freqtrade. *Bot Basics*. https://www.freqtrade.io/en/stable/bot-basics/ — Tier 1.
16. Backtrader. *Live Trading – Interactive Brokers*. https://www.backtrader.com/docu/live/ib/ib/ — Tier 1.
17. vectorbt. *VectorBT vs PRO*. https://vectorbt.dev/getting-started/upgrade/ — Tier 1.
18. QuantConnect. *Lean README*. https://github.com/QuantConnect/Lean#readme — Tier 1.
19. NautilusTrader. *Live Trading*. https://nautilustrader.io/docs/latest/concepts/live/ — Tier 1.
20. Hummingbot Foundation. *Documentation*. https://hummingbot.org/docs/ — Tier 1.
21. Yin, Don; Miki, Takeshi; Lesnichenko, Vladislav; Gural, Vasyl. *Implementation Risk in Portfolio Backtesting*. arXiv:2603.20319, 2026. https://arxiv.org/html/2603.20319v1 — Tier 2, preprint no verificado.
22. Hudson & Thames. *Chapter 7: Cross-Validation in Finance*. https://github.com/hudson-and-thames/example-notebooks/blob/main/Cross_validation/Chapter7_Cross_Validation.ipynb — Tier 2.
23. Arnott, Rob; Harvey, Campbell; Markowitz, Harry. *A Backtesting Protocol in the Era of Machine Learning*. 2019. https://people.duke.edu/~charvey/Research/Published_Papers/P138_A_backtesting_protocol.pdf — Tier 1.
24. Politis, Dimitris N.; Romano, Joseph P. *The Stationary Bootstrap*. 1994. https://users.ssc.wisc.edu/~bhansen/718/Politis%20Romano.pdf — Tier 1.
25. scikit-learn. *TimeSeriesSplit*. https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html — Tier 1.
26. SQLite. *Backup API*. https://www.sqlite.org/backup.html — Tier 1.
27. FastAPI. *TrustedHostMiddleware*. https://fastapi.tiangolo.com/advanced/middleware/#trustedhostmiddleware — Tier 1.
28. Kent, Karen; Souppaya, Murugiah. *NIST SP 800-92: Guide to Computer Security Log Management*. 2006. https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-92.pdf — Tier 1.
29. Binance. *Spot API Documentation – Trading Endpoints*. https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md — Tier 1.
30. U.S. SEC, Division of Trading and Markets. *Responses to FAQs Concerning Risk Management Controls for Brokers or Dealers with Market Access*. 2014. https://www.sec.gov/divisions/marketreg/faq-15c-5-risk-management-controls-bd.htm — Tier 1.
31. CME Group / EBS. *EBS Dealing Rules: FX Spot+ Appendix*. Effective 2025-04-14. https://www.cmegroup.com/trading/market-tech-and-data-services/files/ebs-dealing-rules-fx-spotplus-appendix-effective-041425.pdf — Tier 1.
32. Binance. *How to manage a local order book correctly* and *Websocket Market Streams*. https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/How-to-manage-a-local-order-book-correctly.md ; https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect.md — Tier 1.
33. Freqtrade. *Configuration: Using Dry-run Mode*. https://www.freqtrade.io/en/stable/configuration/#using-dry-run-mode — Tier 1.
34. QuantRocket. *Data-Driven Trading with Python*. https://www.quantrocket.com/ — Tier 1, accessed 2026-11-24.
35. QuantInsti / Blueshift. *API Documentation — Introduction*, v4.0.0. https://blueshift.quantinsti.com/api-docs/introduction.html — Tier 1, accessed 2026-11-24.
36. Alpaca. *Paper Trading*, updated 2026-07-07. https://docs.alpaca.markets/docs/paper-trading/ — Tier 1.
37. Interactive Brokers. *IBKR Trading API Solutions*. https://www.interactivebrokers.com/en/trading/ib-api.php — Tier 1, accessed 2026-11-24.
38. Interactive Brokers. *Paper Trading Account*, modified 2026-10-13. https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/ — Tier 1.
39. NinjaTrader. *Strategy Builder: Automated Futures Strategies Without Coding*. https://ninjatrader.com/trading-platform/trading-simulator/automated-futures-strategies-without-coding/ — Tier 1, accessed 2026-11-24.
40. TradeStation. *Fintech Solutions / Developer Portal*. https://developer.tradestation.com/ — Tier 1, accessed 2026-11-24.
41. MetaQuotes. *MetaTrader 5 — Strategy Testing*. https://www.metatrader5.com/en/terminal/help/algotrading/testing — Tier 1, accessed 2026-11-24.
42. Spotware. *cTrader & Store Basics*. https://ctrader.com/guide — Tier 1, accessed 2026-11-24.
43. MultiCharts. *Official Documentation* — retrieval attempt, HTTP 403. https://www.multicharts.com/documentation/ — Tier 1 target, content inaccessible.
44. Drakkar-Software. *OctoBot — Free Open Source Crypto Trading Bot*, master 2026-11-19. https://github.com/Drakkar-Software/OctoBot — Tier 1.
45. Jesse AI. *jesse-ai/jesse — Advanced Python Algorithmic Trading Framework*, release 3.7.0, 2026-11-23. https://github.com/jesse-ai/jesse — Tier 1.
46. Superalgos. *Superalgos/Superalgos — Open-Source Crypto Trading Platform*. https://github.com/Superalgos/Superalgos — Tier 1, checked 2026-11-24.
47. Mike van Rossum / Gekko contributors. *askmike/gekko*, archived 2020-02-16. https://github.com/askmike/gekko — Tier 1.
48. DeviaVir / Zenbot contributors. *DeviaVir/zenbot*, archived 2022-02-15. https://github.com/DeviaVir/zenbot — Tier 1.
49. Michael Grosner. *michaelgrosner/tribeca*, master 2018-02-26. https://github.com/michaelgrosner/tribeca — Tier 1.
50. 3Commas. *How the DCA Bot Works: Strategy & Setup Guide*, 2026-11-24. https://help.3commas.io/en/articles/16281102-how-the-dca-bot-works-strategy-setup-guide — Tier 1.
51. Cryptohopper. *What is Paper Trading*. https://docs.cryptohopper.com/docs/fundamentals/paper-trading — Tier 1, accessed 2026-11-24.
52. Gunbot. *Gunbot Backtesting for Spot & Futures Strategies*, 2026-07-16. https://live.gunbot.com/features/backtesting — Tier 1.
53. HaasOnline. *Bot Management*, 2025-12-15. https://help.haasonline.com/interface/bots/bot-management/ — Tier 1.
54. ProfitTrailer. *Web Interface Guide*. https://wiki.profittrailer.com/en/webinterfaceguide — Tier 1, accessed 2026-11-24.
55. Autoview. *Run a Deribit Trading Bot From Alerts*, 2026-10-18. https://autoview.com/guides/deribit-trading-bot/ — Tier 1.
56. Trade Ideas. *Features: Scanner, Screener, Backtesting, AI*. https://www.trade-ideas.com/features/ — Tier 1, accessed 2026-11-24.
57. Composer. *Composer by SoFi — Trading. Built Better.* https://www.composer.trade/ — Tier 1, accessed 2026-11-24.
58. Qraft Technologies. *Market Intelligence & Execution*. https://www.qraftec.com/market-intelligence-execution — Tier 1, accessed 2026-11-24. Identity caveat: https://qrafts.ai/ is not a trading product.
59. Capitalise.ai. *Explore Trading Features* and *Get Started*. https://capitalise.ai/explore-trading-features/ ; https://capitalise.ai/getstarted/ — Tier 1, accessed 2026-11-24.
60. Alertatron. *Automate trading from TradingView alerts*. https://alertatron.com/ — Tier 1, accessed 2026-11-24.
61. TradingView. *How to configure webhook alerts*. https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/ — Tier 1, accessed 2026-11-24.
62. OKX. *API Guide v5 — WebSocket / Connect*. https://www.okx.com/docs-v5/en/#overview-websocket-connect — Tier 1, accessed 2026-11-24.
63. Binance. *Spot API — WebSocket Streams*. https://raw.githubusercontent.com/binance/binance-spot-api-docs/master/web-socket-streams.md — Tier 1, accessed 2026-11-24.
64. NautilusTrader. *Actors*. https://nautilustrader.io/docs/latest/concepts/actors/ — Tier 1, accessed 2026-11-24.
65. Freqtrade. *Telegram Usage — pause, stopentry, cancel and forceexit*. https://www.freqtrade.io/en/stable/telegram-usage/ — Tier 1, accessed 2026-11-24.
66. Binance. *Spot API — ENUM Definitions*, source commit 2026-11-11. https://developers.binance.com/en/docs/products/spot/enums — Tier 1.
67. NautilusTrader. *Orders*, source commit 2026-10-16. https://nautilustrader.io/docs/latest/concepts/orders/ — Tier 1.
68. Jesse. *Changelog*, releases 2026-11-03 and 2026-11-23. https://docs.jesse.trade/docs/changelog — Tier 2, official changelog.
69. OKX. *API Guide v5 — Get Instruments*. https://www.okx.com/docs-v5/en/#public-data-rest-api-get-instruments — Tier 1, accessed 2026-11-24.
70. Binance. *Spot API — Filters*. https://developers.binance.com/en/docs/products/spot/filters — Tier 1, accessed 2026-11-24.
71. NautilusTrader. *Instruments*. https://nautilustrader.io/docs/latest/concepts/instruments/ — Tier 1, accessed 2026-11-24.
72. QuantConnect Lean. *SymbolProperties.cs* and *BinanceBrokerageModel.cs*. https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Securities/SymbolProperties.cs ; https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Brokerages/BinanceBrokerageModel.cs — Tier 1, official source.
73. QuantConnect Lean. *Key Concepts* and *OrderSizing.cs*. https://www.quantconnect.com/docs/v2/writing-algorithms/trading-and-orders/key-concepts ; https://raw.githubusercontent.com/QuantConnect/Lean/master/Common/Orders/OrderSizing.cs — Tier 1, official docs/source.

## Extractos de fuentes

1. **Deflated Sharpe Ratio.** Ajusta la significancia por número y dispersión de trials, longitud de muestra, asimetría y curtosis. No repara leakage, datos malos ni ejecución irreal.
2. **Probability of Backtest Overfitting.** CSCV estima la probabilidad de que el ganador in-sample quede por debajo de la mediana out-of-sample. No evalúa la corrección del backtest ni sustituye un holdout bien sellado.
3. **Backtrader slippage.** Distingue market, limit, stop y stop-limit; los parámetros de slippage por defecto pueden ser cero y no todos los modelos cambian con la misma configuración.
4. **SciPy bootstrap.** Proporciona intervalos percentuales, basic y BCa y control de RNG. La cobertura supone muestras aleatorias; no preserva automáticamente dependencia serial.
5. **Walk-forward preprint.** Usa información estricta, 34 trimestres, next-open, costes, intervalos y permutaciones. Con 140 operaciones y p=0,34 reporta resultado no significativo.
6. **OKX API.** Firmas HMAC-SHA256, timestamp de 30 segundos, límites por endpoint/usuario/instrumento. `clOrdId` tiene unicidad entre pendientes; cancel aceptado no es terminal.
7. **Nautilus execution.** Máquina de estados de riesgo, resultados desconocidos persistentes, reconciliación y deduplicación por `trade_id`.
8. **FINRA 15-09.** Validación independiente, testing segregado, pilotos limitados, monitoreo, conciliación y desactivación rápida.
9. **QuantConnect paper.** Órdenes de mercado inmediatas y completas, sin slippage por defecto; reinicios no preservan estado del algoritmo.
10. **SQLite WAL.** WAL es estado persistente y debe acompañar a la base al copiarla. `synchronous=FULL` y `NORMAL` tienen garantías distintas ante pérdida de energía.
11. **OpenTelemetry logs.** Logs estructurados con campos tipados y correlación automática con trazas. No define retención ni inmutabilidad.
12. **Google SRE incidents.** Roles separados, documento vivo y preservación de evidencia; practicar mediante drills.
13. **OWASP ASVS.** Requisitos versionados para diseñar, desarrollar y probar aplicaciones y servicios.
14. **React Effects.** El cleanup debe abortar o ignorar resultados de fetch que ya no son relevantes.
15. **Freqtrade basics.** Callbacks live aproximadamente cada cinco segundos frente a backtest vela a vela; puede causar diferencias.
16. **Backtrader live IB.** Recomienda paper/demo antes de producción y documenta límites de estado y mensajes perdidos.
17. **vectorBT PRO.** Community consume arrays históricos; PRO añade cross-validation, stop ladders, optimización y streaming.
18. **Lean README.** Plataforma event-driven modular para backtest/live; contribuciones deben incluir tests.
19. **Nautilus live.** Comparte código estrategia/ejecución, reconcilia al arrancar y expone métricas; el runner no limita automáticamente el feed.
20. **Hummingbot docs.** Controllers, paper trading, dashboard/API y `make doctor`; advierte sobre puertos públicos preexistentes.
21. **Implementation risk preprint.** Compara 15 estrategias y reporta divergencias de hasta 3,71 puntos porcentuales con costes altos. Es un lead, no una conclusión peer-reviewed.
22. **Hudson & Thames CV.** Purga información solapada, elimina shuffle y aplica embargo; registrar solo resultados positivos de 1.000 configuraciones es sesgo de selección.
23. **Backtesting protocol.** Registrar modelos y variables exitosos y fallidos; ajustar después de ver un holdout lo convierte en in-sample.
24. **Stationary bootstrap.** Remuestrea bloques de longitud aleatoria preservando orden interno; permite recalcular estadísticas dependientes del camino. Su formalización asume estacionariedad estricta y dependencia débil.
25. **TimeSeriesSplit.** Ventanas cronológicas expansivas o rolling con `gap`; no purga labels solapados.
26. **SQLite backup.** Copia online consistente con bloqueos breves; escrituras concurrentes pueden reiniciar la copia.
27. **TrustedHostMiddleware.** Valida Host y devuelve 400; no es autenticación, CSRF ni validación de Origin.
28. **NIST SP 800-92.** Acceso append-only cuando sea posible, archivos protegidos con digests y pruebas activas de logs.
29. **Binance spot API.** `newClientOrderId` es único entre órdenes abiertas; no es idempotencia histórica permanente y permite consultar/cancelar por IDs.
30. **SEC market-access controls.** Los controles aplican a todas las órdenes, incluidas las generadas por computadora, y deben bloquear parámetros erróneos antes del routing. No sustituye el bloqueo pre-trade por cancelación posterior.
31. **EBS halt semantics.** Durante un halt, las Day Orders se cancelan, el matching rechaza nuevas órdenes y las cancelaciones siguen permitidas. La semántica depende del venue.
32. **Binance local order book.** Buffer + snapshot REST + continuidad `pu`/`u`; un salto de secuencia obliga a reiniciar. La conexión tiene ping/pong y vida útil de 24 horas.
33. **Freqtrade dry-run.** Simula wallets y fills, con slippage máximo del 5 %, límites que pueden convertirse en mercado y órdenes abiertas asumidas sin fill tras reinicio. Es ensayo, no evidencia de venue.
34. **QuantRocket.** Plataforma Python self-hosted con investigación, backtest, ejecución multi-broker, revisión de órdenes y riesgo cross-strategy. El usuario opera infraestructura, datos y secretos.
35. **Blueshift.** Motor event-driven Python con API de backtest/live, pipelines, órdenes y riesgo. Excluye HFT y advierte sobre código rogue, feeds corruptos y conectividad.
36. **Alpaca paper.** Misma API que live, datos IEX y parciales aleatorios. No modela impacto, latencia, cola, borrow ni varios fees; no valida tamaño contra liquidez.
37. **IBKR API.** REST/WebSocket, FIX y TWS API; 175 mercados, órdenes avanzadas y drop copy. La página no documenta un backtester integrado ni controles de riesgo configurables.
38. **IBKR paper.** Top-of-book, sin deep book; VWAP/Auction/RFQ/Pegged no soportados y stops complejos se comportan distinto.
39. **NinjaTrader.** Strategy Builder genera NinjaScript con entradas, salidas, stops, targets y filtros; backtest, optimización y simulated forward. Advierte overfitting y diferencias sim/live.
40. **TradeStation.** EasyLanguage, backtesting, sandbox y API multi-activo para acciones, opciones y futuros. Onboarding y latencia/fallos son riesgos documentados.
41. **MetaTrader 5.** Tester con ticks reales/generados, delay, requotes, márgenes, forward y Journal; el trade-request history se documenta en el Toolbox del visual tester. Limitaciones en pending orders y margen pip.
42. **cTrader.** cBots C#/Python, ejecución local/cloud, FX/CFD, OpenAPI y FIX. La guía confirma backtest/optimización, pero no detalla auditoría/riesgo.
43. **MultiCharts.** Solo se verificó integración con API de TradeStation; la documentación propia devolvió 403.
44. **OctoBot.** Python self-hosted, 15+ exchanges CCXT, estrategias visuales/AI/TradingView, paper y live; el backtest integrado está disponible en instancias manuales. La beta 3.0 es WIP.
45. **Jesse.** Python/Rust, dashboard, multi-timeframe, optimización, Monte Carlo, significancia y `risk_to_qty`; `risk_per_capital` usa porcentajes enteros. Varias funciones/exchanges son premium o beta.
46. **Superalgos.** Plataforma visual Node/browser con data mining, backtest, paper/live, multi-servidor y stops. Curva de aprendizaje alta y release estable antiguo.
47. **Gekko.** Backtest/paper/live con plugins y fees/slippage; el repositorio original está archivado y no mantenido desde 2020, aunque pueden existir forks mantenidos.
48. **Zenbot.** Simulación/paper/live y stops; archivado desde 2022 y el README exige supervisión.
49. **Tribeca.** Market making TypeScript con backtester, API y controles de quoting; master de 2018 y stack antiguo.
50. **3Commas.** DCA con safety orders, TP/SL/trailing, límite de posiciones y optimizador de 30 días. Stop puede mantener o cerrar posiciones.
51. **Cryptohopper paper.** Datos reales con fondos simulados; una cuenta paper y bots por exchange. La página no establece backtest/riesgo/kill switch.
52. **Gunbot.** Backtest spot/futures con ledger, drawdown, fees y exposición. No reproduce latencia, outages, liquidez futura ni slippage.
53. **HaasOnline.** Clonado paper→live, tests históricos, Deactivate y Cancel All Orders. La capacidad de bots activos depende de licencia.
54. **ProfitTrader.** GUI local con Test Mode, Stop y Sell Only. La guía no confirma backtest/API ni mantenimiento.
55. **Autoview.** Alertas a órdenes Deribit, log-only `d=1`, Testnet y reduce-only. No tiene backtester nativo y no soporta all/flat en Deribit.
56. **Trade Ideas.** Holly genera señales; Brokerage Plus envía órdenes, pero Money Machine sigue simulated. No hay metodología IA independiente pública.
57. **Composer.** Estrategias no-code/lenguaje natural, backtest con costes y ejecución automática vía brokerage US. Sin paper ni event log documentados.
58. **Qraft.** Infraestructura institucional de ejecución, monitoring y TCA con algoritmos IA. Sin workflow retail self-serve documentado.
59. **Capitalise.** Escenarios en lenguaje natural con backtest, simulación, sizing y stops. La ejecución depende del broker; Fidelity es solo señales.
60. **Alertatron.** Ejecuta alertas en muchos exchanges con Testnet, stops, sizing y logs. El historial de trading queda limitado a 7/30/45 días por plan; alertas y charts tienen retención distinta. Latencia es claim del vendor.
61. **TradingView webhooks.** Transporte POST de alertas con status de entrega. No ejecuta órdenes ni hace backtest; timeout de 3 s y fallos posibles.
62. **OKX WebSocket.** Si no hay datos durante 30 segundos, enviar ping; si no hay pong, error o reconexión. Es liveness de transporte, no un umbral de frescura de vela.
63. **Binance WebSocket.** Ping cada 20 segundos, desconexión tras un minuto sin pong; ticker/kline tienen cadencias documentadas. Un salto `U` exige descartar el libro local y resincronizar.
64. **Nautilus actors.** Timers y alertas independientes de callbacks de mercado. `CONNECTED` indica transporte, no autenticación, replay de suscripciones ni adapter listo.
65. **Freqtrade Telegram.** `/pause`/`stopentry` bloquea entradas nuevas mientras gestiona operaciones abiertas; cancelar y `forceexit` son acciones separadas. La pausa no persiste tras reinicio.
66. **Binance enums.** IOC intenta llenar antes de expirar; FOK expira si no puede llenarse completo. Son reglas de ejecución, no vigencia de señal.
67. **Nautilus orders.** `PENDING_UPDATE`/`PENDING_CANCEL` siguen abiertos e in-flight; fills posteriores a expiración aún actualizan orden y posición. Time-in-force depende del venue.
68. **Jesse changelog.** Corrige estrategias live/paper que operaban con velas no terminadas y mejora la detección de fills de mercado cuando las actualizaciones del exchange llegan tarde.
69. **OKX instruments.** `tickSz` es el incremento mínimo de precio; `lotSz` el incremento de cantidad y `minSz` el tamaño mínimo. Opciones/eventos pueden usar bandas de tick.
70. **Binance filters.** `PRICE_FILTER` exige múltiplos de `tickSize`; `LOT_SIZE` exige múltiplos de `stepSize`; `MARKET_LOT_SIZE` define reglas separadas para mercado.
71. **Nautilus instruments.** `price_precision`/`size_precision` son decimales máximos; `price_increment`/`size_increment` son pasos mínimos. El RiskEngine no redondea ni valida incrementos automáticamente.
72. **Lean SymbolProperties.** Tick, lote y mínimo de orden viven por símbolo/mercado/tipo; el brokerage model valida mínimo de notional.
