---
id: lab-neto-compuesto
title: "Neto del laboratorio: curva diaria compuesta, no suma de patas"
category: decision
status: active
tags: [laboratorio, metricas, funding]
created: "2026-11-27T16:08:22"
updated: "2026-11-27T16:08:22"
---

<!-- compiled_truth -->
El neto de una familia es la curva de capital diaria compuesta: `(1 + daily).prod() - 1`, multiplicada por 25.000 USD. La suma de patas (precio + funding - costes) sirve para atribuir de dónde sale el resultado, nunca para contabilizarlo.

Cifras que fijaron la regla (ventana OOS 2025-01/2026-11): H5 6.086,46 compuesto frente a 6.029,43 de patas; H8 80,17 frente a 80,10; H9 -51,73 frente a -51,74; H10 quintil con filtro 20.259,96 frente a 15.594,43, y k=4 24.589,97 frente a 38.870,12.

La diferencia no siempre va en la misma dirección: en el quintil de H10 el compuesto supera a las patas y en k=4 se queda muy por debajo. Ninguna de las dos cifras es "la conservadora"; la compuesta es la única que representa lo que vería la cuenta.


## Timeline

- time: 2026-11-27T16:08:22
  kind: decision
  summary: "Created this page: Neto del laboratorio: curva diaria compuesta, no suma de patas"
  source: created via brain create-page
  affects: [lab-neto-compuesto]

- time: 2026-11-27T16:08:22
  kind: decision
  summary: "Fija la convención contable del laboratorio"
  source: brain update-truth
  affects: [lab-neto-compuesto]
