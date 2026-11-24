# Auditoría del prompt «AI Strategy Research Engine (BTC) — Elite Quant V3»

**Fecha:** 2026-11-22 · **Activo auditado:** BTCUSDT perpetuo (Binance USDⓈ-M) · **Datos usados:** archivo público de Binance, 2020-01-01 → 2026-10-31 (718.848 barras de 5m, 0 gaps, 0 duplicados).

Este documento hace tres cosas:

1. Audita el prompt adjunto contra literatura revisada por pares y contra datos reales.
2. Muestra con números reproducibles dónde el prompt falla y por qué.
3. Define el pipeline y los umbrales que sí se sostienen (implementados en `PROMPT_V4.md`).

Todo número de mercado de este informe sale de `research/` (scripts incluidos) o de una fuente citada con URL. Lo que no se pudo verificar está marcado `[DATA_UNAVAILABLE]` o en la sección 9.

---

## 0. Resumen ejecutivo

| # | Hallazgo | Evidencia |
|---|---|---|
| 1 | **El prompt confunde al LLM con un motor de cálculo.** Pide «investigar, generar, probar y evaluar» a un modelo que no ejecuta backtests: la única salida posible son métricas inventadas o copiadas. | El propio prompt exige «cero alucinaciones» y a la vez pide métricas que solo puede producir un runner. Contradicción estructural, no de redacción. |
| 2 | **No hay control de selección múltiple.** Con 8 configuraciones probadas, el PBO (probabilidad de sobreajuste) medido fue **0,50** y el DSR **0,58** (< 0,95), aunque la mejor config tenía PF neto 1,68. | `cache/funding_results.json` → `_summary`. Método: Bailey et al. (CSCV) y Bailey & López de Prado (DSR). |
| 3 | **En 5m el coste es la estrategia.** Las cuatro familias probadas tienen expectativa **bruta ≈ 0** y expectativa **neta entre −0,10R y −0,52R** con taker 5,07 bp/lado (las reglas base, −0,17R a −0,52R). El coste por trade en R es 0,10–0,40 R. | Sección 5.1. `cache/study_results.json`. |
| 4 | **El funding no está modelado como coste real.** Media 0,0106% por intervalo de 8h, **86% de los intervalos positivos**, suma anual de hasta **+30,6%** sobre nocional (2021). En swings de días, el funding pesa 3–5× más que las fees. | Sección 5.3, datos `fundingRate` de Binance Vision. |
| 5 | **Los umbrales de la §6 no son significancia.** Con 600 trades y PF real 1,0, el IC95% del PF es **[0,85; 1,17]**: el «PF OOS > 1,15» del prompt cabe dentro del ruido. Probar PF 1,15 exige ~900 trades. | Simulación propia, sección 5.5. |
| 6 | **«WFA sobre el 20% de los datos» es estadísticamente vacío** en este histórico: el mejor sistema diario generó **58 trades en 6,8 años** y el walk-forward solo produjo **11 trades OOS** en 2 folds. | Sección 5.4. |
| 7 | **«Slippage dinámico por ATR y OBI» no es un modelo de ejecución.** La evidencia es impacto lineal en OFI con pendiente ∝ 1/profundidad y ley de raíz cuadrada; para tamaño retail el impacto es ~0,2 bp, dos órdenes de magnitud por debajo de la fee taker. | Cont, Kukanov & Stoikov (2014); Tóth et al. (2011). |
| 8 | **Faltan piezas de gobernanza que el prompt da por hechas:** benchmark, hashes de datos/código/seed, CI en cada métrica, capacidad, hora de la barra, orden SL/TP intrabar, DST de sesiones, y separación spec/runner. | Secciones 3, 6 y `PROMPT_V4.md`. |
| 9 | **Cuadruplicar los activos no compró potencia.** El Donchian 1d tiene PF > 1,4 en BTC, ETH y BNB (XRP 1,00): el edge es transversal. Pero con correlación de mercado 0,644, el t agregado de 2,85 se queda en **1,67** al descontar la dependencia — el mismo 1,66 de BTC solo. | E21. `runner/out-universe/`. |
| 10 | **El supuesto de spread es correcto en calma y 19× corto en crisis.** Medido con el estimador de Roll sobre `aggTrades`: 0,09-0,16 bp en días normales (supuesto 0,07) y hasta 1,30 bp el 2025-10-10. Impacto en R acotado a ~0,25 sobre 146; no cambia ningún veredicto. | E22. `research/cache/spread_results.json`. |

**Veredicto sobre el prompt V3: rechazado como especificación de investigación.** Sirve como declaración de intenciones (parsimonia, costes, OOS, Monte Carlo, versionado), pero no como sistema: no es ejecutable, no controla selección múltiple, y sus umbrales son incompatibles con la potencia estadística disponible.

**Veredicto sobre las estrategias construidas después:** **0 aprobadas de 23 corridas** (13 rechazadas, 7 inconclusas). La línea de tendencia tiene un edge real y transversal (1d: PF neto 1,50 sobre 311 trades; 1d+vol targeting 1,50 con Sharpe 0,64) que no sobrevive a las puertas por falta de potencia, no por falta de señal: t 1,66 frente a 3,0, y MinBTL pide 14,6 años cuando hay 6,8. La evidencia externa acompaña al escepticismo: los crashes de momentum y el carry comprimido desde 2024 son consistentes con un edge que existe y es difícil de cobrar.

---

## 1. Lo que el prompt hace bien

No todo es descartable. Estas piezas se conservan en V4:

- Exigir hipótesis económica antes de la regla (evita indicadorismo).
- Prohibir lookahead y exigir diferenciación maker/taker y funding.
- Pipeline IS/OOS con datos ciegos y perturbación de parámetros.
- Monte Carlo para la peor racha y stress de costes.
- Separación «la IA propone, el motor determinista ejecuta, el operador controla el capital».
- Ficha técnica con riesgos residuales.
- Secuencia BACKTEST → DRY-RUN → LIVE con apagado por defecto.

---

## 2. El error de arquitectura (el más caro)

El prompt asigna a la IA cuatro tareas incompatibles entre sí:

```
investigar → generar → backtestear → evaluar
```

Un LLM puede escribir la especificación de una estrategia y razonar sobre resultados. **No puede** calcular un Sharpe OOS, un PBO o un Monte Carlo sobre 718.848 barras, y cualquier prompt que se lo pida obtiene una de tres cosas: números inventados, números de otro activo/periodo, o una negativa. La instrucción «si falta un dato, declara `[DATA_UNAVAILABLE]`» no arregla nada: el modelo *no sabe* que le falta.

**Corrección (V4):** contrato de tres capas con artefactos verificables.

```
[IA]  strategy_spec.yml  ──►  [RUNNER determinista]  ──►  result.json  ──►  [IA] auditoría
      (hipótesis, reglas,          (backtest, CSCV,          (métricas,           (veredicto con
       params, costes,              DSR, bootstrap,           equity, trades,      evidencia citada
       requisitos de datos)         WFA, stress)              hashes)              por campo)
```

Regla dura: **la IA no puede escribir un número que no exista como campo en `result.json`.** Si el campo no existe, escribe `[DATA_UNAVAILABLE]` y pide la ejecución. Esto convierte «cero alucinaciones» de intención en restricción verificable.

Consecuencia práctica: la ficha técnica debe ser un JSON con esquema (más un render humano), no texto libre. Ver `PROMPT_V4.md` §1.

---

## 3. Errores de especificación, uno por uno

### E1. «Sharpe / Sortino > 1,5 / > 2,0» sin decir cómo se anualiza

BTC cotiza 24/7/365. Anualizar con √252 subestima; con √365 es lo correcto bajo retornos iid. Pero Lo (2002, *Financial Analysts Journal* 58(4), 36–52) demuestra que **multiplicar por √k solo es válido bajo iid**: con autocorrelación positiva (frecuente en 5m por microestructura y en tendencias) el Sharpe anualizado está sobreestimado. Además, anualizar el Sharpe de barras de 5m con √105.120 viola la iid de forma brutal.

**Corrección V4:** calcular el Sharpe sobre **P&L agregado a diario** (o semanal), anualizar con √365, y reportar además el Sharpe con corrección de autocorrelación de primer orden y el número de observaciones. Nunca anualizar desde 5m.

### E2. La validación «60/20/20» no controla el sobreajuste

Bailey, Borwein, López de Prado & Zhu (*The Probability of Backtest Overfitting*, J. Computational Finance 2016; PDF en `davidhbailey.com/dhbpapers/backtest-prob.pdf`) demuestran que el hold-out **no puede** estimar el grado de sobreajuste porque ignora el número de intentos: «as long as the researcher tries more than one strategy configuration, overfitting is always present». Su método CSCV estima el PBO con S submatrices y las C(S, S/2) combinaciones (con S=16, 12.780 combinaciones).

Medición propia (sección 5.4): **PBO = 0,50** en una rejilla de 8 configuraciones de Donchian con PF neto 1,68 la mejor. Es decir: la probabilidad de que la config elegida in-sample quede por debajo de la mediana OOS es la de una moneda. Con el criterio del prompt («rankear por robustez OOS») se habría aprobado igualmente, porque el PF OOS puntual era alto.

**Corrección V4:** PBO ≤ 0,20 obligatorio, con S=16 y registro del número real de trials.

### E3. «DSR» no aparece; sin él, el ranking es winner's curse

El *Deflated Sharpe Ratio* (Bailey & López de Prado, *JPM* 40(5), 94–107, 2014) ajusta el umbral de significancia por (a) número de trials, (b) longitud de la muestra, (c) asimetría y curtosis. Usa `E[max SR]` con la constante de Euler-Mascheroni. Sin esto, el mejor de N backtests tiene un Sharpe esperado positivo **aunque todos sean falsos**.

