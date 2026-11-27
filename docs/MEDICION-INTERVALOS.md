# El intervalo de funding: cuánto explica la dispersión y cuánto es artefacto

Medida sobre el panel extendido 2020-2026 (`data/h10ext/`), con el campo
`funding_interval_hours` que el panel congelado de H10 descartaba. Responde a una
pregunta concreta: de la dispersión de funding de 2026, ¿cuánta viene de que
muchos símbolos hayan pasado a intervalos de 4 h y cuánta de prima real?

## Qué se hizo

`scripts/extend_panel_2020.py` reutiliza el descargador de H10 para bajar sólo el
funding de 2020-01 a 2022-12 y reconstruye el panel completo leyendo los meses
2023-2026 de la caché existente. Escribe en `data/h10ext/`, **sin tocar el panel
congelado de H10 ni sus hashes**.

| | |
|---|---:|
| Símbolos | 899 |
| Filas diarias | 601.450 |
| Eventos de funding | 2.702.024 |
| Checksums fallidos | 0 |
| Errores de descarga | 0 |
| `funding_sha256` | `dac6ad41…c0afbb4` |

Eventos por año: 28.849 (2020), 102.454 (2021), 134.503 (2022), 205.558 (2023),
418.029 (2024), 860.486 (2025), 956.145 (2026). La explosión es real: más
símbolos y más eventos por símbolo.

## Las tres medidas

- **`rate` (cash)**: suma de las tasas del día. Es el coste real en fracción del
  nocional —cada evento cobra la suya, sin importar cuántos haya— y es la medida
  que usa el panel de H10.
- **`rate8h`**: suma de `tasa × 8 / intervalo`. Es la convención de H5. Con
  intervalo de 4 h multiplica cada evento por 2 **y además** hay el doble de
  eventos, así que duplica el funding; con 1 h lo sextuplica.
- **`interval_h`**: mediana de los intervalos del día.

## Dispersión por año (pb del nocional por día)

Desviación típica transversal de la media semanal por símbolo, semanas con al
menos 3 días de datos.

| Año | Símbolos | % con intervalo < 8 h | Cash medio | Disp. cash | Disp. 8h-eq | Disp. solo 8 h | Disp. grupo corto |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 62 | 0,0 % | +3,75 | 16,41 | 16,41 | — | — |
| 2021 | 116 | 0,0 % | +9,52 | 18,94 | 23,34 | — | — |
| 2022 | 142 | 0,0 % | −1,41 | 12,42 | 28,79 | — | — |
| 2023 | 233 | 5,2 % | +1,03 | 17,76 | 29,31 | 13,31 | 53,35 |
| 2024 | 362 | 37,8 % | +3,29 | 12,29 | 22,26 | 8,02 | 17,13 |
| 2025 | 591 | 67,5 % | −2,87 | 32,60 | 202,99 | 9,06 | 39,10 |
| 2026 | 806 | 70,0 % | −2,26 | 30,25 | 189,49 | 9,49 | 35,57 |

## La respuesta

**1. Como nivel, el intervalo no explica nada.** La varianza entre los dos grupos
(media del grupo corto frente a media del grupo de 8 h) es el **0,3 %** del total
en 2026: −3,28 pb/día en el grupo corto frente a +0,10 pb/día en el de 8 h, dos
medias que no separan nada cuando la desviación transversal es de 30 pb. El
intervalo no crea prima.

**2. Como localización, explica casi todo.** El **96,8 % de la varianza
transversal de 2026 vive en el grupo de intervalo corto**, que es el 70 % de los
símbolos: 35,57 pb/día de desviación frente a 9,49 pb/día dentro del grupo de
8 h, un factor 3,75. En 2025 era el 97,1 %.

**3. La subida de la dispersión es toda de ese grupo.** Entre 2023-2025 y 2026 la
dispersión dentro del grupo de 8 h no se movió (10,54 → 9,49 pb/día), mientras la
total pasó de 25,31 a 30,25. Lo que cambió fue cuántos símbolos están en 4 h y
cuánto se mueven allí.

**4. Pero no es un artefacto de la aritmética.** El cash es lo que la posición
paga: si un símbolo en 4 h tuviera la misma tasa por 8 h equivalente que uno en
8 h, su cash diario sería idéntico. Lo que muestran los datos es lo contrario de
un artefacto: cuando el exchange acorta el intervalo, lo hace **porque** ese
símbolo está en tensión, y allí la prima se mueve de verdad. La prueba dentro del
mismo símbolo: los 37 símbolos que alternan intervalo en 2026 pasan de −0,67
pb/día en sus semanas de 8 h a −12,79 pb/día en sus semanas cortas. El intervalo
es un marcador de estrés, no un multiplicador de mentira.

**5. El artefacto está en la convención de 8 h, y es enorme.** Medir la misma
dispersión de 2026 con `rate8h` da **189,49 pb/día frente a 30,25 reales: 6,3
veces**. Casi todo ese exceso es multiplicar por 8/intervalo símbolos que ya
tienen el doble o el cuádruple de eventos. Si el laboratorio hubiera mirado la
dispersión con la convención de H5 habría visto una oportunidad seis veces mayor
que la que existe.

## Qué implica para el laboratorio

- **La medida correcta es el cash diario** (suma de tasas). Es la que usa el
  panel de H10 y la que hay que usar en todas las familias de carry. Queda
  anotada en el plan como convención.
- **El cribado de H10 no se revisa**: sus 80,51 pb de dispersión mediana ya
  estaban en cash. El veredicto (falla frente a 240) se mantiene.
- **H5 usó la convención de 8 h, pero su panel no la sufre**: de 141.980 eventos,
  141.879 son a 8 h, 99 a 2 h y 2 a 4 h. Los 856,80 USD de funding son cash en la
  práctica. El riesgo de la convención es latente y sólo muerde en universos
  anchos como el de H10, que ya medía cash. Corregí aquí una afirmación previa
  mía que daba por inflado ese componente: no lo está.
- **Para familias futuras**: si una señal se define sobre el nivel de funding,
  se define sobre cash anualizado, no sobre la tasa por evento. La tasa por
  evento sólo sirve para comparar símbolos en el mismo intervalo.

## Límites

- 2020-2022 tiene **sólo funding**, sin klines: sirve para caracterizar la prima
  y la dispersión, no para un backtest que necesite precios. Los klines del
  panel congelado siguen empezando en 2023-01.
- El panel extendido no sustituye al congelado de H10: es otra pieza, con su
  propio hash, y no se usó para re-medir ninguna familia.
- 2020 y 2021 tienen 62 y 116 símbolos: la comparación entre años mezcla tamaño
  de universo con régimen. Las cifras de 2025-2026, con 591 y 806 símbolos, son
  las que sostienen la respuesta.

## Reproducir

```
python scripts/extend_panel_2020.py --workers 32
python scripts/funding_interval_analysis.py
```

Salidas: `data/h10ext/funding_daily.csv`, `data/h10ext/freeze.json` (commiteado)
y `data/h10ext/dispersion.json`.
