# Informe de cierre de la puerta de investigación (2027-02-26)

**Adelantado al 2026-11-27.** La puerta sigue formalmente abierta hasta el
2027-02-26, pero no queda familia que medir en el espacio permitido: H10 era la
última y se archivó sin backtest. Este documento es el entregable de esa puerta,
escrito antes de la fecha para que la decisión no se tome con prisa.

**Regla aplicada:** la 3 del plan —sin backtest que pase todas las puertas al
2027-02-26, se detiene la búsqueda de precio/funding, se escribe este informe y
**no se pone capital real**—.

---

## 1. El resultado en una línea

Diez familias, **53 variantes medidas**, ninguna supera las diez puertas duras en
OOS. `live_enabled=false`, cero capital desplegado, cero operaciones reales. El
laboratorio encontró un casi-éxito (H5 raw), tres familias que pierden por
coste o por magnitud, y una que sólo paga en el último año y medio de siete de
muestra.

## 2. Las diez familias

| # | Familia | Hipótesis | Veredicto | Cifra que lo decide |
|---|---|---|---|---|
| H1 | Donchian 1 h | Ruptura de 20/55 velas en 20 majors | **Falla** | PF 0,7529 · esperanza −0,0436 R · P&L −545 USD |
| H2 | Carry BTC | Funding de BTC como renta | **Falla** | 4 episodios · +2,35 % anual · IC80 1,85-6,75 % (no es muestra) |
| H3 | Momentum cross-sectional | Ganadores de 7 d siguen ganando | **Falla** | PF 0,7046 · esperanza −0,0447 R · P&L −30,9 % |
| H4 | Pares spot contra BTC | Cointegración de 20 alts con BTC | **Falla** | PF 0,9235 · esperanza −0,0044 R · P&L −2,75 % |
| H5 | Carry cross-sectional de funding | Largo del quintil inferior de funding, 20 majors | **Falla** | candidata PF 1,1114 · 0,0301 R (puerta 0,05) · top-5 −1.864; raw PF 1,1849 pero **DSR 0,54** |
| H6 | TSMOM long-only | Momentum de 60 d en 20 perpetuos | **Falla** | −40,8 % OOS · PF 0,8766 · peor DD que BTC · top-5 −20.400 |
| H7 | Flujo de taker | Order flow agresivo a 3 días | **Falla** | −27,3 % OOS · PF 0,9355 · top-5 −11.152; ninguna de las 5 variantes pasa |
| H8 | Spread de funding entre venues | Binance contra Hyperliquid | **Falla** | +0,32 % · PF 10,46 · 0,0094 R · **17 episodios / 34 ops**; ninguna variante llega a 100 ops |
| H9 | Basis spot-perp | Spot contra perp en 20 alts | **Falla** | −0,21 % · PF 0,1356 · −0,0047 R · 22 episodios; las 5 variantes pierden |
| H10 | Carry en el tramo largo | Extensión de H5 a 30-60 nombres con deslistados | **Falla el cribado, sin backtest** | **80,51 pb** de dispersión mediana frente a los **240 pb** de su geometría (k = 8) |

Antes de H1, la rejilla canónica de SMA 15 m (5 variantes) quedó en PF 0,9763 y
0,0252 R con PBO 0,4087 y DSR 0,0912: el punto de partida ya avisaba de que el
espacio estaba agotado.

**Cómo fallan, agrupadas:**

- **Por magnitud** (H5, H8, H9): la señal existe pero el edge por operación es
  demasiado pequeño frente a la puerta o frente al coste.
- **Por concentración** (H5 raw, H6, H7): el resultado depende de cuatro o cinco
  operaciones; el top-5 se come el P&L en cada año.
- **Por muestra** (H2, H8): cuatro o diecisiete episodios no sostienen nada.
- **Por coste** (H1, H3, H4): el bruto no cubre la fricción de rotar 20 nombres.

Ninguna falló por un bug de implementación: el motor del carry se validó contra
`server/funding_xs.py` y las cifras publicadas se reprodujeron de forma
independiente.