En nuestro test, el mejor sistema (1d Donchian 40) tiene Sharpe 0,61, umbral deflactado SR₀ = 0,43 y **DSR = 0,58**: no se puede afirmar que su Sharpe sea > 0,43 con confianza. Además el *Minimum Backtest Length* es **11,2 años** y solo hay **6,8**.

### E4. «>100 trades» es un umbral mal puesto

- En 5m, 100 trades se alcanzan en ~2 semanas: el umbral no filtra nada. Nuestros sistemas de 5m tienen 3.507–27.591 trades y **PF neto 0,48–0,86**.
- En 1d, el mejor sistema del estudio tiene **58 trades en 6,8 años**: el umbral lo habría rechazado, y con razón, pero por el motivo equivocado (no por tener pocos trades, sino porque con 58 trades ningún IC permite concluir nada).

**Corrección V4:** sustituir «>100 trades» por **potencia**: IC95% bootstrap de la expectativa y del PF, y mínimo de trades por fold WFA (≥30). Reportar siempre el IC, no el punto.

### E5. Costes: correcto en la intención, incompleto en la práctica

Tarifas reales verificadas (2026-11-22):

| Producto | Maker | Taker | Descuento BNB |
|---|---|---|---|
| USDⓈ-M futuros, usuario regular | 0,0200% | 0,0500% | 10% |
| Spot, usuario regular | 0,1000% | 0,1000% | 25% → 0,075% |

Fuentes: `binance.com/en/fee/futureFee`, FAQ «Fee Structure on Binance», FAQ BNB 25%. La página de futuros muestra además promociones temporales (maker 0% para U-margined): **el modelo de costes no puede hardcodear una promo**.

Lo que falta en el prompt:

1. **Modelo de fills maker.** «Diferenciar maker/taker» sin modelar la probabilidad de fill es ficción: una orden limit puede no ejecutarse y, si se ejecuta, selecciona flujo adverso. En V4: si se asume maker, se exige `fill_probability` calibrada con datos y un escenario con ejecución nula.
2. **Funding como coste en R.** El prompt dice «descontar», pero no define la mecánica. Fórmula correcta y su impacto, en 3.3.
3. **Spread e impacto medidos, no inventados.** Ver E6.
4. **Coste expresado en R, no en bps sueltos.** Un coste de 10,14 bp round-trip es el 0,25R de un stop de 0,40% y el 0,10R de un stop de 1%. Sin normalizar por la distancia del stop, el número no dice nada.

### E6. El modelo de slippage propuesto es el equivocado

El prompt pide «slippage dinámico según ATR y Order Book Imbalance». La literatura:

- **Cont, Kukanov & Stoikov (2014)**, *Journal of Financial Econometrics* 12(1), 47–88: el cambio de precio a corto plazo es **lineal en el OFI** (definido sobre bid/ask, incluyendo cancelaciones), con pendiente **inversamente proporcional a la profundidad**. El imbalance de trades sola explica menos.
- **Tóth et al. (2011)**, *Phys. Rev. X* 1, 021006: la ley empírica de impacto es **Δ = Y·σ·√(Q/V)**, con Y ≈ 1, para metaórdenes; exponente 0,4–0,7 según mercado.

Consecuencia cuantitativa para BTC retail: con σ diaria ~2%, V ~8–15 B USDT y Q = 10.000 USD, √(Q/V) ≈ 10⁻³ → impacto ≈ 0,2 bp. El tick es 0,10 USDT (≈0,13 bp a 77.000) y el medio spread ~0,07 bp. **El coste dominante es la fee taker (5 bp), no el impacto.** Modelar slippage proporcional a ATR añade ruido y, peor, duplica la volatilidad ya contenida en el precio.

Además, los datos necesarios para un modelo OBI realista no están disponibles de forma continua en el archivo público: `bookDepth` existe **solo en granularidad diaria** (snapshots cada 30 s, bandas ±5%), y `bookTicker` mensual está disponible en algunos periodos (2023-06 y 2024-01 existen; 2025-01 y 2026-10 devuelven 404). Sin L2 completo no se puede reconstruir el libro para todo el histórico.

**Corrección V4:** coste = fee + medio spread + impacto estimado por ley de raíz cuadrada con V y σ del propio activo, y **barrido de costes hasta break-even** (no sólo +50%). Si se usa OBI, se limita a la ventana donde existan datos y se reporta cobertura.

### E7. El funding está infravalorado

Fórmula vigente (Binance, actualización 2025-09-18):

```
F = [ P_avg + clamp(interest − P_avg, +0,05%, −0,05%) ] / (8/N)
```

con `interest = 0,01%` por intervalo de 8h por defecto (0,03%/día), `N` = horas del intervalo, y cap/floor de **±0,30%** por intervalo en BTCUSDT (intervalo 8h).

Datos reales 2020-01 → 2026-10 (7.488 eventos, `fundingRate` de Vision):

| Métrica | Valor |
|---|---|
| Media por intervalo 8h | **+0,0106%** |
| Intervalos positivos (long paga) | **86,0%** |
| Suma anual de tasas (nocional) 2020 | +17,2% |
| 2021 | **+30,6%** |
| 2022 | +4,2% |
| 2023 | +7,9% |
| 2024 | +12,0% |
| 2025 | +5,1% |
| 2026 (ene–oct) | +2,6% |

Implicación: un long perpetuos mantenido un año pagó, de media, **≈11,6% del nocional** (0,0106% × 3 × 365) solo en funding. En el sistema 1d Donchian 40, el funding costó **0,077R por trade** frente a **0,018R de fees**: 4,3× más.

**Corrección V4:** `funding_in_R = side · Σ f_i / d_stop`, aplicado con timestamps reales, y reporte separado de fees y funding.

### E8. Kelly sin shrinkage es una receta de ruina

El prompt pide «Kelly con Half-Kelly». Dos problemas:

1. Kelly es óptimo **solo si μ y σ son conocidos**. Con μ estimado con error (y en 5m el error es enorme), el Kelly «estimado» sobreapuesta sistemáticamente. MacLean, Thorp & Ziemba (*Good and Bad Properties of the Kelly Criterion*) muestran que apostar 2× Kelly lleva la tasa de crecimiento a cero, y más allá produce crecimiento negativo; el Half-Kelly no es solo «la mitad de riesgo»: con utilidad lognormal, la fracción c de Kelly da ≈ c(2−c) del crecimiento con c·σ de volatilidad (c=0,5 → 75% del crecimiento, 50% de la volatilidad).
2. El prompt no fija **cap de apalancamiento** ni límite por liquidez, y MDD < 20% con Kelly completo es incompatible en BTC (ver E10).

**Corrección V4:** `f = c · μ/σ²` con c ≤ 0,25–0,5, cap duro de notional, y sizing por volatilidad objetivo (p. ej. 15–25% anualizada) con presupuesto de MDD explícito.

### E9. Monte Carlo iid destruye justo lo que quiere medir

«Remuestrear trades» (iid) rompe la autocorrelación de la serie de P&L y la clusterización de pérdidas, que es exactamente el riesgo de ruina que se quiere estimar. La herramienta correcta es **block bootstrap** o **stationary bootstrap** (Politis & Romano, *JASA* 89:1303–1313, 1994), que preserva dependencia débil.

Además, la racha perdedora no se estima remuestreando trades aislados: se estima remuestreando **bloques** de la curva de P&L y midiendo la distribución del máximo drawdown y del tiempo bajo el agua. Bailey et al. («triple penance rule») formalizan que el tiempo de recuperación esperado es ~3× el tiempo que tardó en formarse la pérdida máxima.

### E10. MDD < 20% ignora el activo

Datos reales 2020-01 → 2026-10:

| Métrica BTCUSDT perp | Valor |
|---|---|
| Buy & hold CAGR | **+41,7%** |
| Buy & hold Sharpe (diario, ×√365) | **0,89** |
| Buy & hold MDD | **−76,7%** |
| Volatilidad anualizada 5m por año | 97,6% – 214,0% |
| Mayor movimiento 5m | **+16,09%** (2020-03-13) / −10,46% |
| Mayor movimiento 1h | +34,34% (2020-03-13) |
| Mayor movimiento 1d | +44,92% / **−50,85%** (2020-03) |
| Rango 2025-10-09 → 10-11 | **21,89%** (5m mínimo −7,76%) |

Un MDD < 20% con estrategia long/short en BTC es posible, pero entonces el retorno esperado también baja; el prompt no reconcilia ambos umbrales. Y no hay benchmark: un Sharpe 1,5 con CAGR 12% es peor que buy & hold en retorno absoluto y mucho mejor en riesgo, pero eso solo se ve comparando.

**Corrección V4:** benchmark obligatorio (BTC buy & hold + T-bill), alpha con IC, y MDD presupuestado en función de la volatilidad objetivo, no un 20% universal.

### E11. El dry-run de 30 días no valida nada

«Cualquier desviación > 10% en slippage o PF bloquea LIVE» no define:

- qué estimador de slippage (bps medios? mediana? p95? por lado?),
- con qué potencia (30 días × 20 trades = 600 trades → IC95% del PF = [0,85; 1,17] bajo PF real 1,0; ver 5.5),
- qué pasa con el funding y con los fees reales del periodo,
- qué es «desviación»: diferencia de medias, de distribuciones, test.

**Corrección V4:** el dry-run es un **smoke test operativo** (conectividad, fills, latencia, reconciliación) de 30 días *más* un test estadístico: comparar la distribución de slippage realizada contra el modelo (KS o Mann-Whitney con n≥100 fills), y exigir que el IC95% del PF realizado se solape con el del backtest. Si no se solapa, halt automático. La promoción a LIVE sigue siendo decisión humana explícita y por tamaño canario.

### E12. Detalles de lookahead que el prompt no cubre y ocurren siempre

Lista de trampas reales, cada una capaz de inflar un backtest sin que se note:

