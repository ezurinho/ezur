# Pre-registro: ¿el cribado de H10 dependió de la ventana?

**Fecha:** 2026-11-27, escrito **antes** de correr la medida.
**Naturaleza:** diagnóstico de robustez sobre una familia ya archivada. **No es
una familia nueva y no produce veredicto.**

## La pregunta

El cribado de H10 se midió sobre el panel congelado 2023-01/2026-10 y dio una
dispersión mediana de **80,51 pb por posición y episodio** frente a los 240 pb
que su geometría exigía (k = 8). El panel se amplió después a 2020-2022 con el
mismo descargador y las mismas reglas. La pregunta es si esos 80,51 pb describen
el mercado o sólo la ventana: 2023-2026 pudo ser un tramo de prima
excepcionalmente baja, y entonces el archivo diría más del periodo que de la
familia.

## El diseño, fijado ahora

- Se aplica **la misma** función de cribado archivada
  (`scripts/screen_h10_dispersion.py`), sin tocar elegibilidad, señal, `k` ni
  ventana de 7 días. Sólo cambia la ruta del panel.
- Se corre sobre el panel extendido 2020-2026 (`data/h10ext/`, con klines
  2020-2022 ya descargadas para que el filtro de liquidez sea el mismo).
- Se publica la mediana por **año natural** y por **ventana móvil de 12 meses**,
  con el número de episodios y de símbolos de cada tramo.
- **Comprobación del motor:** la corrida restringida a 2023-01/2026-10 tiene que
  reproducir **80,51 pb** exactos. Si no los reproduce, el diagnóstico se detiene
  y se investiga la discrepancia antes de leer nada más.

## La regla, fijada ahora

1. **H10 sigue archivada diga lo que diga este diagnóstico.** La regla 1 del plan
   prohíbe reintentar con los mismos datos y la 8 prohíbe medir sin congelar; el
   veredicto se congeló el 2026-11-27 y no se reabre por un cambio de ventana.
2. **No se ajusta ningún umbral.** Si 2020-2022 diera más dispersión, el 240 pb
   sigue siendo la barra con la que se archivó; la nota dirá que el margen era
   dependiente del régimen, no que H10 pase.
3. **No cuenta como ensayo.** `TRIALS` se queda en 53: no hay hipótesis nueva ni
   variante nueva, sólo una lectura distinta de una medida ya archivada.
4. Si la corrida de control no reproduce 80,51 pb, **no se publica** el resto del
   diagnóstico hasta entender por qué.

## Qué se va a poder decir después

- Si la mediana de 2020-2022 es parecida a la de 2023-2026: el archivo fue una
  propiedad del mercado, no del tramo, y el cierre de la búsqueda gana un dato.
- Si es mucho mayor: el mercado de 2020-2022 pagaba más prima por el mismo
  riesgo de cola, y el archivo de H10 queda marcado como dependiente de régimen
  —sin cambiar de veredicto—, lo que hay que decir en el informe de cierre.
- Si es mucho menor: refuerza el archivo y sugiere que la prima se comprime con
  la madurez del mercado.
