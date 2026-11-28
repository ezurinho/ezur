---
id: data-real-adr-0-2
title: "Fuente de datos reales (ADR 0.2)"
category: decision
status: active
tags: [data, adr]
created: "2026-11-27T18:04:59"
updated: "2026-11-27T18:38:56"
---

<!-- compiled_truth -->
# Decisión

El ADR 0.2 quedó cerrado el 2026-11-27. El histórico largo sale de **Binance
Vision** (`data.binance.vision`) y el papel sigue en **OKX**. La decisión
completa, con la tabla de calidad y el plan en seis fases, está en
`docs/DECISIONES.md` (ADR 0.2).

# Por qué

`api.binance.com` responde 451/403 desde esta región y OKX no entrega años de
1 m sin decenas de miles de peticiones. Vision publica ZIPs mensuales con
`.CHECKSUM` para spot, UM y trimestrales, además de funding y mark price. Ya
medido: 3.591.915 velas de 1 m (2020-01 → 2026-10) y 2.496 días diarios sin
huecos.

# Lo que fija

- Base de 1 m; 15 m, 1 h, 4 h y 1 D por resample determinista.
- Ventana canónica 2020-01-01 → presente; 2017-2019 solo contexto.
- Símbolo del bot `BTC-USDT`; el símbolo del vendor vive en el manifiesto.
- `dataset_id` = SHA-256 del CSV; `manifest_sha256` aparte.
- Rolls con contratos reales y ledger explícito; la serie de señales va sin
  ajustar.
- Calidad: checksums, OHLC, huecos, reconciliación Binance/OKX (mediana ≤ 5 pb,
  p99 ≤ 25 pb) y funding cada 8 h.
- El adaptador no está implementado: `data.provider` sigue en `simulated`.

# Consecuencia

G1/G3/G14 pasan de «no medible» a medibles y la nota de datos debería subir de
3 a 8–9. A cambio, descarga mensual, verificación de checksums y reconciliación.


## Timeline

- time: 2026-11-27T18:04:59
  kind: decision
  summary: "Created this page: Fuente de datos reales (ADR 0.2)"
  source: "sesión 2026-11-27"
  affects: [data-real-adr-0-2]

- time: 2026-11-27T18:05:10
  kind: decision
  summary: Rewrote compiled_truth to the new best understanding
  source: brain update-truth
  affects: [data-real-adr-0-2]

- time: 2026-11-27T18:38:56
  kind: evidence
  summary: "Prueba seca ADR 0.2: spot/UM/funding 2020-01..2026-10 con 82 meses y checksums OK; los trimestrales empiezan en 2021-02 (25 contratos) y sus ZIP incluyen barras planas con volumen 0 después del vencimiento."
  source: prueba seca local 2026-11-28
  affects: [data-real-adr-0-2]
