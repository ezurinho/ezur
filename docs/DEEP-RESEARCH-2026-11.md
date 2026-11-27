# Investigación de fondo: qué dice la evidencia sobre el carry y dónde está el dinero

Revisión externa hecha el 2026-11-27 en cuatro frentes —literatura académica y de
industria sobre carry de funding, rendimientos reales de estrategias
market-neutral, práctica estadística de validación y fuentes de datos
disponibles— para contrastar el archivo del laboratorio contra lo publicado. No
es una revisión sistemática: es una lectura con fuentes primarias siempre que
existían, y con la procedencia marcada cuando no.

---

## 1. La prima se comprimió a un T-bill

| Fuente | Muestra | Resultado |
|---|---|---|
| Zetlin-Jones, *The Crypto Carry Trade* (CMU, 2022) | Binance 2020-08/2022-06, 8 h, sin costes | BTC **21,84 %/año, SR 11,47**; el funding aporta 21,3 de los 21,9 puntos; el último subperiodo cae a **7,63 %/año** |
| He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures* (arXiv 2212.06888) | Binance 2020-2024, con costes | Carry siempre activa: BTC **SR 2,24, 10,18 %/año, DD −5,33 %**; BNB **SR −0,66**. La variante con umbral: **SR 3,35, 12,96 %/año** |
| Schmeling, Schrimpf & Todorov, *Crypto Carry*, BIS WP 1087 (rev. 2025) | BTC/ETH, CME + offshore | Carry medio **>10 %/año, hasta 60 %**; el carry alto **predice crashes**; lo explican la escasez de capital de arbitraje y las fricciones de margen |
| Fluxy, *Perp Funding Almanac* (2026) | Suma de liquidaciones Binance BTC | 2021 **+30,6 %**, 2022 +4,2 %, 2023 +7,9 %, 2024 +12,0 %, 2025 **+5,1 %**, ene-ago 2026 **+1,7 %** |
| Amberdata (oct-2025) | Basis a 30 días | Mínimo **1,17 %**, rebote a 4,46 %, **por debajo del 5 % de breakeven** |
| CFTC COT (dic-2024 → nov-2026) | CME BTC, leveraged funds | Short bruto **26.850 → 7.705 contratos (−89 %)**; el trade se ha desmontado |

**Lo que esto dice del laboratorio:** los Sharpe de dos dígitos que circulan son
de 2020-2022, sin costes y sin margen. Netos y en 2025-2026, el carry de majors
paga lo que un T-bill. Que H2 (carry BTC) diera +2,35 % anual con 4 episodios y
H5 midiera 0,0301 R no es un fallo del laboratorio: es el nivel que reporta la
literatura cuando se restan los costes.

## 2. El cambio de fórmula del 18-sep-2025 (lo más importante para nuestra medida)

Binance cambió el cálculo del funding a

```
F = [P + clamp(0,01 % − P, ±0,05 %)] / (8 / N)
```

con N el intervalo en horas. Ejemplo oficial: para un contrato de 4 h,
`F = [P + clamp(...)] / 2`. Antes de ese cambio, un contrato de 4 h imprimía el
premium completo cada 4 h; después, imprime la mitad. Consecuencia directa: **el
cash diario (suma de tasas) es la única medida invariante al intervalo**, y el
equivalente a 8 h se obtiene multiplicando la tasa por `8/N` **sólo si ese
`/N` no está ya aplicado** — que es exactamente lo que la fórmula nueva hace.

Junto a eso, la cronología que explica la serie: 12-oct-2023 quince perpetuos
pasan a 4 h; 2-may-2025 un settlement que toca el cap pasa el contrato a **1 h**;
1-sep-2025 vuelve a 4 h tras 36 ciclos con |funding| ≤ 0,002 %; 18-sep-2025 la
fórmula de arriba.

**Lo que esto dice del laboratorio:**

1. La convención del plan (cash diario) no es una preferencia: es la única que
   sobrevive al cambio de fórmula. Nuestro `rate8h = rate × 8/intervalo` es
   correcto como *tasa equivalente* pero **duplica** el cash al sumarlo por día.
2. La explosión de dispersión de 2026 (**30,25 pb/día**, 309 pb por ventana) **no
   es un artefacto de intervalo**: después de sep-2025 el cash diario ya es
   invariante al intervalo por construcción, y aun así subió 3×.
3. El pico de 2025-2026 coincide con el desmontaje del basis institucional
   (−89 % de shorts en CME): es la prima residual de un trade que se cierra, no
   un régimen nuevo y estable.