1. **Semántica de barra:** señal calculada con el `close` de la barra t y ejecutada al `close` de t. Correcto: ejecutar al `open` de t+1.
2. **Indicadores recursivos:** EMA/RSI calculados con toda la serie en backtest vs. con `startup_candle_count` limitado en vivo (problema de *recursive bias*, ver `freqtrade recursive-analysis`).
3. **Orden SL/TP intrabar:** si en la misma barra se tocan stop y target, elegir el target es lookahead. Asumir **stop primero** (nuestro motor lo hace).
4. **Gaps:** si el open supera el stop, el fill es al open (peor), no al stop.
5. **Sesiones y DST:** «Londres 08:00» y «NY 13:30» en UTC fijo cambian con el horario de verano; un ORB mal alineado mezcla sesiones.
6. **Funding:** se cobra en el timestamp de funding, no «al final del día»; y el signo depende del lado.
7. **Mark price vs last price:** las liquidaciones usan mark price; los stops por last. Modelar stops con mark price cambia resultados en eventos de desanclaje (2025-10-10 es el caso real).
8. **Universo:** BTC solo no tiene survivorship, pero sí *listing bias* si se usan datos previos a 2020-01 para el perpetuo (no existen en el archivo: los ficheros de 2019 devuelven 404) y *régimen* distinto en spot.
9. **Funding de spot margin / borrow:** no cubierto por el prompt.
10. **Reloj y rate limits:** `recvWindow`, desfase de reloj, reconexión de WebSocket, pesos de endpoints.

Freqtrade ofrece `lookahead-analysis` y `recursive-analysis` (docs oficiales) y advierte explícitamente que **un resultado negativo no garantiza ausencia de sesgo**. Son un mínimo, no una garantía.

### E13. La «Ficha Técnica» no es integrable

Texto libre con etiquetas no se puede parsear. Un bot necesita un contrato estable: id, versión, hash, params tipados, costes, datos y veredicto con campos numéricos. Ver `PROMPT_V4.md` §1 y §11.

### E14. Gobernanza incompleta

«Hash y timestamp» sin decir de qué. Un artefacto reproducible exige: **hash del dataset** (o versión+fecha del archivo), **git SHA del código**, **hash de la spec**, **seed del RNG**, y **entorno** (versión de pandas/numpy). El histórico debe ser append-only (registry), no «no sobrescribir» como norma moral.

---

## 4. Tabla de veredictos sobre las afirmaciones del prompt

| Afirmación del prompt V3 | Veredicto | Evidencia |
|---|---|---|
| «Cero alucinaciones, si falta un dato `[DATA_UNAVAILABLE]`» | **No ejecutable tal como está** | El modelo no puede saber que un cálculo no se hizo; se arregla con contrato spec→runner (§2) |
| «Slippage dinámico según ATR y OBI» | **Modelo incorrecto para retail** | OFI lineal ∝1/depth (Cont et al. 2014); Δ=Yσ√(Q/V) (Tóth et al. 2011); impacto ~0,2 bp vs fee 5 bp |
| «Fees maker/taker diferenciadas» | **Correcto pero incompleto** | Falta probabilidad de fill maker; tarifas reales 0,02/0,05 (futuros) y 0,10/0,10 (spot) |
| «Descontar funding» | **Correcto, infravalorado** | 86% intervalos positivos; +30,6% anual en 2021; 4,3× las fees en swings |
| «Latencia de 1–2 ticks» | **Insuficiente** | En 5m, 1 barra; en 1d, el fill es al open siguiente. «Ticks» no está definido en un gráfico de barras |
| «WFA sobre 20% de los datos» | **Sin potencia** | 11 trades OOS en 2 folds con datos diarios |
| «Monte Carlo 1.000 iteraciones remuestreando trades» | **Método incorrecto** | IID rompe clustering; usar stationary bootstrap (Politis & Romano 1994) |
| «Perturbar ±10/20% y ver si colapsa» | **Correcto, mal especificado** | Falta criterio de «colapso»: p. ej. PF sigue >1 y expectancy conserva signo en todo el vecindario |
| «PF > 1,3 IS / > 1,15 OOS» | **No significativo** | IC95% del PF con 600 trades = [0,85; 1,17] |
| «>100 trades» | **Umbral mal puesto** | 5m: 100 trades en 2 semanas; 1d: 58 trades en 6,8 años |
| «Sharpe > 1,5, Sortino > 2, Calmar > 1, Recovery > 2» | **Arbitrario y contradictorio** | Calmar>1 + MDD<20% ⇒ CAGR>20%; Sharpe 1,5 en 5m neto no se observó en ninguna config |
| «MDD < 20%» | **Sin contexto de activo** | BTC B&H MDD −76,7%; vol anual 98–214% |
| «Rankear por robustez OOS» | **Winner's curse** | PBO 0,50 y DSR 0,58 en 8 configs |
| «Dry-run 30 días, desviación >10% bloquea» | **Sin potencia ni métrica** | IC del PF a 600 trades ±17% |
| «Versionado semántico con hash» | **Incompleto** | Falta data hash, código SHA, seed, entorno |
| «La IA no toca controles en vivo» | **Correcto y se conserva** | — |
| «La IA investiga y propone; el sistema verifica; el motor ejecuta» | **Correcto, pero el prompt no lo implementa** | El prompt pide a la IA verificar y ejecutar |

---

## 5. Resultados reales del estudio de referencia

**Qué es y qué no es.** No es una estrategia para operar ni una búsqueda de rentabilidad. Es un banco de pruebas reproducible para medir dos cosas: (a) cuánto cuesta operar en 5m, (b) si los criterios del prompt V3 habrían aprobado algo. Motor: una posición a la vez, señal al cierre de t, fill al open de t+1, stop/target con high/low, stop primero en empate, gap al open, time-stop, riesgo 0,5% por trade, coste en R = coste_rt/distancia_stop.

**Datos.** BTCUSDT perpetuo, klines 5m, 2020-01-01 → 2026-10-31: **718.848 barras, 0 gaps, 0 duplicados**, precio 3.621,81 → 77.522,60. Fuente: `data.binance.vision` (mensual, UM). Verificado además que los ficheros de 2019 **no existen** (404) y que spot 5m empieza en 2017-08.

### 5.1 Cinco minutos: el coste se come todo

Coste aplicado: taker 5,07 bp/lado (fee 5 bp + medio spread 0,07 bp) ⇒ **10,14 bp round-trip**.

| Familia | Config | Trades | PF bruto | PF neto | Exp. bruta (R) | Exp. neta (R) | Coste/trade (R) |
|---|---|---|---|---|---|---|---|
| Trend | Donchian 288 | 5.449 | 1,002 | **0,643** | +0,001 | **−0,313** | 0,25 |
| Momentum | EMA 48/192 | 4.495 | 1,039 | **0,530** | +0,026 | **−0,465** | 0,36 |
| Mean reversion | z2 / 96 | 21.045 | 0,931 | **0,494** | −0,035 | **−0,338** | 0,23 |
| ORB | 30 min (NY/Londres) | 4.461 | 1,047 | **0,710** | +0,028 | **−0,218** | 0,18 |

Lectura: **la expectativa bruta es indistinguible de cero en las cuatro familias**. Con 5m no hay señal explotable en estas reglas simples; todo el resultado neto es coste. Y el coste no es un detalle: el Donchian 288 paga 798 trades/año × 0,25R = **~200R/año**; con riesgo 0,5% por R son **~100% del equity al año en costes**, antes de cualquier edge.

Sensibilidad (misma rejilla): con maker 2,07 bp/lado, el PF neto va de 0,72 a 0,90; con stress 7,6 bp/lado, de 0,33 a 0,66. Es decir: **ningún escenario de costes razonable salva las reglas de 5m probadas.**

### 5.2 Por qué: coste en R ∝ 1/distancia de stop

| Config | Stop mediano | Coste 10,14 bp en R |
|---|---|---|
| Trend 288 (ATR 1,5×) | 0,403% | 0,25R |
| Momentum EMA 48/192 | 0,281% | 0,36R |
| ORB 30 min | 0,562% | 0,18R |
| Trend 576 + floor 100 bp | 1,000% | 0,10R |

Un stop más ancho reduce el coste en R pero también la frecuencia y el tamaño de la posición. **No existe «mejor slippage» que arregle esto; se arregla con menos rotación o con mayor horizonte.**

### 5.3 Timeframes altos: el edge aparece y el funding pesa

Mismo motor, datos remuestreados del mismo 5m. PF neto = fees taker (10,14 bp) **+ funding real**.

| TF | Config | Trades | PF bruto | PF con fees | **PF con fees+funding** | Sharpe | MDD | t-stat |
|---|---|---|---|---|---|---|---|---|
| 4h | Donchian 24 | 524 | 1,155 | 1,072 | **1,055** | 0,19 | −15,3% | 0,50 |
| 4h | Donchian 48 | 358 | 1,238 | 1,154 | **1,128** | 0,35 | −10,3% | 0,92 |
| 1d | Donchian 20 | 78 | 1,625 | 1,587 | **1,490** | 0,54 | −4,1% | 1,42 |
| 1d | Donchian 40 | 58 | 1,877 | 1,833 | **1,683** | 0,61 | −4,6% | **1,60** |
| 1d | Donchian 55 | 47 | 1,781 | 1,742 | **1,579** | 0,49 | −2,8% | 1,27 |
| 1d | Donchian 100 | 39 | 1,193 | 1,167 | **1,033** | 0,03 | −4,2% | 0,08 |
| — | **BTC buy & hold** | — | — | — | — | **0,89** | **−76,7%** | — |

Y aquí está el punto que el prompt V3 no puede ver: **ninguna de estas configuraciones pasaría un control de selección múltiple**, aunque su PF sea atractivo.

