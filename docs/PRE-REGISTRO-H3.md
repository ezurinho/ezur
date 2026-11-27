# Pre-registro H3 — momentum cross-sectional en perpetuos

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar el simulador y antes de medir.
**Hipótesis:** dentro de los perpetuos líquidos, los activos con mejor retorno
de las últimas 2-8 semanas siguen superando a los peores; un long-short
dollar-neutral captura esa continuación después de costes.

## Por qué existiría la ventaja

La literatura de cripto encuentra continuación de retornos a horizontes de
1-4 semanas (Liu, Tsyvinski y Wu, 2022; Liu y Tsyvinski, 2021): la atención
limitada y la adopción escalonada hacen que las noticias se incorporen despacio,
y el flujo retail refuerza a los ganadores. Es una prima de riesgo de atención,
no una profecía: puede desaparecer cuando el mercado madura o cuando el coste
de rotación supera la continuación.

**Datos nuevos:** esta hipótesis no usa el dataset de BTC de H1/H2. Usa un panel
de 7 perpetuos USDT de Binance (BTC, ETH, BNB, XRP, ADA, LTC, LINK), 17.363
cierres diarios 2020-01-01/2026-10-31, SHA-256 `c31a916a…`. El universo se fija
por liquidez de 2020, no por los supervivientes de 2026; aun así hay sesgo de
supervivencia y se declara.

## Reglas exactas

| Campo | Regla |
|---|---|
| Universo | 7 perpetuos USDT: BTC, ETH, BNB, XRP, ADA, LTC, LINK |
| Señal | retorno close-to-close de los últimos `L` días en la fecha de rebalanceo |
| Cartera | largo los 2 mejores, corto los 2 peores, equiponderados; dollar-neutral |
| Exposición | 1× bruto: 12,5 % del capital por pata, 50 % largo + 50 % corto |
| Rebalanceo | cada `H` días (lunes 00:00 UTC), con el cierre del día de señal |
| Ejecución | al cierre del día siguiente (`t+1`), nunca con el precio de la señal |
| Costes | 7 pb por pata y lado: 5 pb taker + 2 pb slippage; se cobran sobre el turnover |
| Funding | no se modela en la base; se estresa con 2 pb/día sobre el bruto |
| Capital | 25.000 USD; sin apalancamiento adicional, sin pirámide |
| Filtro | si un activo no tiene `L+1` cierres, queda fuera ese rebalanceo |

## Universo pre-registrado (5 variantes)

| ID | L (días) | H (días) | Patas | Papel |
|---|---:|---:|---:|---|
| H3-14-7 | 14 | 7 | 2/2 | señal corta |
| **H3-28-7** | **28** | **7** | **2/2** | **candidata a priori** |
| H3-56-7 | 56 | 7 | 2/2 | señal larga |
| H3-28-14 | 28 | 14 | 2/2 | menos rotación |
| H3-28-7-3 | 28 | 7 | 3/3 | más diversificación |

La candidata H3-28-7 es la mediana de la literatura (4 semanas de formación,
1 semana de mantenimiento) y la que menos parámetros añade.

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

**Unidad de operación:** cada pata abierta o cerrada en un rebalanceo cuenta
como una operación; con 4 patas y 52 rebalanceos al año hay ~200 al año, muy por
encima de 100 en 22 meses. **Unidad de R:** 1 % del capital (250 USD); se declara
porque la cartera no tiene stop por operación.

## Criterio de aceptación

Pre-registro en `master` antes de implementar, datos con hash, reglas y
variantes congeladas, ninguna ejecución de backtest hasta cerrar este documento.
El simulador es determinista y separado del motor de órdenes; no toca
`live_enabled` ni el holdout.
