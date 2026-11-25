# Review 2025: perfil 15m, cinco variantes y comparación

> 2026-11-25. Alcance: perfil `profiles/okx/config.json` (reference v0.1.0, 15m, fast 7/21, stop 10 ATR, rr 1,0) y universo `data/specs15m` (fast 4/5/7/10/14). Datos: `data/BTC_15m_2025.csv` (15m) y `data/btc_5m.pkl` (5m). Paper only; no se tocó el perfil que opera.

## TL;DR

- **2025 directo del perfil (CSV 15m):** 132 operaciones, PF **1,030**, esperanza **+0,028 R** (IC80 −0,086), P&L **+107,61** sobre 25.000 (+0,43 %), DD **947,26** (3,79 %), coste 0,036 R. Bate a BTC buy-and-hold (−6,3 %) con una fracción del drawdown, pero **no es estadísticamente distinto de cero**.
- **Puertas completas:** **RECHAZADA** por G5 (PF/esperanza), G6 (DD/racha), G9/G10 (concentración) y G11 (IC80 inferior negativo).
- **Coste ×2:** PF **0,939**, esperanza **−0,008 R**, P&L **−202,96**. El resultado 2025 no paga el doble de coste.
- **Sin tope de stop:** 82 operaciones, PF **1,018**, esperanza **+0,013 R**, IC80 **−0,130**. El tope de 400.000 ticks no está ocultando un edge.
- **Ciclo 2025 de las cinco variantes (5m, límites del perfil):** 165 días, PBO **0,9881**, DSR **0,0878**, WFA 87 operaciones OOS / PF **0,8045**. Las cinco variantes quedan con PF < 1.
- **Problema de fuente:** el CSV de 15m y el pickle de 5m difieren una mediana de **4,4 pb** en OHLC (máx. 140 pb) y el volumen no escala. `fast7` tiene 132 operaciones en ambos, pero PF **1,030** en el CSV y **0,847** en el ciclo de 5m. El resultado 2025 es **sensible a la fuente**, no un edge robusto.
- **Nota:** ingeniería **8,4/10**; readiness live **2,5/10**; edge demostrado **2,5/10**; producto/competencia **6,4/10**. No promover; seguir en paper.

## 1. Qué se midió

Comandos ejecutados:

```bash
# Perfil actual, solo 2025
python -m server.backtest --dataset data/BTC_15m_2025.csv \
  --config profiles/okx/config.json \
  --from 2025-01-01 --to 2026-01-01 --years \
  --out data/research/promotion/profile-15m-2025.json

# Diagnósticos
python -m server.backtest ... --max-stop-ticks 0 --out ...profile-15m-2025-nocap.json
python -m server.backtest ... --commission-per-unit 0.098 --out ...profile-15m-2025-cost2x.json
python -m server.backtest ... --gates --out ...profile-15m-2025-gates.json

# Período completo del CSV (2025-01 a 2026-10), desglose por año
python -m server.backtest --dataset data/BTC_15m_2025.csv \
  --config profiles/okx/config.json --years \
  --out data/research/promotion/profile-15m-2025-2026-years.json

# Ciclo de selección 2025 de las cinco variantes, límites del perfil
python -m server.selection --cycle CYCLE-BOT-15M-2025 \
  --spec-dir data/specs15m --all-specs \
  --config profiles/okx/config.json \
  --from 2025-01-01 --to 2026-01-01 \
  --stress-multiplier 1
```

Artefactos: `data/research/promotion/profile-15m-2025*.json`, `data/validation/CYCLE-BOT-15M-2025.json`, `data/validation/cycle-15m-2025.log`.

Identificadores: dataset CSV `93cd84382cd1c57e`; config `6a599496fbf3a324`; pickle 5m `83f7e6b8858e9064…`; ventana 2025 del ciclo `20f871eeb20b4cbc…`.

## 2. Resultado 2025

