# Archivo H10 — carry cross-sectional en el tramo largo

**Veredicto:** archivada el 2026-11-27, el mismo día del cribado y **sin
backtest**. La dispersión mediana de funding fue **80,51 pb por posición y
episodio** frente a los **120 pb** que exige la regla 10. No se ejecutó el
simulador, no hay P&L que discutir y el holdout no se abrió.

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
la cartera, quintil superior menos quintil inferior, sólo funding y sin precios.

| Métrica | Valor | Umbral |
|---|---:|---:|
| Ventanas medidas | 187 | — |
| **Mediana** | **80,51 pb** | ≥ 120 pb |
| Media | 149,30 pb | — |
| p25 | 21,01 pb | — |
| p75 | 187,61 pb | — |
| Ventanas ≥ 120 pb | 39,6 % | — |
| Elegibles (mediana) | 183 | ≥ 20 |

| Año | Ventanas | Mediana | ≥ 120 pb |
|---|---:|---:|---:|
| 2023 | 39 | 32,11 pb | 20,5 % |
| 2024 | 53 | 29,43 pb | 15,1 % |
| 2025 | 52 | 114,82 pb | 48,1 % |
| 2026 | 43 | 309,42 pb | 76,7 % |

## Lectura

- **Falla la mediana y pasa la media.** Es exactamente el caso para el que se
  eligió la mediana: unas pocas semanas de 2026 (mediana de 309 pb) sostienen una
  media de 149 mientras la mitad de las ventanas no llega a 81. Con la media,
  H10 habría parecido viable y habría entrado a medirse con 60 pb de déficit.
- **La prima es un fenómeno de 2025-2026, no una constante.** 32 pb en 2023, 29
  en 2024, 115 en 2025 y 309 en 2026. El criterio declarado es la ventana
  completa; quedarse con 2025-2026 ahora sería elegir la muestra después de ver
  el resultado, que es justo lo que la regla prohíbe.
- **El déficit es de un tercio.** Con 80,5 pb la cartera no cubre 0,1 R + 2 ×
  coste por posición; necesitaba 120. Ni el funding ni el filtro de liquidez
  estaban mal: la magnitud no llega.
- **No hay P&L que interpretar.** El cribado usa sólo funding y elegibilidad
  sobre el panel congelado; no hay precio relativo, coste ni retorno. El resultado
  no depende de un modelo de ejecución.
- **El panel es el mejor que ha tenido el laboratorio.** 887 símbolos con
  deslistados, 1400 días, checksums verificados y liquidez punto en tiempo. Que
  aun así no llegue hace el fallo más informativo que el de H5, no menos.

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
- Cribado: `scripts/screen_h10_dispersion.py`.
- Datos: `data/h10/funding_daily.csv`, `perp_daily.csv`, `freeze.json` y
  `screen.json`. Los CSV no se trackean; `freeze.json` sí, por los hashes.
