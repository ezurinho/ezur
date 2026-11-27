# Pre-registro H8 — spread de funding entre venues

**Fecha:** 2026-11-27  
**Estado:** congelado antes de implementar el simulador y antes de medir.  
**Hipótesis:** el funding del mismo activo difiere entre venues porque el capital
arbitrajista está segmentado por riesgo de contraparte, colateral y latencia. Una
posición delta-neutral, larga en el venue con funding bajo y corta en el venue con
funding alto, cobra esa diferencia después de costes.

## Por qué existiría la ventaja

El funding es el precio que pagan los apalancados de cada libro. Si dos venues
liquidan el mismo activo con primas distintas, un arbitrajista con capital en ambos
puede cobrar la diferencia sin exposición direccional. La prima persiste porque
transferir colateral entre venues tarda, cuesta y añade riesgo de contraparte; no
es una ley de precios única. Lau (2026, SSRN 6993978) encuentra 14,7 % anualizado
en 2024 y 4,6 % en 2025 con t HAC 4-8 y 4-5 folds walk-forward.

**Dato nuevo:** funding y precios del mismo activo en **Binance y Hyperliquid**,
no otra transformación de precio/funding de un solo venue.

## Datos y ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Warmup | 2023-05-12 / 2023-07-01 | cubrir lookbacks de 30 días |
| Desarrollo | 2023-07-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez |
| Holdout | 2026-12-01 / 2027-05-31 | sellado, no se abre |

- **Activos:** BTC, ETH, SOL, XRP, DOGE.
- **Venues:** Binance USD-M (`BTCUSDT`) y Hyperliquid (`BTC`).
- **Funding:** suma diaria UTC de los eventos de cada venue. Hyperliquid paga cada
  hora; Binance y OKX cada 8 h. Se guardan tasas por evento y agregados diarios.
- **Precios:** cierre diario UTC de cada venue. Si falta el cierre de entrada o
  salida, no se abre/cierra esa posición.
- **Bybit:** excluido por bloqueo geográfico de su API; no se elude.
- **OKX:** descargado y excluido antes de medir: su API pública solo conserva 67
  días de funding (2026-08-26/2026-10-31). No se usa un tramo parcial.
- **Hash:** `data/funding_spread/freeze.json` guarda SHA-256 de los CSV y el
  conteo de eventos. Funding `6dec74d1…`, precios `e594cd7e…`, eventos
  `1169e72f…`. El panel tiene 168.144 eventos, 12.653 filas diarias de funding y
  12.690 cierres. Se completa antes de ejecutar el simulador; las reglas de este
  documento no cambian después.

## Enmienda de cobertura (previa a la medida)

El pre-registro original preveía tres venues. Al comprobar la cobertura, OKX
resultó inutilizable para 2023-2026: su endpoint público devuelve solo 67 días y
una consulta directa a 2025 devuelve vacío. Se excluye **antes de ejecutar el
simulador y sin haber visto P&L**. La hipótesis, las reglas, las cinco variantes
y las puertas no cambian; el panel usado es Binance + Hyperliquid. La evidencia
de Lau compara Hyperliquid contra Binance/Bybit, así que el par Binance-HL sigue
siendo el núcleo de la hipótesis, con menos diversificación de venue.

## Reglas exactas

| Campo | Regla |
|---|---|
| Señal | media móvil del funding diario por venue en `L` días |
| Cobertura de señal | al menos 80 % de días no nulos en la ventana `L` |
| Spread | `(max(media) - min(media)) * 365`, anualizado |
| Entrada | spread ≥ `entry`; largo en el venue de media mínima, corto en el máximo |
| Salida | spread < `exit`, cambio de venue extremo, o `max_hold` cumplido |
| Momento | señal con funding hasta t-1; ejecución al cierre de t |
| Rebalanceo | semanal (lunes) o diario, según variante |
| Tamaño | 25.000 USD de bruto; 5.000 USD por activo (2.500 por pata); en BTC-only, 25.000 USD en BTC |
| Posiciones | máximo una por activo, máximo cinco |
| Capital | 25.000 USD; sin apalancamiento; colateral preposicionado |
| Costes | 7 pb por pata y lado (6 pb taker/slippage + 1 pb transferencia/colateral) |
| Funding | se cobra/paga cada evento; corto recibe funding positivo |
| R | 1 % del capital = 250 USD |

