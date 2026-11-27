# Consultas exploratorias

Aquí se apunta cada pregunta que se hizo a los datos **sin** pre-registro: las
que informaron una decisión de diseño, las que descartaron una idea antes de
medirla y las que se hicieron después de archivar para entender un resultado.
No son ensayos —no producen una variante con veredicto— pero consumen
presupuesto de búsqueda y el DSR debe poder declararlas.

Regla: se añade una línea por consulta, con fecha, pregunta y respuesta en una
línea. No se borran. El recuento lo lee `scripts/lab_ledger.py`.

## 2026-11-27

- ¿El modelo de coste `a + b·sqrt(S/ADV)` explica el coste medido? **No** (R² 0,187, Spearman 0,231) → fallback de medianas empíricas.
- ¿La señal de funding predice el funding futuro? **Sí** (IC1 +0,1023/+0,1245/+0,1350) → diagnóstico obligatorio, no puerta.
- ¿La convención de esperanza en R por operación cambia algún veredicto archivado? **No**, 0 de 6.
- ¿Cuánto de la dispersión de 2026 es artefacto del intervalo? **Nada en cash**; 6,3× con la convención de 8 h.
- ¿El cribado de H10 depende de la ventana 2023-2026? **Sí**: mediana larga 44,66 pb, sólo 2026 cruza la barra.
- ¿El carry se concentra en pocos nombres? **No**: 9 nombres para el 80 % del diferencial; la concentración que mata a H5 es la pata de precio.
- ¿Cuánto capital absorbe el carry en el tramo largo? **~2,26 M USD** de bruto al 1 % del volumen mediano.
- ¿El `shift(1)` de la señal lee el día de evaluación? **No**: envenenar la fila de t deja la señal de t idéntica y cambia la de t+1.
- ¿La dispersión observada de H10 es distinguible de una nulidad sin señal? **Sí**: percentil 100 frente a 50 permutaciones (p = 0,0196).
- ¿El motor de H5 lee el día de rebalanceo? **No**: la señal de ese día no cambia al envenenarlo; la del día siguiente sí.
- ¿H5 sobrevive a 50 permutaciones del funding? **No**: p = 0,0784, percentil 94.
- ¿Cuánto de H5 es carry y cuánto precio? **Todo precio**: con precios constantes la pata de funding da −0,0032 R y no cubre 1.500 USD de costes.