| Test | Resultado | Umbral razonable | Veredicto |
|---|---|---|---|
| PBO (CSCV, 8 configs, S=10, 252 splits, ranking por Sharpe) | **0,50** | ≤ 0,20 | **Falla** |
| DSR del mejor (Sharpe 0,61) | **0,58** | ≥ 0,95 | **Falla** |
| SR₀ deflactado | 0,434 | — | El Sharpe 0,61 no supera el ruido de 8 trials |
| MinBTL | **11,2 años** | ≤ 6,8 disponibles | **Falla** |
| Hurdle Harvey-Liu-Zhu (t > 3) | SR > **1,147** | 0,61 observado | **Falla** |
| Walk-forward (train 2a / test 6m) | **11 trades OOS** en 2 folds | ≥ 30/fold | **Falla** |

Interpretación honesta: el estudio no demuestra que el trend-following diario en BTC no funcione. Demuestra que **con 6,8 años, 8 configuraciones y una regla ingenua, no se puede afirmar que funcione** — que es precisamente lo que el prompt V3 no distingue.

### 5.4 Coste de funding medido

| Concepto | 1d Donchian 40 |
|---|---|
| Fees por trade (en R) | 0,018 |
| Funding por trade (en R) | **0,077** |
| Funding / fees | **4,3×** |
| Coste anualizado (8,5 trades/año) | ≈ 0,8R ≈ 0,4% del equity |

En 5m el funding es irrelevante (posición intradía); en 1d–swing es el primer coste. **Un modelo que solo descuente fees aprueba estrategias que pierden por funding.**

### 5.5 Potencia estadística: el número que falta en el prompt V3

Simulación de PF con payoff 1:1 y PF real 1,0 (20.000 réplicas por tamaño):

| Trades | IC95% del PF |
|---|---|
| 300 | [0,796; 1,256] |
| 600 | [0,852; 1,174] |
| 1.500 | [0,904; 1,107] |
| 3.000 | [0,932; 1,075] |

Trades necesarios para que el IC95% excluya PF = 1,0:

| PF real | Trades |
|---|---|
| 1,15 | **900** |
| 1,30 | 300 |
| 1,50 | 200 |

Conclusión: el umbral «PF OOS > 1,15» **no es verificable con menos de ~900 trades**, y un dry-run de 30 días con 20 trades/día (600 trades) tiene un IC de ±17% alrededor de 1,0. La regla de bloqueo por «>10% de desviación en PF» dispara con ruido puro.

### 5.6 Riesgo de cola

Los datos contienen lo que los backtests suelen suavizar:

- 2020-03-12/13: **−50,85% en 1 día**, **+16,09% en una barra de 5m**, **+34,34% en 1h**.
- 2021-05-19: −22,97% en 1h.
- 2025-10-10: rango de **21,89%** en ~48h, mínimo de 5m −7,76%, en el mayor evento de liquidaciones de la historia (>19 B USD según CoinDesk/Reuters).

Cualquier stop de 1–2% se ejecuta muy por debajo del nivel en estos episodios; el modelo de gap del motor (fill al open) es obligatorio, y aun así optimista frente a un libro que se vacía.

---

## 6. El pipeline que sí se sostiene

```
0. SPEC         → YAML validado contra JSON Schema (params tipados, sin texto libre)
1. DATOS        → descarga + checksum + chequeos de integridad + hash + cobertura
2. COSTE        → coste_R = (2·fee + spread + impacto) / d_stop  +  funding_R
3. BACKTEST     → 1 posición, closed-bar, fill t+1, stop-first, gap al open
4. SELECCIÓN    → CSCV/PBO con S=16 y registro de TODOS los trials
5. DEFLACIÓN    → DSR con N independiente (o N̂ por correlación media) + haircut HLZ
6. ROBUSTEZ     → perturbación ±10/20% (plateau), stress de costes 1,5×/2× hasta break-even
7. MONTE CARLO  → stationary bootstrap (bloques), 10.000 réplicas, MDD y tiempo bajo el agua
8. RÉGIMEN      → segmentos ex-ante con cuantiles expansivos (nunca sobre todo el histórico)
9. WFA          → folds con ≥30 trades; si no se alcanza, el veredicto es INCONCLUSIVE
10. BENCHMARK   → BTC B&H + alpha con IC; sin benchmark no hay veredicto
11. DRY-RUN     → 30 días smoke test + test de distribuciones de slippage + IC del PF
12. LIVE        → off por defecto, tamaño canario, kill-switch, decisión humana
```

**Puertas de aprobación (todas obligatorias, ninguna sustituible por otra):**

| Puerta | Umbral |
|---|---|
| Integridad de datos | 0 gaps no explicados, 0 duplicados, hash registrado |
| PBO | ≤ 0,20 |
| DSR | ≥ 0,95 |
| t-stat OOS (o haircut HLZ) | ≥ 3,0 |
| IC95% inferior del PF OOS | > 1,00 |
| Trades totales / por fold WFA | ≥ 300 / ≥ 30 |
| Stress de costes 2× | PF sigue > 1,00 |
| Funding incluido | Sí, con timestamps reales |
| Plateau de parámetros | PF > 1,00 en todo el vecindario ±20% |
| Benchmark | Alpha > 0 con IC que excluya 0 |
| MDD | ≤ presupuesto declarado (no un 20% universal) |
| Veredicto | Aprobada / Rechazada / **Inconclusa** (esta última es válida y frecuente) |

La categoría **INCONCLUSA** es la novedad más importante frente a V3: permite decir «no hay datos suficientes» sin aprobar por omisión ni rechazar por prejuicio.

---

## 7. Cambios concretos de V3 → V4

| Área | V3 | V4 |
|---|---|---|
| Rol de la IA | Genera, prueba, evalúa | Genera **spec** y **audita** resultados del runner |
| Métricas | Las escribe la IA | Solo campos de `result.json` con ruta citada |
| Anti-overfit | IS/OOS/WFA + perturbación | + PBO, DSR, MinBTL, haircut HLZ, N de trials |
| Costes | Fees + slippage ATR/OBI + funding | Fee real + spread + ley √(Q/V) + funding por timestamp, **en R** |
| Frecuencia | 5m ejecución | 5m solo si `cost_R` y rotación lo permiten; por defecto 15m–4h para señal |
| Potencia | «>100 trades» | IC bootstrap + mínimo por fold + veredicto INCONCLUSIVE |
| Monte Carlo | IID sobre trades | Stationary bootstrap sobre bloques de P&L |
| Sharpe | Sin definir anualización | Diario, ×√365, con nota de autocorrelación (Lo 2002) |
| Dry-run | 30 días, 10% de PF | Smoke test + test de distribuciones + IC; promoción humana |
| Versión | hash + timestamp | hash de datos, git SHA, hash de spec, seed, entorno |
| Entrega | Texto libre | JSON Schema + render |

---

## 8. Anexo matemático

**Coste en R**

```
c_rt   = 2·(fee + half_spread + impact)          [fracción del nocional]
cost_R = c_rt / d_stop,  d_stop = k·ATR_t / P_t   [fracción del precio]
```

**Funding en R**

```
funding_R = side · Σ_{t_i ∈ (t_entry, t_exit]} f_i / d_stop
```

**Kelly fraccional** (MacLean–Thorp–Ziemba)

```
f* = μ/σ² ;  f = c·f* ,  c ∈ (0,1]
crecimiento ≈ c(2−c)·μ²/(2σ²) ;  volatilidad ≈ c·σ
```

**Sharpe y t-stat**

```
SR_diario = mean(r_d)/std(r_d) ;  SR_anual = SR_diario·√365  (solo bajo iid)
t = SR_anual·√T_años
hurdle HLZ: SR > 3/√T
```

**DSR** (Bailey & López de Prado 2014)

```
SR₀ = √Var({SR_n}) · [ (1−γ)·Φ⁻¹(1−1/N) + γ·Φ⁻¹(1−1/(N·e)) ],  γ ≈ 0,5772
DSR = Φ( (SR − SR₀)·√(T−1) / √(1 − γ₃·SR + ((γ₄−1)/4)·SR²) )
```

**MinBTL** (Bailey et al., *Notices AMS* 2014)

```
MinBTL ≈ 2·ln(N) / E[max SR]²   [años]
```

**PBO/CSCV** (Bailey et al. 2016): partir la serie en S bloques; para cada combinación de S/2 bloques como IS, elegir la mejor config IS, calcular su rango OOS normalizado ω y el logit λ = ln(ω/(1−ω)); PBO = P(λ < 0).

**Ley de impacto**

```
Δ = Y·σ·√(Q/V),  Y ≈ 1
OFI: Δp ≈ (1/depth)·OFI
```

---

## 9. Verificación con runner determinista (E15)

El contrato de `PROMPT_V4` exige que ningún número de rendimiento lo produzca un modelo. Para
comprobar que el contrato es ejecutable y no solo declarativo, se implementó el runner y se
re-ejecutaron tres de las corridas ya registradas.

### E15. El registro declaraba un `atr_k` que el motor no usaba

`research/study_costs.py` recibe la distancia de stop dentro de cada tupla de entrada
(`(bar_index, side, stop_distance)`); el campo `Exit.k_atr` **no participa** en `run_trades`.
Todas las corridas se generaron con `1,5 × ATR(14)`, pero `build_registry_seed.py` escribía
`params.atr_k = 2.0` para las variantes 4h/1d.

Consecuencia: las **métricas del registro son correctas** (corresponden a 1,5×ATR); lo que estaba
mal era el metadato de parámetros, que es justo lo que un auditor usaría para re-ejecutar. Un
registro con parámetros incorrectos es un registro que no se puede verificar.

Corrección: `build_registry_seed.py` declara `atr_k = 1.5` y `Exit(1.5, …)`; el hallazgo queda
anotado como evento en el log del registro. No se reescribe ninguna corrida (append-only): los
artefactos históricos conservan su metadato original y el runner documenta la diferencia.