| Corrida | Ops | Acierto | PF | Esperanza (IC80) | P&L neto | DD | Coste |
|---|---:|---:|---:|---:|---:|---:|---:|
| Perfil 15m, 2025 | 132 | 52,3 % | **1,030** | **+0,028 R** (−0,086) | **+107,61** | **947,26** | 0,036 R |
| Perfil, coste ×2 | 132 | 52,3 % | 0,939 | −0,008 R (−0,121) | −202,96 | 1.035,46 | 0,071 R |
| Perfil, sin tope de stop | 82 | 52,4 % | 1,018 | +0,013 R (−0,130) | +42,49 | 604,07 | 0,030 R |
| BTC buy-and-hold 2025 | — | — | — | — | −6,3 % | −32,02 % | — |

El perfil termina 2025 con una posición abierta (long 21 unidades, entrada 88.905,01, stop 86.061,67, target 91.942,21, abierta 2025-12-22 05:00 UTC). Las métricas no la incluyen (`marked_to_market=false`); el efecto es pequeño, pero debe declararse.

La distribución es una apuesta 1:1: 63 pérdidas cerca de −1 R, 42 ganancias cerca de +0,5/1 R y 27 cerca de +1/2 R. Con 132 operaciones, el IC80 de la esperanza cruza cero. El P&L sin los cinco mejores trades es **−278,11**; los cinco mejores aportan el 10,5 % del bruto. La muestra no demuestra edge.

## 3. Puertas y robustez

`--gates` devuelve **RECHAZADA**:

- **G5:** PF 1,030 y esperanza +0,028 R, por debajo del umbral.
- **G6:** DD 3,79 % y racha de 6 pérdidas.
- **G9/G10:** P&L sin top-5 −278,11; top-5 10,5 %.
- **G11:** IC80 inferior −0,0857 R.

El **coste ×2** convierte el PF en 0,939 y el P&L en −202,96: el margen es más fino que el coste. **Sin tope de stop** no mejora; el tope bloquea 147 señales, pero al quitarlo el resultado baja a PF 1,018 y 82 operaciones. El tope no es la causa del mal resultado ni oculta un edge.

El período completo del CSV (2025-01 → 2026-10) da 231 operaciones, PF 1,095, esperanza +0,052 R (IC80 −0,033), P&L +593,40. El desglose muestra que **2025 aporta +107,61 (PF 1,030)** y **2026 aporta +485,79 (PF 1,182)**: el positivo se concentra en 2026, que ya forma parte del período de selección. 2025 es el año débil, no un out-of-sample limpio.

## 4. Ciclo 2025 de las cinco variantes

`CYCLE-BOT-15M-2025` usa el pickle de 5m con límites del perfil y 165 días de matriz:

| Variante | Ops | PF | Esperanza |
|---|---:|---:|---:|
| fast10 | 121 | 0,843 | −0,071 R |
| fast14 | 134 | 0,753 | −0,131 R |
| fast4 | 135 | 0,744 | −0,113 R |
| fast5 | 131 | 0,850 | −0,051 R |
| fast7 | 132 | 0,847 | −0,060 R |

PBO **0,9881** (10 bloques de 16 días), DSR **0,0878** (Sharpe anual −1,374; 165 observaciones), WFA **87 operaciones OOS / PF 0,8045**, CPCV con **91,1 %** de paths OOS negativos. Es un rechazo claro: la selección 2025 no tiene estabilidad.

## 5. El problema de fuente

El CSV de 15m y el pickle de 5m cubren exactamente las mismas 35.040 velas de 15m en 2025, pero no son la misma serie:

| Campo | Diferencia mediana | p95 | Máx. |
|---|---:|---:|---:|
| open | 4,44 pb | 5,94 pb | 68,8 pb |
| high | 3,95 pb | 5,59 pb | 140,6 pb |
| low | 4,92 pb | 6,68 pb | 109,6 pb |
| close | 4,44 pb | 5,94 pb | 68,8 pb |

