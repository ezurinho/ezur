# Diseño: Hallmark como suelo, no como rediseño

La skill [hallmark](https://github.com/nutlope/hallmark) (MIT, de Together AI)
vive en `.agents/skills/hallmark`. No es un tema ni una librería: es un conjunto
de reglas que impiden que una pantalla generada parezca generada — colores por
token, nada de `transition: all`, `overflow-x: clip`, foco visible, movimiento
reducido, ni una métrica inventada.

Se instaló para que **lo que se construya a partir de ahora** pase ese suelo. La
UI que ya existía no se rediseña por esto: la propia skill prohíbe tocar un
diseño existente salvo que se pida con `/hallmark redesign <ruta>`.

## Cómo se pasa

```bash
# el CSS construido (lo que se mide de verdad en una SPA)
node .agents/skills/hallmark/scripts/sloplint.mjs frontend/dist/assets/index-*.css

# y las páginas, cuando las haya con su CSS dentro
node .agents/skills/hallmark/scripts/sloplint.mjs frontend/dist
```

Sin `--render` hace análisis estático; con `--render` añade comprobaciones en
Chrome real y necesita `puppeteer-core`.

Sobre `dist/index.html` el pase estático da un falso positivo: la página construida
no lleva CSS (está en un asset aparte), así que avisa de que faltan reglas que sí
están en la hoja. Por eso las cifras de abajo son las del CSS.

## Medición del 24 de noviembre de 2026

Hoja construida: **99 FAIL, 145 REFLEX, 13 WARN**. Por regla:

| Regla | Cuántas | Qué es |
|---|---|---|
| 48 | 68 | color o `font-family` fuera de `:root` |
| 67 | 22 | etiqueta en mayúsculas espaciadas |
| 10a | 4 | transición sobre `width` / `left` |
| 34 | 2 | `100vw` en dos superposiciones fijas |
| 56 | 1 | dos elementos `sticky top: 0` |
| 62 | 1 | contenido que necesita JS para verse |
| 20 | 1 | falta el sello de Hallmark |

Y dos REFLEX de acabado: 134 medidas fuera de la retícula de 4 px (`24b`) y 11
etiquetas en mono (`64`).

## Lo que se arregló

- **34 (página)** — `overflow-x: clip` en `html` y `body`. `clip` no crea
  contenedor de scroll: la página sigue scrolleando en vertical y deja de poder
  abrir una barra horizontal.
- **7a** — `::selection` usaba `#fff` puro; ahora usa `var(--text)`, que ya está
  tintado hacia el acento.

## Lo que se deja como está, con motivo

- **48 (68)** — tokenizar 68 literales de color es reescribir el sistema de color
  de 3.724 líneas de CSS. Es un rediseño, no una corrección. Es la deuda real.
- **67 (22) y 64 (11)** — etiquetas en mono, mayúsculas y espaciadas. En un
  terminal de trading es la voz de la casa: cifras y rótulos comparten mono para
  que el ojo alinee columnas. La regla existe para páginas de marketing.
- **10a (4)** — `.simple-bar span`, `.concentration-track > span`,
  `.conviction-fill` y `.trade-range-price` animan `width` o `left` con el valor
  puesto desde el estado de React. Pasarlas a `transform: scaleX()` es correcto y
  es trabajo de componente y CSS; se hace al tocar esos componentes.
- **34 (2)** — `.toast-stack` y `.palette` son `position: fixed` y se dimensionan
  con `min(340px, calc(100vw - 36px))`. Ahí `width: 100%` no significa el hueco,
  significa la pantalla; la corrección es reposicionarlas con `inset`, no un
  cambio de una línea.
- **56** — el `thead` pegajoso vive dentro de su propio contenedor con scroll, no
  bajo la barra superior; desplazarlo lo rompería.
- **62** — la app es una SPA de React: sin JS no hay nada, por construcción. La
  regla apunta a páginas que deben leerse con el script apagado.
- **20** — el sello de Hallmark va en la primera línea del CSS de una página
  construida con Hallmark. Esta se construyó antes y con su propio sistema
  (`:root` con nombres en español y comentarios de intención).
- **24b (134)** — la retícula es de 2 px, no de 4. Cambiarla mueve cada margen del
  producto para satisfacer una preferencia.

El suelo que sí se cumple desde ya: sin `transition: all`, sin animar `top` ni
`height`, foco visible, `prefers-reduced-motion`, nada de métricas inventadas —
las cifras de la UI salen del backtest o del broker, nunca de un placeholder.
