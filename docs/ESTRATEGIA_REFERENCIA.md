# Estrategia de referencia (sin validar)

`server/strategy/reference.py` existe para probar la infraestructura, no para
ganar dinero. Es un cruce de medias móviles con stop basado en ATR, la
construcción más simple que produce señales deterministas con fases, métricas,
zonas y marcadores.

**No es una ventaja de mercado.** No ha pasado ninguna puerta de validación. No
debe promoverse a LIVE.

## Reglas

| Parámetro | Default | Qué hace |
|---|---:|---|
| `fast` | 9 | Media rápida |
| `slow` | 21 | Media lenta (debe ser mayor que `fast`) |
| `atr_period` | 14 | Periodo del ATR |
| `stop_atr` | 1.5 | Stop en múltiplos de ATR |
| `rr` | 1.5 | Objetivo en múltiplos del riesgo |

- **Entrada:** cruce al alza de `SMA(fast)` sobre `SMA(slow)` → largo; a la baja → corto.
- **Stop:** `close ∓ stop_atr × ATR`.
- **Objetivo:** `close ± rr × distancia del stop`.
- **Una entrada por señal**, identificada por `sesión + dirección + instante`.
- **Filtros:** ninguno. Sin filtro de tendencia, sin filtro de volatilidad, sin
  filtro horario más allá de la ventana de riesgo.

## Fases expuestas al panel

| Fase | Significado |
|---|---|
| `warmup` | Faltan velas para calcular media lenta y ATR |
| `bias` | Relación actual entre media rápida y lenta |
| `trigger` | Cruce detectado en la última vela cerrada |

## Resultado medido

Simulación de **180 sesiones** sintéticas × 390 velas (70.200 ticks), una unidad
por operación según el dimensionado de riesgo:

| Métrica | Valor |
|---|---:|
| Operaciones | 540 |
| Ganadoras / perdedoras | 212 / 328 |
| Win rate | 39,3 % |
| Profit Factor | 0,34 |
| Expectativa | −0,58 R |
| P&L neto | −4.868,11 USD |
| Comisiones | 3.348,00 USD |
| Drawdown máximo | 4.877,45 USD |
| Peor racha perdedora | 18 |
| IC bootstrap 80 % (inferior) | −0,635 R |
| P&L sin las 5 mejores | −5.060,86 USD |
| Duración media | 9,8 min |

Origen: `reports/backtest/simulation-180d.json` (determinista: repetir el
comando produce el mismo archivo).

Desglose: largos 285 ops / −2.453,17 USD; cortos 255 ops / −2.414,95 USD. Los
cinco días de la semana pierden, entre −716 y −1.349 USD. No hay un tramo que
sostenga el resultado: no hay resultado que sostener.

Lectura honesta: sobre un paseo aleatorio sintético, un cruce de medias paga
comisiones y se queda sin edge. El 69 % de la pérdida son costes. Además, el
límite de tres operaciones diarias se alcanza todos los días, así que la muestra
está truncada por el riesgo, no por la señal.

## Veredicto automático

`GET /api/validation` y el cierre de `server.simulation` evalúan las puertas
medibles con los datos disponibles:

| Puerta | Estado | Detalle |
|---|---|---|
| G4 muestra | Pasa | 540 ops, 285 largos / 255 cortos |
| G5 edge | Falla | PF 0,34 < 1,25; expectativa −0,58 R < +0,10 R |
| G6 riesgo | Falla | DD 4.877,45 = 19,5 % > 2 %; racha 18 > 8 |
| G9/G10 concentración | Falla | P&L sin las 5 mejores −5.060,86 < 0 |
| G11 significancia | Falla | IC80 inferior −0,635 R |
| G13 barras ambiguas | Pasa | 0 % |
| G1/G3/G14, G8, G2, H1–H5 | No medible | Requieren datos reales, costes duplicados, golden test y holdout |

**Veredicto: RECHAZADA.** El sistema rechaza su propia estrategia de ejemplo.
Eso es el protocolo funcionando.

## Por qué este resultado es útil

1. El motor ejecuta, dimensiona, llena, aplica brackets y persiste de verdad.
2. Las estadísticas son reales y auditables, no maquetas.
3. El sistema **rechaza** la estrategia con los criterios del protocolo
   (PF < 1,25, expectativa < +0,10 R, drawdown elevado). Eso es el sistema
   funcionando, no fallando.

## Qué haría falta para que contara

- Datos reales, no sintéticos.
- Reconciliación de costes contra fills reales.
- Puertas G1–G14 en verde y holdout ejecutado una sola vez.
- Una hipótesis económica explícita, no un cruce de medias.

Ninguna de esas cuatro cosas está hecha.
