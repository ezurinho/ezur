# Mediciones fuera de muestra

Cada fila sale de un backtest con `--split 2024-01-01` sobre datos Binance y de
la puerta de promoción (`python -m server.promotion`). Se guardan todas las
mediciones, incluidas las que pierden: si una idea se descarta, queda el número
que la descartó.

Regla de lectura: **ninguna configuración se promueve** hasta cumplir, a la vez,
PF fuera de muestra > 1 con 100+ operaciones, coste < 0,25 R, PF > 1 con coste
duplicado y PBO ≤ 0,2 en su ciclo.

## 1 h · BTC

| estrategia | config | IS ops | IS PF | OOS ops | OOS PF | OOS esp. | coste |
|---|---|---|---|---|---|---|---|
| donchian | ch40 · sa1.5 · rr2.0 (la que opera) | 694 | 0.666 | 521 | 0.979 | −0.012 R | 0.025 R |
| donchian | ch20 · sa2.5 · rr1.5 | 675 | 0.701 | 508 | 1.014 | +0.018 R | 0.052 R |
| donchian | ch20 · sa1.5 · rr2.5 | 880 | 0.634 | 567 | 0.996 | +0.008 R | 0.057 R |
| donchian | ch20 · sa1.5 · rr1.5 | 973 | 0.509 | 377 | 0.941 | −0.026 R | 0.056 R |
| cruce + marea | fast9 · slow21 · marea100 | 672 | 0.531 | 406 | 0.859 | −0.099 R | — |
| cruce + marea | fast9 · slow21 · marea200 | 684 | 0.619 | 493 | 0.860 | −0.094 R | — |
| canal + tendencia | ch20 · marea200 | 761 | 0.620 | 554 | 0.969 | −0.019 R | — |
| canal + tendencia | ch40 · marea200 | 605 | 0.671 | 464 | 0.990 | +0.001 R | — |
| fade | p20 · s2.0 · sa1.5 | 1255 | 0.411 | 176 | 0.706 | −0.118 R | — |
| fade | p20 · s2.5 · sa1.5 | 1126 | 0.435 | 180 | 0.586 | −0.222 R | — |

El mejor candidato de 1 h (ch20 · sa2.5 · rr1.5) **no se promueve**:

```
pf_fuera_de_muestra             1.014          > 1.0  si
operaciones_fuera_de_muestra        508         >= 100  si
coste_por_operacion             0.052       < 0.25 R  si
pf_con_coste_duplicado          0.915          > 1.0  NO
pbo_del_ciclo                   0.976         <= 0.2  NO
```

## 1 d · BTC

| config | IS ops | IS PF | OOS ops | OOS PF | OOS esp. | coste |
|---|---|---|---|---|---|---|
| ch20 · sa1.5 · rr2.0 | 66 | 1.293 | 51 | 0.947 | −0.014 R | 0.030 R |
| ch40 · sa1.5 · rr2.0 | 52 | 1.141 | 36 | **1.134** | +0.069 R | 0.028 R |

El diario reduce el coste a la mitad y el PF fuera de muestra mejora, pero
**36 operaciones no demuestran nada** y el PBO del ciclo 1d es 0,976. La puerta
lo rechaza por muestra, no por rentabilidad: para juntar 100 operaciones fuera
de muestra en diario harían falta más de diez años.

## Lo que dicen los números juntos

- El coste no es el asesino principal: bajarlo de 0,05 R a 0,03 R no cambia la
  conclusión.
- Ninguna familia de señal de precio probada gana fuera de muestra con muestra
  suficiente.
- Tocar parámetros sobre las mismas señales solo produce candidatos que mueren
  al duplicar el coste o al mirar su PBO.

La siguiente idea tendría que ser otra fuente de señal, no otra rejilla.
