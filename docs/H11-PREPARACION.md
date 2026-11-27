# H11 lista antes de la ventana

**Fecha:** 2026-11-27
**Estado:** motor parametrizado, control de H5 revalidado y panel base congelado
con hashes. Queda una decisión (el arranque de la ventana) y una descarga (la
rebanada de evaluación) antes de la única lectura.
**No se ha medido H11.** Ni una simulación con sus reglas sobre datos nuevos; el
holdout sigue sellado y la familia sigue siendo el ensayo 54.

## 1. Coste parametrizado

`replay(..., cost_side=...)` cobra el mismo parámetro en la entrada y en la
salida. El valor por defecto sigue siendo 6 pb, así que H5 y la medición de H10
no cambian; H11 pasará `0.001` (10 pb por lado), como fija su pre-registro.

El motor también acepta ya `min_week_coverage`, la regla de H11 de exigir al
menos un 80 % de días con funding en la ventana de 7. Con `None` —el defecto y lo
que usan H5 y H10— promedia los días no nulos, igual que antes.

## 2. Control de H5 revalidado

`python scripts/validate_h5_engine.py` sale con código distinto de cero si
cualquiera de los tres controles falla.

| Control | Resultado |
|---|---|
| H5 a 6 pb | **PASA**: 400 episodios, 800 operaciones, PF 1,1114, esperanza 0,0301 R, precio 6.672,63, funding 856,80, patas 6.029,43, compuesto 6.086,46 |
| H5 a 10 pb | **PASA**: costes 2.500 USD (800 × 3,125), precio y funding intactos, patas 5.029,43 |
| H5 con cobertura del 80 % | **PASA**: 400 episodios; los majors tienen funding diario, así que el filtro no los toca |

El tercer control no valida la regla sobre el panel de H11 —no hay dato todavía—,
sólo comprueba que el filtro está cableado y que no altera el control.

## 3. Panel base congelado

`scripts/freeze_h11_panel.py` verifica que los CSV coinciden con el manifiesto de
`data/h10ext` y escribe `data/h11/freeze.json`. El manifiesto se versiona en el
repo, así que los hashes quedan publicados antes de la primera lectura.

| Pieza | SHA-256 |
|---|---|
| `funding_daily.csv` | `dac6ad41fcb197d1f17a0c698c6027a65d6cb00e4ebc71f9b2ea8b282c0afbb4` |
| `perp_daily.csv` | `c2a74f508149e3ac5b8840252771f25ce64ef91be98b55389fbec046d9723ab3` |
| `PRE-REGISTRO-H11.md` | `f9951f3b9efe71bd290ae899df3917c223e147f7227c6fb0ceaab3f9e4ce1865` |
| `PRE-REGISTRO-H10.md` | `c43d8bf0837dcbbc5fdbc2cac3260340501c4a5585ec15406eed7bb879b7b0dc` |
| `fetch_h10_data.py` | `0d30d4dc8ae7fa322c50dd083bb49311a7792dad58225f1a2edf20da60a37d6a` |
| `extend_panel_2020.py` | `67e4ec42b62e1942ebb02f64261f5c233f1aea8d9700a150caae52c88fdb6e05` |
| `validate_h5_engine.py` | `7fa5ab728971bdd9a8094c5d6e3f95f01d5aa91fe764105fcb2655240184db07` |

Base: `data/h10ext`, 899 símbolos, 601.450 filas de funding y 642.189 de
perpetuos, 2020-01-01/2026-10-31.

La **rebanada de evaluación** (2027-06-01/2028-05-31) no existe todavía. Se
descargará con el mismo `fetch_h10_data.py`, se añadirá al manifiesto con su
hash y sólo entonces se correrá el motor, una vez.

## 4. La decisión pendiente: cuándo empieza la ventana

El pre-registro fija la ventana en 2027-06-01/2028-05-31. El motor exige 90 filas
de historia para la primera señal, y el holdout termina el 2027-05-31. Si no se
usa el holdout —no se debe—, **la primera señal posible es el 2027-08-30**.

El coste de esperar es de unas 13 semanas: a 12,3 operaciones por semana son ~160
operaciones, ~80 episodios de los ~320 de la ventana. Quedan ~240, muy por encima
de los 47 que exige la puerta de potencia con el suelo de 40 pb.

Dos salidas, y ninguna se toma aquí:

- **Enmendar la ventana a 2027-08-30/2028-05-31** (recomendada): mantiene el
  sello y pierde sólo el arranque.
- **Usar el holdout como calentamiento**: rompe el sello para siempre y no lo
  recomiendo.

El pre-registro está congelado y no se toca; el cambio, si se hace, se decide
antes de medir y se documenta aparte.

## 5. Lo que no se ha hecho

- No se ha corrido H11: no hay ninguna simulación con k = 4, 10 pb ni la ventana
  futura.
- No se ha leído el holdout ni se ha usado como historia.
- No se añaden ensayos: H11 sigue siendo el 54, con una sola lectura.
