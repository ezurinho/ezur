# Familias con dato nuevo después de H7

**Fecha:** 2026-11-27
**Estado:** propuesta. No hay simulador, pre-registro ni medida de ninguna de
estas familias. Cualquier ejecución futura empieza por un pre-registro con hash.

## Criterio de valor

No ordeno por lo interesante que suena, sino por:

1. **Evidencia fuera de muestra con costes** (no solo contemporánea).
2. **Dato realmente nuevo**, no otra transformación de precio/funding sobre los
   mismos 20 nombres.
3. **Desplegabilidad con este bot** (spot/perp en Binance; dos venues como
   máximo razonable).
4. **Relación esfuerzo/beneficio** y disponibilidad gratuita del dato.

Las 40 variantes ya medidas enseñan tres cosas que condicionan la lista:
el carry de un solo venue está arbitrado (H2/H5), el momentum de precio es beta
o está muerto (H3/H6), y el flujo de taker a 3 días se desvanece (H7). Una
familia nueva tiene que ser **ortogonal** a esas tres.

## Ranking

| # | Familia | Dato nuevo | Evidencia | Esfuerzo | ¿Desplegable? | Valor |
|---|---|---|---:|---:|---|---|
| 1 | Spread de funding entre venues | Funding de Hyperliquid/Bybit/OKX, no solo Binance | Lau 2026: 4,6 % en 2025, t HAC 4-8, 4-5/5 folds | 2-3 semanas | Sí, dos venues | **Alto** |
| 2 | Basis spot-perp en 20 alts | Precios spot de los alts; el basis no es funding | Chi 2023: t=7,10; BIS carry | 1-2 semanas | Sí, spot+perp | **Alto-medio** |
| 3 | Flujos on-chain de stablecoins | Oferta de stablecoins, TVL, volumen DEX | JBF 2022 (reservas), Grobys 2026 (MVRV) | 1-2 semanas | Como filtro | **Medio** |
| 4 | Liquidez macro | DXY, tipos reales, balance de la Fed, TGA | Mixta; es timing de beta | 1 semana | Como filtro | **Medio-bajo** |
| 5 | Prima de volatilidad de opciones | DVOL/IV de Deribit | QF 2024, JEF 2023; decay 2024-2026 | 3-4 semanas | No sin opciones | **Medio (research)** |
| 6 | Cascadas y open interest | OI y liquidaciones | Reversión real, no pagable | 2 semanas + bloqueo de datos | No | **Bajo** |
| 7 | Sentimiento (Google/Twitter) | Términos de búsqueda, posts | Débil y ruidosa | 1-2 semanas | No | **Bajo** |

---

## 1. Spread de funding entre venues — la mejor apuesta

**Por qué.** Es el único carry que sobrevivió a un test OOS con costes en la
investigación: Lau (2026, SSRN 6993978) encuentra que Hyperliquid paga 14,7 %
anualizado más que Binance/Bybit en 2024 y 4,6 % en 2025, con t HAC 4-8 y 4-5 de
5 folds walk-forward. No es el carry de nivel de H2 ni el cross-section de H5:
es el **mismo activo en dos venues**, delta-neutral, sin exposición a la
dirección del precio ni a la ordenación por momentum.

**Dato nuevo.** Funding histórico de Hyperliquid (`fundingHistory`), Bybit
(`/v5/market/funding/history`) y OKX (`/api/v5/public/funding-rate-history`),
más mark price de cada venue. Todo público y gratis; se puede congelar con hash.
Binance ya está descargado.

**Esbozo de regla (no pre-registrada).** Spread anualizado = funding del venue
caro − funding del barato. Entrar cuando el spread supere 10-15 % anualizado y
haya liquidez; largo del perp en el venue barato, corto en el caro, mismo
notional; salir cuando baje de 3 %. Costes 6 pb por pata y lado, más un coste de
transferencia declarado (no se transfiere en cada rebalanceo).

**Qué la mataría.** Menos de 100 operaciones OOS; neto después de costes de
transferencia por debajo de T-bill + 2 %; DSR < 0,95 con 45 ensayos; spread
comprimido a <3 % en 2025-2026 (que es lo que sugiere Talos).

