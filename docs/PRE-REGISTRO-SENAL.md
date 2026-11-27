# Pre-registro — diagnóstico de señal de funding

**Fecha:** 2026-11-27.
**Estado:** congelado y commiteado **antes** de calcular ningún IC.
**Qué es:** el paso que el laboratorio se saltó en las diez familias. Antes de
construir una cartera, comprobar si la señal predice lo que la cartera necesita
cobrar. No produce P&L, no añade ensayos (`TRIALS.md` sigue en 53) y no puede
promocionar nada.

## 1. La pregunta

Los diez simuladores asumen que ordenar por funding de los últimos 7 días ordena
el funding de la semana siguiente. Eso es una hipótesis **medible sin cartera**:
si la señal no predice el funding futuro, ninguna construcción la va a arreglar, y
si lo predice pero la cartera pierde, el problema es de economía, no de señal.

## 2. Universos

Tres, sobre el panel congelado de H10 y la misma rejilla semanal (lunes):

| Universo | Definición | Para qué |
|---|---|---|
| **U20** | los 20 majors de H5 (lista de `data/funding_xs`) | decir qué habría dicho de H5 |
| **ANCHO** | todo el panel con ≥ 90 días de historia | el tramo largo sin filtro |
| **FILTRADO** | ANCHO con ADV ≥ 5 M USD | el universo real de H10 |

Ventana: 2023-01-01 / 2026-10-31, la del panel. **No se puede reproducir el
desarrollo 2020-2024 de H5**, y se declara: lo que se diga de H5 es sobre 2023-2026.

## 3. Métricas, definidas antes de mirar

**Señal** en la fecha `t` (lunes): media del funding diario de los 7 días
anteriores a `t`, estandarizada contra su media y desviación de 90 días. Idéntica
a la de H5 y H10.

**Objetivo** a horizonte `h` semanas: media del funding diario de los días
`(t, t + 7h]` — el funding que la cartera cobraría si abriera al cierre de `t`.

**Rank-IC:** Spearman transversal entre señal y objetivo, por semana, sobre los
símbolos elegibles (≥ 90 días de historia, precio > 0, y ADV ≥ 5 M en FILTRADO).

Se publican por universo: mediana, media, **proporción de semanas con IC > 0** y
la serie por año. Para `h > 1` las ventanas se solapan y el t de la media está
inflado: **el criterio es la mediana y la proporción de semanas positivas**, no el
t.

**Decaimiento:** el mismo IC a `h = 1, 2, 4` semanas.

**Autocorrelación de la dispersión:** desviación transversal del funding medio de
7 días, por semana; autocorrelación a retardos 1-4. Se publica también la del
nivel (mediana transversal). Mide si el régimen de dispersión persiste, que es lo
que hace explotable un carry transversal.

**Estabilidad por régimen:** IC mediano por año y por tercil de dispersión
(baja/media/alta, cortes calculados sobre la propia serie).

## 4. Puertas, declaradas antes de medir

| # | Puerta | Umbral |
|---|---|---:|
| F1 | Rank-IC mediano a 1 semana | ≥ 0,05 |
| F2 | Semanas con IC > 0 | ≥ 60 % |
| F3 | Rank-IC mediano a 4 semanas | ≥ 0,03 |
| F4 | Años con IC mediano > 0 | ≥ 3 de 4 |

Se evalúan por universo. **Un universo que no pase F1 y F2 no debería haber
llegado a simulador**: la señal no ordena el funding futuro lo suficiente como
para que la cartera cobre.

## 5. Regla para el protocolo, declarada aquí

Si el diagnóstico se confirma útil, entra en `docs/PLAN-2027.md` como **puerta
-1**, antes del cribado económico y antes de escribir un simulador: ninguna
familia pasa a backtest con rank-IC mediano < 0,05 o menos del 60 % de semanas
positivas en su universo. Se evalúa sobre el panel congelado, sin costes y sin
precios.

## 6. Qué no se hace

- No se construye ninguna cartera ni se calcula P&L.
- No se cambian H5, H10 ni sus veredictos.
- No se toca el holdout ni se descargan datos nuevos.
- No se elige el universo después de ver el IC: los tres están fijados arriba.

## 7. Artefactos previstos

- `scripts/signal_diagnostics.py` → `data/signal/diagnostics.json`.
- `docs/MEDICION-SENAL.md`.
