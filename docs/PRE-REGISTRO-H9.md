# Pre-registro H9 — basis spot-perp (cash-and-carry)

**Fecha:** 2026-11-27  
**Estado:** congelado antes de descargar el panel y antes de medir.  
**Hipótesis:** el perpetuo cotiza por encima del spot porque la demanda de
apalancamiento paga una prima; una posición larga en spot y corta en el perpetuo
del mismo activo cobra esa convergencia y el funding, sin exposición direccional.
El basis no es el funding de H5 ni el spread entre venues de H8: es el precio
relativo de dos instrumentos del **mismo venue**.

## Por qué existiría la ventaja

El arbitrajista que compra spot y vende el perpetuo inmoviliza capital en spot,
paga fees y asume margen y liquidación en la pata corta. Esa fricción impide que
el basis se cierre del todo. Chi (2023) encuentra que el factor de basis es el
predictor cross-sectional más fuerte (t=7,10); el BIS documenta un carry medio
superior al 10 % anualizado. La prima no es una ley de precios: sube cuando el
apalancamiento escasea y se comprime cuando el capital arbitrajista llega.

**Dato nuevo:** precios spot diarios de 20 alts de Binance, que no se usaron en
H1-H8. El funding y el perpetuo ya existen, pero la señal es el premium
spot-perp, no el nivel de funding ni el precio del perpetuo.

## Datos y ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Warmup | 2023-05-12 / 2023-07-01 | cubrir lookbacks de 30 días |
| Desarrollo | 2023-07-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez |
| Holdout | 2026-12-01 / 2027-05-31 | sellado, no se abre |

- **Activos (20):** BTC, ETH, BNB, SOL, XRP, ADA, DOGE, AVAX, LINK, DOT, LTC,
  BCH, TRX, ATOM, NEAR, ETC, FIL, UNI, AAVE, SAND. Son los 20 perpetuos del panel
  H5 con spot USDT en Binance.
- **Spot:** klines diarias de Binance (`data.binance.vision`, mercado `spot`,
  intervalo `1d`). Cierre UTC de cada día, verificado contra el `.CHECKSUM`
  mensual. Es dato público y gratuito.
- **Perpetuo:** `data/funding_xs/perp_1d_panel.csv`, ya congelado en H5.
- **Funding:** `data/funding_xs/funding_panel.csv`, suma diaria de los eventos.
- **Ventana del panel:** 2023-05-12 / 2026-11-01 exclusive. No se descarga ni se
  usa nada posterior al 2026-10-31.
- **Hash:** `data/basis/freeze.json` guarda SHA-256 de `spot_daily.csv`,
  `perp_daily.csv` y `funding_daily.csv`, el conteo de filas y la cobertura por
  activo. El panel se completa **antes** de ejecutar el simulador y no cambia
  después de ver resultados.
- **Alineación:** spot y perpetuo usan velas diarias con el mismo `open_time`
  (00:00 UTC); sus cierres son comparables sin interpolar. Si falta el cierre de
  un activo, ese activo no entra ese día.

## Reglas exactas

| Campo | Regla |
|---|---|
| Basis diario | `perp_close / spot_close − 1` |
| Funding diario | suma de los eventos de funding del día (decimal) |
| Señal | media de basis y media de funding en `L` días, con datos hasta t-1 |
| Cobertura de señal | al menos 80 % de días no nulos en la ventana `L` |
| Score | `media_basis + media_funding`, carry esperado por día |
| Anualizado | `score × 365` (solo para reportar) |
| Entrada | score ≥ `entry` y el activo en el quintil superior (o decil, según variante) |
| Salida | score < `exit`, caída fuera del 40 % superior, o `max_hold` cumplido |
| Momento | señal con datos hasta t-1; ejecución al cierre de t |
| Rebalanceo | semanal (lunes) o diario, según variante |
| Posiciones | máximo 4 (Q20) o 2 (Q10), una por activo |
| Tamaño | 25.000 USD de bruto por variante, repartido a partes iguales entre su máximo de posiciones: Q20 = 6.250 por posición (3.125 por pata); Q10 = 12.500 (6.250 por pata) |
| Capital | 25.000 USD; spot pagado, perpetuo con colateral; sin apalancamiento adicional |
| Costes | 7 pb por pata y lado (6 pb taker/slippage + 1 pb gestión de colateral) |
| Funding | se cobra/paga cada día; corto en perpetuo recibe funding positivo |
| R | 1 % del capital = 250 USD |

Las dos patas se abren con el mismo notional y **no se rebalancean a diario**; la
deriva del delta es de segundo orden porque el basis es pequeño. Una posición
abierta al cierre t no devenga el funding de t; empieza en t+1. El P&L separa
precio, funding y costes. El precio se calcula con el retorno del spot menos el
retorno del perpetuo; el funding se suma aparte.

