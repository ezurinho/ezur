# Archivo de la familia SMA 15m

**Fecha:** 2026-11-27
**Veredicto:** la familia SMA 15m queda archivada como «sin ventaja». El ciclo
canónico completo sobre 6,8 años de BTC spot repite el rechazo de la ventana
2025 y ninguna de las cinco variantes sobrevive a las puertas. El holdout sigue
sellado y no se abrió.

## Qué se ejecutó

| Campo | Valor |
|---|---|
| Ciclo | `CYCLE-BOT-15M-CANONICAL-FULL` (`method_version` 1.2.0) |
| Estrategia | `reference@0.1.0`: SMA 7/21, stop 10 ATR, objetivo 1 R, sin time stop |
| Candidato | `15m_7_21_a10_ref7` |
| Dataset | `data/btc_5m_spot_canonical.pkl`: 718.386 velas de 5m, 2020-01-01/2026-10-31, sha256 `90d33bd1cfb25d2a38e0d499501963eca93b7e06a835df078664d58a9a9d889b` |
| Límites y costes | `profiles/okx/config.json` (paper, riesgo 0,25 %, freno de drawdown 2,5 %) |
| Universo | cinco variantes SMA pre-registradas |
| Estrés | re-ejecución con costes ×2 |
| Cobertura | 6,81 años; 958 días con operaciones |
| Ejecución | 2026-11-27T05:28:02Z; 26 min 41 s |
| Artefacto | `data/research/cycles/CYCLE-BOT-15M-CANONICAL-FULL.json`, sha256 `1ed9f3fa8a1204fb22bd879f61921bc2bf2844d6754e054cd2d01d42a752f48a` |
| Trial ledger | `data/research/cycles/CYCLE-BOT-15M-CANONICAL-FULL.trials.jsonl`, sha256 `8a8f10bbeca66de88c06e00060fc85a39b97eecf4546c95da12e8b8e569af5c8` |

```
python -m server.selection --cycle CYCLE-BOT-15M-CANONICAL-FULL \
  --spec-dir data/specs_canonical --all-specs \
  --dataset data/btc_5m_spot_canonical.pkl \
  --config profiles/okx/config.json \
  --blocks 10 --folds 5 --stress-multiplier 2.0 --random-iterations 50
```

La reconstrucción del trial ledger vuelve a calcular PBO 0,4087 y DSR 0,0912
desde las series diarias y coincide con el artefacto (`matches: true`).

## Resultado por variante

| Variante | Operaciones | PF | Esperanza | PF ×2 | ¿Sobrevive? | Días con operaciones |
|---|---:|---:|---:|---:|---|---:|
| 15m_5_21_a10_ref5 | 638 | 0,9071 | +0,0039 R | 0,8287 | no | 595 |
| 15m_9_21_a10_ref9 | 645 | 0,9754 | +0,0373 R | 0,9039 | no | 595 |
| **15m_7_21_a10_ref7** (canónica) | **604** | **0,9763** | **+0,0252 R** | **0,5425** | **no** | 556 |
| 15m_7_34_a10_ref34 | 274 | 0,7112 | −0,1151 R | 0,7057 | no | 253 |
| 15m_7_55_a10_ref55 | 442 | 0,8343 | −0,0556 R | 0,7545 | no | 426 |

Ninguna variante llega a PF 1,00 después de costes y ninguna aguanta el estrés
de costes ×2. La mejor por PF es la canónica, y aun así queda por debajo de 1.

## Puertas duras

| Puerta | Umbral | Resultado | Veredicto |
|---|---:|---:|---|
| Operaciones | ≥ 80 | 604 | pasa |
| PF | ≥ 1,25 | 0,9763 | falla |
| Esperanza | ≥ +0,10 R | +0,0252 R | falla |
| PBO | ≤ 0,20 | 0,4087 (252 particiones, bloques de 95 días) | falla |
| DSR | ≥ 0,95 | 0,0912 (Sharpe anual −0,1557) | falla |
| Estrés ×2 | PF > 1,00 | 0,5425 | falla |
| CPCV | > 50 % de caminos positivos | 40,0 % (60 % negativos, 45 caminos) | falla |
| WFA OOS | PF > 1,10 | 1,0460 (495 operaciones OOS, mínimo 51 por fold) | falla |
| Entradas aleatorias | p < 0,05 | no medible | limitación |
| MinBTL | — | no calculable con Sharpe negativo | — |

