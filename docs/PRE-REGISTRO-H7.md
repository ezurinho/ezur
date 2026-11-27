# Pre-registro H7 — desequilibrio de flujo de taker

**Fecha:** 2026-11-27
**Estado:** congelado antes de implementar el simulador y antes de medir.
**Hipótesis:** cuando la compra agresiva (taker buy) domina el volumen de un
perpetuo durante varios días, el precio tiende a seguir subiendo en los
siguientes 1-3 días; cuando domina la venta agresiva, tiende a seguir bajando.
Una cartera dollar-neutral larga de los flujos altos y corta de los bajos cobra
esa continuación después de costes y funding.

## Por qué existiría la ventaja

El flujo de taker es información que el precio diario no contiene: mide quién
cruzó el spread y en qué dirección, no solo dónde cerró la vela. La literatura
encuentra poder predictivo real a horizontes cortos (Anastasopoulos et al.
2026: 0,2 % diario y 0,9 % semanal por 1 desviación de order flow rezagado),
pero advierte que a frecuencias altas el edge es del orden del coste. Esta
hipótesis lo prueba a 1-3 días, que es el horizonte más favorable para un bot
lento, y con una cartera diversificada de 20 nombres.

**Dato nuevo:** volumen total y `taker_buy_base` por vela diaria, campos que no
se usaron en H1-H6. 47.255 barras de 20 perpetuos USD-M, 2020-01-01/2026-10-31,
SHA-256 `baa1a7bd…`; cero volúmenes nulos.

## Reglas exactas

| Campo | Regla |
|---|---|
| Universo | 20 perpetuos USD-M; elegible si su notional medio de 20 días ≥ 5 M USD |
| Señal | `flujo = taker_buy_base / volume`; z-score de 20 días; media de los últimos 3 z |
| Momento de la señal | cierre del día t-1 |
| Entrada | cierre del día t, nunca con el precio de la señal |
| Cartera | largo del quintil superior de flujo, corto del inferior, mismo notional |
| Exposición | 25.000 USD de bruto (12.500 largo / 12.500 corto), dollar-neutral |
| Rebalanceo | cada 3 días al cierre |
| Funding | se cobra/paga en cada evento de 8 h; corto recibe funding positivo |
| Costes | 6 pb por posición y lado (5 pb taker + 1 pb slippage) |
| Capital | 25.000 USD; sin apalancamiento |
| R | 1 % del capital (250 USD) por operación |

## Variantes pre-registradas (5)

| ID | Señal | Rebalanceo | Cartera |
|---|---|---|---|
| **H7-Z20-3D** | z 20 d, media 3 d | 3 días | quintiles |
| H7-Z5-1D | z 5 d, media 1 d | diario | quintiles |
| H7-Z60-3D | z 60 d, media 3 d | 3 días | quintiles |
| H7-Z20-3D-T | z 20 d, media 3 d | 3 días | terciles |
| H7-BTC-TS | z 20 d de BTC | 1 día | largo BTC si z>1, si no cash |

La candidata es H7-Z20-3D: 20 días de z-score, media de 3 días y rebalanceo
cada 3 días. No se eligió por resultado; es el punto medio entre ruido diario y
coste.

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

## Sesgos declarados

- Supervivencia: los 20 nombres son los líquidos de 2026.
- El flujo de taker es agregado por vela, no order flow de libro; no distingue
  órdenes grandes de pequeñas.
- El funding se incluye; sin él, el long-short de perpetuos estaría incompleto.
- El coste estimado es alto (8 posiciones cada 3 días): si el bruto no supera
  la fricción, se archiva sin buscar un umbral que lo salve.

## Criterio de aceptación

Pre-registro en `master` antes de implementar, datos con hash, reglas y
variantes congeladas, ninguna ejecución hasta cerrar este documento. La medida
se hace en la sesión del 2026-11-30 y el resultado se archiva el mismo día.
