# Archivo H10 — carry cross-sectional en el tramo largo

**Veredicto:** archivada el 2026-11-27, el mismo día del cribado y **sin
backtest**. La dispersión mediana de funding fue **80,51 pb por posición y
episodio** frente a los **240 pb** que la regla 10 exige con la geometría
empleada; 120 pb es la barra de 4 posiciones por lado, no la del cribado. No se
ejecutó el simulador, no hay P&L que discutir y el holdout no se abrió.

## Qué se construyó

Panel congelado de perpetuos USD-M fuera de los 20 mayores de H5, con los
deslistados dentro y filtro de liquidez punto en tiempo.

| Dato | Valor |
|---|---:|
| Símbolos en el panel | 887 |
| De ellos con velas diarias | 886 |
| Ventana | 2023-01-01 / 2026-10-31 |
| Filas de funding | 512.801 |
| Filas de velas | 552.628 |
| ZIP descargados y verificados | 35.790 |
| Checksums que no cuadran | 0 |
| Meses sin fichero (no listado o ya retirado) | 46.918 |

- **Universo:** 904 perpetuos con liquidación en USDT fuera de los 20 mayores;
  899 tras descartar cinco nombres fuera de `[A-Z0-9]`; 887 con datos en la
  ventana.
- **Deslistados dentro:** ICXUSDT hasta 2026-08 y SXPUSDT hasta 2025-12, entre
  otros. El sesgo de supervivencia que H5 declaró como límite queda corregido
  aquí, y no fue la causa del fallo.
- **Liquidez punto en tiempo:** mediana de 30 días del `quote_volume`, con datos
  hasta t-1 y umbral de 5 M USD. Se usa el volumen que el símbolo tenía entonces.
- **Hash:** `data/h10/freeze.json` con SHA-256 del funding
  (`1b18cb96…`) y de las velas (`ae0db754…`), cobertura por símbolo y estadísticas
  de descarga. El panel se cerró antes de mirar ninguna dispersión.
- **Fuente:** Binance Vision, `futures/um/monthly/fundingRate` y
  `futures/um/monthly/klines/1d`, cada ZIP contra su `.CHECKSUM` mensual.

## El cribado (regla 10)

Ventanas no solapadas de 7 días desde cada lunes, con la misma elegibilidad que
la cartera, los 8 nombres de funding más alto menos los 8 más bajo (ver el límite
del tope más abajo), sólo funding y sin precios.

| Métrica | Valor | Barra |
|---|---:|---:|
| Ventanas medidas | 187 | — |
| **Mediana** | **80,51 pb** | ≥ 240 pb (k = 8) |
| Media | 149,30 pb | — |
| p25 | 21,01 pb | — |
| p75 | 187,61 pb | — |
| Margen mediano | −159,49 pb | — |
| Ventanas ≥ su barra | 20,3 % | — |
| Elegibles (mediana) | 183 | ≥ 20 |

| Año | Ventanas | Mediana | ≥ barra | Margen mediano |
|---|---:|---:|---:|---:|
| 2023 | 39 | 32,11 pb | 7,7 % | −207,89 pb |
| 2024 | 53 | 29,43 pb | 1,9 % | −210,57 pb |
| 2025 | 52 | 114,82 pb | 19,2 % | −125,18 pb |
| 2026 | 43 | 309,42 pb | 55,8 % | +69,42 pb |

## Límite del cribado: el tope de 8 posiciones por lado

El cribado topó la cartera en **8 posiciones por lado**. Con 183 elegibles de
mediana, la fórmula del pre-registro (`k = max(2, round(n/5))`) da **37**, y la
tabla de reglas declara **4** posiciones por lado de 3.125 USD. Las tres cifras no
coinciden: el pre-registro es inconsistente y el cribado resolvió a favor del
tope de 8.

Eso mide **la cola extrema** —8 de 183, el 4,3 % superior e inferior— y no el
quintil. La consecuencia es numérica:

