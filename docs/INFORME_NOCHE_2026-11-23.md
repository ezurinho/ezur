# Informe de la noche · 22–23 de noviembre de 2026

Todo lo que sigue son números medidos en esta máquina, no proyecciones.

Perfil `profiles/okx`: BTC-USDT, feed OKX real, modo `paper`, comisión
0,049 por lado, `fill_model=intrabar`, riesgo 0,75 % por operación, 12 ops/día,
pausa de 45 min tras 3 pérdidas seguidas, guardián de drawdown 5 %.

## 1 · La sesión en vivo (datos reales de OKX)

| Dato | Valor |
|---|---|
| Operaciones cerradas | 7 |
| Aciertos | 0 |
| Todas cerradas por | `stop` |
| P&L del día | −714,84 USD (−2,86 % del capital) |
| Equity | 24 285,16 USD desde 25 000 |
| Racha | 7 pérdidas seguidas |
| Última vela | 06:30 UTC, 15 s de edad |

El bot no está roto: está perdiendo exactamente como el arnés avisa que pierde.
La pausa de racha hizo su trabajo dos veces. A las 05:41 UTC reanudó tras 45
minutos, tomó una operación, la perdió y volvió a la pausa. Sin esa pausa
configurable habría pasado 18 horas bloqueado sin mirar el mercado, o habría
seguido martillando stops sin descanso.

Límite diario de pérdida: 3 % = 750 USD. Con −714,84 el margen que queda es de
35 USD: el siguiente stop cierra el día. Ese es el sistema de riesgo funcionando,
no una avería.

## 2 · Comparación de estrategias sobre el mismo CSV real

`data/BTC_1m.csv` (600 velas de 1 m de OKX, dos sesiones), mismo motor, mismos
costes, ordenado por esperanza en R:

| Estrategia | Ops | Acierto | PF | Esperanza | DD | Veredicto |
|---|---|---|---|---|---|---|
| reference | 7 | 14 % | 0,05 | −1,94 R | 247,32 | RECHAZADA |
| donchian | 6 | 0 % | 0,00 | −2,80 R | 254,06 | RECHAZADA |
| fade | 6 | 0 % | 0,00 | −4,10 R | 143,37 | RECHAZADA |
| null | 0 | — | — | sin operaciones | 0,00 | RECHAZADA |

Puertas que fallan en las tres: G4 (menos de 80 operaciones), G5 (PF < 1,25 y
esperanza < +0,10 R), G6 (drawdown), G9/G10 (concentración), G11 (intervalo de
confianza de la esperanza por debajo de cero) y G8 (costes ×2).

Que `null` también salga RECHAZADA es la prueba de que el arnés no aprueba por
inercia: una estrategia que no opera no pasa el filtro de significancia.

## 3 · Simulación: 20 sesiones sintéticas × 300 velas

| Estrategia | Fill | Ops | Acierto | PF | Esperanza | P&L | Puertas que fallan |
|---|---|---|---|---|---|---|---|
| reference | next_open | 60 | 30 % | 0,20 | −0,78 R | −771,92 | G4 G5 G6 G9/G10 G11 G8 |
| reference | intrabar | 60 | 30 % | 0,20 | −0,78 R | −771,92 | G4 G5 G6 G9/G10 G11 G8 |
| donchian | next_open | 60 | 28 % | 0,27 | −0,77 R | −649,31 | G4 G5 G6 G9/G10 G11 G8 |
| donchian | intrabar | 60 | 28 % | 0,27 | −0,77 R | −649,31 | G4 G5 G6 G9/G10 G11 G8 |
| fade | next_open | 60 | 20 % | 0,18 | −0,90 R | −573,67 | G4 G5 G6 G9/G10 G11 G8 |
| fade | intrabar | 60 | 20 % | 0,18 | −0,90 R | −573,67 | G4 G5 G6 G9/G10 G11 G8 |

Dos lecturas honestas:

1. **Sobre datos sintéticos ninguna estrategia debe aprobar**, y ninguna aprueba.
   Si alguna hubiera pasado G5 aquí, el problema sería el generador, no el genio.
2. En esta simulación `next_open` e `intrabar` coinciden al céntimo. No es un
   fallo del modelo de fill: `signal_price` sí cambia la entrada en el CSV real
   (comprobado en `tests/test_parity.py`), pero con barras sintéticas sin huecos
   ambas rutas ejecutan al mismo precio. El día que el generador produzca huecos,
   la diferencia aparecerá; el test que exige que el ajuste cambie algo ya existe.

## 4 · Lo que se arregló esta noche (y cómo se supo)

| Fallo | Cómo se vio | Estado |
|---|---|---|
| Activar alertas en la interfaz no activaba nada | la prueba contra un webhook local decía «desactivadas» con la config en `enabled: true` | notifier reconstruido al guardar |
| «En vivo» con velas de hace horas | revisión del chip contra `last_bar_ts` | chip con edad real |
| «Espera un poco» para una racha que duraba hasta la sesión siguiente | frase inventada | frase con el mecanismo real |
| La pausa de racha no sobrevivía al reinicio | `last_exit_ts` solo en memoria: bloqueo sin fecha | persistido en `kv`, con test |
| La tabla del laboratorio resaltaba a la «mejor» perdedora | comparación de 4 estrategias todas en rojo | el resaltado exige esperanza > 0 |
| `/api/health` decía `ok` con el feed muerto | no distinguía proceso vivo de motor vivo | `status`, `feed`, `last_bar_age_s` |
| Dos hilos escribiendo en la misma conexión SQLite | «cannot commit - no transaction is active» | `RLock` + test de concurrencia |

## 5 · Conclusión

El instrumento de medida está mejor: trazabilidad por corrida, comparación de
estrategias con puertas a la vista, paridad backtest↔vivo, lecturas que no
adulan. La estrategia sigue sin ventaja demostrable en BTC 1 m, y este informe lo
dice con el mismo énfasis con el que diría lo contrario.

Lo siguiente con más probabilidad de cambiar el resultado no es más interfaz:
es 5 m/15 m (menos ruido, costes menos brutales por operación) y una estrategia
con hipótesis propia, medida con el mismo arnés.
