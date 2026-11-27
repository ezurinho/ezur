# Revisión de diseño H8 — spread de funding entre venues

**Fecha:** 2026-11-27  
**Adelanta** la revisión prevista para el 2026-12-04.  
**Decisión:** H8 es el spread de funding del mismo activo entre Binance y
Hyperliquid. No se eligen opciones ni on-chain en esta ronda.

## Por qué H8

Es la única familia del ranking post-H7 con evidencia fuera de muestra reciente
y específica: Lau (2026, SSRN 6993978) documenta una prima de Hyperliquid sobre
Binance/Bybit del 14,7 % anualizado en 2024 y del 4,6 % en 2025, con t HAC 4-8 y
4-5 de 5 folds walk-forward. La posición es **el mismo activo en dos venues**,
delta-neutral: no es el carry de nivel de H2, ni el cross-section de funding de
H5, ni una apuesta direccional. Ataca una fuente de retorno distinta.

La prima tiene una explicación económica concreta: el funding es el precio que
pagan los apalancados de cada venue, y el capital arbitrajista no fluye libremente
entre plataformas por riesgo de contraparte, latencia de transferencia, colateral
fragmentado y límites operativos. Quien cobra la prima asume riesgo de venue y de
ejecución, no riesgo de precio.

## Por qué no las alternativas

- **Opciones (DVOL):** no hay ejecución de opciones en este bot, ni margen, ni
  liquidación de volatilidad corta. Sería research, no una estrategia desplegable.
- **On-chain de stablecoins:** el dato gratuito es oferta de stablecoins y TVL, no
  netflows etiquetados de exchanges; la señal probable es un proxy de beta y la
  historia útil es corta.
- **Macro:** es timing de beta, no una prima market-neutral.
- **Cascadas/OI:** el histórico público está truncado y el edge vive en minutos,
  fuera del horizonte de este bot.

## Venues y datos

- **Binance USD-M:** funding y cierres diarios ya congelados en
  `data/funding_xs/` para 20 símbolos.
- **Hyperliquid:** funding horario y velas diarias por API pública. El endpoint
  devuelve como máximo 500 eventos por llamada; se pagina por `startTime`.
- **OKX queda fuera:** se descargó, pero su API pública solo conserva 67 días de
  funding (2026-08-26/2026-10-31), insuficiente para 2023-2026. Se excluye antes
  de medir, sin usar un tramo parcial.
- **Bybit queda fuera:** su API devuelve un bloqueo de CloudFront para esta
  región. No se intenta eludir el bloqueo ni se usa un proxy. La ausencia se
  declara como límite de cobertura, no como resultado.

Universo: **BTC, ETH, SOL, XRP y DOGE**, los cinco mayores con historia común en
los tres venues. La ventana común empieza el 2023-05-12 (primer funding de
Hyperliquid). Se usa warmup desde esa fecha, desarrollo desde 2023-07-01 y
validación hasta 2026-11-01. El holdout 2026-12-01/2027-05-31 no se toca.

## Por qué puede fallar

- El spread de 2025-2026 puede estar comprimido por debajo de los costes, como
  sugiere Talos. Si es así, se archiva; no se baja el umbral para rescatarlo.
- Hyperliquid fuera de BTC/ETH tiene menos profundidad y riesgo de capacidad.
- Solo hay dos venues: el spread es un único par por activo, sin una tercera
  referencia que diversifique el riesgo de contraparte.
- Los intervalos de funding no coinciden (1 h frente a 8 h); se suman a diario,
  pero el instante de pago y el mark de cada venue introducen ruido.
- El riesgo de venue no es observable en un backtest: una quiebra o una retirada
  bloqueada no aparece en el P&L histórico.

## Criterio de parada

Si el candidato no supera PF, esperanza, top-5 o muestra en OOS, se archiva el
mismo día y se pasa a H9 (basis spot-perp). No se prueban umbrales adicionales
después de ver los resultados. El pre-registro con las cinco variantes queda en
`docs/PRE-REGISTRO-H8.md`.