### Reproducción exacta

| Spec ejecutada | Trades | PF bruto | PF neto | IC95% PF | MDD | Sharpe | Corrida registrada |
|---|---|---|---|---|---|---|---|
| `btc-trend-1d-donchian-40` | 58 | 1,877 | 1,683 | 0,912–2,685 | −4,6% | 0,64 | idéntica |
| `btc-trend-4h-donchian-24` | 524 | 1,155 | 1,055 | 0,843–1,276 | −15,3% | 0,15 | idéntica |
| `btc-mom-5m-ema-12-48` | 15.102 | 0,998 | 0,490 | 0,472–0,509 | −100,0% | −12,73 | idéntica |

Única diferencia: `t-stat` del 1d sale 1,67 frente a 1,66 registrado, por redondeo del Sharpe en
el cuarto decimal. Todo lo demás coincide al dígito.

### Lo que el runner añade sobre el registro

| Puerta de §6 | Registro SQLite | Runner |
|---|---|---|
| Integridad de datos | declarada en la semilla | recalculada del fichero + `data_hash` |
| t-stat OOS | no existía (todo era in-sample) | calculado sobre el 20% reservado |
| IC95% del PF OOS | solo sobre el total | por tramo IS/OOS/reserva |
| Stress 2× | sí | sí, más **break-even de coste** por bisección |
| Plateau ±10%/±20% | no | sí, re-ejecutando la spec perturbada |
| Alpha vs BTC con IC | no | sí, bootstrap de bloques del exceso diario |
| MDD vs presupuesto | sí | sí |
| PBO / DSR / MinBTL / WFA | sí (a nivel de ciclo) | `null` + `missing_artifacts` → INCONCLUSIVE |

El runner **no** sustituye al ciclo: PBO, DSR, MinBTL y WFA requieren el conjunto de
configuraciones, y por eso se reportan como ausentes en vez de estimarse con una sola spec. Un
veredicto `APPROVED` sigue siendo imposible sin ellos.

### Verificación de las tres specs

```
BTC-TREND-1D  n=58     PF neto 1,683  CI95 [0,912; 2,685]  MDD −4,6%   break-even 269,5 pb RT
BTC-TREND-4H  n=524    PF neto 1,055  CI95 [0,843; 1,276]  MDD −15,3%  break-even  17,7 pb RT
BTC-MOM-5M    n=15102  PF neto 0,490  CI95 [0,472; 0,509]  MDD −100,0% sin break-even
```

Lectura económica de esos tres números: el 4h y el 5m mueren por coste (break-even 17,7 pb frente
a los 10,14 pb pagados, y en 5m ni con coste cero llega a PF 1,00); el 1d tiene margen de coste
amplio (269,5 pb) pero no potencia: 58 trades y 10 en OOS. Ninguno bate a BTC con significancia.

### E16. El registro y el runner podían dar veredictos distintos

Al registrar una spec desde el runner apareció una incoherencia real: para
`BTC-TREND-1D-v1.0.0-1d_40` el servidor devolvía `INCONCLUSIVE` y el runner `REJECTED`. No era un
fallo de cálculo de ninguno de los dos: el registro solo evaluaba 7 puertas y la que tumba el 1d
es el **alpha frente a buy & hold** (−72,8 % anual, IC95 % [−147,7 %; +11,4 %]), que el registro
no conocía. Dos fuentes de verdad con veredictos distintos es exactamente el fallo que este
informe denuncia en el prompt original.

Corrección, sin reescribir historia:

- `POST /api/runs` acepta `alpha_annual` y `plateau_pass`; con ellos el servidor añade las puertas
  `benchmark_alpha` y `plateau` y aplica la misma regla de rechazo que el runner. Verificado: la
  misma spec pasa de `INCONCLUSIVE` a `REJECTED` con razón «alpha nulo o negativo frente a buy &
  hold».
- Si el veredicto enviado por el runner (`runner_verdict`) difiere del recalculado, el servidor
  responde con `conflict` y escribe un evento `audit` en el log. Nada se corrige en silencio.
- Las corridas históricas conservan su veredicto (append-only); la vista Runner marca la
  discrepancia en pantalla con el motivo.

```
registro: 201 verdict=REJECTED reason="alpha nulo o negativo frente a buy & hold" conflict=None
          gates: 7 de registro + benchmark_alpha(-0,7284) + plateau(plano)
```

### E17. Cuatro de las doce puertas no podían evaluarse nunca

El runner dejaba PBO, DSR, MinBTL y WFA en `null` y anotaba `missing_artifacts`. Era honesto —no
se inventaban cifras— pero dejaba el sistema en un callejón: **ninguna estrategia podía pasar de
`INCONCLUSIVE`**, por muy buena que fuera, porque tres de esas cuatro puertas están en
`REJECT_ON_FAIL` y su ausencia se registraba como dato faltante para siempre.

Esas cuatro puertas no son propiedades de un backtest, son propiedades de una **selección**. Por
eso no se pueden añadir al runner: hay que ejecutar el universo y medir cómo se eligió. Se
implementó `runner/selection_cycle.py`:

| Puerta | Método | Implementación |
|---|---|---|
| PBO | CSCV, Bailey-Borwein-López de Prado-Zhu (2015) | 15 configuraciones × 2.496 días → matriz diaria; 10 bloques; las 252 particiones 5+5; rango OOS de la ganadora IS |
| DSR | Deflated Sharpe, Bailey & López de Prado (2014) | SR₀ con `Var({SRₙ})` de las 5 variantes de la misma hipótesis; ajuste por skew y kurtosis |
| MinBTL | `2·ln(N)/SR²` | comparado con la cobertura real del dataset |
| WFA | ventana expansiva con 30 % de calentamiento | 5 folds; en cada uno se elige por PF IS y se mide PF y trades OOS |

Universo: 5 vecindades paramétricas (×0,5 ×0,7 ×1,0 ×1,4 ×2,0) sobre el parámetro que se ajustó
en cada familia — Donchian N en 1d y 4h, EMA lenta en 5m. 15 configuraciones, 2.496 días.

**Resultado medido** (`runner/validation/CYCLE-2026-11-selection.json`, `specs_hash 87eea8aa…`):

| Puerta | Valor | Umbral | |
|---|---|---|---|
| PBO | 0,238 | ≤ 0,20 | falla |
| DSR | 0,792 | ≥ 0,95 | falla |
| MinBTL | 14,6 años | ≤ 6,8 disponibles | falla |
| Trades/fold | 6 | ≥ 30 | falla |

Tres lecturas que el registro anterior no podía dar:

1. **El PBO mejora al ampliar el universo, y aun así falla.** Con las 8 configuraciones del
   estudio 5m el PBO era 0,50; con las 15 de las tres familias baja a 0,238. Sigue por encima de
   0,20: en el 24 % de las particiones, la configuración que gana in-sample queda por debajo de la
   mediana out-of-sample. Más datos de selección ayudan, pero no lo arreglan.
2. **El DSR dice que el Sharpe no sobrevive.** El mejor Sharpe anual del universo es 0,61 y el
   máximo esperado por azar entre 5 variantes es 0,34. Con 58 trades, la probabilidad de que ese
   Sharpe sea real es 0,792, por debajo de 0,95.
3. **El walk-forward sí gana, y no basta.** El procedimiento de selección produce PF 1,387 sobre
   43 trades fuera de muestra en 5 folds — la señal existe. Pero 6 trades por fold no permiten
   afirmar nada: es el mismo problema de potencia que el resto del informe, visto por dentro.

Efecto sobre las corridas: los tres specs pasan de `INCONCLUSIVE` a `REJECTED` con las 12 puertas
evaluadas y cero datos faltantes. El ciclo se registró por `POST /api/cycles`, un endpoint nuevo
que **no se cree las cifras**: exige el `validation_ref` del artefacto y devuelve `409` si algún
número del payload no coincide con el fichero citado.

### E18. La segmentación por regímenes no particionaba los trades

Al añadir el corte por régimen (volatilidad y tendencia en terciles) para cerrar el último paso
pendiente del pipeline, el conteo delató el error: los tres tramos sumaban 20.136 trades sobre una
corrida de 15.102. El tercer tramo usaba `values >= q1` en lugar de `values >= q2`, así que se
llevaba también el tramo medio — dos tercios de la muestra etiquetados como "volatilidad alta".

El PF por régimen de los tres specs estaba mal calculado. Corregido, y ahora hay un test que exige
que los tres tramos de cada eje sumen exactamente el número de trades:

```
BTC-MOM-5M    n 15102 | suma buckets 15102 | OK
BTC-TREND-1D  n    58 | suma buckets    58 | OK
BTC-TREND-4H  n   524 | suma buckets   524 | OK
```

### El régimen explica el 4h

Con el corte corregido aparece un patrón que ninguna métrica agregada mostraba:

| Corrida | PF volatilidad baja / media / alta | PF quieto / deriva / tendencia |
|---|---|---|
| 1d Donchian 40 | 2,91 / 1,31 / 1,15 | 1,08 / 1,71 / **2,42** |
| 4h Donchian 24 | 1,07 / 1,09 / 1,00 | **0,73 / 0,81** / 1,83 |
| 5m EMA 12/48 | 0,27 / 0,55 / 0,78 | 0,30 / 0,47 / 0,82 |

El 4h es plano en volatilidad y **pierde dinero en mercado lateral** (PF 0,73 y 0,81) ganándolo
todo en tendencia (1,83). Su PF neto agregado de 1,055 no es un edge débil: es un edge real
compensado por dos regímenes en los que la regla no debería operar. El 5m, en cambio, pierde en
todos los tramos: no hay régimen que lo salve, solo coste.

