# Interfaz

Sistema visual de la terminal. Una sola fuente de verdad: `frontend/src/styles.css`
(tokens en `:root`) más cuatro componentes con dibujo propio (`Sparkline`,
`Gauge`, `EquityChart`, `Chart`).

## Principios

1. **Un acento.** Cian `#37e0d0` para lo activo, ámbar `#ffb547` para aviso, rojo
   `#ff5c6c` para pérdida o fallo, verde `#3ddc84` para ganancia. Nada más brilla.
2. **Cifras tabulares.** Todo número usa `font-variant-numeric: tabular-nums` y
   monoespaciado: las columnas se comparan de un vistazo.
3. **Micro-etiquetas.** 11 px, versalitas, `letter-spacing: 0.16em`, color
   apagado. Informan sin competir con el dato.
4. **Hairlines, no sombras.** Bordes de 1 px y gradientes de una línea. El único
   glow es el de estado vivo y el de las agujas de los medidores.
5. **Movimiento con sentido.** Animación de entrada de página, pulso del LED de
   estado y nada más. `prefers-reduced-motion` lo apaga todo.
6. **El color nunca es la única señal.** Cada estado lleva texto además de color
   (`running`, `bloqueado`, `ok`), para daltonismo y para capturas en gris.

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