La suma de funding se hace sobre eventos reales, no sobre una interpolación. El
P&L separa precio, funding y costes. Una posición abierta al cierre t no devenga
el funding de t; empieza en t+1.

## Variantes pre-registradas (5)

| ID | Lookback | Rebalanceo | Entrada | Salida | Universo | Máx. hold |
|---|---:|---|---:|---:|---|---:|
| **H8-S7-W-12** | 7 d | semanal | 12 % | 3 % | 5 activos | 4 semanas |
| H8-S30-W-12 | 30 d | semanal | 12 % | 3 % | 5 activos | 4 semanas |
| H8-S7-D-12 | 7 d | diario | 12 % | 3 % | 5 activos | 4 semanas |
| H8-S7-W-8 | 7 d | semanal | 8 % | 3 % | 5 activos | 4 semanas |
| H8-BTC-W-12 | 7 d | semanal | 12 % | 3 % | solo BTC | 4 semanas |

La candidata es **H8-S7-W-12**: 7 días capturan el funding reciente sin reaccionar
a un solo pago; el rebalanceo semanal reduce costes; 12 % es el punto medio del
rango 10-15 % de la literatura. No se eligió por resultado.

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

Se aplican en orden. Si la candidata falla PF, esperanza o top-5, se archiva sin
gastar tiempo en PBO/DSR; el archivo debe decirlo. Si pasa las pruebas simples, se
calculan PBO con las 5 variantes, DSR con **45 ensayos** (40 previos + 5 de H8),
estrés 2×, CPCV, aleatorias y benchmark. No se cambia ningún umbral.

## Controles de robustez

- **PBO:** CSCV con 10 bloques sobre las cinco curvas diarias.
- **DSR:** Sharpe anualizado de la candidata contra las 45 pruebas declaradas.
- **CPCV:** bloques contiguos con purga de 5 días; se reporta la fracción de
  caminos con retorno neto positivo.
- **Aleatorias:** mismas fechas, mismo número de posiciones y duración, pares de
  venues elegidos al azar entre los disponibles; 1.000 réplicas.
- **Estrés:** duplicar los costes (14 pb por pata y lado) sobre el mismo OOS.
- **Benchmark:** efectivo (0 %) y BTC buy-and-hold; el carry debe ser positivo
  después de costes, no solo batir a BTC.

## Sesgos declarados

- Los cinco activos son los mayores y líquidos de 2023-2026; no incluye venues ni
  tokens deslistados. El sesgo de supervivencia favorece al test.
- Solo dos venues: el spread es un único par por activo, sin elección
  cross-sectional de venues. El resultado depende de Binance y Hyperliquid, no
  de un consenso de tres bolsas.
- Hyperliquid tiene menos profundidad fuera de BTC/ETH; el tamaño de 5.000 USD por
  activo es pequeño, pero no prueba capacidad institucional.
- No se modela el riesgo de quiebra, congelación de retiradas ni cambio de reglas
  de funding de un venue. Es un riesgo cualitativo, no un número del backtest.
- Los precios de cada venue pueden divergir; el P&L de precio lo recoge, pero el
  modelo no ejecuta transferencias ni llama a margen.
- El funding de Hyperliquid es horario y el de OKX/Binance es de 8 h; la suma
  diaria alinea el cash, no el instante exacto de pago.

## Criterio de aceptación

Pre-registro en `master` antes de implementar y medir; panel con hash; reglas y
variantes congeladas; ninguna ejecución hasta cerrar este documento. La medida se
hace el 2026-11-27, se archiva el mismo día y se actualiza `docs/TRIALS.md` a 45
variantes. Si falla, H9 (basis spot-perp) es la siguiente familia.
