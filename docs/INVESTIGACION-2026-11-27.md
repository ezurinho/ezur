# Investigación — qué ventajas tienen evidencia real en cripto

**Fecha:** 2026-11-27
**Uso:** insumo para decidir la próxima familia del laboratorio. No es una
recomendación de inversión; es un mapa de evidencia con sus sesgos.

## Resumen ejecutivo

Ocho familias revisadas. Solo dos tienen evidencia fuera de muestra con costes:
el **carry cross-sectional de funding** (modesto, Sharpe ~0,4, PBO alto) y el
**TSMOM long-only** (Sharpe ~1,5 en una cesta amplia, pero es beta y se
concentra en mercados alcistas). El resto o no tiene evidencia peer-reviewed
(Coinbase premium), o el efecto es real pero no pagable después de costes
(order flow, reversión de 15 m, cascadas), o depende de datos propietarios
(on-chain) o de superficies de opciones que no se pueden reconstruir gratis.

## 1. Carry de funding y basis

- **BIS WP 1087 / Management Science 2026 (Schmeling, Schrimpf, Todorov):** carry
  medio >10 % anual, picos 40-60 %, muestra 2019-2022; cash-and-carry Sharpe
  0,59 antes de costes; el carry alto predice crashes y liquidaciones.
  https://www.bis.org/publ/work1087.htm
- **Chi (2023, Journal of Futures Markets):** factor basis high-minus-low
  +329 % anualizado bruto, +305 % neto de 5 pb, t=7,10, Sharpe 3,82; max DD
  99,9 %; el efecto desaparece a horizontes semanales/mensuales.
  https://onlinelibrary.wiley.com/doi/full/10.1002/fut.22425
- **Franz & Schmeling (2021):** el carry de funding predice retornos de BTC y en
  el corte transversal de 51 monedas; es un WP corto, sin costes ni OOS formal.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3774118
- **Bryan Vine (2026, no revisado):** 30 perpetuos, 2023-2026; el carry de nivel
  da +5,6 %/año y muere en 2026; el factor cross-sectional long-low/short-high
  tiene Sharpe OOS 0,39, PBO 0,81, DSR 0,63. Es el mejor test directo y aun así
  no supera un umbral serio.
  https://bryanvine.github.io/alpha-research/paper2.html
- **Ichikawa & Nakagawa (2026):** 28 perpetuos Hyperliquid, 2024-2026; carry puro
  -2,9 %/año antes de costes: funding +11,7 % comido por precio -14,6 %.
  https://www.jstage.jst.go.jp/article/jsaisigtwo/2026/FIN-037/2026_168/_pdf/-char/ja
- **Mtrinkner (2026):** panel punto-en-tiempo, neto -78,9 %; el 77 % de la
  pérdida viene de 10 semanas de rally de alts; el IC se anula al corregir
  supervivencia. https://github.com/mtrinkner/crypto-funding
- **Talos (2026):** el funding anualizado de BTC pasó de 20-40 % en 2024 a 3-5 %
  en 2026, cerca o por debajo de T-bills.
  https://www.talos.com/insights/following-the-funding-the-shift-towards-the-equity-basis-trade

**Lectura:** el nivel de carry ya no paga; el cross-sectional sobrevive con
Sharpe ~0,4 y PBO 0,81, y su pata corta es un short-momentum que sufre en los
rallies. Si se prueba, z-score por contrato, vol-targeting y medir precio y
funding por separado.

## 2. Momentum

- **Han, Kang & Ryu (2024):** 2013-2023, 28 días/5 días, 15 pb por operación;
  TSMOM long-only Sharpe 1,51 neto vs 0,85 del mercado, en posición solo el
  48 % del tiempo, mejor en 8 de 10 años. La pata corta pierde dinero.
  https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf
- **Grobys & Sapkota (2019):** momentum cross-sectional no significativo en 143
  monedas, 2014-2018.
- **Springer (2025):** todas las estrategias de momentum fallaron en 2022-2023.
- **Han et al. (2024):** de 21 carteras cross-sectional, 5 se liquidan y solo 6
  baten al mercado; el top-5 % deja de funcionar desde 2021.
- **Arefev (2026):** replicación neta de costes en 832 perpetuos; el spread
  bruto 0,573 %/semana es del orden del coste 0,40 pp/semana y desaparece.
  https://papers.ssrn.com/sol3/Delivery.cfm?abstractid=7404139

**Lectura:** el TSMOM long-only es la única pieza con evidencia limpia, pero es
beta y depende del régimen; el cross-sectional está muerto después de 2021.

## 3. Coinbase premium y flujos de ETF

- **Fabus et al. (2026):** el flujo de ETF parece predecir retornos solo si se
  alinea mal el timestamp; con una ventana posterior al flujo público, el
  coeficiente cae a 1,67 y el R² a 0,036; la relación inversa (retorno pasado →
  flujo) es la significativa.
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7545019
- **Ashish (2026):** VAR 2024-2025; los flujos de ETF **no** Granger-predicen
  BTC (p=0,325-0,943); BTC sí predice flujos.
  https://spectrum.library.concordia.ca/id/eprint/997714/1/Ashish_MSc_F2026.pdf