La correlación de cierres es 0,99999936, pero el nivel y el volumen no coinciden (primera vela: 93.576 / 175,86 en el CSV frente a 93.548,8 / 988,15 en el pickle). El pickle declara `data.binance.vision futures/um 5m BTCUSDT`; el CSV no declara venue en el artefacto. No son la misma fuente/venue, y 4 pb bastan para cambiar fills, stops y P&L en 15m.

Consecuencia: el **mismo `fast7`** hace 132 operaciones en ambos, pero PF 1,030 en el CSV y 0,847 en el ciclo de 5m. El resultado 2025 positivo del backtest directo no se reproduce en el ciclo de selección; no es un bug del motor, es una diferencia de datos. Cualquier conclusión de edge 2025 debe resolverse con una fuente única.

## 6. Comparación con otros

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

## 7. Calificación

| Dimensión | Nota | Justificación |
|---|---:|---|
| Ingeniería y motor | **8,4/10** | 1.045 tests, motor determinista, gates, DSR/PBO, auditoría y paper-only. |
| Readiness live | **2,5/10** | Sin broker, sin reconciliación, sin adapter; no es un bot para dinero real. |
| Edge demostrado | **2,5/10** | 2025: PF 1,030, IC80 cruza cero; ciclo 2025 PBO 0,988, WFA PF 0,805; coste ×2 negativo; fuente no reconciliada. |
| Producto/competencia | **6,4/10** | Mejor que Backtrader/VectorBT en validación; lejos de Nautilus/LEAN en ejecución y datos. |

**Veredicto:** laboratorio serio, estrategia no demostrada. El 2025 es positivo frente a BTC y el control de riesgo funciona (DD 3,79 % vs 32,02 %), pero no hay evidencia estadística de edge y el resultado depende de la fuente de datos. **No promover; mantener paper y `live_enabled=false`.**

## 8. Qué mejorar, por orden

1. **Reconciliar la fuente de datos.** Es el hallazgo principal. El ciclo de selección usa `data/btc_5m.pkl` y el backtest del perfil usa `data/BTC_15m_2025.csv`; difieren 4,4 pb de mediana y el volumen no escala. Antes de otra conclusión 2025, usar la misma venue/feed en promoción, selección y paper; añadir un chequeo de alineación de precios/volumen y registrar la procedencia en el artefacto.
2. **No promover y no relajar puertas.** El 2025 no pasa G5/G6/G9/G10/G11; el coste ×2 lo tumba. La respuesta no es otro barrido de parámetros.
3. **Tratar 2025 como regresión, no como OOS.** El perfil ya vio 2025/2026 en la selección; para un OOS real hace falta un holdout nuevo y congelado.
4. **Añadir benchmark y coste ×2 al reporte.** BTC buy-and-hold, DD y coste duplicado deben estar en la misma tabla que el perfil, no en documentos separados.
5. **Cerrar la posición abierta en las métricas o declararla siempre.** El backtest 2025 termina con una posición long abierta; `marked_to_market=false` es correcto, pero el P&L no es el final completo.
6. **Trial ledger y validador independiente.** Registrar cada spec, dataset, semilla y descarte; contrastar el motor con fixtures calculados a mano. Es la mejora de investigación con más retorno.
7. **Si se sigue investigando, cambiar de hipótesis:** funding, base, flujo de órdenes o cartera multi-activo; no otra rejilla de medias/canales 15m. El propio `docs/MEDICIONES.md` ya concluye que el coste y la falta de señal son el límite.

## 9. Reproducibilidad

- Perfil 2025: `data/research/promotion/profile-15m-2025.json`.
- Diagnósticos: `profile-15m-2025-nocap.json`, `profile-15m-2025-cost2x.json`, `profile-15m-2025-gates.json`.
- Período completo: `profile-15m-2025-2026-years.json`.
- Ciclo 2025: `data/validation/CYCLE-BOT-15M-2025.json` y `data/validation/cycle-15m-2025.log`.
- Datos: `data/BTC_15m_2025.csv` (dataset_id `93cd84382cd1c57e`), `data/btc_5m.pkl` (hash `83f7e6b8858e9064…`), perfil `6a599496fbf3a324`.
