# Registro de ensayos del laboratorio

Este fichero existe para que el DSR y el PBO se calculen sobre **todos** los
intentos, no solo sobre el que se enseña. Cada fila es una variante que llegó a
medirse; las que se descartaron antes de medir no cuentan, pero se listan para
que no haya dudas.

## Familias y variantes medidas

| Familia | Variantes | Periodo de medida | Resultado OOS | Archivo |
|---|---:|---|---|---|
| SMA 15 m (rejilla canónica) | 5 | 2020-2026, WFA/CPCV | PF 0,9763, esperanza +0,0252 R, PBO 0,4087, DSR 0,0912 | `docs/ARCHIVO-SMA-15M.md` |
| Donchian 1 h (H1) | 5 | 2025-01/2026-11 | PF 0,7529, esperanza -0,0436 R, P&L -545 USD | `docs/ARCHIVO-H1.md` |
| Carry BTC (H2) | 5 | 2025-01/2026-11 | 4 episodios, +2,35 % anual, IC80 1,85-6,75 % | `docs/ARCHIVO-H2.md` |
| Momentum cross-sectional (H3) | 5 | 2025-01/2026-11 | PF 0,7046, esperanza -0,0447 R, P&L -30,9 % | `docs/ARCHIVO-H3.md` |
| Pares spot contra BTC (H4) | 5 | 2025-01/2026-11 | PF 0,9235, esperanza -0,0044 R, P&L -2,75 % | `docs/ARCHIVO-H4.md` |

**Total de variantes medidas:** 25. A ellas se suman las pruebas de viabilidad
exploratorias (umbrales de funding, ventanas de momentum) que no llegaron a
pre-registro; no se usan para coronar nada, pero inflan el espacio de búsqueda.
El DSR de cualquier hipótesis futura debe declarar al menos 25 ensayos, no 5.

## Lo que el registro ya dice

- Ninguna de las 25 variantes supera las puertas duras del plan en OOS.
- La mejor expectativa OOS es la del carry (+2,35 % anual), pero con 4
  episodios; no es una muestra.
- El mejor PF de desarrollo (momentum 14/7, 1,3523) se convierte en 1,0468 en
  OOS; el mejor PF OOS (carry, 34,33) es degenerado por tener un solo perdedor.
- El patrón se repite: el bruto se desvanece al cambiar de régimen y el coste no
  es la causa principal (0,006-0,03 R por operación, muy por debajo de 0,25 R).

## Regla de higiene

Antes de medir una hipótesis nueva se añade aquí su familia y su número de
variantes. Si el DSR se calcula sin este registro, el resultado no se acepta.
No se borran filas: una hipótesis archivada sigue contando para el múltiple
testing.
