# Repaso de seis vídeos de estrategias

> **Qué es este documento.** Una herramienta de triaje, no una validación de
> rentabilidad. Resume qué promete cada vídeo, qué evidencia enseña y si merece
> la pena convertirlo en una hipótesis medible. Ninguna de las seis estrategias
> se ha probado en este repo; los veredictos son sobre la evidencia del vídeo.
>
> **Fecha:** 2026-11-25.
>
> **Fuente:** transcripciones locales en `data/tmp_transcripts/<id>.wrapped.txt`
> (ignoradas por git) y metadatos públicos de YouTube cuando estaban
> disponibles. Dos IDs no devolvieron título en oEmbed; se identifican por ID.
> Cuatro de los seis IDs comparten el mismo mecanismo de arbitraje on-chain y se
> revisan por separado porque el encargo es de seis vídeos.

## Cómo usar este documento

Antes de escribir una estrategia, abrir el laboratorio o copiar una regla:

1. Rellenar las siete preguntas de abajo con datos, no con impresiones.
2. Si falla cualquiera de las cuatro primeras, **descartar**: no hay nada que
   medir todavía.
3. Si las cuatro primeras pasan pero fallan las tres últimas, queda como
   **hipótesis para research**, nunca como candidata a paper.
4. Solo si las siete tienen respuesta se convierte en una spec y se pasan las
   puertas del repo (`docs/PROTOCOLO_BACKTEST.md` y `docs/MEDICIONES.md`).
5. En este repo, “probar” significa **paper trading**. `live_enabled` sigue en
   `false`; ninguna idea de un vídeo cambia eso.

## El checklist de 7 preguntas

| # | Pregunta | Evidencia mínima que exigir | Si la respuesta es no |
|---|---|---|---|
| 1 | **¿De dónde sale la ganancia?** | Un mecanismo concreto: arbitraje, MEV, tendencia, reversión, prima de riesgo, flujo de órdenes… y quién paga esa ganancia. | “La IA lo encuentra” no es un mecanismo. Descartar. |
| 2 | **¿Por qué sigue existiendo y por qué te deja participar?** | Competencia, capacidad, latencia, barreras de entrada y selección adversa. Si el edge es público, explicar por qué no se agota. | Si no hay una razón defendible, es marketing. Descartar. |
| 3 | **¿Qué evidencia hay, con qué muestra y fuera de muestra?** | Dataset, periodo, número de operaciones, corte IS/OOS o holdout, benchmark y drawdown. Una sesión de 24 h o 45 operaciones no es una muestra. | Sin muestra y OOS no hay veredicto. Descartar. |
| 4 | **¿Se puede reproducir?** | Código o contrato auditable, datos, comisiones, slippage, fills y logs. No un enlace, un Telegram o una caja negra. | Si no se puede repetir, no es evidencia. Descartar. |
| 5 | **¿Se corrigió el sesgo de selección?** | Número de variantes probadas, pre-registro, PBO ≤ 0,2 y DSR ≥ 0,95 en el ciclo de selección. No elegir la mejor después de ver los resultados. | Si probó veinte y enseña la mejor, el número está contaminado. Solo research. |
| 6 | **¿Sobrevive a costes, liquidez y tamaño?** | Comisiones, gas, spread, funding, borrow, capacidad, tamaño de posición y drawdown/ruina; PF con coste duplicado > 1. | Si el edge desaparece al pagar costes, no hay edge. Solo research o descartar. |
| 7 | **¿Qué pasa en el peor caso y quién responde?** | Custodia, contrato/bróker/plataforma, retiradas, regulación, legalidad, incentivos del promotor y pérdida máxima. | Si no sabes dónde está el dinero ni quién responde, no se prueba. Descartar. |

### Regla de decisión

- **1–4 fallan:** descartar. No gastar tiempo en backtest.
- **1–4 pasan, 5–7 fallan:** guardar como hipótesis; medir antes de creer.
- **Las siete pasan:** escribir la spec y aplicar las puertas del repo.
- **Ninguna de las seis cumple las siete.** La única que deja una hipótesis
  testeable es la de breakout de Minara; las otras cinco no pasan del triaje.

## Señales de alarma