## 3. H8 no es un outlier: es lo que encuentra la literatura

El estudio más duro sobre arbitraje de funding entre venues (MDPI *Mathematics*
14(2):346, 2026) usa 35,7 M de observaciones por minuto, 749 símbolos y 26
exchanges: **17 % de las observaciones superan 20 pb** de spread (≈219 %
anualizado), pero al simular carteras de 10.000 USD por pata con costes
realistas, **8 de 20 son rentables, el P&L medio es +22 USD y el Sharpe medio
−7,40**; el 95 % de las oportunidades se revierten y el coste de ida y vuelta en
pares ilíquidos (~220 USD) tarda 3,7 días de funding en amortizarse.

Nuestro H8: +0,32 %, PF 10,46, 17 episodios, 0,0094 R. Misma forma: la
oportunidad existe, la muestra y el coste la hacen inejecutable.

## 4. La concentración que importa es la de la pata de precio

El análisis de Hyperliquid (preprint 2026) documenta que **BTC/ETH/SOL cotizan
cerca del 0 % anualizado mientras small caps y memecoins muestran primas
estructurales de +6 % a +35 %**, y que el clamp de funding se ata el 96,8 % de
las horas en AAVE frente al 6,4 % en BTC. La prima, por unidad de nocional, vive
en los nombres pequeños; por dólar desplegable, sólo existe diversificando
docenas.

Nuestra medición (`scripts/carry_concentration.py`, 95 semanas de 2025-2026):

- el nombre mayor aporta el **24,8 %** del diferencial, el top-3 el **47,3 %**,
  el top-5 el **61,6 %**; hacen falta **9 nombres** para el 80 %; ninguna semana
  con un solo nombre por encima del 50 %.
- capacidad: **2,26 M USD** de bruto al 1 % del volumen mediano por posición.

**Lo que esto dice:** el carry del tramo largo está razonablemente repartido. Lo
que concentra el P&L de H5 no es el funding, es la **pata de precio** (H5 es
largo de un quintil y corto de otro, no delta-neutral). Eso reencuadra el
archivo: la familia que falló por top-5 falló por beta cruzada, no por carry.

## 5. Dónde está el dinero de verdad (y por qué no es una señal)

El registro completo de Hyperliquid (729.540 carteras, 15 meses, AFT 2026):

| Grupo | P&L neto | Comisiones |
|---|---:|---:|
| Market makers algorítmicos | **+208 M USD** | 50 M (0,16 pb) |
| Takers algorítmicos | ≈ 0 | 55 M (2,17 pb) |
| Retail | **−1.110 M USD** | **725 M (2,99 pb)** |

El retail pierde por **demandar inmediatez, cruzar el spread y pagar el tier de
comisiones más caro**, no por información. En opciones, el mejor neto documentado
(Anchorage, 37.000 backtests sobre Deribit, con 1 punto de slippage) es una
covered call a 20 delta y 30 días: **+5,5 % neto** en el último año, **−0,5 % en
el ciclo completo 2021-2026**, con profit factor 1,00. Ethena, el mejor
experimento natural de basis a escala, pasó de **37,7 % APY en marzo de 2024 a
6,5 % en 2025 y 4,0 % en el primer trimestre de 2026**.

**Lo que esto dice, sin adornos:** en 2026 el dinero de las estrategias
market-neutral no está en una señal de funding que un laboratorio de 25.000 USD
pueda capturar. Está en market making (donde la ventaja es el tier de comisiones
y la latencia) y en vender volatilidad con filtros (donde el neto del ciclo es
cero). Un edge de funding de 40 pb semanales sobre 25.000 USD son 100 USD por
semana antes de costes: no es un negocio, es un ejercicio.

## 6. Lo que la práctica estadística exige y el laboratorio ya puede hacer

- **Potencia primero**: `n ≈ (z_α + z_β)² / SR²`. Con α = 5 % y potencia 80 %,
  detectar un SR anual de 0,5 exige **31 años**; 1,0, unos 8 años. Por eso H2
  (4 episodios) y H8 (17) no eran medibles: no era un resultado, era un diseño
  inviable. Implementado en `scripts/power_gate.py`.
- **DSR con el denominador honesto**: el número de ensayos es el dato que casi
  nunca se publica y el que decide los casos límite (H5 raw, DSR 0,54).
  Implementado en `scripts/lab_ledger.py` con cadena de hash.
- **Baseline nulo por permutación**: hay que barajar el emparejamiento
  señal-mercado, **no** la serie de retornos de la estrategia (el Sharpe es
  invariante al orden: ese null es degenerado). Implementado en
  `scripts/validation_suite.py`; sobre H10 la dispersión observada queda en el
  **percentil 100** de 50 permutaciones (p = 0,0196).
