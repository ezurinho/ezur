# CONTINUACIÓN — Motor IA para Estrategias BTC

Pega este documento como primer mensaje del chat nuevo. Está escrito para que no tengas que
reconstruir nada: el estado, los números y las trampas ya están verificados.

## 1. Qué es este proyecto (y qué no es)

Motor de investigación quant para **BTCUSDT perpetuo (Binance USDⓈ-M)**: specs ejecutables,
runner determinista, registro auditable en SQLite y una UI local. Nació de auditar el prompt
«Elite Quant V3» y acabó siendo un pipeline con 12 puertas de aprobación.

**No es un bot que manda órdenes.** No hay claves de exchange, no hay ejecución en vivo, no hay
conexión a la API de trading. Es un banco de pruebas de costes y potencia estadística. Si en algún
momento hace falta ejecución real, eso es un proyecto aparte y se decide explícitamente.

## 2. Dónde está

| Qué | Dónde |
|---|---|
| Código (copia original de DeepAI Code) | `C:\Users\Administrator\.deepai-code\scratch\2026-11-22-motor-ia-para-estrategias-btc-a2100b36` |
| Repo privado | `github.com/ezurinho/motor-ia-estrategias-btc` |
| Documentos de diseño previos | `C:\Users\Administrator\Downloads\bot\` (`BOT_TRADING_PROMPT_BASE.md`, `ARQUITECTURA.md`, prompt V3) |

## 3. Estado verificado — cítalo, no lo re-derives

- **24 corridas**: 21 reconstruibles + 3 con registro defectuoso documentado.
- **Veredicto: 0 APPROVED · 7 INCONCLUSIVE · 13 REJECTED.** El resultado negativo *es* el resultado.
- **Gate**: `python runner/verify_all.py` → **5 de 5** (sintaxis, tests, 19/19 corridas reproducen al dígito, 36 puertas evaluadas, ciclo coherente con su `data_hash`).
- **Datos**: 718.848 barras de 5m, 2020-01-01 → 2026-10-31, **0 gaps, 0 duplicados**, `data_hash 80d6a6014eb92b23`.
- **Multi-activo**: BTC, ETH, BNB, XRP, SOL; ventana común 2020-02-10 → 2026-10-31 (6,72 años), 0 gaps.

Números que no se pueden contradecir sin un artefacto nuevo:

| Dato | Valor |
|---|---|
| 1d Donchian 40 | PF neto 1,683 · 58 trades · t 1,60 |
| MinBTL vs historia | 14,6 años necesarios vs 6,8 disponibles |
| PBO del ciclo | 0,238 (umbral ≤ 0,20 → falla) |
| DSR del ciclo | 0,792 (umbral ≥ 0,95 → falla) |
| WFA | 6 trades por fold (umbral ≥ 30 → falla) |
| 5m EMA 12/48 | PF neto 0,490, MDD −100% |
| Contra buy & hold | 0 de 19 baten · alpha 1d D40 = −72,8% |
| Coste en 5m | 0,18–0,36 R por trade; expectativa bruta ≈ 0 |

**Discrepancia abierta**: el gate reporta 66 tests, `PLAN_MEJORA.md` dice 77. Hay que resolverlo
antes de citar cualquiera de los dos números.

## 4. Entorno: esto te va a morder

- Python por defecto: **3.14.6**. Y **no hay numpy ni pandas en 3.14, 3.12 ni 3.11**. Los scripts
  de `research/` no arrancan sin reponer el entorno:
  ```
  python -m venv .venv
  .venv\Scripts\activate
  pip install numpy pandas
  ```
  Versiones probadas: numpy 2.5.5, pandas 3.1.1, Python 3.14. Semilla 7 en las simulaciones.
- `runner/` **no** es stdlib: `runner/test_runner.py` importa pandas en la línea 19, así que los tests tampoco corren sin dependencias. Solo `app/server.py` es stdlib puro. En esta máquina hay un `.venv` ya creado con numpy 2.5.5 y pandas 3.1.1.
- `fapi.binance.com` devuelve **HTTP 451** desde este entorno: no hay datos en vivo. Todo sale de
  `data.binance.vision` y de los cachés de `research/cache/`.
- `research/cache/` pesa 602 MB y está ignorado en git (`*.pkl`, `*.parquet`). Sí están versionados
  los JSON de resultados, `multi_manifest.json`, `registry_seed.json` y `chart_data.json`.

## 5. Documentos que mandan (en este orden)

1. **`PROMPT_V4.md`** — la ley: contrato de `strategy_spec`, modelo de ejecución, 12 puertas,
   prohibiciones (§10) y checklist de autoaditoría (§12).
2. **`INFORME_AUDITORIA.md`** (1.028 líneas) — evidencias E1–E21, tabla de veredictos y anexo
   matemático. Toda cifra citada sale de aquí o de un artefacto.
3. **`PLAN_MEJORA.md`** — fases 1–6, con estado y resultado de cada una. **Fase 6 parcial.**
4. **`README.md`** — mapa de archivos, comandos, API y hashes.

## 6. Reglas de hierro (heredadas, no negociables)

- **La IA no produce números**: los produce el runner y la IA los cita con ruta
  (`result.json#/metrics/oos/...`).
