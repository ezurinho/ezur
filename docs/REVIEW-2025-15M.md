# Review 2025: perfil 15m, cinco variantes y comparación

> 2026-11-26. Alcance: perfil `profiles/okx/config.json` (reference v0.1.0, 15m, fast 7/21, stop 10 ATR, rr 1,0) y universo `data/specs15m` (fast 4/5/7/10/14). Fuente única: **Binance Spot BTCUSDT 1m**, agregada a 15m para el perfil y a 5m para el ciclo. Paper only; no se tocó el perfil que opera ni `config/gates.json`.

## TL;DR

- **Fuente identificada:** `data/BTC_15m_2025.csv` es **Binance Spot**; `data/btc_5m.pkl` es **Binance USDⓈ-M Futures perpetual** (`BTCUSDT_PERP`). No son la misma serie ni el mismo mercado.
- **Alineación 2025:** 35.040 velas 15m comunes, sin faltantes; correlación de cierres **0,999999357**. Los futuros cotizan una mediana de **−4,43 pb** frente a spot (p95 absoluto **5,94 pb**, máximo **138,61 pb** en high). El volumen de futuros es **8,00×** el spot (p05 3,94×, p95 14,25×); no hay factor constante.
- **Fuente única:** se construyó `data/btc_5m_spot.pkl` desde `BTC_1m_binance.csv`; su rejilla 15m coincide con el CSV del perfil con diferencias OHLC **0** y volumen **1,8e-12**. El perfil usa la rejilla 15m spot y el ciclo la rejilla 5m spot.
- **2025 directo del perfil (spot):** 132 operaciones, PF **1,030**, esperanza **+0,028 R** (IC80 −0,086), P&L **+107,61** sobre 25.000 (+0,43 %), DD **947,26** (3,79 %), coste 0,036 R. **RECHAZADA** por G5, G6, G9/G10 y G11.
- **Coste ×2:** PF **0,939**, esperanza **−0,008 R**, P&L **−202,96**. El resultado no paga el doble de coste.
- **Ciclo 2025 de las cinco variantes (5m spot):** 169 días, PBO **0,9762**, DSR **0,0609**, WFA 93 operaciones OOS / PF **0,6603**, CPCV con **91,11 %** de paths OOS negativos. Las cinco variantes quedan con PF < 1; la seleccionada es `fast5` (PF 0,775).
- **Perfil y ciclo no son la misma estrategia:** el perfil usa el plugin `reference` (cruce SMA, sin time stop); las specs usan `ema_state` con time stop de 240 barras. Comparten el nombre `fast7`, no la implementación. La diferencia 132/PF 1,030 frente a 135/PF 0,774 **no es de datos**.
- **YEDBot:** otro mercado (MNQ/NQ/ES 1m), 38 operaciones, PF 1,133, esperanza +0,131 R, DD 7,14 %; falla 9 de sus 14 puertas. Tiene holdout sellado y forward ledger; ezur tiene trial ledger/PBO/DSR/CPCV, pero no holdout sellado. **No se pueden ordenar por PF**; ninguno es promocionable.
- **Nota:** ingeniería **8,4/10**; readiness live **2,5/10**; edge demostrado **2,5/10**; producto/competencia **6,4/10**. No promover; seguir en paper y `live_enabled=false`.

## 1. Fuente y reconciliación

### 1.1 Qué es cada archivo

| Artefacto | Mercado | Evidencia | Cobertura |
|---|---|---|---|
| `data/BTC_15m_2025.csv` | **Binance Spot BTCUSDT** | Es exactamente el remuestreo 15m de `data/BTC_1m_binance.csv` y un subconjunto exacto de `data/BTC_15m_binance.csv`. El CSV no trae venue en una columna; la identificación es por igualdad exacta, no por un metadato embebido. | 64.224 velas 15m, 2025-01-01 → 2026-10-31 |
| `data/btc_5m.pkl` | **Binance USDⓈ-M Futures perpetual** (`BTCUSDT_PERP`) | `data/btc_5m.freeze.json`: `data.binance.vision futures/um 5m BTCUSDT`; hash `83f7e6b8858e9064…`. | 725.760 velas 5m, 2020-01-01 → 2026-11-24 |
| `data/BTC_1m_2025.csv` / `data/BTC_1m_binance.csv` | Binance Spot BTCUSDT 1m | Coinciden en las 963.360 filas comparadas; alimentan la fuente única. | 2025 / histórico spot |
| `data/btc_5m_spot.pkl` | Binance Spot BTCUSDT 5m | Derivado de `BTC_1m_binance.csv`; manifiesto `data/btc_5m_spot.freeze.json`; hash `0d552776…`. | 718.386 velas 5m, 2020-01-01 → 2026-10-31; 105.120 en 2025 |
| `data/BTC_5m_spot.csv` | Binance Spot BTCUSDT 5m | Copia legible del pickle anterior. | Igual que el pickle |

