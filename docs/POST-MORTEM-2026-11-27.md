# Post-mortem — cuatro familias, 25 variantes, ningún edge desplegable

**Fecha:** 2026-11-27
**Alcance:** SMA 15 m, Donchian 1 h (H1), carry BTC (H2), momentum
cross-sectional (H3), reversión de pares (H4). Todas pre-registradas, medidas y
archivadas. Ninguna pasa las puertas duras en OOS.

## Qué se midió

| Familia | Variantes | Mejor OOS | Veredicto |
|---|---:|---|---|
| SMA 15 m | 5 | PF 0,9763, +0,0252 R | archivada |
| Donchian 1 h | 5 | PF 0,7529, -0,0436 R | archivada |
| Carry BTC | 5 | +2,35 % anual, 4 episodios | archivada por muestra |
| Momentum cross-sectional | 5 | PF 0,7046, -30,9 % | archivada |
| Pares contra BTC | 5 | PF 0,9235, -2,75 % | archivada |

**Total: 25 variantes medidas.** El registro está en `docs/TRIALS.md`.

## El patrón

1. **El bruto se desvanece fuera de 2020-2021.** Las cuatro familias tienen su
   mejor tramo en el ciclo de alt-season y tipos cero; 2025-2026 es negativo o
   plano para todas. No es un problema de parámetros: es un cambio de régimen.
2. **El coste no es el culpable.** El coste ponderado OOS está entre 0,006 y
   0,03 R por operación, muy por debajo de la puerta de 0,25 R. Cuando la señal
   existe, la fricción no se la come; cuando no existe, bajarla no la crea.
3. **La concentración delata la falta de prima.** En H1 y H3, quitar cinco
   operaciones/periodos convierte el beneficio en pérdida. Una ventaja estable
   no depende de cinco rachas.
4. **El mejor resultado es el carry**, +2,35 % anual con 4 episodios: positivo,
   pero indistinguible de la suerte y por debajo de una letra del Tesoro.
5. **La muestra no es el problema principal.** H1, H3 y H4 tienen 227-728
   operaciones OOS y pierden; el carry tiene 4 y gana poco. Más muestra no
   arregla una señal que no está.

## Lo que sí mejoró

- Pre-registro antes de medir, datos congelados con SHA-256 y variantes
  declaradas.
- Corrección de un fallo real de medición: el R se calculaba contra el stop
  trailed y amplificaba las pérdidas.
- Registro de 25 ensayos para que el DSR no se calcule sobre la variante
  conveniente.
- Separación entre el motor de órdenes y los simuladores de investigación
  (carry, momentum, pares), con pruebas propias.

## Lo que habría que cambiar (requiere decisión, no se aplica solo)

1. **Datos de otra clase:** flujo de órdenes, opciones (Deribit), on-chain
   (MVRV, flujos de exchanges) o liquidaciones. Las cuatro familias usan precio
   y funding; el filo puede estar en datos que el precio no contiene.
2. **Universo:** salir de BTC-only y de los 7 grandes. El cross-section de
   altcoins pequeñas tiene más dispersión, pero también más coste y más
   supervivencia.
3. **Puerta para baja rotación:** el carry no puede dar 100 operaciones en 22
   meses. Si se quiere estudiar, necesita una puerta propia (episodios ≥ 30,
   ≥ 5 años, neto > letra + 2 %, concentración top-5). Cambiarla sin declararlo
   sería maquillar el resultado.
4. **Ejecución multi-venue:** el carry y los pares viven del basis y del
   funding; un modelo con un solo venue y un proxy de funding no basta para
   poner dinero.

## Regla para la próxima sesión

No se ejecuta otra hipótesis de precio/funding sobre BTC o los 7 grandes sin
declarar el ensayo en `docs/TRIALS.md` y sin una razón nueva (dato, universo o
microestructura). Repetir la búsqueda con otro umbral no es una hipótesis nueva:
es la misma prueba con otro nombre.

**No se pone dinero real.** `live_enabled=false`; el laboratorio no tiene una
ventaja que justifique capital.