| Señal | Por qué es una alarma | Dónde aparece |
|---|---|---|
| Retornos de 100–5.700 % anual, o 500 → 2.922 en 14 minutos | Sin drawdown, sin muestra y sin costes no es una estrategia; es una captura de pantalla. | Minara y opciones binarias |
| “24 horas” o “una sesión” como prueba | Una muestra de un día no distingue habilidad de suerte; menos aún con apalancamiento. | Los cuatro de arbitraje y binarias |
| 80 % de acierto sin enseñar el pago medio | El win rate no dice nada si la pérdida media es mayor que la ganancia media. | Binarias |
| Pérdida media 151 frente a ganancia media 105; una stake casi el 40 % del saldo | Con esa asimetría, una racha mala se lleva la cuenta. El propio vídeo dice que puede ir al revés. | Binarias |
| “14 victorias seguidas” o “nunca tres pérdidas seguidas” en 45 operaciones | Una racha no es evidencia de edge; es lo que produce el azar en muestras pequeñas. | Binarias |
| “La IA escribió el código; no necesitas entenderlo” | Sin auditoría no sabes qué firma el contrato ni qué permisos pide la wallet. | Arbitraje on-chain |
| Guía, enlace o Telegram en la descripción | El incentivo del vídeo es el embudo, no tu rentabilidad. | Arbitraje on-chain y binarias |
| Fondear 0,5–20 ETH en un contrato sin auditoría | Riesgo de contrato, de retirada y de contraparte; verificar el owner no es auditar. | Arbitraje on-chain |
| “Es open source” sin revisión independiente | Código abierto no significa código seguro ni ejecución reproducible. | Arbitraje on-chain |
| Estrategias del marketplace con 26.000 operaciones y solo 3 meses OOS | Supervivencia y selección: se enseña la que ganó, no el universo que se probó. | Minara |
| El promotor revela una colaboración o partnership con la plataforma | El análisis deja de ser independiente; hay que descontar el incentivo. | Minara |
| “Resultados variables”, “solo educativo”, “no es asesoramiento” después de prometer rentabilidad | El descargo contradice la promesa; no sustituye la evidencia. | Todos |
| Backtest sin corte IS/OOS, o solo in-sample | Es una curva ajustada al pasado, no una predicción. | Minara |
| Apalancamiento 3×/5× y stop al 50 % del principal | El riesgo de ruina se dispara; el stop no protege de un gap o de un mal fill. | Minara |
| No hay comisiones, slippage, funding ni drawdown en el balance | La contabilidad está incompleta; el número no es neto. | Todos |

## Veredicto de los seis vídeos

| ID | Título / canal | Qué promete | Veredicto |
|---|---|---|---|
| `5i5lkg1vhlE` | Título no disponible en oEmbed | Bot on-chain de arbitraje en Ethereum; 24 h; mínimo 1 ETH; guía en la descripción | **DESCARTAR** |
| `a2fCgb0wJag` | *AI Trading: Build Your Own Trading Bot with Claude AI - Live AI Trading Bot Strategy: Full Guide* — David Web3Developer | El mismo mecanismo on-chain; 24 h; 2–20 ETH; código en la descripción | **DESCARTAR** |
| `atW53M8223I` | *Day Trading with Claude AI Trading Agents (full tutorial)* — Peter Rush | El mismo mecanismo on-chain en español; 24 h; 2–20 ETH | **DESCARTAR** |
| `rN7pXgjnam0` | *Full Guide to Building an AI Trading Bot with ChatGPT AI Agents* — Peter Rush | El mismo mecanismo on-chain en español; 24 h; 0,5–4 ETH | **DESCARTAR** |
| `qklXQosyZKI` | *I Did It! I Finally Found The #1 AI Trading Bot (we're early)* — Miles Deutscher Finance | Marketplace de estrategias, backtests y ejecución; ventana de 5.700 / 750 / 570 (unidad no aclarada) y 5.500 % total | **OBSERVAR** (herramienta, no estrategia) |
| `wYmr5mKeUGo` | Título no disponible en oEmbed | Bot de opciones binarias; 500 → 2.922 en 14 minutos; 45 operaciones; 80 % de acierto | **DESCARTAR** |

### Los cuatro vídeos de arbitraje on-chain

`5i5lkg1vhlE`, `a2fCgb0wJag`, `atW53M8223I` y `rN7pXgjnam0` enseñan el mismo
mecanismo con distinto idioma, canal y cantidad mínima:

- Se observa el mempool de un DEX.
- Al detectar una compra grande pendiente, se envía otra transacción con más gas
  para adelantarse.
- Después se vende y se captura la diferencia de precio.

**Lo que muestran:** un contrato desplegado, una wallet conectada, el bot en la
nube durante 24 horas y un saldo al volver. En algunas versiones se enseña el
retiro; en ninguna se enseña un estado de resultados con comisiones, gas,
operaciones fallidas, drawdown o benchmark.

**Lo que falta:** no hay serie de operaciones, ni comparación con un periodo
anterior, ni análisis de competencia. El mecanismo es una carrera de gas y
latencia contra otros bots; que el vídeo lo llame “arbitraje” no lo convierte en
una ventaja estable para un retail. Además, el contrato no está auditado en el
vídeo, la wallet firma permisos y el dinero queda en el contrato.

**Veredicto: DESCARTAR los cuatro.** No es una estrategia para este motor:
requiere datos de mempool, ejecución on-chain y un contrato auditado; nada de eso
está en el repo. El único aprendizaje transferible es que la ejecución y los
costes importan, no que el bot gane.

### Minara: marketplace de estrategias

`qklXQosyZKI` no enseña un bot propio: enseña **Minara**, una plataforma con
marketplace, “strategy studio”, backtests y ejecución. Las cifras que aparecen
son afirmaciones del vídeo, no mediciones independientes:

- estrategias con retornos de ventana de 5.700, 750 y 570 (el vídeo no aclara
  la unidad de los dos primeros);
- una estrategia destacada con 5.500 % total, 105 % anual y 79 % de alfa;
- la mejor con casi 26.000 operaciones;
- el propio autor reconoce que la estrategia solo lleva **tres meses** fuera de
  muestra y que no hay datos suficientes para juzgarla;
- el autor declara una colaboración/partnership con la plataforma.

**Lo que falta:** el universo de estrategias que se probaron antes de enseñar
esas tres, el detalle de comisiones y slippage, la independencia del backtest y
una muestra OOS suficiente. Un marketplace que ordena por retorno es una
fábrica de sesgo de supervivencia.

**Veredicto: OBSERVAR.** La plataforma puede servir para investigar, pero no es
una estrategia ni una validación. Lo único que merece pasar al repo es la
hipótesis que el autor prueba de pasada: **comprar la ruptura del máximo de 20
días y salir bajo el mínimo de 10 días, long-only, sin apalancamiento**. Eso se
puede medir aquí con datos diarios, costes, corte OOS y las puertas de selección;
no se copia el resultado del vídeo ni se ejecuta su marketplace.

### Opciones binarias: 500 → 2.922 en 14 minutos

`wYmr5mKeUGo` enseña Pocket Option y “Tradeex AI” operando acciones (Tesla,
Apple, Netflix, Boeing) en una cuenta real. Las cifras del propio vídeo:

- 45 operaciones: 36 ganadas y 9 perdidas;
- 80 % de acierto;
- ganancia media 105 y pérdida media 151;
- las nueve pérdidas costaron 1.356;
- una stake fue casi el 40 % del saldo inicial;
- “nunca tres pérdidas seguidas” en esa sesión;
- el método se explica en Telegram;
- el autor cierra diciendo que puede ir “al revés de la misma forma”.

La aritmética de la sesión cuadra: `36 × 105 − 9 × 151 = 2.421`, que lleva el
saldo de 500 a 2.922. Pero el punto de equilibrio con esos pagos es
`151 / (105 + 151) ≈ 59 %` de acierto; el 80 % observado es una sola sesión de
45 operaciones, con una stake que puede liquidar la cuenta en una racha. No hay
OOS, ni costes del bróker, ni auditoría de la “cuenta real”.

**Veredicto: DESCARTAR.** No es una estrategia validable en este repo: las
opciones binarias tienen pago fijo y contraparte, y el tamaño de la stake es
parte del problema, no un detalle. El vídeo lo dice al final: puede ir al revés.

## Qué se puede probar y qué no

| Idea | ¿Se puede probar aquí? | Qué haría falta |
|---|---|---|
| Arbitraje/MEV on-chain de los cuatro vídeos | **No** | Datos de mempool, RPC privado, modelo de gas, contrato auditado y revisión legal. Fuera del alcance del motor. |
| Breakout 20/10 de Minara | **Sí, como research** | Datos diarios, costes, corte OOS, 100+ operaciones y ciclo de selección con PBO/DSR. No usar el backtest del marketplace como evidencia. |
| Opciones binarias | **No** | No hay bróker ni payoff modelado; el riesgo de ruina y la contraparte no son compatibles con paper trading honesto. |
| “La IA lo hace todo” | **No** | La IA no es un mecanismo; sin regla explícita no hay nada que medir. |

## Ficha rápida antes de probar

Copiar esta ficha y rellenarla; si falta una respuesta, no se abre el
laboratorio.

```text
Estrategia:
Vídeo/fuente:
1. Mecanismo y quién paga:
2. Por qué sigue existiendo / capacidad:
3. Dataset, periodo, operaciones, OOS, benchmark:
4. Código/datos/logs reproducibles:
5. Variantes probadas, PBO, DSR:
6. Costes, liquidez, tamaño, drawdown:
7. Peor caso, custodia, regulación, incentivos:
Veredicto: DESCARTAR / OBSERVAR / RESEARCH / PAPER
```

## Anexo: las puertas del repo

Una hipótesis que pase el checklist no está aprobada: tiene que pasar las mismas
puertas que cualquier otra configuración.

| Criterio | Umbral |
|---|---|
| PF fuera de muestra | > 1 |
| Operaciones fuera de muestra | ≥ 100 |
| Coste ponderado por operación | < 0,25 R |
| PF con coste duplicado | > 1 |
| PBO del ciclo de selección | ≤ 0,2 |
| DSR del ciclo de selección | ≥ 0,95 |

Además, el protocolo de desarrollo exige muestra mínima, drawdown, significancia
y concentración (`G4`, `G5`, `G6`, `G8`, `G11`). Si una idea no puede medir estas
puertas, no se prueba: se queda en la lista de “interesante”, que no es una
categoría operativa.

Referencias: `docs/PROTOCOLO_BACKTEST.md` y `docs/MEDICIONES.md`.