**Lectura:** no hay evidencia de alpha direccional; el premium es en parte
consecuencia del movimiento y el flujo institucional va por OTC.

## 4. Order flow

- **Anastasopoulos et al. (2026, Journal of Empirical Finance):** 82 monedas,
  2018-2022; order flow contemporáneo explica 10,4 % diario y 19,6 % semanal;
  el rezagado aporta 0,2 % diario y 0,9 % semanal; Sharpe 2,14 bruto, sin costes
  verificados.
- **Quantitative Finance (2025):** ninguna estrategia de latency trading es
  rentable después de fees de taker.
- **Digital Finance (2022):** predictibilidad sub-1s real, rentable solo con fee
  de maker extrema.
- **Imbalance Labs:** rank-IC 0,0498 a 1 min → 0,0030 a 60 min (-94 %).

**Lectura:** es un juego de market making/latencia; no de bot horario.

## 5. On-chain

- **Grobys, Näsman & Sandretto (2026):** MVRV Z-score, NUPL y CVDD,
  2013-2025; Sharpe 0,45 B&H → 1,28 con MVRV Z; umbrales elegidos in-sample y
  solo 3 ciclos.
  https://www.sciencedirect.com/science/article/pii/S0275531926002138
- **Journal of Banking & Finance (2022):** reservas de exchanges predicen
  retornos y volatilidad mejor que otros factores, pero los datos son de
  CryptoQuant (pago) y el clustering es propietario.

**Lectura:** la mejor evidencia depende de datos caros y de pocos ciclos; no es
la vía para este laboratorio.

## 6. Opciones

- **Quantitative Finance (2024):** los risk premia de Deribit son negativos y
  significativos; vender volatilidad paga a largo plazo.
- **Journal of Empirical Finance (2023):** el spread RV-IV es negativo y mayor
  que en el S&P 500, pero el order imbalance no predice dirección.
- **Finance Research Letters (2026):** IV y slope mejoran el forecast de RV,
  pero ninguna señal predice la dirección.
- **Bryan Vine (2026):** el Sharpe del harvest cae de 1,53 a ~0 con estimadores
  Parkinson/Garman-Klass y decae a ~0 en 2024-2026.

**Lectura:** la prima existe, pero no se puede reconstruir la superficie
histórica ejecutable gratis y el harvest depende del estimador.

## 7. Liquidaciones y reversión

- **De Nicola (2021):** autocorrelación de retornos -0,14 (1 min) a -0,007
  (1 día); a mayor movimiento, mayor reversión.
- **arXiv 2608.21888 (2026):** 90 % de los pares cripto muestran reversión
  significativa a 15 m vs 2,7 % de las acciones; AUC OOS 0,536; holdout 6 meses
  +0,020; **"persiste a un tamaño no explotable bajo costes de referencia"**.
- **Cascada 10-oct-2025:** $19B de OI evaporado, $8,55B liquidados, BTC -7,9 %,
  rebote +4,2 % en 24 h, spreads ×20 durante el pico.

**Lectura:** mecánicamente documentada, económicamente no pagable para un bot
lento; solo con órdenes límite pasivas pre-colocadas.

## 8. Estacionalidad intradía

- **Review of Quantitative Finance and Accounting (2024):** 1.940 pares, 38
  exchanges; retornos máximos 15:00-16:00 UTC, mínimos 01:00-05:00; volumen y
  volatilidad pican 16:00-17:00.
- **Grobys et al. (2024):** no hay estacionalidad robusta en retornos con 500
  monedas; el efecto lunes desaparece después de 2015.
- **FRL (2026):** los efectos día-de-semana se concentran en pocas horas y son
  específicos de activo, no anomalías persistentes.

**Lectura:** sirve para **ejecutar** (liquidez, spread), no para predecir.

## Ranking para este laboratorio

1. **Carry cross-sectional de funding** — dato gratis, dollar-neutral, único
   test OOS con costes positivo (Sharpe 0,39), pero PBO 0,81 y pata corta de
   momentum. Ya probado en H5; la variante raw murió en DSR 0,54.
2. **TSMOM long-only** — evidencia neta más limpia, implementación trivial, pero
   es beta y se concentra en alcistas. Ya probado en H6; perdió en OOS.
3. **Carry de nivel oportunista** — activar solo con funding anualizado >15-20 %
   (percentil 90); el nivel actual (3-5 %) no paga y el tail es letal.

## Lo que no se puede verificar

- Si el Sharpe 2,14 de order flow está neto de comisiones.
- Los coeficientes exactos de "Loaded for bear" (JBF 2022).
- La disponibilidad histórica completa de `allForceOrders` en Binance.
- El detalle de construcción de Franz & Schmeling (solo abstract).

## Consecuencia para el plan

Las dos mejores candidatas de la literatura ya se midieron y fallaron en OOS
(H5 y H6). La próxima hipótesis no debería ser otra variante de precio/funding
sobre los mismos 20 nombres: necesita un dato nuevo (order flow agregado,
opciones, on-chain) o un universo distinto (small caps, multi-venue). Y debe
declararse en `docs/TRIALS.md` antes de medir: ya van 35 variantes.