| Geometría | Posiciones por lado | Nocional por posición | Mediana capturada | Barra de la regla 10 |
|---|---:|---:|---:|---:|
| Reglas del pre-registro | 4 | 3.125 USD | 82,75 pb | 120 pb |
| **Cribado ejecutado (tope)** | **8** | **1.562,50 USD** | **80,51 pb** | **240 pb** |
| Quintil de la fórmula | 37 | 337,84 USD | 28,86 pb | 1.110 pb |

Dos efectos, y **los dos favorecen a H10**:

1. **La cola extrema paga más que el quintil.** Pasar de 8 a 37 nombres baja la
   mediana de 80,51 a 28,86 pb: el tope infla la dispersión medida unas 2,8
   veces. Es decir, el cribado no fue más exigente que el quintil, fue más
   generoso.
2. **La barra en pb depende del tamaño de posición.** Los 37,50 USD por posición
   son 120 pb sobre 3.125, 240 sobre 1.562,50 y 1.110 sobre 337,84. El cribado
   comparó la dispersión más ancha contra la barra más baja.

Corregido en cualquier dirección el hueco se agranda: con el quintil puro la
mediana es 28,86 pb frente a 1.110, y con 8 posiciones 80,51 frente a 240. **El
fallo no depende del tope**; el tope sólo hacía que costara más verlo. Si el
tope se hubiera aplicado con su propia barra (240 pb), H10 habría fallado por el
triple.

**Defecto del pre-registro, para la próxima familia.** `k` no puede depender de
`n` y convivir con un nocional fijo por posición: si `k` crece, el nocional baja
y la barra en pb sube. O se fija `k` y el nocional, o el umbral se declara en
dólares por posición y se recalcula por geometría. Aquí quedó del lado generoso,
que es el lado equivocado para fallar.

## Lectura

- **Falla la mediana y pasa la media.** Es exactamente el caso para el que se
  eligió la mediana: unas pocas semanas de 2026 (mediana de 309 pb) sostienen una
  media de 149 mientras la mitad de las ventanas no llega a 81. Con la media,
  H10 habría parecido viable y habría entrado a medirse con 60 pb de déficit.
- **La prima es un fenómeno de 2025-2026, no una constante.** 32 pb en 2023, 29
  en 2024, 115 en 2025 y 309 en 2026. El criterio declarado es la ventana
  completa; quedarse con 2025-2026 ahora sería elegir la muestra después de ver
  el resultado, que es justo lo que la regla prohíbe.
- **El déficit es de dos tercios.** Con 80,5 pb la cartera no cubre 0,1 R + 2 ×
  coste por posición: con 8 por lado necesitaba 240 pb y se quedó en un tercio de
  esa cifra, un margen mediano de −159 pb. Incluso 2026, el único año con
  dispersión alta, sólo supera la barra en el 55,8 % de sus ventanas y su margen
  mediano (+69 pb) es el único positivo de la muestra. Ni el funding ni el filtro
  de liquidez estaban mal: la magnitud no llega.
- **No hay P&L que interpretar.** El cribado usa sólo funding y elegibilidad
  sobre el panel congelado; no hay precio relativo, coste ni retorno. El resultado
  no depende de un modelo de ejecución.
- **El panel es el mejor que ha tenido el laboratorio.** 887 símbolos con
  deslistados, 1400 días, checksums verificados y liquidez punto en tiempo. Que
  aun así no llegue hace el fallo más informativo que el de H5, no menos.

**Alcance tras la nulidad de H5 (2026-11-27).** Este cribado mide sólo la pata de
funding. La permutación del motor de H5 mostró que su edge realizado era precio y
que su pata de carry pierde sola, así que este fallo descarta el carry en el
tramo largo, **no** la apuesta de precio de H5 trasladada a 60 nombres, que no se
midió. No es motivo para reabrir: la ventana está gastada y no hay pre-registro.

## Dependencia de régimen (panel extendido 2020-2026)

Nota añadida el 2026-11-27, después de archivar, al ampliar el panel con el
mismo descargador y las mismas reglas (`docs/PRE-REGISTRO-VENTANA-H10.md` y
`data/h10ext/screen_2020_2026.json`). **No cambia el veredicto**: H10 sigue
archivada.

