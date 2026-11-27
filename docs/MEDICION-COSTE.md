# Medición del coste real de ejecución

**Veredicto:** el modelo ajustado **no es usable** —falla dos de sus cinco puertas
pre-registradas— y se aplica el *fallback* declarado (medianas empíricas por cubeta
y tamaño). Lo medido sí sirve, y corrige un supuesto que estaba en los diez
veredictos del laboratorio: **el coste declarado era conservador en los majors y
está por debajo de la realidad en el tramo pequeño**.

**Fecha:** 2026-11-27, una sola foto del libro. **Pre-registro:**
`docs/PRE-REGISTRO-COSTE.md`, commiteado antes de medir.

## 1. Puertas

| # | Puerta | Umbral | Resultado | |
|---|---|---:|---:|---|
| G1 | Símbolos con libro válido | ≥ 60 | 125 | pasa |
| G2 | R² del ajuste | ≥ 0,50 | **0,1872** | **falla** |
| G3 | Error absoluto mediano | ≤ 8 pb | 3,29 pb | pasa |
| G4 | Monotonía coste(12.500) > coste(500) | en todas | 5/5 cubetas | pasa |
| G5 | Spearman Corwin-Schultz vs libro | ≥ 0,50 | **0,2312** | **falla** |

El ajuste `a + b·sqrt(S/ADV)` da `a = −2,37` y `b = 673,1`: un intercepto negativo
que predice coste negativo en órdenes pequeñas. La causa es que la dispersión de
spread **entre símbolos de la misma cubeta** domina sobre el efecto del tamaño; el
modelo agregado no la recoge. Por la regla §6 del pre-registro, **el modelo se
descarta y no se usa para nada**, tampoco para capacidad.

## 2. Coste medido (pb por lado), medianas por cubeta

125 símbolos, 25 por cubeta, libros de OKX SWAP con al menos 20 niveles por lado.

| Cubeta | Spread | 500 USD | 1.562 USD | **3.125 USD** | 12.500 USD |
|---|---:|---:|---:|---:|---:|
| C1 < 1 M | 15,41 | 14,10 | 21,23 | **31,25** | 98,97 |
| C2 1-5 M | 6,50 | 8,27 | 12,14 | **17,82** | 47,98 |
| C3 5-20 M | 3,68 | 5,13 | 7,31 | **10,40** | 22,91 |
| C4 20-100 M | 2,00 | 2,37 | 3,51 | **5,23** | 8,64 |
| C5 > 100 M | 1,20 | 0,74 | 0,99 | **1,33** | 2,17 |

**Contra lo que el laboratorio suponía:**

- **H5 declaró 6 pb por lado en majors: la realidad es 1,33-5,23 pb.** Sus números
  estaban por el lado conservador.
- **H8, H9 y H10 declararon 10 pb:** correcto o conservador en nombres con más de
  5 M de ADV (1,33-10,4 pb), pero **2-3 veces corto por debajo de 5 M** (17,8-31,25
  pb). El filtro de liquidez de H10 a 5 M resulta ser, sin haberlo buscado, la
  frontera donde el coste real se sale de lo declarado.
- **En el tramo pequeño el spread solo ya cuesta más que todo el presupuesto:**
  15,4 pb en C1 frente a los 10 pb declarados para un ida y vuelta completo.

## 3. Techo de capacidad (interpolando las medianas medidas)

Mayor tamaño de posición al que el coste medido no supera el declarado:

| Cubeta | ≤ 6 pb/lado | ≤ 10 pb/lado |
|---|---|---|
| C1 < 1 M | < 500 USD | < 500 USD |
| C2 1-5 M | < 500 USD | 500 – 3.125 USD |
| C3 5-20 M | 500 – 3.125 USD | 500 – 3.125 USD |
| C4 20-100 M | 3.125 – 12.500 USD | ≥ 12.500 USD |
| C5 > 100 M | ≥ 12.500 USD | ≥ 12.500 USD |

Lectura: **las posiciones de 3.125 USD del laboratorio están justo en el borde de
capacidad de C4 y por encima del de C3.** Escalar a 25.000 USD por posición exige
C5, y por tanto abandonar el tramo largo. La cartera de 25.000 USD de bruto no es
el problema —lo es el nocional por posición— pero deja de haber margen: a 12.500
USD por posición en C3 el coste se come 23 pb por lado.

## 4. Los dos contrastes que fallaron, y por qué importa