**Lo que no se hace con esto.** La tentación inmediata es añadir un filtro de tendencia al 4h y
volver a medirlo. Sería data snooping: el régimen se identificó mirando los 6,8 años completos, así
que un filtro construido ahora y validado sobre los mismos datos hereda el sesgo que este informe
mide. La forma correcta es tratarlo como hipótesis nueva — spec `donchian` con condición de
régimen, ciclo de selección propio, y datos posteriores a esta fecha como único juez. Queda
anotado como línea de trabajo, no como resultado.

### El registro entero se re-ejecutó: 19 de 19

Las métricas del registro las escribieron los scripts de `research/`. El motor que las produce es
una pieza distinta. Hasta ahora nadie había comprobado que coincidieran para las 19 corridas, solo
para 3 specs de referencia.

`runner/verify_registry.py` reconstruye cada corrida desde sus propios `params` — familia, marco
temporal, regla, ATR, objetivo, time-stop, coste y funding — la re-ejecuta sobre el mismo dataset y
compara contra lo almacenado. No lee `runner/out/` ni el artefacto del ciclo: parte de la base de
datos y del motor, que es lo que hace la comprobación significativa.

```
19/19 corridas reproducen al dígito   (n exacto · PF/MDD/t ±0,0015)
```

| Familia | Corridas | PF neto observado |
|---|---|---|
| Donchian (5m/4h/1d) | 10 | 0,643 – 1,683 |
| EMA 12/48 – 48/192 | 3 | 0,490 – 0,530 |
| Reversión z=2 (N 48/96/192) | 3 | 0,478 – 0,537 |
| ORB 15/30/60 min | 3 | 0,624 – 0,746 |

Que todas reproduzcan no valida ninguna estrategia: valida el **instrumento**. Significa que las
cifras de este informe salen de ejecutar el código, no de una transcripción, y que cualquiera
puede llegar al mismo número desde la base de datos con un comando.

El verificador confirma además el diagnóstico E15 desde el otro lado: usa `1.5·ATR` porque es lo
que el motor ejecutó, y deja el valor en el informe (`atr_k_executed`) para que la discrepancia con
el metadato de 4h/1d sea visible en lugar de silenciosa.

### Prueba de sensibilidad: qué pasa si el universo son las 19 corridas

El ciclo canónico mide el PBO sobre vecindades paramétricas (15 configuraciones de 3 ejes). Pero
el investigador miró más: también descartó momentum, reversión y ORB en 5m. Si el espacio de
búsqueda real fue de 19 configuraciones, el PBO debería contarlas.

Se puede medir: `selection_cycle.py --from-registry` reconstruye las 19 corridas registradas como
specs ejecutables y repite las puertas sobre ese universo. El resultado desmonta una intuición.

| Puerta | Canónico (15) | Registro (19) |
|---|---|---|
| PBO | 0,238 | **0,000** |
| DSR | 0,792 | 0,843 |
| SR₀ anual | 0,34 | 0,28 |
| MinBTL | 14,6 años | 15,8 años |
| Trades/fold | 6 | 6 |

**El PBO de 0,000 no es robustez, es un artefacto.** Nueve de las 19 configuraciones pierden dinero
en todos los bloques temporales, así que la ganadora in-sample (1d Donchian 40) gana también fuera
de muestra por eliminación: el CSCV no tiene nada que discriminar. Un PBO bajo exige un universo
**homogéneo**, donde todas las candidatas son plausibles. Mezclar familias con y sin edge hace que
la métrica premie lo obvio.

Por eso el ciclo canónico no adopta este universo. El experimento se conserva como
`runner/validation/sensitivity/CYCLE-2026-11-full.json` (fuera del glob que consume el runner) y se
muestra en la interfaz marcado como *prueba, no canónico*.

Lo que sí aporta es el **DSR por grupo de hipótesis**, que ordena los marcos temporales sin
ambigüedad:

| Familia | Trials | DSR | Sharpe anual vs SR₀ |
|---|---|---|---|
| TREND-1D | 5 | 0,843 | 0,61 vs 0,28 |
| TREND-4H | 3 | 0,573 | 0,35 vs 0,28 |
| TREND-5M | 2 | 0,000 | −4,08 vs 0,66 |
| MOM-5M | 3 | 0,000 | −6,46 vs 2,62 |
| MR-5M | 3 | 0,000 | −11,32 vs 2,49 |
| ORB-5M | 3 | 0,000 | −3,26 vs 1,12 |

Ninguna familia aprueba el 0,95, pero la distancia al umbral es informativa: el 1d está a 0,11, el
4h a 0,38, y todo lo de 5m tiene Sharpe negativo — no es que no supere el ruido, es que pierde
dinero antes de comparar. El coste por operación, con 4.000 a 27.000 operaciones, se come cualquier
señal intradía de esta muestra.

### Ninguna de las 19 bate a comprar y mantener

Un PF de 1,68 no dice nada sobre si convenía operar en lugar de comprar el activo y esperar. El
verificador mide ahora ese exceso en el tramo fuera de muestra (60–80% del intervalo), con
bootstrap de bloques.

```
0 baten · 6 sin concluir · 13 pierden
```

El patrón no es accidental: los seis "sin concluir" son las tres variantes de 1d y las tres de 4h
— las únicas con PF > 1 — y su intervalo roza el cero por arriba sin cruzarlo. Todo lo de 5m pierde
con el intervalo entero en negativo.

| Configuración | α anual | IC95 | Veredicto |
|---|---|---|---|
| 1d Donchian 55 | −63,1% | [−130%, +16%] | sin concluir |
| 1d Donchian 40 | −72,8% | [−148%, +11%] | sin concluir |
| 4h Donchian 24 | −76,8% | [−155%, +8%] | sin concluir |
| 1d Donchian 10 | −81,4% | [−155%, −2%] | pierde |
| ORB 60 min | −127,1% | [−211%, −43%] | pierde |
| EMA 12/48 | −558,4% | [−671%, −447%] | pierde |

**La comparación directa es injusta, y por eso se hace también igualada.** Una regla que arriesga
0,5% por operación produce retornos pequeños por construcción: pierde frente a un activo que subió
mucho por razones de tamaño de posición, no de edge. El verificador escala la serie diaria por
σ(B&H)/σ(estrategia) y repite el cálculo:

```
a igual riesgo: 0 baten · 7 sin concluir · 12 pierden
mejor caso: −28,6% anual con apalancamiento ×17,5
```

Es decir: para igualar la volatilidad de comprar y mantener, la mejor configuración necesitaría
apalancarse 17,5 veces y aun así quedaría 28,6% anual por debajo. El escalado es constante y no
capitaliza el apalancamiento (que también multiplicaría el drawdown), así que el número es
optimista para la estrategia, no pesimista.

La conclusión operativa de todo el informe cabe aquí: en esta muestra, ninguna de las 19
configuraciones justifica operar en vez de mantener el activo.

### E19. El gate encontró lo que nadie había mirado

`runner/verify_all.py` existe para responder una sola pregunta antes de citar cualquier cifra:
¿sigue todo esto siendo cierto? En su primera ejecución encontró tres defectos reales.

**1. El script de la semilla no compilaba.** En `research/build_registry_seed.py` la lista de marcos
temporales y el bucle `for` habían quedado en la misma línea, producto de una edición previa:

```python
htf = [("4h", 12, 20), ..., ("1d", 100, 90)]    for rule, n, hold in htf:
```

`ast.parse` falla. El registro existente se había generado antes de esa edición, así que nada se
notó: el proyecto tenía un fichero que no se podía ejecutar y ningún proceso lo comprobaba. Es el
tipo de error que solo aparece cuando alguien intenta reproducir el trabajo desde cero.

**2. Los artefactos citaban un ciclo y consumían otro.** Los tres `result.json` decían
`cycle_id: CYCLE-2026-11` mientras sus cifras de PBO/DSR venían de `CYCLE-2026-11-selection`. El
default de `--validation` era una ruta fija (`CYCLE-2026-11.json`) y la interfaz mostraba el
artefacto más reciente del directorio; nadie comparaba ambas cosas. Un artefacto que nombra un
ciclo distinto del que lo juzgó es un problema de trazabilidad, no de formato: invalida el campo
`cycle_id` como prueba.

Corrección: el default pasa a ser el directorio ("usa el más reciente", igual que la interfaz) y el
`cycle_id` que se escribe **se lee del artefacto de validación consumido**, no de la línea de
comandos. Si no coinciden, avisa por stderr y registra el real.

**3. Un tipo de evento mal escrito se degradaba en silencio.** `POST /api/events` aceptaba
cualquier `type` y caía a `note` cuando faltaba. Tres auditorías entraron como `note` por enviar
`kind` en lugar de `type`, y el log las mostraba como observaciones humanas, perdiendo su
significado. Ahora el endpoint rechaza campos desconocidos, valida `type` contra
`{run, audit, note, cycle}` y exige `run_id` en los eventos de tipo `run`:

```
kind mal escrito -> 400 campos desconocidos: ['kind']; se espera 'type', no 'kind'
type inválido    -> 400 type inválido: 'kind'
run sin run_id   -> 400 un evento de tipo 'run' necesita run_id
audit correcto   -> 201 {"id": 28, "type": "audit"}
```

Los eventos 25–27 **no se reescribieron**: siguen en el log como `note` y el evento 28 documenta
qué pasó. Reescribir historia es justo lo que este registro existe para impedir.

El gate queda como comando único, con código de salida para CI:

```
$ python runner/verify_all.py
  ok   sintaxis  9 py · 1 js
  ok   tests     49 tests, 1.964s OK
  ok   registro  19/19 corridas reproducen al dígito
  ok   puertas   3 artefactos · 36 puertas evaluadas
  ok   ciclo     CYCLE-2026-11-selection · data 80d6a6014eb92b23 · PBO 0.2381 · DSR 0.7917

5 de 5 comprobaciones pasan
```