En el WFA el procedimiento elige `15m_9_21_a10_ref9` en los cinco folds, con PF
OOS por fold de 1,205, 0,8373, 0,9452, 0,9641 y 1,2549. El agregado 1,0460
queda por debajo del 1,10 de la puerta. El benchmark de entradas aleatorias no
pudo colocarse (`una iteración no pudo colocar 604 operaciones`), así que esa
puerta queda sin medir; no cambia el veredicto porque las demás fallan.

## 2025 frente a la historia completa

| Métrica | Ventana 2025 | 6,8 años |
|---|---:|---:|
| Operaciones | 134 | 604 |
| PF | 1,0016 | 0,9763 |
| Esperanza | +0,0410 R | +0,0252 R |
| Estrés ×2 (PF) | 0,9298 | 0,5425 |
| PBO | 0,631 | 0,4087 |
| DSR | 0,1681 | 0,0912 |
| WFA OOS (PF) | 0,8863 | 1,0460 |
| CPCV negativos | 66,67 % | 60,0 % |

El único año que parecía empatar (PF 1,0016) era ruido de una ventana: con
2020-2024 y 2026 dentro, el PF cae por debajo de 1 y el estrés de costes baja a
0,54. El PBO mejora de 0,631 a 0,409, pero sigue duplicando el máximo de 0,20;
el DSR baja de 0,168 a 0,091. Más datos no rescatan la señal: la confirman como
inexistente después de fricción.

## Freno de drawdown en dos variantes

`15m_7_34_a10_ref34` y `15m_7_55_a10_ref55` dejan de operar el 2023-10-01 y el
2025-02-21. No es un hueco de datos: ambas alcanzan un drawdown cerrado de
3,78 % y 3,79 % sobre el capital, justo el umbral de parada del perfil
(2,5 % × 1,5 = 3,75 %), y el freno no se rearma porque, sin posición, el
drawdown no vuelve por debajo del umbral. Sus series terminan ahí y el artefacto
las trata con retorno cero desde entonces; por eso sus métricas no cubren los
6,8 años.

La variante canónica 7/21 y las variantes 5/21 y 9/21 sí operan hasta 2026-10.
El veredicto se apoya en la canónica, que tiene la muestra completa, y en que
ninguna variante sobrevive al estrés. Cambiar el rearme del freno alteraría las
reglas de riesgo y no se hace en este ciclo: queda registrado como
comportamiento medido, no como dato faltante.

## Nota de ejecución

El ciclo se relanzó con el arreglo de `server/db.py` (commit `f03f4e4`): la poda
de `equity_marks` pasó de materializar 5.000 ids por vela a cortar por el último
id insertado, conservando exactamente las mismas 5.000 marcas. La paridad se
verificó sobre la ventana 2025: 134 operaciones, PF 1,0015857, esperanza
0,0409625 y estrés PF 0,9297576, idénticos al artefacto
`CYCLE-BOT-15M-CANONICAL-2025`. El arreglo no toca señales, costes ni puertas;
solo evita que cada backtest sea O(velas × 5.000).

## Decisión

1. La familia SMA 15m se archiva como «sin ventaja». No se promociona ninguna
   variante ni se añaden parámetros nuevos.
2. El holdout `income-lab-2027` (2026-12-01/2027-05-31) sigue `sealed`, con
   `opened_by: null`. No se descarga ni se mira.
3. La evidencia queda congelada en los dos ficheros de `data/research/cycles/`
   con los hashes de arriba.
4. La siguiente hipótesis del plan es H1 (tendencia BTC spot 4 h); este ciclo no
   la ejecuta.
