# Investigación: dónde estamos frente al resto

Fecha: 2026-11-23. Revisión: 2026-11-28. Método: métricas de GitHub obtenidas en
vivo de la API pública (estrellas, forks, último push, licencia, issues abiertos)
y evaluación técnica de cada proyecto a partir de su documentación y su
arquitectura. Lo que no pude verificar aparece marcado como tal. Ningún número de
este documento es estimado a ojo: los de GitHub son los que devolvió la API ese
día y los totales son la suma ponderada de la matriz.

La revisión de 2026-11-28 recalcula todos los totales con la ponderación declarada
(antes no cuadraban), contrasta las notas propias con el código y corrige
validación (9→8) y datos (3→5). Las notas por criterio de los competidores son
las de la revisión original y no se re-auditaron; solo se corrigió su total.
El cierre del mismo día devuelve validación a 9 al cablear el candado del holdout
en el runner y unificar la medición de G8/G2/G1/G3/G14 entre CLI y API; el total
propio se recalcula con esa nota. No se cambió ningún peso.

## 1. Qué hay ahí fuera (datos reales)

| Proyecto | ★ | Forks | Último push | Lenguaje | Licencia | Issues |
|---|---:|---:|---|---|---|---:|
| freqtrade/freqtrade | 57.171 | 11.802 | 2026-11-23 | Python | GPL-3.0 | 29 |
| nautechsystems/nautilus_trader | 31.751 | 4.338 | 2026-11-22 | Rust | LGPL-3.0 | 130 |
| mementum/backtrader | 23.783 | 5.330 | 2024-08-19 | Python | GPL-3.0 | 64 |
| QuantConnect/Lean | 22.659 | 5.444 | 2026-11-20 | C# | Apache-2.0 | 334 |
| hummingbot/hummingbot | 21.356 | 5.168 | 2026-11-20 | Python | Apache-2.0 | 217 |
| quantopian/zipline | 20.264 | 5.066 | 2024-02-13 | Python | Apache-2.0 | 368 |
| polakowo/vectorbt | 9.917 | 1.324 | 2026-11-11 | Python | NOASSERTION | 133 |
| kernc/backtesting.py | 9.281 | 1.594 | 2026-08-05 | Python | AGPL-3.0 | 114 |
| jesse-ai/jesse | 8.828 | 1.295 | 2026-11-17 | Python | MIT | 9 |
| Drakkar-Software/OctoBot | 6.973 | 1.330 | 2026-11-21 | Python | GPL-3.0 | 195 |
| Superalgos/Superalgos | 5.816 | 5.991 | 2026-11-14 | JavaScript | Apache-2.0 | 107 |
| robswc/tradingview-webhooks-bot | 782 | 210 | 2024-02-29 | Python | GPL-3.0 | 18 |
| **este repositorio** | — | — | — | Python + TS | — | — |

Estrellas no es calidad: `backtrader` tiene 23.783 y lleva dos años sin commit;
`hummingbot` tiene 21.356 y su backtester es prácticamente inexistente.

## 2. Rúbrica

Ocho criterios ponderados. La ponderación es una opinión explícita, no un hecho:
pesa más lo que rompe cuentas (ejecución) y lo que produce falsos positivos
(disciplina de validación).

| # | Criterio | Peso | Qué mide |
|---|---|---:|---|
| 1 | Ejecución en vivo | 25 % | Conectores reales, órdenes, reconciliación, reconexión |
| 2 | Disciplina de validación | 20 % | Anti-sobreajuste: puertas, holdout, costes, determinismo |
| 3 | Backtesting realista | 15 % | Modelo de fill, costes, barras ambiguas, sesiones |
| 4 | Gestión de riesgo | 10 % | Tamaño por riesgo, límites diarios, emergencia |
| 5 | Interfaz y observabilidad | 10 % | UI, gráfico, estado en vivo, diagnóstico |
| 6 | Extensibilidad y agnosticismo | 10 % | Añadir estrategia/activo sin tocar el núcleo |
| 7 | Documentación | 5 % | Claridad, ejemplos, honestidad |
| 8 | Datos de mercado | 5 % | Feeds, histórico, rolls, calidad |

## 3. Notas por proyecto

