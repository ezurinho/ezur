# Pre-registro — modelo de coste real de ejecución

**Fecha:** 2026-11-27.
**Estado:** congelado y commiteado **antes** de calcular ningún spread ni ajustar
ningún modelo.
**Qué no es:** no es una familia de estrategia. No produce P&L, no añade ensayos a
`docs/TRIALS.md` (sigue en 53) y no puede promocionar nada. Es la medición de un
input que hoy está supuesto en los diez veredictos del laboratorio.

## 1. El problema

Todas las familias se juzgaron con un coste declarado a ojo: **6 pb por lado** en
H5, **10 pb por lado** en H8, H9 y H10. Es el único input que aparece en los diez
veredictos y el único que nadie midió. Si el coste real del tramo largo es 25 pb
por lado, la conclusión «pierde poco» de H9 se convierte en «pierde el triple»; si
es 5 pb, alguna conclusión cambia al revés. Y sin coste real no hay **capacidad**:
no se sabe cuánto capital soporta el edge antes de que el impacto se lo coma.

## 2. Unidad de medida (declarada antes de mirar)

**Coste por lado, en pb del nocional**, para una orden de tamaño `S` USD:

```
coste_lado_bp(S) = (VWAP_compra(S) − VWAP_venta(S)) / (2 · mid) · 10.000
```

donde `VWAP_compra(S)` es el precio medio de recorrer el libro de venta hasta
completar `S` USD y `VWAP_venta(S)` el de recorrer el de compra. El coste de ida y
vuelta es `2 × coste_lado_bp`. Todo se publica en pb; el equivalente en R se
calcula con el nocional de cada familia, nunca al revés.

## 3. Fuentes, cobertura y el bloqueo declarado

`fapi.binance.com` (futuros) **responde con bloqueo geográfico desde esta
máquina** («Service unavailable from a restricted location»), así que el libro de
los perpetuos de Binance no se puede muestrear directamente. Se declara aquí, antes
de medir, lo que se usa en su lugar:

| Fuente | Qué aporta | Papel |
|---|---|---|
| **OKX SWAP** (`/api/v5/market/books`, 400 niveles) | libro real de perpetuos | **primaria** para impacto y spread directo |
| **Binance spot** (`data-api.binance.vision/api/v3/depth`) | libro real de spot, misma casa | contraste de spread |
| **Barras diarias congeladas** (`data/h10/perp_daily.csv`) | OHLC de los 886 símbolos | **estimador offline** con cobertura total |

Limitaciones declaradas de antemano: OKX no lista la mayoría del tramo largo, así
que la muestra directa estará sesgada a los nombres grandes; el tramo pequeño sólo
se caracteriza con el estimador offline. Y un libro de OKX no es el de Binance: se
usa como orden de magnitud y como calibración de la *forma* del impacto, no como el
libro exacto en el que se ejecutaría.

## 4. Estratificación y muestra

Cubetas por **ADV** = mediana de 30 días del `quote_volume` del panel congelado,
medida al final del panel, cinco tramos fijos:

| Cubeta | ADV (USD) |
|---|---:|
| C1 | < 1 M |
| C2 | 1 M – 5 M |
| C3 | 5 M – 20 M |
| C4 | 20 M – 100 M |
| C5 | > 100 M |

**Muestra directa:** hasta **25 símbolos por cubeta**, tomados por orden
alfabético de los que OKX liste (determinista y reproducible, sin elección
discrecional), con un mínimo de **8 por cubeta** para que la cubeta cuente.

**Tamaños de orden:** `S ∈ {500, 1.562, 3.125, 12.500}` USD. Cubren el nocional
del quintil de H10 (278-1.389 USD), el de H5/H9 (3.125) y el doble, para ver la
curvatura.

## 5. Estimadores

**Spread directo (libro):** `(ask₁ − bid₁) / mid × 10.000` pb, con un mínimo de 20
niveles por lado; si el libro no cubre `S`, el símbolo no aporta ese tamaño.

**Estimador offline (Corwin-Schultz, 2012),** sobre barras diarias congeladas:

```
β = [ln(H_t/L_t)]² + [ln(H_{t+1}/L_{t+1})]²
γ = [ln(max(H_t,H_{t+1}) / min(L_t,L_{t+1}))]²
α = (√(2β) − √β) / (3 − 2√2) − √(γ / (3 − 2√2))
S_cs = 2(e^α − 1) / (1 + e^α)
```

Se toma la **mediana de 21 días** por símbolo, los valores negativos se llevan a 0
(convención del paper) y el resultado se lee como spread de ida y vuelta: el coste
por lado es `S_cs / 2`.

**Modelo declarado:**

```
coste_lado_bp(S, ADV) = α + β · sqrt(S / ADV)
```

ajustado por MCO sobre la muestra emparejada (símbolo, tamaño) del libro directo,
con `ADV` en USD. Se publican α, β, R² y el error absoluto mediano.

## 6. Puertas, declaradas antes de medir

| # | Puerta | Umbral |
|---|---|---:|
| G1 | Símbolos con libro válido (≥ 20 niveles) | ≥ 60 |
| G2 | R² del ajuste | ≥ 0,50 |
| G3 | Error absoluto mediano del modelo | ≤ 8 pb |
| G4 | Monotonía: mediana de coste(12.500) > coste(500) en cada cubeta con muestra | en todas |
| G5 | Coherencia libro vs Corwin-Schultz (Spearman, símbolos comunes) | ≥ 0,50 |

**Si falla G1-G4:** el modelo se declara **no usable** y la sensibilidad se hace
con el *fallback* declarado —la mediana empírica de coste por cubeta y tamaño, sin
curva ajustada—, y todas las conclusiones de la medición bajan de fuerza y se
etiquetan como tales.

**Si falla G5:** el estimador offline no se usa para el tramo sin libro; esas
cubetas se reportan como «no medidas» en vez de rellenadas.

## 7. Techo de capacidad

**Capacidad** de una cubeta = mayor `S` del grid fino (100 USD a 2 M USD, pasos
logarítmicos de 0,1 décadas) tal que `coste_lado_bp(S) ≤ umbral`, para los dos
umbrales que el laboratorio ya usa:

- **6 pb por lado** — el coste declarado de H5.
- **10 pb por lado** — el coste declarado de H8, H9 y H10.

Se publica por cubeta como rango (mediana y p25-p75 de los símbolos de la cubeta).
El techo global es el de la cubeta en la que opera cada familia, no el mejor de la
tabla.

## 8. Aplicación a las familias archivadas

Sin re-ejecutar ningún simulador, sin tocar paneles, reglas, umbrales ni el
holdout. Sólo se re-expresa el coste, que es lineal en el nocional:

```
neto' = precio + funding − operaciones · nocional · coste_lado_bp / 10.000
esperanza' = neto' / (operaciones · 250)
```

Con los componentes publicados de cada archivo (precio, funding, coste, número de
operaciones y nocional) se publica, por familia: neto y esperanza con el coste
declarado, con el coste medido en la mediana de su cubeta y con el p75 de su
cubeta. La cubeta de cada familia se asigna por el ADV de sus símbolos, no por su
resultado.

**Qué se declara de antemano:** si con el coste medido alguna familia cruza una
puerta, **no se desarchiva**. La ventana está gastada y este ejercicio sólo mide
cuánto se equivocaban sus números, no si eran desplegables.

## 9. Qué no se hace

- No se toca el holdout 2026-12-01/2027-05-31 ni el panel congelado de H10.
- No se modifican reglas, umbrales ni veredictos congelados.
- No se añaden ensayos: `TRIALS.md` sigue en 53.
- No se elige la muestra después de ver spread alguno: la regla es alfabética.
- No se reporta un modelo si falla G1-G4: se reporta el fallback y se dice.

## 10. Artefactos previstos

- `scripts/measure_execution_cost.py` — muestreo, ajuste y puertas.
- `data/cost/books.json`, `data/cost/model.json`.
- `docs/MEDICION-COSTE.md` — resultados y sensibilidad de las familias.
