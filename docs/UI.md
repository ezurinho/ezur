# Interfaz

Sistema visual de la terminal. Una sola fuente de verdad: `frontend/src/styles.css`
(tokens en `:root`) más cuatro componentes con dibujo propio (`Sparkline`,
`Gauge`, `EquityChart`, `Chart`).

## Principios

1. **Un acento.** El del tema (cian `#37e0d0` por defecto, cambiable por el
   operador) para lo activo, ámbar `#ffb547` para aviso, rojo
   `#ff5c6c` para pérdida o fallo, verde `#3ddc84` para ganancia. Nada más brilla.
2. **Cifras tabulares.** Todo número usa `font-variant-numeric: tabular-nums` y
   monoespaciado: las columnas se comparan de un vistazo.
3. **Micro-etiquetas.** 11 px, versalitas, `letter-spacing: 0.16em`, color
   apagado. Informan sin competir con el dato.
4. **Hairlines, no sombras.** Bordes de 1 px y gradientes de una línea. El único
   glow es el de estado vivo y el de las agujas de los medidores.
5. **Movimiento con sentido.** Animación de entrada de página, pulso del LED de
   estado y nada más. `prefers-reduced-motion` lo apaga todo.
6. **Dos densidades, un diseño.** Modo básico y avanzado comparten tokens,
   tipografía y geometría; solo cambia cuánto se muestra.
7. **El color nunca es la única señal.** Cada estado lleva texto además de color
   (`running`, `bloqueado`, `ok`), para daltonismo y para capturas en gris.

## Marca

`Logo` (`frontend/src/components/Logo.tsx`): placa redondeada de 48 con la E
tallada en tres barras de 6,5 y huecos de 3,25. A 16 px las barras siguen
midiendo más de 2 px y el hueco no se cierra, que es el punto donde una marca
deja de leerse. La placa toma `--accent`, así que el logo cambia con el tema y
con el acento que elija el operador; las barras se recortan con `--logo-cut` (el
color del fondo) para que la letra se lea como un hueco y no como un trazo.
`public/favicon.svg` y `public/logo.svg` repiten la geometría con el cian fijo,
porque fuera de la app no hay variables CSS.

## Temas y acento

Cinco temas son conjuntos de tokens, no hojas de estilo distintas: los mismos
componentes, cinco ánimos. `hud` (cian), `aurora` (violeta), `ember` (ámbar),
`matrix` (lima) y `daylight` (claro). La elección vive en `localStorage`
(`ezur.theme`) y **Automático** la resuelve contra `prefers-color-scheme` en
vivo: si el sistema cambia con la terminal abierta, el tema cambia con él.

El acento es del operador, no del tema. Ocho presets (`ACCENT_PRESETS`) y un
selector libre escriben `--accent` y `--glow-accent` como variables en línea del
`documentElement`, que ganan sobre cualquier bloque de tema; «restablecer» borra
la variable en vez de adivinar el color del tema. Solo se acepta `#rrggbb` y el
valor guardado se revalida al leerlo (`ezur.accent`).

El gráfico de velas elige tipo de serie —velas, línea o área—, rejilla y leyenda
de O/H/L/C bajo el cursor; las tres preferencias se guardan en `ezur.chart.prefs`
junto al marco temporal.

El chip de versión, junto al selector de tema, dice qué se está ejecutando. Solo
se enciende con el acento y se convierte en enlace cuando `/api/update` ve una
versión más nueva publicada: avisa, no instala. Si la comprobación falla o no hay
canal configurado, el chip se queda quieto y el motivo vive en el `title`; una
terminal de trading no debe gritar por no tener red. La respuesta se reutiliza
diez minutos en `sessionStorage`.

## Dos modos, un motor

El mismo snapshot se puede leer a dos densidades. El interruptor está en el HUD
y la elección vive en `localStorage` (`ezur.ui.mode`): es preferencia de UI, no
estado del motor, así que no viaja al servidor.

| | **Básico** (por defecto la primera vez) | **Avanzado** |
|---|---|---|
| Vistas | Inicio, Gráfico, Historial, Ajustes | las siete |
| Inicio | una frase de estado, dinero de hoy, cuenta, posición abierta, últimas 3 operaciones | KPIs, fases, métricas, sesión, riesgo, posiciones, símbolos |
| Gráfico | velas y precio; sin zonas ni marcadores | velas, zonas, marcadores, series |
| Historial | cuándo, qué hizo, resultado, por qué cerró | precios, unidades, R, motivo, modo, CSV |
| Ajustes | tres cifras: riesgo por operación, pérdida diaria, operaciones al día | todo el árbol de configuración |
| Controles | solo **Detener** (emergencia) y **Reanudar** si está parado | los cuatro |