Hay un tercer hallazgo implícito: **nada de esto lo detectaron los tests**. El test suite cubre el
motor y las métricas, no el proyecto. Un fichero que no compila y un campo mal citado son fallos de
integridad del repositorio, y para eso hace falta ejecutar el repositorio, no sus funciones.

---

### E20. Dos métodos estándar no coinciden sobre el PBO, y uno de los míos estaba sesgado

La revisión de literatura de 2024-2026 trajo tres correcciones que afectan al ciclo de selección.

**Primera: el PBO depende del método más de lo que el informe admitía.** El ciclo publicaba un
único PBO de 0,238 medido con CSCV (particiones simétricas, mitad dentro y mitad fuera). Añadí
CPCV —validación cruzada combinatoria con purga y embargo, el método que la literatura reciente
encuentra superior a walk-forward para controlar falsos descubrimientos (Knowledge-Based Systems,
vol. 305, dic. 2024)— sobre el mismo universo y los mismos datos:

| Método | Valor | Umbral 0,20 | Caminos |
|---|---|---|---|
| PBO · CSCV (S=10, 252 particiones) | 0,238 | falla | 252 |
| PBO · CPCV (10 bloques, 2 de test, purga 1) | 0,156 | pasa | 45 |

El umbral cae justo en medio. La conclusión honesta no es elegir el número que conviene: es que
**con 15 configuraciones y 6,8 años, el PBO en este rango no distingue**, y sostener «la puerta PBO
falla» como evidencia fuerte era más de lo que el dato aguanta. La puerta se sigue evaluando con
CSCV por ser el método declarado y pre-registrado, y CPCV se publica al lado. El veredicto no cambia
porque no depende de esta puerta: PF neto 1,683 sobre 58 trades, t OOS 1,66, MinBTL 14,6 años sobre
6,8 disponibles y alpha negativo la rechazan por separado.

**Segunda: al implementar CPCV encontré un sesgo mío.** La primera versión descartaba toda
partición en la que el lado de entrenamiento quedara por debajo de la mitad de los bloques. Como
cada bloque de test prohíbe a sus vecinos por la purga, eso eliminaba sistemáticamente los caminos
con bloques de test separados: reportaba 0,150 medido sobre 20 caminos de 45 posibles. Corregido a
«al menos dos bloques de entrenamiento», el número es 0,156 sobre los 45 caminos completos. El sesgo
no cambiaba la conclusión, pero medía una submuestra no aleatoria y lo presentaba como el total.

**Tercera: el PSR y el DSR responden preguntas distintas, y las dos importan.**

| Diagnóstico | Valor | Pregunta |
|---|---|---|
| PSR contra cero, sin deflactar | 0,968 | ¿hay señal, o esto es ruido? |
| DSR con 5 pruebas, SR₀ 0,34 anual | 0,792 | ¿sobrevive esa señal a haber probado 5 variantes? |

Ambos son ciertos a la vez: hay algo por encima de cero, y no alcanza para atribuirlo a la regla
tras ajustar por multiplicidad. Presentar solo el DSR hacía parecer que no había nada; presentar
solo el PSR habría sido una venta. La revisión independiente de la geometría de mesetas llega a la
misma conclusión por otro camino: sobre 9.000 problemas de optimización simulados, el PSR simple
resultó el mejor diagnóstico único y los umbrales fijos de «robustez de meseta» no están calibrados
(*Plateaus, Peaks, and the Probability of Backtest Overfitting*, 2025). Por eso la puerta de meseta
±20% queda declarada como heurístico, no como test: sigue en el pipeline porque detecta picos
aislados evidentes, pero no se presenta como evidencia estadística.

**Contexto de literatura que respalda el veredicto negativo.**

- El momentum en cripto sufre crashes severos y un solo activo puede volver insignificante el
  retorno del portafolio; el escalado por volatilidad mitiga el problema (Financial Markets and
  Portfolio Management, 2025; Finance Research Letters, vol. 85, 2025: Sharpe 1,12 → 1,42). Nuestro
  4h pierde precisamente en los tramos de baja volatilidad (PF 0,73 en «quieto»), que es el régimen
  donde el escalado ayudaría.
- El carry de futuros perpetuo (largo spot, corto perp) fue muy rentable y **su rentabilidad se
  comprimió con fuerza desde 2024** (BIS Working Paper 1087; *Cryptocurrency as an Investable Asset
  Class*, arXiv 2510.14435, 2026). Esto importa para la puerta de funding: el signo del funding ya no
es el de 2021, y una estrategia larga en perp paga un carry que dejó de ser marginal.
- La evidencia de momentum en cripto es discutida: hay trabajos que lo encuentran robusto en
  large-caps y otros que lo llaman ilusión (Grobys, *Cryptocurrency Momentum: Is It an Illusion?*,
  International Journal of Finance & Economics, 2026). Un solo estudio no sostiene una estrategia.

---

### E21. La diversificación entre activos cripto no compra potencia

El rechazo de la línea de tendencia nunca fue por rentabilidad: el ensemble 1d tiene PF neto 1,50
sobre 311 trades. Fue por potencia. Con un solo activo y 6,8 años, la única salida era esperar una
década, así que el paso siguiente fue ampliar el universo: BTC, ETH, BNB y XRP perpetuos, 5m desde
2020, con la misma fuente y la misma validación de integridad.

**Integridad.** Cuatro activos, 0 gaps y 0 duplicados tras rellenar desde el archivo diario los
huecos que los mensuales dejan a fin de mes (XRP tenía 72 h y 48 h ausentes en febrero y marzo de
2022; los 7 días se recuperaron). Ventana común 2020-02-10 → 2026-10-31, 6,72 años, limitada por BNB.

**El edge es en parte transversal.**

| Activo | Trades | PF neto | Sharpe | t | MDD |
|---|---|---|---|---|---|
| BTCUSDT | 311 | 1,496 | 0,64 | 1,66 | −3,1% |
| ETHUSDT | 318 | 1,781 | 0,91 | 2,37 | −2,7% |
| BNBUSDT | 308 | 1,635 | 0,72 | 1,86 | −2,6% |
| XRPUSDT | 274 | 1,001 | −0,02 | −0,04 | −6,1% |
| **Agregado (1/4 de riesgo cada uno)** | **1 211** | **1,489** | **1,10** | **2,85** | **−1,7%** |

Tres de cuatro activos tienen PF > 1,4 y XRP no tiene edge. Eso es un resultado real: la regla no
está calibrada a BTC.

**Y sin embargo no gana potencia, que era el objetivo.** El t agregado de 2,85 trata 1 211 trades
como independientes. No lo son. Hay tres correlaciones medibles entre los activos:

| Correlación entre activos | Valor | Qué mide |
|---|---|---|
| De los retornos de la estrategia | 0,078 | Engaña: dos libros que no operan el mismo día no están correlacionados, solo desincronizados |
| Condicional a que ambos libros estén dentro | 0,342 | La dependencia cuando de verdad hay exposición simultánea |
| De los retornos diarios del activo | 0,644 | La dependencia real; es la que usaría un crítico |

Con k activos y correlación media ρ, la potencia efectiva es ≈ n/(1+(k−1)ρ). Con ρ = 0,644 y k = 4,
el factor es 0,341, y el t ajustado queda:

| Ajuste | t | Pasa el umbral 3,0 |
|---|---|---|
| Bruto (activos independientes) | 2,85 | no |
| Con correlación condicional 0,342 | 2,00 | no |
| Con correlación de mercado 0,644 | **1,67** | no |

**1,67 frente al 1,66 de BTC solo.** Cuadruplicar el número de activos no movió la potencia: la
ganancia bruta de 2,85 era la ilusión de contar el mismo movimiento cuatro veces. Para alcanzar
t = 3 con esta correlación harían falta 21,8 años, más que los 22 que ya pedía un solo activo.

La misma prueba sobre el 4h da lo mismo con peor PF: agregado 1,127 con t ajustado 1,00.

**Lo que sí mejoró.** El PF agregado (1,489) es más estable que cualquier activo suelto, el MDD
cae a −1,7% y el stress de costes 2× sigue en 1,459. El universo ampliado no demuestra el edge,
pero lo hace mucho más difícil de explicar por un artefacto de un solo instrumento.

**Consecuencia para el plan.** La vía de la potencia por número de activos está cerrada con
evidencia. Quedan dos: subir el Sharpe por unidad de riesgo, o aceptar que la muestra disponible
no alcanza y decirlo. Cualquier afirmación de que «con más activos el edge se confirma» es falsa
con estos datos.

---

### E22. El coste de spread está bien en calma y se multiplica por diez en las crisis

El informe declaraba que el slippage por fill no se midió. `aggTrades` permite medir el spread
efectivo sin libro, con el estimador de Roll: con rebote bid-ask, los cambios de precio
consecutivos están negativamente autocorrelacionados y el spread se recupera como
2·√(−cov(Δp_t, Δp_t−1)). Cuatro días elegidos por régimen, ~1,2-6 millones de trades cada uno:

| Día | Régimen | Spread medido | Medio spread | Veces el supuesto |
|---|---|---|---|---|
| 2026-06-15 | calma | 0,325 bp | 0,163 bp | ×2,3 |
| 2026-06-16 | calma | 0,181 bp | 0,090 bp | ×1,3 |
| 2024-08-05 | deshacer carry | 1,513 bp | 0,757 bp | ×10,8 |
| 2025-10-10 | liquidación | 2,609 bp | 1,304 bp | ×18,6 |

**El supuesto de 0,07 bp es correcto en régimen normal** (el medido está entre 0,09 y 0,16, es
decir entre 1,3 y 2,3 veces lo asumido) **y se queda corto por un factor de 10 a 19 el día que más
importa**. El modelo de costes aplica un medio spread constante y el stress del runner lo duplica;
un 2× no representa un mercado donde el spread salta 19×.

