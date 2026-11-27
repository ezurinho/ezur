# Pre-registro H2 — carry de funding BTC (delta-neutral)

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar el simulador y antes de medir.
**Hipótesis:** el funding positivo del perpetuo de BTC es una prima que cobra
quien está corto de perpetuo y largo de spot; después de costes y de la
variación del basis, queda un retorno neto positivo y estable.

## Por qué existiría la ventaja

El perpetuo necesita anclarse al spot. Cuando el funding es positivo, los
largos apalancados pagan a los cortos por mantener la exposición; el carry
delta-neutral cobra esa renta sin apostar a la dirección. No es arbitraje
libre de riesgo: el basis puede moverse, la liquidez puede faltar y el venue
puede cambiar las reglas. Es una prima de servicio (dar el short que el mercado
necesita), no una predicción.

## Estudio de viabilidad (exploratorio, no es un test)

Antes de congelar reglas se midió la distribución del funding de BTCUSDT
(Binance Vision, 2020-01-01/2026-10-31, 7.488 pagos de 8 h, SHA-256
`35cec5b7…`): media 0,0106 % por 8 h (11,6 % anual), 86,0 % de pagos positivos,
mediana 0,0089 %. Un carry con ventana de 21 pagos y umbral 0,005 % da 84
entradas y 6,8 años, 75,3 % bruto y 54,3 % neto con 0,25 % por ida y vuelta
(7,95 % anual). **Este estudio informó el umbral; el test formal sigue siendo
OOS y la regla queda congelada aquí.**

## Reglas exactas

| Campo | Regla |
|---|---|
| Venue | BTC spot + BTC-USDT-SWAP perpetuo (OKX para precios; funding histórico de Binance como proxy declarado) |
| Posición | Larga spot 1× + corta perpetuo 1×, delta-neutral, gross 2×, net 0 |
| Señal | media de los últimos `W` pagos de funding (8 h) > `umbral` → entrar; < 0 → salir |
| Ejecución | en el siguiente pago de funding (rejilla de 8 h), al cierre de esa vela de 1 h |
| Funding | se cobra/paga en cada pago mientras la posición está abierta, sobre el nocional del perpetuo |
| Costes | 0,25 % por ida y vuelta: 4 piernas × 5 pb + 5 pb de spread/slippage |
| Capital | 25.000 USD; nocional 25.000 USD (el spot sirve de colateral del corto) |
| Basis | se mide con el cierre de spot y de perpetuo en la entrada y la salida; el P&L de precio de las dos piernas se suma |
| Sin | apalancamiento adicional, sin pirámide, sin cortos de spot, sin funding negativo forzado |

## Universo pre-registrado (5 variantes)

| ID | W (pagos) | Umbral (por 8 h) | Papel |
|---|---:|---:|---|
| H2-9-05 | 9 | 0,005 % | ventana corta |
| **H2-21-05** | **21** | **0,005 %** | **candidata a priori** |
| H2-63-05 | 63 | 0,005 % | ventana larga |
| H2-21-10 | 21 | 0,010 % | umbral alto |
| H2-9-025 | 9 | 0,0025 % | umbral bajo |

La candidata es H2-21-05 por razón económica: 0,005 % por 8 h son ~5,5 %
anual, el mínimo que amortiza 0,25 % de coste en menos de un mes; 21 pagos
(7 días) suavizan el ruido sin reaccionar a un solo pago.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Desarrollo | 2020-01-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez, reglas congeladas |
| Holdout | 2026-12-01 / 2027-05-31 | sellado |

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

**Riesgo declarado:** un carry de baja rotación no produce 100 operaciones en
22 meses. Con 21 pagos y 0,005 % se esperan ~27 entradas OOS, muy por debajo
de 100. La puerta se mantiene: si no llega, H2 se archiva por muestra, aunque
el neto sea positivo. No se redefine «operación» para maquillar el conteo.

## Criterio de aceptación

Pre-registro en `master` antes de implementar, datos con hash, reglas y
variantes congeladas, y ninguna ejecución de backtest hasta cerrar este
documento. El simulador será determinista y separado del motor de órdenes; no
toca `live_enabled` ni el holdout.