Reglas que sostienen el modo básico:

1. **Arranca solo.** `auto_start` (por defecto `true`) hace que el motor esté
   `running` al abrir la terminal. En básico no hay botón «Empezar» porque no
   hay nada que empezar; el botón que sí queda es el que para.
2. **Frases, no códigos.** `position_open` se muestra como «Ya tiene una
   operación abierta. Primero tiene que cerrarse». El código crudo sigue
   disponible en Configuración y en la Consola.
3. **Dinero, no ratios.** En básico un resultado es `-121.31`, nunca `-1.0 R`.
   El R es una herramienta de evaluación de estrategia, no de operación.
4. **Nada se esconde sin estar en otro sitio.** Cada vista básica enlaza a
   «modo avanzado»; el modo no es una jaula, es una lente.
5. **Los tres ajustes básicos guardan por el mismo endpoint validado.** El
   formulario no relaja ninguna comprobación del servidor.

## Gráficos

| Gráfico | Qué responde | Dónde |
|---|---|---|
| Velas + medias + volumen | estructura y ritmo del mercado | Gráfico (capas conmutables) |
| Curva de equidad con línea de inicio | ¿estoy por encima de donde empecé? | Estadísticas |
| `MarketPulse` | ¿va subiendo o bajando ahora? | Inicio (básico) |
| Histograma de R | ¿el resultado es homogéneo o depende de dos trades? | Estadísticas |

Los dos canvas de `lightweight-charts` se recrean al cambiar de tema porque no
heredan variables CSS; los SVG (`Sparkline`, `Gauge`, `MarketPulse`) se
recolorean solos. Todo respeta `prefers-reduced-motion`: sin animación, pero con
el trazo completo.

## Razonamiento

Tarjeta `Reasoning`, en Inicio del modo avanzado. Contesta tres cosas en este
orden: qué decidió, por qué, y qué decidió **no** hacer.

| Paso | De dónde sale |
|---|---|
| Datos | `data.provider`, `bars_available`, `staleness_ms`, `quality` |
| Sesión | `session.label`, `phase`, `is_open` |
| Estrategia | `strategy.name`, `state`, `state_label` |
| Señal | `strategy.signal` o `strategy.rejection` |
| Riesgo | `risk.blocked`, `block_reason`, `daily_trades`, `limits` |
| Ejecución | `position`, `orders` |

Cada paso lleva ✓ (cumple), ✗ (no cumple), ! (a medias) o · (sin dato). El
veredicto no se genera: sale de `buildReasoning()` (`frontend/src/reasoning.ts`),
una función pura con tests, y de los códigos ya traducidos en `reasons.ts`; por
eso la tarjeta lleva el sello **determinista**. La convicción solo aparece si la
estrategia publica `signal.strength`, en bandas alta/media/baja: un 0,73 suelto
no se puede accionar. El veto —«rechazó N señales hoy por riesgo»— solo aparece
cuando **no** hay bloqueo activo: con el bloqueo puesto, el recuento y la fecha
ya los da el aviso de arriba. Un panel que siempre felicita es decoración, y dos
frases idénticas seguidas se leen como un fallo.

El reparto con `BlockedBanner` es deliberado: el aviso se queda con lo que solo
él sabe —cuándo fue el último rechazo y qué desbloquea— y la tarjeta con el
motivo en palabras, una sola vez, en el veredicto. Los pasos muestran medidas,
no prosa.

## Laboratorio

Vista de modo avanzado. Corre backtests contra CSV guardados —nunca contra la
sesión viva—, enseña puertas con ✓/✗ y motivo, y compara varias estrategias
sobre las mismas velas. El ranking ordena por esperanza en R y manda al final a
quien no operó.

## Capturas

| Vista | Imagen |
|---|---|
| Inicio (básico) | `docs/img/basic-home.png` |
| Gráfico con medias y volumen | `docs/img/chart-layers.png` |
| Laboratorio | `docs/img/lab.png` |

## Estadísticas: ¿de dónde sale el resultado?

Tres piezas que responden a la misma pregunta desde ángulos distintos:

| Pieza | Qué enseña |
|---|---|
| Distribución de R | los buckets reales de `stats.r_distribution`; la forma de la ventaja |
| Bajo el agua | cuánto se separó la cuenta de su máximo, y cuándo |
| Concentración | qué parte del beneficio bruto aportan las 5 mejores, y el P&L sin ellas |

La frase de concentración cambia con los datos: con menos de 10 operaciones dice
que es ruido; si todo el beneficio sale de una sola, lo dice así. Un panel que
felicita siempre es decoración.

