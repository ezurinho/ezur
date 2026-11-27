# Pre-registro H6 — TSMOM long-only en 20 perpetuos

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar el simulador y antes de medir.
**Hipótesis:** en cripto, un activo que sube en las últimas 4-12 semanas tiende a
seguir subiendo; una cartera long-only que solo mantiene los activos con
tendencia positiva captura la subida y se queda fuera de las caídas, con menos
drawdown que comprar y mantener.

## Por qué existiría la ventaja

El TSMOM es una de las pocas anomalías cripto con evidencia neta de costes
(Han, Kang & Ryu 2024: Sharpe 1,51 neto con 15 pb por operación, 2013-2023,
vs 0,85 del mercado; superior en 8 de 10 años). El mecanismo es sobrerreacción
y flujo de nuevos entrantes, no una prima de riesgo clásica. La pata corta
pierde dinero en cripto; por eso esta hipótesis es **long-only**.

**Advertencia:** una estrategia long-only puede pasar las puertas absolutas
solo por beta. Por eso se añade una puerta de benchmark pre-registrada: el neto
debe superar a BTC buy-and-hold y el drawdown debe ser menor. Sin esa puerta, el
resultado no se acepta.

## Datos

20 perpetuos USD-M, cierres diarios 2020-01-01/2026-10-31 (47.255 filas,
SHA-256 `53c169aa…`). Es el panel de H5; se declara que **no es un dataset
nuevo**, sino un universo más amplio que el de H3 (7 símbolos). Sesgo de
supervivencia: los 20 nombres líquidos de 2026.

## Reglas exactas

| Campo | Regla |
|---|---|
| Universo | 20 perpetuos; un símbolo entra si tiene precio y 28 días de historia |
| Señal | retorno de 28 días al cierre del lunes |
| Entrada | al cierre del martes, solo si la señal es > 0 |
| Salida | al cierre del martes siguiente si la señal deja de ser > 0 |
| Cartera | equal-weight entre los activos activos; si no hay ninguno, 100 % cash |
| Exposición | 25.000 USD, largo-only, sin apalancamiento |
| Rebalanceo | semanal (martes) |
| Costes | 7 pb por posición y lado |
| Capital | 25.000 USD |
| R | 1 % del capital (250 USD) por operación |

## Variantes pre-registradas (5)

| ID | Lookback | Peso | Rebalanceo |
|---|---|---|---|
| **H6-28-EW** | 28 d | equal-weight | semanal |
| H6-60-EW | 60 d | equal-weight | semanal |
| H6-90-EW | 90 d | equal-weight | semanal |
| H6-28-IV | 28 d | inverso a volatilidad 20 d | semanal |
| H6-28-BI | 28 d | equal-weight | bisemanal |

La candidata es H6-28-EW: 4 semanas y equal-weight, el estándar de la
literatura.

## Ventanas

| Bloque | Periodo | Uso |
|---|---|---|
| Desarrollo | 2020-01-01 / 2025-01-01 | PBO, DSR, estabilidad |
| Validación | 2025-01-01 / 2026-11-01 | OOS real, una vez |
| Holdout | 2026-12-01 / 2027-05-31 | sellado |

## Puertas duras

| Criterio | Umbral |
|---|---:|
| Operaciones OOS | ≥ 100 |
| PF OOS | > 1,10 |
| Esperanza OOS | > 0,05 R |
| Coste ponderado | < 0,25 R |
| P&L sin top-5 | > 0 |
| **Neto > BTC buy-and-hold** | sí |
| **Max DD < DD de BTC buy-and-hold** | sí |
| PBO | ≤ 0,20 |
| DSR | ≥ 0,95 |
| Estrés 2× | PF > 1,00 |
| CPCV positivos | > 50 % |
| Entradas aleatorias | p < 0,05 |

La puerta de benchmark se añade **antes de medir** y se aplica a las cinco
variantes; no se puede elegir después la que gane a BTC.

## Criterio de aceptación

Pre-registro en `master` antes de implementar, datos con hash, reglas y
variantes congeladas, ninguna ejecución hasta cerrar este documento.