## 3. Las dos convenciones que corrigen la medida

Estas dos reglas no cambian ningún veredicto, pero cambian lo que se mide. Se
aplican a cualquier familia futura.

### 3.1 Esperanza en pb del nocional, no en R por operación

La puerta antigua pedía `esperanza > 0,05 R` por operación con R = 250 USD fijo.
En pb del nocional eso es `125.000 / nocional`: 40 pb con posiciones de 3.125 USD,
90 pb con 1.389 y 450 pb con 278. La barra medía la amplitud de la cartera, no el
edge: con 9 posiciones por lado exigía un 0,9 % semanal por nombre cuando el
diferencial entero del quintil son 44-98 pb.

**La convención:**

```
esperanza_bp = neto / (operaciones × nocional) × 10.000  ≥  40 pb
```

40 pb es el 0,05 R antiguo sobre la posición de referencia de 3.125 USD: la
puerta conserva su contenido y deja de moverse con `k`. **R = 250 USD se queda
para dimensionar y para la regla 10**; las puertas operativas (paper, micro-live,
live) siguen en R, porque allí R es el riesgo asumido, no una unidad de medida.

Comprobado sobre las seis familias con geometría publicada: **0 de 6 cambian de
veredicto** (`scripts/expectancy_convention.py`).

### 3.2 Funding en cash diario, nunca por evento

El funding se mide como **suma de las tasas del día**, que es lo que la posición
paga. Multiplicar por `8/intervalo` —la convención de H5— duplica el funding de
un símbolo con intervalo de 4 h (multiplica cada evento por 2 cuando además hay
el doble de eventos) y lo sextuplica con 1 h.

En 2026 el 70 % de los símbolos cotiza en intervalos cortos. La dispersión
transversal en cash es **30,25 pb/día**; con la convención de 8 h sale **189,49**,
6,3 veces más, y casi todo el exceso es aritmética. El grupo corto no tiene más
prima media (0,3 % de la varianza entre grupos) pero concentra el 96,8 % de la
varianza: **es un marcador de estrés, no un multiplicador**.

El cribado de H10 ya medía cash; el panel de H5 es 99,9 % a 8 h y sus 856,80 USD
de funding son correctos.

## 4. Lo que el método también corrigió

- **El modelo de coste `a + b·sqrt(S/ADV)` se rechazó por sus propios datos**
  (R² 0,187, Spearman 0,231) y se aplicó el fallback pre-registrado: medianas
  empíricas. Coste medido de 1,33 pb (C5, 3.125 USD) a 31,25 pb (C1).
- **La señal de funding predice pero no discrimina.** IC1 de +0,1023 (U20),
  +0,1245 (ANCHO) y +0,1350 (FILTRADO), con F1-F4 en verde en los tres paneles.
  Entra como **diagnóstico obligatorio**, no como puerta: predecir el signo del
  funding no es ganar dinero con él.
- **La regla 10 pasó a derivarse de la geometría**: `B ≥ 0,1 R + 2C` por
  posición, que en pb es `30 × k`. Con k = 37 la barra son 1.110 pb y comparar
  contra 120 es un error de unidades, no un cribado.

## 5. El hallazgo de régimen de H10

Al ampliar el panel a 2020-2026 con el mismo descargador y las mismas reglas
(899 símbolos, 642.189 velas, 0 checksums fallidos), el cribado da una mediana de
**44,66 pb** en 311 ventanas:

| Año | Mediana | Ventanas | Sobre la barra |
|---|---:|---:|---:|
| 2020 (desde abril) | 29,28 pb | 7 | 0,0 % |
| 2021 | 40,81 pb | 52 | 1,9 % |
| 2022 | 29,21 pb | 52 | 1,9 % |
| 2023 | 20,11 pb | 52 | 5,8 % |
| 2024 | 29,43 pb | 53 | 1,9 % |
| 2025 | 114,82 pb | 52 | 19,2 % |
| 2026 (hasta octubre) | **309,42 pb** | 43 | **55,8 %** |