No se usaron `BTC_15m_2025_20261124.csv` ni `recent_15m.csv` para la prueba 2025: extienden o recortan el mismo CSV spot y no aportan una fuente distinta.

El 5m spot conserva el alias interno `BTCUSDT_PERP` porque las cinco specs lo declaran. **El alias no convierte los datos en futuros**: precios y volumen son spot y así quedan en el manifiesto y en el artefacto del ciclo.

### 1.2 Alineación 2025 spot vs futuros

Se compararon las 35.040 velas 15m de 2025, sin faltantes en ninguna de las dos series:

| Campo | Base mediana (futuros/spot − 1) | p95 absoluto | Máximo absoluto |
|---|---:|---:|---:|
| open | −4,4328 pb | 5,9398 pb | 69,2516 pb |
| high | −3,9354 pb | 5,5885 pb | 138,6120 pb |
| low | −4,9142 pb | 6,6765 pb | 108,4146 pb |
| close | −4,4319 pb | 5,9395 pb | 69,2516 pb |

La correlación de cierres es **0,9999993570360303**, pero la base es negativa y persistente: los futuros cotizan por debajo del spot. En 15m, 4 pb ya cambian fills, stops y P&L; el máximo de 138 pb en high es suficiente para invalidar una comparación de operaciones.

El volumen no es comparable: el ratio futuros/spot tiene mediana **8,0035**, p05 **3,9435** y p95 **14,2535**. No existe un factor constante que permita “convertir” uno en otro. La primera vela de 2025 lo ilustra: 93.576 / 175,86 en el CSV spot frente a 93.548,8 / 988,15 en el pickle de futuros.

**Decisión:** usar **Binance Spot 1m** como fuente única. El perfil consume su rejilla 15m; el ciclo consume un 5m derivado de la misma fuente. El pickle de futuros queda como referencia de reconciliación, no se sobrescribe y no se usa para la conclusión 2025.

### 1.3 Verificación de la rejilla

El 5m spot tiene 105.120 velas en 2025 y su agregación a 15m produce 35.040 velas. Contra `BTC_15m_2025.csv`:

| Campo | Diferencia máxima absoluta | Velas exactas |
|---|---:|---:|
| open | 0,0 | 35.040 / 35.040 |
| high | 0,0 | 35.040 / 35.040 |
| low | 0,0 | 35.040 / 35.040 |
| close | 0,0 | 35.040 / 35.040 |
| volume | 1,8189894035458565e-12 | 35.040 / 35.040 |

La rejilla es exacta a efectos numéricos. Cualquier diferencia entre el perfil y el ciclo no puede atribuirse a la fuente ni al remuestreo.

## 2. Perfil 2025 sobre spot

Comando: `python -m server.backtest --dataset data/BTC_15m_2025.csv --config profiles/okx/config.json --from 2025-01-01 --to 2026-01-01 --gates --out data/research/promotion/profile-15m-2025-spot-gates.json`.

| Corrida | Ops | Acierto | PF | Esperanza (IC80) | P&L neto | DD | Coste |
|---|---:|---:|---:|---:|---:|---:|---:|
| Perfil 15m spot, 2025 | 132 | 52,3 % | **1,030** | **+0,028 R** (−0,086) | **+107,61** | **947,26** | 0,036 R |
| Perfil, coste ×2 | 132 | 52,3 % | 0,939 | −0,008 R (−0,121) | −202,96 | 1.035,46 | 0,071 R |
| Perfil, sin tope de stop | 82 | 52,4 % | 1,018 | +0,013 R (−0,130) | +42,49 | 604,07 | 0,030 R |
| BTC buy-and-hold 2025 | — | — | — | — | −6,3 % | −32,02 % | — |

El CSV ya era spot; por eso las cifras son idénticas a las de `profile-15m-2025.json` y `profile-15m-2025-cost2x.json`. El cambio de nombre a `...spot-gates.json` y `...spot-cost2x.json` documenta la procedencia, no un resultado nuevo.

El perfil termina 2025 con una posición abierta (long 21 unidades, entrada 88.905,01, stop 86.061,67, target 91.942,21, abierta 2025-12-22 05:00 UTC). Las métricas no la incluyen (`marked_to_market=false`); el efecto es pequeño, pero debe declararse.