- **PBO**: 0,5 es el baseline nulo, no un aprobado. Nuestro 0,4087 de la rejilla
  SMA se lee como "no hay evidencia de sobreajuste", no como "está bien".

## 7. Datos que harían falta para una familia nueva

| Señal | Fuente gratuita | Desde |
|---|---|---|
| Imbalance / profundidad L2 | Bybit (archivo público), OKX | 2023-01 / 2023-03 |
| CVD / agresión de taker | Binance Vision `aggTrades` | 2017-08 |
| Superficie de volatilidad, skew, DVOL | Deribit público | 2021 (DVOL) |
| Funding cross-venue horario | Hyperliquid `fundingHistory` | 2023-05 |
| Trades y OI de un venue nuevo | Lighter (AWS Open Data, parquet) | 2025-01 |
| Liquidaciones con historia | **nada gratis** (CoinGlass 35 USD/mes a 4 h+) | — |

Aviso de look-ahead en cada una: el funding de Hyperliquid es horario y se cobra
al cerrar la hora (para señal hay que usar el *predicted funding*); los trades
Block RFQ de Deribit se insertan retroactivamente; los agregados de liquidación
son un mínimo, no un total.

## 8. Qué cambia para el laboratorio

1. **Nada del veredicto.** Diez familias archivadas, ninguna desplegable. La
   literatura no ofrece ninguna que hayamos medido mal.
2. **Se refuerza la convención de cash**: el cambio de fórmula del 18-sep-2025 la
   hace obligatoria, no preferible.
3. **Se reencuadra H5**: falló por la pata de precio, no por el carry; el carry
   estaba repartido en 9 nombres.
4. **Se cierra la puerta del carry de majors con una razón externa**: es un trade
   que se ha comprimido a T-bill y que se está desmontando.
5. **Si algún día se reabre**, las tres únicas direcciones con datos gratuitos y
   mecanismo plausible son microestructura (L2/CVD), volatilidad (Deribit) y
   cross-venue con funding horario — y las tres necesitan la puerta de potencia
   antes de tocar un backtest.

## Fuentes

- Zetlin-Jones, *The Crypto Carry Trade* — andrew.cmu.edu/user/azj/files/CarryTrade.v1.0.pdf
- He, Manela, Ross & von Wachter, *Fundamentals of Perpetual Futures* — arxiv.org/html/2212.06888v7
- Schmeling, Schrimpf & Todorov, *Crypto Carry*, BIS WP 1087 — bis.org/publ/work1087.htm
- Chi, *J. Futures Markets* (2023) — onlinelibrary.wiley.com/doi/full/10.1002/fut.22425
- Fluxy, *Perp Funding Almanac 2020-2026* — fluxy.io/blog/perp-funding-almanac-2020-2026
- Amberdata, basis y breakeven — blog.amberdata.io/the-etf-exodus-decoded-basis-arbitrage-not-capitulation
- COT de CME y desmontaje del basis — hedgeco.net/news/11/2026/... ; howdoescryptowork.com/articles/the-crypto-basis-trade
- MDPI *Mathematics* 14(2):346 (2026), funding cross-venue — mdpi.com/2227-7390/14/2/346
- Jia, Moallemi et al., AFT 2026, Hyperliquid — drops.dagstuhl.de/.../LIPIcs.AFT.2026.36.pdf
- Anchorage, covered calls — anchorage.com/insights/synthetic-yield-on-bitcoin...
- Binance, anuncios de intervalo y fórmula — binance.com/en/support/announcement/detail/c00588a7e8504b3eb28d02a2da00530b (18-sep-2025); .../98d6b24d3e5c4f84a8ed04087997d8d0 (12-oct-2023); .../3243c81a35bd4f0c86a37315c3dc96cc (2-may-2025)
- Bailey & López de Prado, PSR y DSR — davidhbailey.com/dhbpapers/sharpe-frontier.pdf ; .../deflated-sharpe.pdf
- Bailey, Borwein, López de Prado & Zhu, PBO — davidhbailey.com/dhbpapers/backtest-prob.pdf
- Aronson, *Monte-Carlo Evaluation of Trading Systems* — evidencebasedta.com/montedoc12.15.06.pdf
- Fuentes de datos — bybit.com/derivatives/en/history-data ; github.com/binance/binance-public-data ; docs.deribit.com ; hyperliquid.gitbook.io/hyperliquid-docs/historical-data ; docs.lighter.xyz