**Freqtrade (7,0/10)** — El estándar de facto en cripto. `ccxt` le da 100+ exchanges,
dry-run real, FreqUI es una UI web competente, Telegram, Docker. Su debilidad es
la disciplina estadística: `hyperopt` optimiza in-sample con un sesgo conocido, y
el análisis de *lookahead* avisa pero no impide. Riesgo por operación básico
(stake fijo o tamaño por saldo), sin límite de pérdida diaria nativo.

**NautilusTrader (7,0/10)** — Lo técnicamente mejor construido: núcleo Rust,
event-driven, paridad backtest/live, nanosegundos, tipos de dominio serios. Cuesta
entrar y no opina sobre validación: te da el motor, no el método. Sin UI propia.

**QuantConnect LEAN (7,7/10)** — Institucional: datos, `alpha streams`, risk
management integrado (`MaximumDrawdownPercentPerSecurity`, etc.), cloud. C#
pesado para iterar, y el código del usuario vive dentro de su plataforma.

**Hummingbot (6,0/10)** — Ejecución y market making de primera; backtesting casi
nulo. Es una herramienta de ejecución, no de investigación.

**Jesse (6,4/10)** — API de backtest muy limpia, sintaxis agradable, buen
`optimize` con advertencias. Solo cripto, live limitado a pocos exchanges, sin
puertas de validación.

**Backtrader (4,6/10)** — Motor de backtest excelente y flexible; muerto desde
2024, sin live creíble, sin UI, sin validación.

**Zipline (3,1/10)** — Histórico de acciones intradía/diario, ecosistema
Quantopian desaparecido, proyecto congelado.

**OctoBot (5,7/10)** — UI web muy buena, muchos exchanges, pero es un producto de
automatización (DCA, grid) más que una plataforma de investigación.

**VectorBT (4,2/10)** — Insuperable para barridos masivos de parámetros; nada de
live; invita al sobreajuste si no se pone disciplina encima.

**Backtesting.py (3,4/10)** — Simple y honesto, con advertencias contra optimizar;
sin live, sin riesgo, sin UI.

**Superalgos (4,9/10)** — Diseñador visual llamativo, rigor estadístico dudoso,
crypto solamente.

**SaaS tipo 3Commas / Cryptohopper / Bitsgap (5,3/10)** — UI de 9, ejecución
decente con claves de exchange, cero capacidad de investigación propia y cero
auditoría del método.

**TradingView + Pine (4,3/10)** — El mejor gráfico del mercado (10/10) y el peor
backtest de esta lista: repintado, fills idealizados, sin portfolio risk.

## 4. Matriz de puntuaciones

| Proyecto | Live | Valid. | Backtest | Riesgo | UI | Extend. | Docs | Datos | **Total** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| QuantConnect LEAN | 9 | 5 | 9 | 8 | 7 | 7 | 8 | 9 | **7,7** |
| NautilusTrader | 9 | 4 | 9 | 7 | 3 | 8 | 7 | 8 | **7,0** |
| Freqtrade | 9 | 4 | 7 | 5 | 8 | 8 | 9 | 6 | **7,0** |
| Jesse | 6 | 5 | 8 | 6 | 7 | 7 | 8 | 6 | **6,4** |
| **este repositorio** | **2** | **9** | **6** | **9** | **8** | **9** | **8** | **5** | **6,5** |
| Hummingbot | 10 | 2 | 2 | 7 | 4 | 9 | 8 | 8 | **6,0** |
| OctoBot | 8 | 2 | 4 | 5 | 9 | 6 | 7 | 6 | **5,7** |
| SaaS (3Commas & cía.) | 9 | 1 | 3 | 6 | 9 | 2 | 7 | 6 | **5,3** |
| Superalgos | 6 | 2 | 4 | 4 | 8 | 6 | 6 | 5 | **4,9** |
| Backtrader | 3 | 3 | 8 | 4 | 2 | 8 | 8 | 5 | **4,6** |
| TradingView + Pine | 4 | 2 | 3 | 2 | 10 | 4 | 9 | 8 | **4,3** |
| VectorBT | 1 | 4 | 7 | 2 | 3 | 9 | 6 | 7 | **4,2** |
| Backtesting.py | 1 | 4 | 6 | 2 | 2 | 5 | 7 | 4 | **3,4** |
| Zipline | 1 | 2 | 6 | 2 | 2 | 5 | 6 | 6 | **3,1** |

