# Pre-registro H5 — carry cross-sectional de funding

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar el simulador y antes de medir.
**Hipótesis:** los perpetuos con funding muy alto están cargados de largos
apalancados y pagan por mantener esa posición; los de funding bajo o negativo
están cargados de cortos. Una cartera dollar-neutral larga de los segundos y
corta de los primeros cobra esa prima, si el precio relativo no se mueve en
contra más de lo que paga el funding.

## Por qué existiría la ventaja

El funding es un pago cash entre largos y cortos, no una comisión. Cuando el
lado largo se satura, el funding sube para compensar al lado corto por el riesgo
de squeeze; cuando el lado corto se satura, baja. La prima existe por escasez de
capital de arbitraje y por apalancamiento retail, y es dollar-neutral: no
depende de la beta del mercado. La literatura la documenta (BIS WP 1087;
Franz-Schmeling 2021) y advierte de dos cosas que este pre-registro asume:
el nivel de carry ya no paga y el funding alto puede ser señal de momentum, no
de reversión.

## Datos

20 perpetuos USD-M de Binance, 2020-01-01/2026-10-31: 141.980 pagos de funding
(8 h) y 47.255 cierres diarios. SHA-256 funding `36956d1c…`, cierres
`53c169aa…`. Universo elegido por liquidez de 2026: **sesgo de supervivencia
declarado**; no incluye perpetuos deslistados.

## Reglas exactas

| Campo | Regla |
|---|---|
| Universo por semana | símbolos con ≥ 90 días de funding y precio en la fecha |
| Señal | media del funding diario de los últimos 7 días, estandarizada contra su media/desviación de 90 días |
| Elegibilidad | al menos 10 símbolos; si hay menos, se mantiene la cartera anterior |
| Cartera | largo del quintil inferior de señal, corto del superior, mismo notional por posición |
| Exposición | 25.000 USD de bruto (12.500 largo / 12.500 corto), dollar-neutral |
| Rebalanceo | lunes al cierre UTC; se mantiene una semana |
| Ejecución | al cierre del lunes, con la señal del domingo |
| Funding | se cobra/paga en cada evento de 8 h; corto recibe funding positivo |
| Costes | 6 pb por posición y lado (5 pb taker + 1 pb slippage) |
| Capital | 25.000 USD; sin apalancamiento |
| R | 1 % del capital (250 USD) por operación |

## Variantes pre-registradas (5)

| ID | Quintil | Señal | Rebalanceo |
|---|---|---|---|
| **H5-Q20-Z90-W** | 20 % | z-score 90 d | semanal |
| H5-Q30-Z90-W | 30 % | z-score 90 d | semanal |
| H5-Q20-RAW-W | 20 % | funding medio 7 d sin z | semanal |
| H5-Q20-Z90-D | 20 % | z-score 90 d | diario |
| H5-Q20-Z30-W | 20 % | z-score 30 d | semanal |

La candidata es la primera: quintil, z-score de 90 días y rebalanceo semanal,
que es la versión con menos fragilidad documentada.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Desarrollo | 2020-01-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez |
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

## Diagnóstico obligatorio: precio vs funding

La literatura advierte que un "carry" puede ser funding positivo compensado por
una pérdida de precio relativo mayor. Por eso el simulador reporta por separado
el P&L de precio, el de funding y los costes. Si el neto depende del funding
pero el precio relativo lo supera en contra, no se acepta como carry aunque el
PF salga alto.

## Criterio de aceptación

Pre-registro en `master` antes de implementar, datos con hash, reglas y
variantes congeladas, ninguna ejecución hasta cerrar este documento.
