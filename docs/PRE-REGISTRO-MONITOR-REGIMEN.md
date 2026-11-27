# Pre-registro: monitor de régimen del carry (H10)

**Fecha:** 2026-11-27, escrito **antes** de calcular el estado actual.
**Naturaleza:** instrumento de observación. **No es una estrategia, no abre
posiciones, no calcula P&L y no reabre nada por sí solo.**

## Por qué existe

El diagnóstico de ventana dejó un hecho: la dispersión del carry fue de 20-41 pb
por ventana entre 2020 y 2024, 114,82 pb en 2025 y 309,42 pb en 2026. Sólo el
último año y medio cruza los 240 pb de la geometría de H10. Si ese régimen es
pasajero, el archivo de H10 es definitivo; si persiste, hay una familia que
medir —pero sólo se puede medir con una regla fijada **antes** de ver el año que
la cumple.

Este monitor es esa regla. Se escribe hoy, con el dato de 2026 ya visto —no hay
forma de evitarlo—, y precisamente por eso la regla es mecánica y no discrecional:
no permite elegir el umbral, la ventana ni el momento.

## La regla, fijada ahora

- **Medida:** la misma del cribado archivado, sin cambios: ventanas de 7 días
  desde cada lunes, `k = max(2, round(n/5))` topado a 8 por lado, señal
  estandarizada de 7 días contra 90, elegibilidad con 90 días de historia y
  5 M USD de volumen mediano.
- **Estadístico:** la mediana móvil de las **últimas 13 ventanas** de dispersión
  capturada (pb del nocional por posición y episodio).
- **Umbral:** **240 pb**, la barra de la regla 10 con k = 8. No se toca.
- **Estado ACTIVE:** la mediana móvil de 13 semanas es ≥ 240 pb en la última
  semana cerrada.
- **Estado INACTIVE:** < 240 pb.
- Se publica también cuántas semanas lleva activo y el primer lunes activo de la
  serie.

## Qué permite y qué no

**No** reabre H10 ni autoriza capital. **No** cambia el veredicto archivado.

Sirve para una sola cosa: cuando exista muestra **posterior al holdout**
(2027-06 en adelante), decidir si hay régimen que justifique un pre-registro
nuevo. Ese pre-registro, si llega, tendrá que pasar además la puerta de potencia
y explicar el mecanismo; el monitor sólo dice si el mercado sigue pagando.

## Reglas de higiene

1. El monitor se ejecuta sobre datos **hasta 2026-11-30**, nunca dentro del
   holdout (2026-12-01/2027-05-31), que sigue sellado.
2. Se ejecuta como máximo **una vez por semana**, los lunes, y el resultado se
   commitea. No se re-ejecuta hasta que cambie el estado.
3. Si el estado cambia, se anota en `docs/TRIALS.md` como observación, no como
   ensayo: no consume presupuesto de búsqueda.
4. Cambiar el umbral, la ventana de 13 semanas o la definición de ACTIVE después
   de ver la serie invalida el monitor y obliga a pre-registrarlo de nuevo con
   otro nombre.