## Variantes pre-registradas (5)

| ID | Lookback | Rebalanceo | Universo | Entrada | Salida | Máx. hold |
|---|---:|---|---:|---:|---:|---:|
| **H9-C7-Q20-W-25** | 7 d | semanal | quintil (4) | 2,5 pb/día | 1,0 pb/día | 28 d |
| H9-C30-Q20-W-25 | 30 d | semanal | quintil (4) | 2,5 pb/día | 1,0 pb/día | 28 d |
| H9-C7-Q20-D-25 | 7 d | diario | quintil (4) | 2,5 pb/día | 1,0 pb/día | 28 d |
| H9-C7-Q10-W-25 | 7 d | semanal | decil (2) | 2,5 pb/día | 1,0 pb/día | 28 d |
| H9-C7-Q20-W-10 | 7 d | semanal | quintil (4) | 1,0 pb/día | 0,5 pb/día | 28 d |

La candidata es **H9-C7-Q20-W-25**. Los umbrales salen del coste, no del
resultado: un viaje completo cuesta 28 pb (4 lados × 7 pb), así que 2,5 pb/día
recupera el coste en 11 días y deja margen para 28; 1,0 pb/día es exactamente el
punto de equilibrio a 28 días y sirve de prueba de sensibilidad. El lookback de 7
días captura el carry reciente sin reaccionar a un solo día; el semanal reduce
churn; el quintil diversifica entre cuatro activos. No se eligió por P&L.

## Puertas duras (las del plan, sin cambios)

| Criterio | Umbral |
|---|---:|
| Operaciones OOS | ≥ 100 |
| PF OOS | > 1,10 |
| Esperanza OOS | > 0,05 R |
| Coste ponderado | < 0,25 R |
| PBO | ≤ 0,20 |
| DSR | ≥ 0,95 |
| Estrés 2× | PF > 1,00 |
| CPCV positivos | > 50 % |
| Entradas aleatorias | p < 0,05 |
| P&L sin top-5 | > 0 |

Se aplican en orden. Si la candidata falla muestra, PF, esperanza o top-5, se
archiva sin gastar tiempo en PBO/DSR; el archivo debe decirlo. Si pasa las
pruebas simples, se calculan PBO con las 5 variantes, DSR con **50 ensayos**
(45 previos + 5 de H9), estrés 2×, CPCV, aleatorias y benchmark. No se cambia
ningún umbral ni se añaden variantes después de ver resultados.

## Controles de robustez

- **PBO:** CSCV con 10 bloques sobre las cinco curvas diarias.
- **DSR:** Sharpe anualizado de la candidata contra las 50 pruebas declaradas.
- **CPCV:** bloques contiguos con purga de 5 días; fracción de caminos con
  retorno neto positivo.
- **Aleatorias:** mismas fechas, mismo número de posiciones y duración, activos
  elegidos al azar entre los disponibles; 1.000 réplicas.
- **Estrés:** duplicar los costes (14 pb por pata y lado) sobre el mismo OOS.
- **Benchmark:** efectivo (0 %) y BTC buy-and-hold; el carry debe ser positivo
  después de costes, no solo batir a BTC.

## Sesgos declarados

- Los 20 activos son los mayores con spot y perpetuo en Binance; no incluye
  tokens deslistados. El sesgo de supervivencia favorece al test.
- Un solo venue: no hay riesgo de transferencia entre exchanges, pero tampoco
  diversificación de contraparte. Una caída de Binance no aparece en el P&L.
- El spot se compra, no se toma prestado: la estrategia no explota basis
  negativo (short spot / long perp), que exigiría préstamo.
- No se modela margen, liquidación de la pata corta ni llamadas de garantía. El
  backtest asume colateral suficiente y preposicionado.
- El cierre spot (23:59:59 UTC) y el del perpetuo pueden diferir en segundos; el
  basis diario absorbe ese ruido.
- El funding se suma por día, no por evento; el instante exacto de pago no se
  modela. El tamaño de 3.125-6.250 USD por pata es pequeño y no prueba capacidad.

## Criterio de aceptación

Pre-registro en `master` antes de descargar el panel y medir; panel con hash;
reglas y variantes congeladas; ninguna ejecución hasta cerrar este documento. La
medida se hace el 2026-11-27, se archiva el mismo día y se actualiza
`docs/TRIALS.md` a 50 variantes. Si falla, H10 (on-chain de stablecoins) queda
como siguiente familia, sujeto a la revisión trimestral del 2027-01-08.