Sobre 2020-01/2026-10 la mediana del cribado es **44,66 pb** en 311 ventanas,
por debajo de los 80,51 pb con los que se archivó. El año a año:

| Año | Mediana | Ventanas | Sobre la barra |
|---|---:|---:|---:|
| 2020 (desde abril) | 29,28 pb | 7 | 0,0 % |
| 2021 | 40,81 pb | 52 | 1,9 % |
| 2022 | 29,21 pb | 52 | 1,9 % |
| 2023 | 20,11 pb | 52 | 5,8 % |
| 2024 | 29,43 pb | 53 | 1,9 % |
| 2025 | 114,82 pb | 52 | 19,2 % |
| 2026 (hasta octubre) | **309,42 pb** | 43 | **55,8 %** |

**Sólo 2026 cruza los 240 pb de su geometría.** Durante los cinco años
anteriores la prima por ventana se queda entre 20 y 41 pb, entre seis y doce
veces por debajo de la barra; 2025 la roza con 115 pb.

La lectura es incómoda y conviene dejarla escrita: el archivo se sostiene por la
ventana completa, no porque la prima fuera estable y algo menor que la barra.
2023-2026, el tramo con el que se midió, era **más generoso que el histórico**
(80,51 frente a 44,66 pb), y el único periodo que paga es el último año y medio
sobre siete de muestra. Eso es dependencia de régimen: un carry que aparece
cuando el mercado paga por estar corto de alts, no una ventaja persistente que
se pueda desplegar con la confianza de que seguirá ahí.

**El veredicto no se toca**, y no por comodidad:

- La puerta se congeló sobre la ventana completa y la regla 1 prohíbe reabrir una
  familia archivada con los mismos datos. Que 2026 aislado pase no es un pase:
  elegir el subperiodo que cruza la barra es exactamente el sesgo que el
  pre-registro existe para impedir.
- No se ajusta ningún umbral ni se cambia la geometría. Los 240 pb siguen siendo
  la barra con la que se archivó.
- `TRIALS` sigue en **53**: es una lectura distinta de una medida ya archivada,
  no una variante nueva.

Lo que sí cambia es lo que hay que decir en el informe de cierre: la familia no
falló por poco en un mercado representativo, falló en un mercado que ya la
favorecía.

## Qué no se hizo

- No se ejecutó ningún simulador: no hay operaciones, PF, esperanza ni drawdown
  de H10.
- **Las cinco variantes no se midieron.** `TRIALS.md` sigue en **50**, no en 55:
  el pre-registro decía 55 asumiendo que se mediría, y la regla del registro es
  que sólo cuentan las variantes que llegaron a medirse. El cribado no produce
  estadístico de estrategia, así que el denominador del DSR no cambia.
- No se abrió el holdout 2026-12-01/2027-05-31.
- No se probó el decil, ni otra permanencia, ni un umbral más bajo. El
  pre-registro lo prohibía antes de ver el resultado y se cumple.

## Consecuencia para el plan

H10 se archiva sin backtest por la regla 10. **No se reserva H11**: no queda
familia en el espacio permitido —on-chain es filtro, macro es beta, opciones no
son ejecutables, cascadas viven en minutos y cualquier rejilla nueva de
precio/funding en los majors está prohibida por el post-mortem—. La puerta dura
del 2027-02-26 se resuelve con el informe de cierre, no con otra medida.

## Artefactos

- Pre-registro: `docs/PRE-REGISTRO-H10.md`.
- Revisión de diseño: `docs/REVISION-DISENO-H10.md` (§7.1, regla 10).
- Descarga: `scripts/fetch_h10_data.py`.
- Cribado: `scripts/screen_h10_dispersion.py`. La barra se deriva de la
  geometría (`30 × k` pb), no es una constante, y el JSON publica la geometría,
  la barra aplicada y el margen por ventana.
- Datos: `data/h10/funding_daily.csv`, `perp_daily.csv`, `freeze.json` y
  `screen.json`. Los CSV no se trackean; `freeze.json` sí, por los hashes.
- Sensibilidad del tope: `data/h10/screen_k4.json` y `screen_k37.json`
  (`--max-per-side`).