La distribución es una apuesta 1:1: 63 pérdidas cerca de −1 R, 42 ganancias cerca de +0,5/1 R y 27 cerca de +1/2 R. Con 132 operaciones, el IC80 de la esperanza cruza cero. El P&L sin los cinco mejores trades es **−278,11**; los cinco mejores aportan el 10,5 % del bruto. La muestra no demuestra edge.

### 2.1 Puertas

`--gates` devuelve **RECHAZADA**:

- **G5:** PF 1,030 y esperanza +0,028 R, por debajo del umbral.
- **G6:** DD 3,79 % y racha de 6 pérdidas.
- **G9/G10:** P&L sin top-5 −278,11; top-5 10,5 %.
- **G11:** IC80 inferior −0,0857 R.

El **coste ×2** convierte el PF en 0,939 y el P&L en −202,96: el margen es más fino que el coste. **Sin tope de stop** no mejora; el tope bloquea 147 señales, pero al quitarlo el resultado baja a PF 1,018 y 82 operaciones. El tope no es la causa del mal resultado ni oculta un edge.

El período completo del CSV (2025-01 → 2026-10) da 231 operaciones, PF 1,095, esperanza +0,052 R (IC80 −0,033), P&L +593,40. El desglose muestra que **2025 aporta +107,61 (PF 1,030)** y **2026 aporta +485,79 (PF 1,182)**: el positivo se concentra en 2026, que ya forma parte del período de selección. 2025 es el año débil, no un out-of-sample limpio.

## 3. Ciclo 2025 de las cinco variantes

`CYCLE-BOT-15M-2025-SPOT` usa `data/btc_5m_spot.pkl` (5m spot), límites del perfil y 169 días de matriz. El ciclo ejecuta las cinco specs de `data/specs15m` con `--all-specs`.

| Variante | Ops | PF | Esperanza |
|---|---:|---:|---:|
| fast10 | 129 | 0,7655 | −0,1162 R |
| fast14 | 131 | 0,7604 | −0,1429 R |
| fast4 | 135 | 0,7365 | −0,1123 R |
| fast5 | 132 | **0,7753** | **−0,0918 R** |
| fast7 | 135 | 0,7745 | −0,1099 R |

La configuración seleccionada es **`fast5`** (la mejor PF del universo, todavía perdedora). No hay stress ×2 en este ciclo: se ejecutó con `--stress-multiplier 1`, por lo que `stress` queda `null`; no debe citarse como si se hubiera hecho.

| Diagnóstico | Resultado |
|---|---|
| PBO | **0,9762** (CSCV, 10 bloques de 16 días, 252 particiones) |
| DSR | **0,0609** (Sharpe diario −0,109; Sharpe anual −2,0826; 169 observaciones) |
| WFA | 5 folds, **93 operaciones OOS**, PF agregado **0,6603**, `fast14` elegido en los 5 folds |
| CPCV | 45 paths, **91,11 %** con Sharpe OOS negativo; Sharpe medio −0,2017; rank medio 33,78 % |
| PSR | 0,0783; `minBTL` nulo porque el Sharpe no es positivo |

PBO y DSR son propiedades de este universo de cinco variantes, no de una configuración aislada. El WFA vuelve a elegir en cada fold y mide el procedimiento de selección, no la ganadora del ciclo. El CPCV es la lectura más contundente: **nueve de cada diez caminos OOS son negativos**.

### 3.1 Por qué `fast7` no coincide con el perfil

El perfil usa el plugin `reference`: entrada por **cruce** de SMA 7/21, stop 10 ATR, objetivo 1R y **sin time stop**. Las specs usan la regla `ema_state`: entrada tras un cambio de estado EMA 7/21, stop 10 ATR, objetivo 1R y **time stop de 240 barras**. Comparten el periodo rápido 7 y el nombre de la variante, pero no la entrada ni la salida.

Por eso `fast7` hace 135 operaciones en el ciclo y 132 en el perfil, con PF 0,774 frente a 1,030. La rejilla 5m→15m es exacta; la diferencia es de **implementación de estrategia**, no de fuente. La comparación correcta es: el perfil mide el plugin `reference`; el ciclo mide cinco vecindades `ema_state`. No son dos corridas de la misma estrategia.

Esto también corrige la lectura anterior de la review: decir que `fast7` era “el mismo” en ambos artefactos era incorrecto. Lo que comparten es el nombre y el periodo, no la lógica.

## 4. YEDBot: comparación de proceso

YEDBot se analizó desde el clone `https://github.com/yescobard76/YEDBot`, commit `fadf2ae` (2026-11-23). No es un competidor directo: opera otro mercado, otro horario y otra muestra.