**Riesgos.** Riesgo de venue (solvencia, retiradas), latencia de transferencia,
desalineación de intervalos de funding, capacidad de Hyperliquid fuera de BTC y
ETH. Es la familia con más partes móviles; también la que tiene la evidencia más
reciente y específica.

## 2. Basis spot-perp en 20 alts

**Por qué.** Chi (2023) encuentra que el factor de basis es el predictor
cross-sectional más fuerte (t=7,10, 305 % neto a 5 pb, holding de 1 día); el BIS
documenta carry medio >10 %. H5 ordenó por **funding**, no por basis, y su pata
corta era momentum. Aquí la posición es long spot / short perp por activo: no
hay pata corta de precio, solo cobro de basis y funding.

**Dato nuevo.** Precios spot diarios de los 20 alts (Binance Vision, gratis),
que no se usaron en H1-H7; el basis se calcula contra el perp que ya tenemos.
El funding sigue siendo insumo, pero la señal es el premium spot-perp.

**Esbozo de regla.** Basis anualizado = (perp/spot − 1) × 365 / días de
holding. Ordenar los 20 alts; long spot / short perp en el quintil superior;
salir cuando el basis caiga por debajo del 3 %; rebalanceo semanal; 6 pb por
pata y lado. Alternativa de un solo activo con umbral (solo cuando el basis
supere 10 %).

**Qué la mataría.** Menos de 100 operaciones OOS (si se usa umbral alto); neto
< T-bill + 2 %; PF < 1,10; DSR < 0,95. El basis de 2025-2026 está en 3-5 %:
puede no haber episodios suficientes, y ese sería el resultado, no un fallo de
implementación.

**Riesgos.** Capacidad, fees, slippage en spot, funding que cambia, y solapamiento
económico con H2/H5 (aunque la construcción es distinta). Es la familia más
fácil de implementar y la que más rápido se puede descartar.

## 3. Flujos on-chain de stablecoins

**Por qué.** Es una clase de dato distinta: la oferta de stablecoins y el flujo
hacia exchanges miden liquidez y apetito de riesgo, no precio. La literatura
encuentra que las reservas de exchanges predicen retornos y volatilidad
(Journal of Banking & Finance 2022) y que MVRV/NUPL baten a buy-and-hold
(Grobys et al. 2026), aunque con umbrales in-sample y pocos ciclos.

**Dato nuevo.** DefiLlama (gratis): oferta de stablecoins por cadena, TVL, volumen
de DEX; complemento on-chain de USDT/USDC. Los flujos de exchange etiquetados
siguen siendo de pago (CryptoQuant/Glassnode), así que la versión gratuita es
más débil: oferta de stablecoins y TVL, no netflows de exchanges.

**Esbozo de regla.** Señal semanal: crecimiento de la oferta de stablecoins a 7 y
30 días; long BTC/ETH cuando el crecimiento supere su mediana histórica, cash si
no. Puerta de benchmark obligatoria: batir a BTC buy-and-hold en neto y en DD.

**Qué la mataría.** No batir a BTC en neto o tener peor DD; DSR < 0,95; que la
señal sea solo un proxy de beta. Es probable que termine siendo un filtro de
régimen, no una estrategia.

**Riesgos.** Beta, confusión con el ciclo, revisiones de datos on-chain y
historia corta de algunas cadenas.

## 4. Liquidez macro

**Por qué.** El crypto es sensible a la liquidez global y a los tipos reales;
FRED es gratis y diario/semanal. Puede reducir drawdowns de una exposición long
BTC, aunque no genera una prima market-neutral.

**Dato nuevo.** DXY, rendimiento real a 10 años (DFII10), balance de la Fed
(WALCL), TGA (WTREGEN) y RRP (RRPONTSYD). Ninguno se usó en H1-H7.

**Esbozo de regla.** Risk-on cuando el rendimiento real baja o la liquidez se
expande; long BTC, cash si no. Rebalanceo semanal; benchmark BTC; 5 variantes.