Totales = suma ponderada de las ocho notas con los pesos de la §2, redondeados a
un decimal. LEAN queda primero por amplitud (datos, riesgo, UI), no porque su
motor sea mejor que el de Nautilus.

### Desglose de la nota propia

| Criterio | Nota | Por qué |
|---|---:|---|
| Ejecución en vivo | 2 | No hay adaptador de broker: `LiveConfig.can_start()` exige `adapter_implemented`, `live_enabled`, confirmación y un broker distinto de `none`, y los valores por defecto lo bloquean. El motor paper y el feed OKX son reales, pero no hay órdenes reales. 2, no 1, por la paridad paper/backtest |
| Disciplina de validación | 9 | Puertas G4–G13 con umbrales versionados; G8 (costes ×2)/G2 (determinismo) y la integridad G1/G3/G14 se miden en la ruta API y ahora también en el CLI `--gates`; el candado del holdout bloquea runner, API y CLI sin pre-registro y sello reproducible; IC bootstrap, concentración top-5, walk-forward, ledger append-only y promoción PBO/DSR. No llega a 10 porque G3 sigue sin poder verificar rolls en una serie continua: eso se penaliza en Datos (5), no se disfraza aquí |
| Backtesting realista | 6 | `next_open`, comisión, slippage con tope, gana el stop en barra ambigua, coste de sesión. Falta modelo intrabar, funding/rolls y datos de futuros; el histórico spot real ya se usa |
| Gestión de riesgo | 9 | Riesgo por operación, pérdida diaria, máximo de operaciones, cooldown, tope de stop, cierre de sesión y emergencia que veta entradas sin bloquear salidas (no aplana automáticamente). Límites sobre P&L realizado; el stop acota el riesgo abierto |
| Interfaz | 8 | Contrato de snapshot agnóstico, siete vistas, HUD oscuro con un solo acento, sparklines y medidores de límite propios. Falta historial de snapshots y multi-ventana |
| Extensibilidad | 9 | Tres plugins incompatibles sin tocar el núcleo; un test prohíbe nombres de activo en `server/` y `frontend/` |
| Documentación | 8 | Arquitectura, protocolo, API, runbook, cómo escribir una estrategia, ADR con valores por defecto |
| Datos | 5 | Feed OKX real en paper e histórico Binance Vision spot/UM con `.CHECKSUM` (3.591.915 velas 1 m medidas, 2.496 días sin huecos); sintético y CSV siguen disponibles. Falta integrar futuros/rolls/funding en el pipeline, manifiesto y reconciliación |

**6,5/10** (6,3 antes de cablear el holdout y las puertas del CLI, con las notas
corregidas). Por debajo de LEAN (7,7), Nautilus (7,0) y Freqtrade (7,0), y por
encima de Jesse (6,4), Hummingbot (6,0) y del resto; a 0,5 de Nautilus, no «lejos».
Somos el mejor de la lista en lo que impide engañarse a uno mismo y estamos en el
furgón de cola en ejecución real y por debajo de la media en datos. Ese es
exactamente el perfil de un esqueleto de investigación serio con el motor de
mercado pendiente.

Un 6,5 con histórico spot real vale menos que uno con futuros, rolls y ejecución
real: la nota mide capacidades, no resultados. Ninguno de estos proyectos tiene
ventaja demostrada en su repositorio, y el nuestro tampoco.

## 5. Lo que hay que copiar, por orden

1. **Integrar el histórico real en el pipeline (Nautilus/LEAN).** El ADR 0.2 ya
   está cerrado y `binance_vision` descarga spot/UM con checksums; falta cablearlo
   al estudio y al flujo de promoción, añadir funding/rolls y reconciliación. Sin
   rolls, G3 puede pasar con «sin rolls que verificar»: la puerta necesita datos,
   no solo un hash.
2. **Adaptador de ejecución paper contra un broker real (Freqtrade).** `ccxt` o
   el sandbox del broker: reconciliación de posiciones al arrancar, que es donde
   todos los bots caseros fallan.
3. **Modelo de fill intrabar (LEAN).** Nuestro `next_open` es conservador pero
   pierde información; un modelo de tres precios (open/high/low) con volumen
   daría backtests más cercanos a la realidad.
4. **Reconexión y *heartbeat* de feed (Hummingbot).** Nosotros detectamos
   frescura; ellos reconectan solos. Detectar sin actuar es media solución.