| Dimensión | ezur 2025 | YEDBot |
|---|---|---|
| Mercado y datos | BTCUSDT **spot** 15m (Binance) | MNQ/NQ/ES **1m** (Databento GLBX.MDP3) |
| Estrategia | `reference`: cruce SMA 7/21, stop 10 ATR, rr 1 | ORB + SMT 1m |
| Muestra | 132 ops, ventana 2025 | 38 ops, 362 sesiones 2025-01-10 → 2026-06-30 |
| PF | 1,0303 | 1,1328 |
| Esperanza | +0,0279 R | +0,1311 R |
| Neto | +107,61 | +661,44 |
| DD | 947,26 (3,79 %) | 1.967,82 (7,14 %) |
| Peor racha | 6 | 10 |
| Puertas | Falla G5, G6, G9/G10, G11 | Falla G4, G5, G6, G7, G8, G9, G10, G11, G12 (9 de 14) |
| Holdout | No hay holdout sellado; 2025 ya vio selección | Sellado 2026-07-01 → 2026-10-30 |
| Forward | 0 operaciones | 0 sesiones |
| Live | Paper, `live_enabled=false` | Paper, live bloqueado |

**Lectura:**

- YEDBot tiene mejor PF y esperanza en su muestra, pero con **38 operaciones** y un mercado distinto. No se puede concluir que sea mejor por mirar solo el PF; tampoco que ezur sea mejor por tener más operaciones o menor DD.
- Los dos fallan sus puertas. YEDBot falla **9 de 14**; ezur falla **5** (G5, G6, G9/G10, G11). El PF alto de YEDBot no compensa la muestra corta ni las nueve puertas.
- YEDBot tiene una ventaja de **proceso**: holdout sellado y forward ledger encadenado. Ezur tiene **trial ledger encadenado, PBO, DSR, WFA y CPCV**, pero su 2025 no es un OOS limpio y no tiene holdout nuevo. Son fortalezas distintas; no hay ganador metodológico único.
- La comparación honesta es de **disciplina**: ambos son paper, ambos bloquean live y ambos rechazan la promoción. La diferencia de PF es de mercado/muestra, no evidencia de edge.

## 5. Otras referencias

| Referencia | 2025 | Lectura |
|---|---|---|
| BTC buy-and-hold | −6,3 % (apertura→cierre), DD −32,0 % | El perfil bate en retorno y DD, pero con 132 ops y esperanza nula. |
| Perfil 15m | +0,43 % sobre 25k, PF 1,030, DD 3,79 % | Defensivo, no significativo; coste ×2 lo tumba. |
| 4H trend n20 (`CYCLE-2025`) | 25 ops, PF 1,428, esperanza +0,448 R; PBO 0,1667, DSR 0,0371, WFA 15 OOS | Mejor PF, muestra minúscula; no es promocionable. |
| 1D trend n20 | 2 ops, PF 0,0 | No evaluable. |
| 5M EMA | 222 ops, PF 0,538, esperanza −0,577 R | Pierde; el coste domina. |
| Donchian 240 1H (2020-2026) | 2025 −207; PF global 1,034 | Positivo de ruido, sin potencia. |
| Zarattini, Pagani & Barbon (2025) | BTC ensemble: CAGR ~30 %, Sharpe ~1,56, DD ~19 % (2015-2025); top-20: CAGR 18 %, DD 11 %, alpha 10,8 % | Otro horizonte/universo (diario, 9 modelos, vol target 25 %, multi-activo); no comparable, pero el listón de evidencia es muy superior. |

Plataformas (de `docs/INVESTIGACION_COMPETENCIA.md`): NautilusTrader 8,6; QuantConnect LEAN 8,2; Jesse 7,3; Freqtrade 7,1; este repo 6,4. La ventaja propia es disciplina de validación y honestidad de datos; la debilidad es ejecución live y datos. El 2025 no cambia ese perfil.

## 6. Calificación

| Dimensión | Nota | Justificación |
|---|---:|---|
| Ingeniería y motor | **8,4/10** | Motor determinista, gates, DSR/PBO, trial ledger, auditoría y paper-only. |
| Readiness live | **2,5/10** | Sin broker, sin reconciliación de ejecución, sin adapter; no es un bot para dinero real. |
| Edge demostrado | **2,5/10** | 2025: PF 1,030, IC80 cruza cero; ciclo 2025 PBO 0,976, WFA PF 0,660, CPCV 91 % negativo; coste ×2 negativo. La fuente ya está reconciliada y no rescata el edge. |
| Producto/competencia | **6,4/10** | Mejor que Backtrader/VectorBT en validación; lejos de Nautilus/LEAN en ejecución y datos. |

