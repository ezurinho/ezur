# Las nueve mejoras del laboratorio

Implementadas el 2026-11-27, después del informe de cierre. **No cambian ningún
veredicto ni desarchivan nada**: cambian lo que el laboratorio puede demostrar y
lo que no dejará pasar la próxima vez.

| # | Mejora | Dónde | Estado |
|---|---|---|---|
| 1 | Puerta de potencia en el pre-registro | `scripts/power_gate.py`, regla 11 del plan | hecha |
| 2 | Canarios de look-ahead | `scripts/validation_suite.py` | hecha y en verde |
| 3 | Denominador honesto del DSR | `scripts/lab_ledger.py`, `docs/QUERIES.md` | hecho |
| 4 | Baseline nulo por permutación | `scripts/validation_suite.py` | hecho |
| 5 | Monitor de régimen pre-registrado | `scripts/regime_monitor.py`, `docs/PRE-REGISTRO-MONITOR-REGIMEN.md` | hecho |
| 6 | Concentración y capacidad del carry | `scripts/carry_concentration.py` | hecho |
| 7 | Verificación reproducible del archivo | `scripts/verify_archive.py` | hecha |
| 8 | Candado del holdout | `scripts/holdout_guard.py` | hecho |
| 9 | Simulador de ejecución con 1 m | `scripts/fill_simulator.py` | hecho, con límite de datos |

---

## 1. Puerta de potencia

`python scripts/power_gate.py --table` da la tabla de episodios necesarios. Con
σ = 81,3 pb (la dispersión semanal del cribado, estimada por el rango
intercuartílico) detectar 40 pb exige **29 episodios**; con σ = 200 pb, 158; con
σ = 400 pb, 621.

Lo que habría bloqueado: H2 con 4 episodios y H8 con 17. Ahora el pre-registro se
rechaza antes de medir, no después.

## 2. Canarios de look-ahead

Tres pruebas sobre el motor del cribado:

- **Señal**: se envenena una sola fila del día de evaluación y se compara la
  señal de ese día. Resultado: **diferencia 0,0** en 20 lunes; la del día
  siguiente cambia (3,48), lo que demuestra que el veneno actúa. El `shift(1)`
  hace su trabajo.
- **Ruido**: con un pago de ruido puro la mediana capturada es **+0,70 pb**.
- **Nulo**: ver punto 4.

El primer intento de canario dio «falla» y era el test el que estaba mal escrito
—envenenaba todos los lunes a la vez, así que la señal de un lunes cambiaba por
los lunes anteriores de su ventana—. Queda escrito porque el episodio es la
lección: un canario que falla hay que desmontarlo antes de creerlo.

**También sobre el motor de H5** (`scripts/engine_validation.py`): la señal del
día de rebalanceo no cambia al envenenarlo (0,0), la del día siguiente sí (2,33)
y los episodios cerrados antes del veneno son idénticos al céntimo. La nulidad de
50 permutaciones deja el resultado de H5 en **p = 0,0784** (percentil 94) y, con
los precios constantes, la pata de funding da **−0,0032 R**: el carry no cubre
los costes y todo el neto es precio. Ver `docs/ARCHIVO-H5.md`.

## 3. Denominador del DSR

`docs/TRIALS.md` → `data/lab_ledger.jsonl` con **cadena de hash**: 11 familias,
**53 variantes**. `--verify` recalcula la cadena. `docs/QUERIES.md` declara las
consultas exploratorias (8 hasta hoy) para que el escenario conservador del DSR
sea 53 + 8 y no 53 a secas.

## 4. Baseline nulo

50 permutaciones barajando el pago dentro de cada símbolo, conservando la
marginal y destruyendo el emparejamiento señal-pago. Sobre el panel congelado:

- nulidad: media ≈ 0, p95 **9,62 pb**, máximo 9,75;
- observado: **80,51 pb**, **percentil 100**, p = 0,0196.

La dispersión del cribado no es lo que produce una cartera sin señal. Es la
primera vez que el archivo tiene una prueba no paramétrica de que el estadístico
mide algo real.

## 5. Monitor de régimen

Regla fijada antes de calcularla: mediana móvil de 13 semanas ≥ 240 pb. Estado
al corte 2026-11-30: **INACTIVE**, mediana 160,82 pb, última semana 119,69 pb.
Estuvo activo **31 semanas** desde el 19-ene-2026 y se apagó antes del corte.

Es el dato más incómodo del día: el régimen que justificaba reabrir el carry ya
se estaba apagando cuando se escribió el informe.

## 6. Concentración y capacidad

95 semanas de 2025-2026: top-1 **24,8 %**, top-3 **47,3 %**, top-5 **61,6 %**,
HHI 0,1175, **9 nombres** para el 80 %, ninguna semana con un nombre por encima
del 50 %. Capacidad: **2,26 M USD** de bruto al 1 % del volumen mediano.

Conclusión: el carry está repartido; lo que concentra el P&L de H5 es la pata de
precio, no el funding. Eso reencuadra el archivo (ver `DEEP-RESEARCH-2026-11.md`
§4).

## 7. Verificación del archivo

`python scripts/verify_archive.py` comprueba hashes de los dos paneles, el
80,51 pb del cribado, los seis veredictos de la convención de esperanza, las
cifras de dispersión de 2026 y la cadena del ledger. Falla con código distinto de
cero si algo deriva.

## 8. Candado del holdout

`holdout_guard.guard(frame)` aborta si aparece una fecha entre 2026-12-01 y
2027-05-31, salvo que exista un pre-registro hasheado y `EZUR_HOLDOUT_UNSEAL=1`.
No borra datos: impide el uso accidental y deja rastro. Probado con `--test`.

## 9. Simulador de ejecución

Sobre velas de 1 minuto (BTC, 10 h de muestra): 3.125 USD ejecutados en 1 minuto
al 10 % del volumen, deslizamiento **−1,13 pb** (favorable por azar del minuto).
Es una **cota inferior**: con velas no se modela selección adversa ni impacto
permanente, y sólo hay 1 m de BTC. Sirve para comprobar que el coste declarado de
la cubeta líquida es alcanzable, no para sustituir la medición de coste.

---

## Lo que estas mejoras no hacen

No generan retorno. Ninguna de las nueve crea un edge, y el laboratorio sigue sin
nada desplegable. Lo que hacen es que el «no» sea defendible, que el próximo
«sí» no sea un artefacto y que el dinero no se ponga donde la evidencia dice que
se pierde.

## Reproducir todo

```
python scripts/power_gate.py --table
python scripts/validation_suite.py --panel-dir data/h10 --permutations 50
python scripts/lab_ledger.py && python scripts/lab_ledger.py --verify
python scripts/regime_monitor.py
python scripts/carry_concentration.py --start 2025-01-01
python scripts/verify_archive.py
python scripts/holdout_guard.py --test
python scripts/fill_simulator.py --size-usd 3125
```