**Impacto acotado sobre el veredicto.** Para el 1d, con stop mediano del orden del 5%, un spread de
1,3 bp en lugar de 0,07 añade ≈0,025 R por lado, 0,05 R por trade. Si 5 trades de 311 caen en días
de crisis, son 0,25 R sobre un total de 146 R: no mueve ninguna puerta. El hallazgo no cambia el
veredicto, cambia la confianza en el modelo de costes, que es otra cosa.

**Un error propio, y cómo se detectó.** La primera versión del estimador dividía el desequilibrio
de flujo por el nocional y devolvía un spread de 808 pb — un 8%, unas 11 500 veces el coste
modelado. Era imposible y aun así se imprimió. La versión corregida aplica el estimador de Roll y
añade una cota de plausibilidad: si el spread estimado supera 100 pb, el script declara el
día no fiable y no lo usa. Un estimador roto debe fallar en voz alta, no publicar un número.

---

## 10. Límites de este informe (lo que no se verificó)


- **No se ejecutó nada en vivo.** `fapi.binance.com` devuelve HTTP 451 desde este entorno (restricción geográfica de Binance), comprobado el 2026-11-22. Los datos vienen del archivo público `data.binance.vision`, no de la API de trading.
- **No hay L2 completo del histórico.** El slippage realizado por fill no se midió; se modeló con tick, medio spread y ley de impacto. Un modelo OBI calibrado requiere `bookTicker`/`bookDepth`, cuya cobertura en el archivo es parcial (bookDepth solo diario cada 30 s; bookTicker con huecos).
- **No se probaron estrategias de funding carry, basis, ni market making**, que son donde el coste de funding es ingreso y no gasto.
- **Los resultados del estudio de referencia no son una recomendación de inversión** ni una estimación de rentabilidad futura. Son un test de admisión de costes y de potencia estadística.
- **Las tarifas y fórmulas de Binance cambian** (la propia página de futuros muestra promociones temporales). Deben re-verificarse antes de cada ciclo.
- **No se auditó el bot del usuario**, solo el prompt.

---

## 11. Fuentes

| Fuente | Qué se usó | URL |
|---|---|---|
| Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting* (2016) | PBO, CSCV, crítica al hold-out, S=16 → 12.780 combinaciones | https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf |
| Bailey & López de Prado, *The Deflated Sharpe Ratio* (JPM 2014) | PSR/DSR, E[max SR], N de trials | https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf |
| Bailey, Borwein, López de Prado & Zhu, *Pseudo-Mathematics and Financial Charlatanism* (Notices AMS 61(5), 2014) | MinBTL, 2·ln N / E[max SR]² | https://www.ams.org/notices/201405/rnoti-p458.pdf |
| Harvey & Liu, *Backtesting* (JPM 2015) | Haircut del Sharpe; ejemplo SR 0,75 → 0,32 con N=200 | https://people.duke.edu/~charvey/Research/Published_Papers/P120_Backtesting.PDF |
| Harvey, Liu & Zhu, *…and the Cross-Section of Expected Returns* (RFS 2016) | t > 3,0 como hurdle | https://academic.oup.com/rfs/article/29/1/5/1843824 |
| Lo, *The Statistics of Sharpe Ratios* (FAJ 2002) | Anualización √k solo bajo iid | https://www.tandfonline.com/doi/abs/10.2469/faj.v58.n4.2453 |
| Politis & Romano, *The Stationary Bootstrap* (JASA 1994) | Remuestreo con dependencia | https://www.tandfonline.com/doi/abs/10.1080/01621459.1994.10476870 |
| Sullivan, Timmermann & White (JF 1999) | Data snooping; ~8.000 parametrizaciones | https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00163 |
| MacLean, Thorp & Ziemba, *Good and Bad Properties of the Kelly Criterion* | Kelly fraccional, overbet 2× → crecimiento 0 | https://www.stat.berkeley.edu/~aldous/157/Papers/Good_Bad_Kelly.pdf |
| Cont, Kukanov & Stoikov (JFEc 2014) | OFI lineal, pendiente ∝ 1/profundidad | https://academic.oup.com/jfec/article-abstract/12/1/47/816163 |
| Tóth et al. (PRX 2011) | Ley de raíz cuadrada Δ=Yσ√(Q/V) | https://arxiv.org/abs/1105.1694 |
| Shen, Urquhart & Wang (Financial Review 2022) | Momentum intradía BTC: primera media hora predice la última, pendiente 0,968, t NW 4,38, R² 1,44% | https://centaur.reading.ac.uk/100181/3/21Sep2021Bitcoin%20Intraday%20Time-Series%20Momentum.R2.pdf |
| Baltussen, Da, Lammers & Martens (JFE 2021) | Momentum intradía, últimos 30 min, 60+ futuros 1974–2020 | https://academicweb.nd.edu/~zda/intramom.pdf |
| Liu & Tsyvinski (RFS 2021) | Time-series momentum en cripto | https://academic.oup.com/rfs/article-abstract/34/6/2689/5912024 |
| Liu, Tsyvinski & Wu (JF 2022) | Factores market/size/momentum | https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119 |
| Makarov & Schoar (JFE 2020) | Arbitraje y dispersión entre exchanges | https://researchonline.lse.ac.uk/id/eprint/100409/1/Cryptocurrency_Markets_JFE_final_v4.pdf |
| Scaillet, Treccani & Trevisan (JFEc 2020) | Jumps frecuentes y clusterizados; OFI los predice | https://scaillet.ch/pdfs/bitcoin.pdf |
| Zarattini, Pagani & Barbon, *Catching Crypto Trends* (SSRN 5209907, 2025) | Donchian ensemble: Sharpe 1,58, Sortino 2,03, alpha 10,8%, costes excluidos en Tabla 1 | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5209907 |
| Knowledge-Based Systems, vol. 305 (2024) | CPCV supera a walk-forward y K-fold en PBO y DSR; WFA falla en prevenir falsos descubrimientos | https://dl.acm.org/doi/10.1016/j.knosys.2024.112477 |
| *Plateaus, Peaks, and the PBO* (2025) | Sobre 9.000 optimizaciones: la geometría de meseta es diagnóstico débil; el PSR simple es el mejor diagnóstico único; umbrales fijos de robustez no calibrados | https://plateau.marketmaker.cc/paper.pdf |
| Bailey & López de Prado, *The Deflated Sharpe Ratio* | DSR corrige selección bajo múltiples pruebas y no normalidad; base del PSR | https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf |
| Bailey, Borwein, López de Prado & Zhu, *The Probability of Backtest Overfitting* | Definición formal de PBO y CSCV | https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf |
| Schmeling, Schrimpf & Todorov, *Crypto Carry* (BIS WP 1087) | Carry de perpetuos: rentabilidades altas con skew muy negativo; base del trade largo spot / corto perp | https://www.bis.org/publications/working-paper-1087-crypto-carry.pdf |
| *Cryptocurrency as an Investable Asset Class* (arXiv 2510.14435, 2026) | El carry de cripto se comprimió con fuerza desde 2024 | https://arxiv.org/abs/2510.14435 |
| *Cryptocurrency momentum has (not) its moments* (FMPM, 2025) | El momentum cripto sufre crashes severos; un solo activo puede volverlo insignificante; el escalado por volatilidad lo mitiga | https://link.springer.com/article/10.1007/s11408-025-00474-9 |
| *Cryptocurrency market risk-managed momentum* (Finance Research Letters, vol. 85, 2025) | Barroso–Santa-Clara en cripto: Sharpe 1,12 → 1,42, mejora por retorno y no solo por riesgo | https://ideas.repec.org/a/eee/finlet/v85y2025ipas1544612325011377.html |
| Grobys, *Cryptocurrency Momentum: Is It an Illusion?* (IJFE, 2026) | Cuestiona la robustez del momentum cripto por dependencia de cola | https://onlinelibrary.wiley.com/doi/10.1002/ijfe.70036 |
| Huang, Sangiorgi & Urquhart, *Cryptocurrency Volume-Weighted TSMOM* (SSRN 4825389, 2024) | TSMOM ponderado por volumen: 0,94%/día, Sharpe 2,17 (sin costes explícitos) | https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4825389 |
| Freqtrade docs | `lookahead-analysis`, `recursive-analysis`, advertencia de falsos negativos | https://www.freqtrade.io/en/stable/lookahead-analysis/ |
| Binance — futuros fees | Maker 0,0200% / Taker 0,0500% regular; BNB 10% | https://www.binance.com/en/fee/futureFee |
| Binance — spot fees | 0,1000% / 0,1000%; 0,0750% con BNB | https://www.binance.com/en/support/faq/fee-structure-on-binance-115000429332 |
| Binance — funding | Fórmula actualizada 2025-09-18; 0,01% por 8h; cap ±0,30% BTCUSDT | https://www.binance.com/en/support/faq/introduction-to-binance-futures-funding-rates-360033525031 |
| Binance — trading rules USDⓈ-M | Tick 0,10; mín. 0,001 BTC; price protection 3%; liquidation clearance fee 1,25%; mín. nocional 50 USDT | https://www.binance.com/en/futures/trading-parameters/perpetual |
| Binance Data Collection | Datasets y cobertura (klines, aggTrades, bookDepth, bookTicker, fundingRate, metrics) | https://data.binance.vision/ |
| Binance Developer Docs | Base `fapi.binance.com`; testnet `demo-fapi.binance.com` | https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/general-info |
| CoinDesk / Reuters (2025-10) | Liquidaciones >19 B USD el 2025-10-10 | https://www.coindesk.com/research/market-spotlight-the-19-billion-liquidation-that-shook-crypto |

**Datos y reproducibilidad:** `research/load_data.py` (descarga + integridad), `research/study_costs.py` (5m, costes, PBO/DSR), `research/funding_study.py` (4h/1d, funding real, WFA), resultados en `research/cache/*.json`. Semilla fija (7) para las simulaciones de potencia.