**Corwin-Schultz sobre las barras diarias no sirve aquí.** Da 35-103 pb de spread
—20 a 30 veces el libro real— y su correlación de rango con el libro es 0,23. El
estimador asume un proceso de precio continuo con ruido de microestructura; en
cripto el rango diario está dominado por volatilidad, no por spread. Por la regla
§6, **las cubetas sin libro no se rellenan**: C1 y C2 quedan medidas sólo por los
símbolos que OKX lista (92 de 167 y 164 de 332), lo que sesga esas cubetas hacia
los nombres más grandes de cada tramo. El coste real del extremo del panel es, si
acaso, **peor** que lo reportado.

**El libro de spot de Binance es 2,0× más ancho que el perpetuo de OKX** (5,65 pb
frente a 2,83 en los 7 símbolos comparables). Confirma que usar el perpetuo como
referencia es lo correcto y que el spot no sirve de sustituto.

## 5. Sensibilidad de las familias archivadas

Coste re-expresado sobre los componentes publicados; ni un simulador re-ejecutado.

| Familia | Declarado | Medido | Neto declarado | Neto medido | Esperanza declarada | Esperanza medida |
|---|---:|---|---:|---|---:|---|
| H5 candidata | 6 pb | 1,33-5,23 | +6.029 | +7.196 / +6.221 | 0,0301 R | 0,0360 / 0,0311 R |
| H5 raw | 6 pb | 1,33-5,23 | +8.343 | +9.270 / +8.495 | 0,0525 R | 0,0583 / 0,0534 R |
| H8 spread entre venues | 7 pb | 1,33 | +80 | **+176** | 0,0094 R | **0,0208 R** |
| H9 basis spot-perp | 10 pb | 1,33-5,23 | −52 | **+115 / +40** | −0,0047 R | **+0,0105 / +0,0036 R** |
| H10 quintil (k=9) | 10 pb | 7,26 | +15.594 | +16.007 | 0,0066 R | 0,0068 R |
| H10 k=4 | 10 pb | 5,23-10,40 | +38.870 | +39.914 / +38.782 | 0,1331 R | 0,1367 / 0,1328 R |

**Ningún veredicto cambia.** H5 sigue fallando esperanza y top-5; H8 sigue sin
muestra (34 operaciones frente a 100); H9 sigue sin muestra (44), con esperanza
0,0036-0,0105 R frente a 0,05 y PF 0,1356; H10 sigue fallando el cribado.

**Pero H9 cambia de signo**, y eso merece decirse: con el coste real su neto pasa
de −52 a +40/+115 USD. El coste declarado era la mayor parte de su pérdida, no la
señal. No se desarchiva —la familia falla por muestra, PF y esperanza, y la ventana
está gastada—, pero si alguna vez se revisita el basis, el coste no es el problema.

## 6. Qué se lleva el plan

1. **Los 10 pb por lado valen para símbolos con más de 5 M de ADV y para nada
   más.** Cualquier familia futura que baje de ahí debe usar el coste de su cubeta
   o el techo de capacidad, no el 10 pb genérico.
2. **Regla 10 con coste medido:** el umbral `B ≥ 0,1 R + 2C` sigue siendo correcto,
   pero `C` deja de ser una constante. Con 3.125 USD en C3 son 10,4 pb por lado,
   no 10; con 1.389 USD son 7,3.
3. **El techo de capacidad entra en el diseño, no en la revisión.** Una cartera de
   3.125 USD por posición en el tramo largo ya está en el límite; pedirle 25.000
   por posición es pedirle otro mercado.

## 7. Límites declarados

- **Una sola foto** (2026-11-27). El spread varía con la hora y la volatilidad; no
  hay historia de libros y no se puede promediar.
- **OKX, no Binance.** El libro de futuros de Binance está geo-bloqueado desde esta
  máquina. OKX se usa como orden de magnitud y calibración de forma; si Binance
  fuera más estrecho, el coste real bajaría, no subiría.
- **25 símbolos por cubeta**, elegidos alfabéticamente entre los que OKX lista: en
  C1 y C2 eso sesga hacia los mayores de cada tramo.
- **Sin coste de financiación del colateral ni de transferencia**, que H8 sí
  declaraba aparte (1 pb).

## 8. Contabilidad y artefactos

No añade ensayos: `TRIALS.md` sigue en **53**. Es la medición de un input, no una
variante de estrategia, y no puede promocionar nada.

- Pre-registro: `docs/PRE-REGISTRO-COSTE.md`.
- Medición: `scripts/measure_execution_cost.py` → `data/cost/model.json`,
  `data/cost/books.json`.
- Sensibilidad: `scripts/cost_sensitivity.py` → `data/cost/sensitivity.json`.