- **Spec-first**: primero la spec validada contra `runner/strategy_spec.schema.json`, después la
  ejecución. Nunca al revés.
- **Nada de `APPROVED` sin las 12 puertas.** Si faltan PBO, DSR, MinBTL o WFA, el veredicto es
  `INCONCLUSIVE` y se listan en `missing_artifacts`. No se inventa la cifra.
- **Cambiar una regla del motor = bump de versión.** Añadir una regla nueva también.
- **No se suben umbrales ni se relajan puertas** para que algo apruebe. No se elige el método de
  validación que da el número favorable.
- **No se declara rentabilidad futura.**
- Antes de citar cualquier cifra: `python runner/verify_all.py --quick`.
- Todo en español, directo, sin relleno.

## 7. Trampas conocidas — no las repitas

- **E15**: el registro declaraba `atr_k = 2.0` y el motor ejecutaba **1,5 × ATR(14)**. Las métricas
  son correctas; el metadato era el que mentía. El verificador expone `atr_k_executed`.
- **E18**: la segmentación por regímenes usaba `>= q1` en vez de `>= q2` y se llevaba dos tercios de
  la muestra.
- **PBO = 0,000 con las 19 corridas es un artefacto**, no robustez: nueve configuraciones pierden en
  todos los bloques. Vive en `runner/validation/sensitivity/`, fuera del glob que consume el runner.
- **`verifyCard` hacía `r.diffs.join(...)`** y tiraba la vista Runner entera con 23 corridas.
  Arreglado con `(r.diffs || [])` y estado `omite` para `ok === null`.
- **En 5m el coste es la estrategia**: expectativa bruta ≈ 0, neta −0,10 a −0,52 R. No busques edge
  ahí sin un modelo de costes nuevo.
- **Más activos no compran potencia** (E21): t agregado 2,85 → 1,67 al descontar correlación 0,644.
- **El spread supuesto es correcto en calma y 19× corto en crisis** (hasta 1,30 bp el 2025-10-10).

## 8. Qué está pendiente

**Fase 6 (cerrar):**
1. Comparación de variantes v1.0.0 → v1.4.0 en la UI.
2. Curva de la estrategia contra buy & hold en la UI.

**Inmediato:**
3. Reponer el venv con numpy y pandas.
4. Correr el gate completo y pegar la salida real.
5. Resolver la discrepancia 66 vs 77 tests.

**Después:** proponer Fase 7, pero **primero la hipótesis y el criterio de falsación**, y sólo con
aprobación explícita. El plan prohíbe abrir frentes para “mejorar el número”.

## 9. Cómo trabajar conmigo

- Antes de tocar código: qué cambias, en qué archivo y **qué comando lo verifica**.
- Después: pega la salida real del comando, no un resumen.
- Si el gate está en rojo, no está hecho.
- Commits pequeños y en español. El repo es **privado**: no se publica, no se hace release, no se
  hace push a otro remoto.
- Si una decisión cambia el veredicto de una estrategia, párate y pregúntame.

## 10. Primer paso que te pido

1. Abre el repo y lee `PROMPT_V4.md` §0, §6 y §10.
2. Usa el `.venv` del proyecto (numpy 2.5.5, pandas 3.1.1); si falta, créalo e instala.
3. Corre `python runner/verify_all.py` **completo** y pega la salida.
4. Dime el estado real antes de proponer una sola línea de código.