**Qué la mataría.** No batir a BTC en neto, o batirlo con peor DD; DSR < 0,95.
Es una estrategia de timing: el riesgo de overfitting con 5 variables macro es
alto.

**Riesgos.** Beta, régimen, revisión de datos y estacionalidad de la Fed. Valor
medio-bajo; sirve más como filtro de otra estrategia que como familia propia.

## 5. Prima de volatilidad de opciones

**Por qué.** La prima de riesgo de volatilidad en BTC es real y mayor que en el
S&P 500; vender volatilidad paga a largo plazo (Quantitative Finance 2024;
Journal of Empirical Finance 2023). Es una clase de dato totalmente nueva.

**Dato nuevo.** DVOL de Deribit y la cadena de opciones actual; el histórico de
superficies ejecutables no se reconstruye gratis, así que el backtest sería con
DVOL y realized variance, no con precios de opciones históricos.

**Problema.** Este bot es spot/perp: no hay ejecución de opciones, margen ni
liquidación de opciones cortas. Sin esa infraestructura, la familia es research,
no una estrategia desplegable. Además, el harvest se concentra en 2021-2023 y
decae a ~0 en 2024-2026 según la evidencia no revisada.

**Qué la mataría.** No poder reconstruir una superficie ejecutable; neto negativo
con costes conservadores; DSR < 0,95; dependencia del estimador de volatilidad.

**Riesgos.** Ejecución, margen, cola, y datos históricos incompletos.

## 6. Cascadas y open interest

**Por qué.** La reversión tras cascadas está bien documentada mecánicamente
(autocorrelación negativa a 1-30 minutos; rebotes del 4 % en 24 h tras
liquidaciones masivas). Pero el edge vive en minutos, el spread se multiplica
×20 justo cuando quieres entrar y el histórico de `forceOrders` está truncado.

**Dato nuevo.** Open interest histórico y liquidaciones; el OI de Binance es
gratis pero limitado a 30 días, y las liquidaciones completas no están
disponibles por API pública.

**Qué la mataría.** No conseguir el histórico; coste > retorno esperado; spread
de cascada; muestra insuficiente. Es la familia con peor relación
evidencia/disponibilidad para un bot lento.

## 7. Sentimiento (Google/Twitter)

**Por qué.** Es dato nuevo y barato, pero la evidencia es débil y ruidosa; Google
Trends tiene revisión y muestreo, y Twitter/X limita la API. El riesgo de data
mining es alto.

**Qué la mataría.** Falta de OOS, coste, y que la señal sea un proxy de atención
que ya está en el precio. No la pondría por delante de las anteriores.

---

## Lo que no hay que volver a probar

- Otra variante de Donchian, SMA, momentum o funding sobre los mismos 20 nombres:
  ya está en las 40 y solo infla el DSR.
- Coinbase premium o flujos de ETF: la investigación muestra que el efecto se
  desvanece al alinear timestamps y que los flujos no Granger-predicen retornos.
- Estacionalidad intradía como señal de dirección: no es robusta; solo sirve
  para ejecutar cuando el spread es menor.
- Order flow a menos de 1 hora: el edge es del orden del coste y el bot no es de
  latencia.
- Pares contra BTC: H4 mostró que los spreads tienden, no revierten, a 30 días.

## Recomendación de secuencia

1. **H8: spread de funding entre venues.** Es la única familia con evidencia OOS
   reciente y específica; si falla por muestra o por compresión del spread, se
   aprende algo sobre el carry que H2/H5 no pudieron dar.
2. **H9: basis spot-perp.** Más fácil y rápida; si H8 consume más de dos semanas,
   H9 puede adelantarse porque el dato spot se descarga en una sesión.
3. **H10: on-chain de stablecoins** solo si H8/H9 fallan y queda tiempo antes de
   la puerta del 2027-02-26. Macro y opciones quedan para después de esa puerta
   o para un bot con opciones.

Cada una empieza con pre-registro y hash, 5 variantes como máximo, las 10
puertas del plan y la regla de archivo del mismo día. Sin excepciones.