**Veredicto:** laboratorio serio, estrategia no demostrada. El 2025 es positivo frente a BTC y el control de riesgo funciona (DD 3,79 % vs 32,02 %), pero no hay evidencia estadística de edge y el ciclo de las cinco variantes es claramente perdedor. **No promover; mantener paper y `live_enabled=false`.**

## 7. Qué mejorar, por orden

1. **Fuente única: hecho.** El perfil y el ciclo usan spot; la rejilla 15m coincide con el CSV y el 5m está documentado. Mantener el chequeo de alineación en cada regeneración y registrar la procedencia en los artefactos.
2. **No promover y no relajar puertas.** El 2025 no pasa G5/G6/G9/G10/G11; el coste ×2 lo tumba. La respuesta no es otro barrido de parámetros.
3. **Tratar 2025 como regresión, no como OOS.** El perfil ya vio 2025/2026 en la selección; para un OOS real hace falta un holdout nuevo y congelado, como el de YEDBot.
4. **Alinear perfil y specs antes de comparar variantes.** `reference` y `ema_state` no son la misma estrategia. Si se quiere comparar el perfil con las cinco variantes, ejecutar la misma regla y el mismo time stop en ambos lados; si no, declarar que son hipótesis distintas.
5. **Trial ledger y validador independiente.** El ledger encadenado ya existe y reconstruye PBO/DSR; falta un validador externo con fixtures calculados a mano y un control de mutaciones del ledger.
6. **Añadir benchmark y coste ×2 al reporte.** BTC buy-and-hold, DD y coste duplicado deben estar en la misma tabla que el perfil, no en documentos separados.
7. **Si se sigue investigando, cambiar de hipótesis:** funding, base, flujo de órdenes o cartera multi-activo; no otra rejilla de medias/canales 15m. El propio `docs/MEDICIONES.md` ya concluye que el coste y la falta de señal son el límite.

## 8. Reproducibilidad

```bash
# 1. Reconciliar y construir la fuente única spot
python scripts/reconcile_btc_sources.py

# 2. Perfil 2025 con puertas
python -m server.backtest --dataset data/BTC_15m_2025.csv \
  --config profiles/okx/config.json \
  --from 2025-01-01 --to 2026-01-01 --gates \
  --out data/research/promotion/profile-15m-2025-spot-gates.json

# 3. Perfil con coste ×2
python -m server.backtest --dataset data/BTC_15m_2025.csv \
  --config profiles/okx/config.json \
  --from 2025-01-01 --to 2026-01-01 \
  --commission-per-unit 0.098 \
  --out data/research/promotion/profile-15m-2025-spot-cost2x.json

# 4. Ciclo 2025 de las cinco variantes sobre 5m spot
python -m server.selection --cycle CYCLE-BOT-15M-2025-SPOT \
  --dataset data/btc_5m_spot.pkl \
  --spec-dir data/specs15m --all-specs \
  --config profiles/okx/config.json \
  --from 2025-01-01 --to 2026-01-01 \
  --stress-multiplier 1

# 5. Reconstruir PBO/DSR desde el ledger
python -m server.trial_ledger \
  --ledger data/validation/CYCLE-BOT-15M-2025-SPOT.trials.jsonl \
  --artifact data/validation/CYCLE-BOT-15M-2025-SPOT.json
```

Artefactos:

- `data/research/reconciliation/btc_sources_2025.json`: procedencia, alineación y decisión.
- `data/btc_5m_spot.pkl` / `data/BTC_5m_spot.csv`: fuente 5m spot.
- `data/btc_5m_spot.freeze.json`: manifiesto de la fuente 5m spot.
- `data/research/promotion/profile-15m-2025-spot-gates.json`: perfil 2025 y puertas.
- `data/research/promotion/profile-15m-2025-spot-cost2x.json`: coste ×2.
- `data/validation/CYCLE-BOT-15M-2025-SPOT.json`: ciclo spot.
- `data/validation/CYCLE-BOT-15M-2025-SPOT.trials.jsonl`: ledger de los cinco trials.

Identificadores: CSV spot `93cd84382cd1c57e…`; pickle de futuros `83f7e6b8858e9064…`; 5m spot `0d552776199ae850a632c2515a4b5d6b5b4ffae188589003fc85378f0e960071`; config `6a599496fbf3a324`. La reconstrucción del ledger devuelve `matches: true` con PBO 0,9762, DSR 0,0609 y `fast5`.

`data/*` está ignorado por Git: los artefactos se regeneran con los comandos anteriores; no se commitean.