**Sólo 2026 cruza los 240 pb.** La ventana con la que se archivó H10 (2023-2026,
80,51 pb) era más generosa que el histórico, no más dura. El carry no es una
ventaja estable que estuviera ahí y no se viera: es una prima que aparece cuando
el mercado paga por estar corto de alts, y sólo el último año y medio de siete la
cruza.

Esto **refuerza el archivo** y a la vez dice lo que hay que decir: la familia no
falló por poco en un mercado representativo, falló en un mercado que ya la
favorecía. Un carry que sólo paga en el 55,8 % de las ventanas de un año
excepcional no es desplegable con la confianza de que seguirá.

## 6. Decisión

**No se despliega nada.** `live_enabled=false`, cero capital, cero operaciones
reales. La puerta del 2027-02-26 se resuelve con este informe y no con otra
medida.

Lo que **sí** queda:

- La infraestructura de paper, el adaptador, el kill switch y las puertas
  operativas, listos y probados. No se tiran.
- El método: pre-registro, hash, congelación, DSR sobre 53 ensayos, coste medido,
  convenciones de esperanza y funding, cribado antes de simular.
- El panel 2020-2026 y la caché completa, para que una familia futura no vuelva a
  pagar la descarga.
- Un registro de diez familias que dicen **dónde no está el edge**, que es el
  activo más útil que produce un laboratorio que no gana.

Lo que **no** se hace: reabrir H5 con la barra más baja, probar otro `k` en H10,
quedarse con 2026, abrir el holdout para mirar, o poner dinero para «ver si
funciona». Cada una de esas es la regla 1 disfrazada.

## 7. Qué haría falta para reabrir la búsqueda

Reabrir no es reintentar. Hacen falta las cuatro cosas, en este orden:

1. **Un mecanismo, no una correlación.** La familia tiene que explicar **por qué**
   alguien paga esa prima y por qué no desaparece al competir. H10 mostró una
   prima que aparece en tensión; el mecanismo sería un precio por riesgo de cola
   al que se le puede poner cobertura, no un número que se repite.
2. **Una muestra que no sea el régimen que la favorece.** Con H10 eso significa
   datos posteriores al holdout (desde 2027-06) o una regla de régimen
   pre-registrada **antes** de ver el año que la cumple. Usar 2026 porque pasa es
   exactamente el sesgo que este laboratorio existe para no cometer.
3. **Una solución a la concentración.** El top-5 hunde a H5 raw y a H10 k = 4 en
   cada año. Sin un límite de exposición por nombre que no sea un ajuste
   posterior, cualquier PF alto es cuatro operaciones con suerte.
4. **Pasar las diez puertas con el denominador declarado en 53 ensayos**, y con
   el holdout abierto una sola vez, con la familia ya congelada.

Si en la revisión de diseño no aparece nada que cumpla 1-3, la búsqueda **no se
reabre**: el laboratorio queda como infraestructura y archivo, y este informe
sigue siendo su conclusión. Eso también es un resultado válido: diez familias
descartadas con números es más de lo que tiene la mayoría.

## 8. Reproducibilidad

| Qué | Dónde |
|---|---|
| Registro de ensayos (53) | `docs/TRIALS.md` |
| Plan, puertas y convenciones | `docs/PLAN-2027.md` |
| Archivos por familia | `docs/ARCHIVO-H1.md` … `ARCHIVO-H10.md` |
| Cribado de H10 y ventana | `scripts/screen_h10_dispersion.py`, `data/h10ext/screen_2020_2026.json` |
| Esperanza por convención | `scripts/expectancy_convention.py` |
| Coste medido | `docs/MEDICION-COSTE.md`, `docs/PRE-REGISTRO-COSTE.md` |
| Señal | `docs/MEDICION-SENAL.md` |
| Intervalos y cash | `docs/MEDICION-INTERVALOS.md` |

Todo lo publicado se midió sobre datos con hash y se commiteó con su pre-registro
antes de ver el resultado. Ningún número de este informe se ajustó después.