5. **Paridad backtest/live (Nautilus).** Ya usamos el mismo motor, pero falta un
   test que compare el mismo día en ambos modos y exija desviación cero en fills.
6. **Datos de calidad y símbolos de referencia (LEAN).** Contratos, expiraciones y
   rolls como datos, no como supuestos.
7. **Multi-estrategia simultánea (LEAN alpha streams).** Hoy es una estrategia a
   la vez; para cartera hace falta capital asignado por estrategia.
8. **Alertas externas (freqtrade/Telegram).** Una parada de emergencia que solo
   se ve en la pantalla que no estás mirando no sirve.
9. **Exportación de resultados con esquema (LEAN).** Nuestro CSV es plano; un
   JSON con esquema versionado permitiría análisis externo reproducible.
10. **Reproducibilidad por contenedor.** Un `docker-compose` con la versión de
    Python y Node fijadas evita «en mi máquina funciona».

## 6. Lo que no hay que copiar

- `hyperopt` sin holdout ni corrección por múltiples comparaciones.
- Backtests con fills al cierre de la barra de la señal.
- Bots que deciden en el cliente (el navegador) y ejecutan sin autorización del
  servidor.
- Métricas sin intervalo de confianza presentadas como prueba.
- Optimizadores que eligen el máximo de una rejilla y lo llaman estrategia.

## 7. Investigación de interfaz

Referencias reales y qué se tomó de cada una:

| Referencia | ★ | Qué aporta | Qué adoptamos |
|---|---:|---|---|
| Grafana | 78.048 | Panel chrome, stat panels con sparkline, densidad | Tarjetas KPI con sparkline y etiqueta en versalitas |
| Dear ImGui | 77.266 | Controles compactos, docking, cero adornos | Densidad, bordes de 1 px, sin sombras difusas |
| emilk/egui | 32.439 | Paleta oscura moderna, foco claro | Fondo grafito, un solo acento |
| lucide | 25.944 | Iconos de trazo consistentes | Set de iconos propio en SVG inline (sin dependencia) |
| tradingview/lightweight-charts | 17.946 | Velas, ejes y crosshair | Ya en uso; tema alineado con los tokens |
| Bloomberg Terminal | — | Monoespaciado, ámbar/cian sobre negro, cifras tabulares | `font-variant-numeric: tabular-nums` en toda cifra |
| Linear / Vercel | — | Hairlines, gradientes sutiles, micro-etiquetas | Reglas de 1 px y gradiente superior por panel |
| HUD cinematográfico | — | Esquinas, scanlines, glow | Esquinas de encuadre, línea de escaneo muy tenue, glow solo en estado vivo |

Reglas de diseño que se aplican en `frontend/src/styles.css`:

1. Un solo acento (cian `#37e0d0`); el ámbar solo para aviso y el rojo solo para
   pérdida o fallo. Si todo brilla, nada destaca.
2. Cifras siempre tabulares y monoespaciadas; el ojo compara columnas, no frases.
3. Micro-etiquetas en versalitas de 11 px con `letter-spacing`: informan sin
   competir con el dato.
4. Glow y animación solo en elementos vivos (estado, última vela). Contenido
   estático, quieto.
5. Movimiento respetando `prefers-reduced-motion`.
6. Contraste mínimo AA sobre el fondo: `#e6edf3` sobre `#0a0e14`.
7. Ningún icono sin `aria-hidden`, ningún botón sin `aria-pressed` cuando alterna.

## 8. Veredicto

Nuestro punto fuerte no es el motor: es el método. La lista de arriba está llena
de motores mejores con métodos peores, y por eso casi todos sus repositorios
públicos no pueden demostrar que funcionan. Un 6,5 con la mejor disciplina de
validación de la tabla es una base honesta; el histórico spot real ya se usa y el
feed OKX alimenta el paper, pero todavía no hay ejecución real ni futuros/rolls.

La nota de interfaz subió de 6 a 8 al reescribir la capa visual: HUD oscuro con
un solo acento, cifras tabulares en todo, sparkline por KPI y medidores de uso de
límite dibujados a mano. Sigue faltando lo que separa un panel bonito de una
herramienta profesional: historial de snapshots reproducible y comparación de
varias ejecuciones en la misma pantalla.
