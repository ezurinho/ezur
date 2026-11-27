# Diagnóstico de señal de funding

**Respuesta corta:** la señal **sí predice** el funding de la semana siguiente en
los tres universos, y pasa las cuatro puertas pre-registradas. Eso significa que
**no habría parado ni a H5 ni a H10**: las dos tenían señal. El dinero se perdió
en la economía, no en la predicción. Por eso **no entra como puerta** —no
discrimina—, pero sí como diagnóstico obligatorio en cada familia.

**Fecha:** 2026-11-27. **Pre-registro:** `docs/PRE-REGISTRO-SENAL.md`, commiteado
antes de calcular ningún IC.

## 1. Resultado

Rank-IC transversal semanal, ventana 2023-01-01 / 2026-10-31.

| Universo | Semanas | IC 1 sem | IC 2 sem | IC 4 sem | Semanas IC>0 |
|---|---:|---:|---:|---:|---:|
| U20 majors de H5 | 200 | **+0,1023** | +0,1000 | +0,0797 | 64,3 % |
| ANCHO (886 símbolos) | 187 | **+0,1245** | +0,1039 | +0,0755 | 85,5 % |
| FILTRADO (ADV ≥ 5 M) | 187 | **+0,1350** | +0,1159 | +0,0827 | 84,9 % |

| Puerta | Umbral | U20 | ANCHO | FILTRADO |
|---|---:|---|---|---|
| F1 IC1 mediano | ≥ 0,05 | +0,102 ✔ | +0,125 ✔ | +0,135 ✔ |
| F2 semanas positivas | ≥ 60 % | 64,3 % ✔ | 85,5 % ✔ | 84,9 % ✔ |
| F3 IC4 mediano | ≥ 0,03 | +0,080 ✔ | +0,076 ✔ | +0,083 ✔ |
| F4 años con IC1 > 0 | ≥ 3 de 4 | 4/4 ✔ | 4/4 ✔ | 4/4 ✔ |

**El decaimiento es lento:** a cuatro semanas todavía queda el 60-80 % del IC de
la primera. Eso es consistente con lo que dice la autocorrelación: el nivel de
funding tiene 0,78 de autocorrelación a un retardo y la dispersión 0,45-0,66.

| Universo | Dispersión mediana | Autocorr. dispersión (1-4) | Autocorr. nivel (1-4) |
|---|---:|---|---|
| U20 | 1,7 pb | 0,45 / 0,19 / 0,05 / 0,04 | 0,78 / 0,64 / 0,51 / 0,44 |
| ANCHO | 13,4 pb | 0,66 / 0,55 / 0,52 / 0,45 | 0,76 / 0,60 / 0,45 / 0,35 |
| FILTRADO | 12,9 pb | 0,63 / 0,58 / 0,55 / 0,48 | 0,78 / 0,64 / 0,51 / 0,42 |

## 2. Estabilidad por régimen

**Por año (IC1 mediano):**

| Universo | 2023 | 2024 | 2025 | 2026 |
|---|---:|---:|---:|---:|
| U20 | +0,066 | +0,030 | +0,135 | +0,171 |
| ANCHO | +0,154 | +0,126 | +0,140 | +0,092 |
| FILTRADO | +0,138 | +0,101 | +0,154 | +0,124 |

**Por tercil de dispersión:**

| Universo | Baja | Media | Alta |
|---|---:|---:|---:|
| U20 | **+0,018** | +0,099 | +0,197 |
| ANCHO | +0,145 | +0,111 | +0,123 |
| FILTRADO | +0,135 | +0,130 | +0,129 |

En los majors la señal **sólo funciona cuando la dispersión es alta** (+0,197
frente a +0,018 en el tercil bajo). En el panel ancho da igual el régimen: hay
siempre suficientes nombres con funding extremo.

## 3. Qué habría dicho de H5 y de H10

**De H5: que la señal valía.** IC1 +0,102 sobre sus 20 majors, cuatro años
positivos, decaimiento suave. El filtro la habría dejado pasar. Su archivo dice
que el P&L fue 89 % precio y 11 % funding: la señal ordenaba el funding, pero lo
que se cobraba era otra cosa —momentum relativo—, y por eso falló en top-5 y DSR.
**El diagnóstico habría acertado en el diagnóstico y no habría evitado el gasto.**

**De H10: lo mismo, con más claridad.** IC1 +0,135 en su universo filtrado, el más
alto de los tres. La señal predecía el funding que la cartera necesitaba cobrar y
el cribado de la regla 10 la tumbó por magnitud (80,51 pb frente a 240). Es la
confirmación directa de lo que ya decía `ARCHIVO-H10.md`: **no falló la señal,
falló la economía**.

## 4. Por qué un IC alto no es evidencia de edge

El IC mide ordenación, no cobro. Con autocorrelación de nivel 0,78, buena parte de
ese +0,13 es **persistencia**: los mismos símbolos están siempre en el mismo
extremo, y la cartera no puede volver a cobrar esa diferencia cada semana —al
rebalancear mantiene los mismos nombres—. Por eso conviven un IC de 0,135 con una
esperanza de 0,0066 R: la señal acierta, pero la prima por acierto es pequeña, y
el coste y la concentración se la comen.

Esta es la lectura que faltaba en el laboratorio y es la más útil del ejercicio:
**la pregunta «¿predice?» se responde que sí; la pregunta que decide es «¿cuánto
paga por acierto?»**, y esa sólo la responde el cribado económico.

## 5. ¿Entra en el protocolo?

**Como puerta, no.** Las cuatro puertas están puestas para que un IC bajo frene una
familia, y resultó que ninguna familia de funding baja de 0,10. Una puerta que
todo lo pasa no es una puerta: es un sello. Añadirla daría falsa seguridad («pasó
la puerta -1») sin haber filtrado nada. La condición del pre-registro era «si el
diagnóstico se confirma útil»; se confirma útil **como diagnóstico**, no como
filtro.

**Como diagnóstico obligatorio, sí**, y así queda en `docs/PLAN-2027.md`: cada
familia publica su rank-IC1, IC4, semanas positivas y estabilidad por régimen
**antes** de cualquier simulador. Un IC nulo o negativo sí es una señal de parada
—indica que la hipótesis no ordena lo que dice ordenar—, pero un IC positivo no
autoriza nada.

**Lo que propongo para la v2, pre-registrada aparte y no medida aquí:** IC sobre
la **innovación** (funding futuro menos el nivel actual del símbolo) o IC después
de quitar el efecto fijo por símbolo. Eso separa persistencia de predicción y
debería discriminar entre familias donde ésta no discrimina. No lo he calculado
porque el pre-registro fijaba las métricas y cambiar de métrica después de ver el
resultado es exactamente lo que el laboratorio no hace.

## 6. Límites

- U20 se mide sobre el panel de H5 (2020-2026) recortado a 2023-2026; el
  desarrollo 2020-2024 de H5 no se compara aquí.
- El panel de H10 excluye a los 20 majors por construcción, así que los dos
  universos no son anidados.
- Horizonte 2 y 4 con ventanas solapadas: la mediana y la proporción de semanas
  positivas son el criterio, no el t estadístico.
- Sin costes ni precios: mide predicción de funding, no rentabilidad.

## 7. Contabilidad y artefactos

No añade ensayos: `TRIALS.md` sigue en **53**. Es un diagnóstico, no una variante.

- Pre-registro: `docs/PRE-REGISTRO-SENAL.md`.
- Medición: `scripts/signal_diagnostics.py` → `data/signal/diagnostics.json`.