## Paleta de comandos

`Ctrl/Cmd+K`. Contiene las vistas del modo activo, el control del motor, los cinco
temas, el cambio de modo, **enviar alerta de prueba** (con el motivo si falla) y
**reiniciar estadísticas** tras una confirmación que dice cuántas operaciones se
borran. Los atajos `1..n` cambian de vista y `?` abre el mapa de teclas.

## Frescura de los datos

El chip del gráfico no dice «en vivo» por defecto: mide la edad de la última vela.

| Edad | Chip |
|---|---|
| ≤ 150 s | `en vivo` (verde) |
| ≤ 15 min | `retrasado N min` (ámbar) |
| más | `parado hace N min/h` (rojo) |
| sin vela | `sin datos` |

## Tokens

| Token | Valor | Uso |
|---|---|---|
| `--bg` | `#070b11` | Fondo base |
| `--panel` | `#0c121b` | Tarjetas |
| `--panel-2` | `#101825` | Elevación |
| `--line` | `#1b2533` | Bordes |
| `--text` | `#e6edf3` | Texto principal |
| `--text-dim` | `#a9b6c6` | Texto secundario |
| `--muted` | `#6f8096` | Etiquetas |
| `--accent` | `#37e0d0` | Activo, selección, series |
| `--violet` | `#9b8cff` | Categorías y estados de estrategia |
| `--good` / `--bad` / `--warn` | `#3ddc84` / `#ff5c6c` / `#ffb547` | Semántica |
| `--rail` | `232px` | Ancho de la barra lateral |
| `--topbar` | `58px` | Alto del HUD superior |

Contraste de `--text` sobre `--bg`: 15,4:1. De `--muted` sobre `--panel`: 5,1:1.
Ambos por encima de AA.

## Estructura

```
┌ top-bar ─────────────────────────────────────────────────────────┐
│ marca · LED+estado · modo · equity · P&L │ sesión · calidad · WS · reloj │
└──────────────────────────────────────────────────────────────────┘
┌ sidebar ─┬ main ─────────────────────────────────────────────────┐
│ 7 vistas │ page: h2 + cards                                     │
│ icono+txt│ kpi-grid · grid-two · chart-card                      │
│ pie ADR  │                                                       │
└──────────┴───────────────────────────────────────────────────────┘
```

## Componentes con dibujo propio

| Componente | Qué dibuja | Sin dependencias |
|---|---|---|
| `Sparkline` | Línea de tendencia con relleno degradado; verde si sube, rojo si baja | Sí, SVG a mano |
| `Gauge` | Arco de 240°, marca de aviso, porcentaje y cifras absolutas | Sí, SVG a mano |
| `EquityChart` | Curva de equidad | `lightweight-charts` |
| `Chart` | Velas, crosshair, línea de precio | `lightweight-charts` |

`Sparkline` no interpola ni suaviza: dibuja exactamente los puntos que recibe y
con menos de dos devuelve un hueco vacío en lugar de inventar una línea.

`Gauge` recibe valores absolutos, no porcentajes (`62.02 / 741 USD`), y recorta el
arco al 100 % aunque el uso lo supere: un medidor que marca 140 % es un medidor
roto.

## Qué se probó y con qué

| Comprobación | Test |
|---|---|
| 0, 3 y 12 fases sin asumir un número fijo | `src/__tests__/render-contract.test.tsx` |
| Zonas y marcadores con `kind` desconocido | idem |
| Sparkline con un punto no dibuja línea | `src/__tests__/hud.test.tsx` |
| Gauge recorta por encima del 100 % y tolera límite 0 | idem |
| Ningún nombre de activo en el frontend | `tests/test_no_hardcoded_instruments.py` |

## Accesibilidad

- Navegación con `aria-current="page"` en la vista activa.
- Los SVG decorativos llevan `aria-hidden`; los informativos, `role="img"` con
  etiqueta descriptiva.
- `:focus-visible` con contorno cian en botones, vistas y campos.
- El LED de estado es decorativo: el estado siempre aparece como texto.
- Ningún texto depende del color para entenderse.

## Responsive

| Ancho | Comportamiento |
|---|---|
| > 1100 px | HUD completo con reloj |
| 900–1100 px | HUD en dos filas, se oculta el reloj |
| < 900 px | Barra lateral a 64 px, solo iconos; tarjetas a una columna |

## Referencias

Ver `docs/INVESTIGACION_COMPETENCIA.md` §7: Grafana (stat panels con sparkline),
Dear ImGui y egui (densidad y paleta), lucide (trazo de iconos), Bloomberg
(cifras tabulares) y el lenguaje HUD (esquinas, glow solo en lo vivo).
