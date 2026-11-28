# Manifiesto del dataset histórico (ADR 0.2)

Este documento fija el contrato de `data` y el esquema del `manifest.json` que
acompaña al CSV construido desde Binance Vision. El motor y el feed vivo no
cambian: `data.provider=simulated` sigue siendo el camino completo por defecto.

## Configuración

```json
{
  "data": {
    "provider": "vision",
    "market": "spot",
    "symbol": "BTCUSDT",
    "interval": "1m",
    "history_start": "2020-01",
    "history_end": "2026-10",
    "manifest": "data/vision/BTC-USDT.spot.1m.manifest.json"
  }
}
```

| Campo | Valores | Regla |
|---|---|---|
| `provider` | `simulated` (defecto), `vision` | `vision` solo habilita el constructor; no cambia el feed. |
| `market` | `spot`, `um`, `quarterly` | `um` y `quarterly` leen de `futures/um`. |
| `symbol` | `BTCUSDT`, `BTCUSDT_240329` | El símbolo exacto del vendor. `quarterly` exige `_YYMMDD`. |
| `interval` | `1m` | Es la base; 15 m, 1 h, 4 h y 1 D salen del remuestreo. |
| `history_start` | `YYYY-MM` | Primer mes incluido. |
| `history_end` | `YYYY-MM` o `null` | Último mes incluido; si falta, el último mes cerrado en UTC. |
| `manifest` | ruta no vacía | Ruta del manifiesto; conviene que sea específica del dataset. |

El CSV usa el símbolo normalizado `BTC-USDT` (o el par deducido del símbolo), no
el nombre del contrato. Así el motor no aprende rutas ni nombres de exchange.

## Comando

```bash
python -m server.market.vision_builder \
    --config data/config.json \
    --out data/vision/BTC-USDT.spot.1m.csv \
    --cache data/vision
```

El constructor revalida **siempre** el ZIP cacheado contra el `.CHECKSUM`
publicado. Si el checksum no existe, no se puede leer o no coincide, aborta el
mes; no reutiliza un fichero sin control. También escribe un CSV diario por
defecto; `--no-resample` lo desactiva.

## Esquema del manifiesto

Ejemplo abreviado (un mes):

```json
{
  "manifest_version": 1,
  "vendor": "binance_vision",
  "market": "spot",
  "symbol": "BTCUSDT",
  "bot_symbol": "BTC-USDT",
  "interval": "1m",
  "dataset_id": "<sha256 del CSV de 1 m>",
  "range": {
    "start": "2020-01",
    "end": "2020-01",
    "first": "2020-01-01T00:00Z",
    "last": "2020-01-31T23:59Z"
  },
  "rows": 44640,
  "days": 31,
  "expected_days": 31,
  "missing_days": 0,
  "gaps": {"count": 0, "missing_bars": 0, "max_gap_minutes": 0},
  "months": [
    {
      "month": "2020-01",
      "rows": 44640,
      "file": "BTCUSDT-1m-2020-01.zip",
      "url": "https://data.binance.vision/data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2020-01.zip",
      "sha256": "<sha256 del ZIP>"
    }
  ],
  "checksums": {"BTCUSDT-1m-2020-01.zip": "<sha256 del ZIP>"},
  "checksum_coverage": 1.0,
  "rolls": [],
  "continuous": false,
  "funding": {"status": "not_applicable"},
  "derived": {
    "rule": "1D",
    "rows": 31,
    "first": "2020-01-01T00:00:00+00:00",
    "last": "2020-01-31T00:00:00+00:00",
    "dataset_id": "<sha256 del CSV diario>"
  },
  "built_at": "2026-11-28T00:00:00+00:00",
  "code_version": "0.1.0",
  "manifest_sha256": "<sha256 canónico de este objeto sin este campo>"
}
```

### Campos

| Campo | Significado |
|---|---|
| `manifest_version` | Versión del esquema; hoy `1`. |
| `vendor` | `binance_vision`. |
| `market` / `symbol` | Mercado del bot y símbolo exacto del vendor. |
| `bot_symbol` | Símbolo normalizado que aparece en el CSV (`BTC-USDT`). |
| `interval` | `1m`; la base no se remuestrea en el CSV principal. |
| `dataset_id` | SHA-256 del CSV principal; es el identificador que usa el ledger. |
| `range` | Mes solicitado y primera/última barra efectiva. |
| `rows` | Barras escritas, después del recorte trimestral si aplica. |
| `days` | Días UTC distintos con al menos una barra. |
| `expected_days` / `missing_days` | Días naturales entre la primera y la última barra, y los que no tienen ninguna. |
| `gaps` | Huecos entre barras consecutivas: número, minutos ausentes y hueco máximo en minutos. No se rellenan. |
| `months` | Un registro por mes: filas, URL, ZIP y checksum. |
| `checksums` | Mapa ZIP → SHA-256 para comprobar la caché. |
| `checksum_coverage` | `1.0` solo si todos los meses incluidos tienen checksum; el constructor no admite otra cosa. |
| `rolls` | `[]` en Fase 1. Los rolls continuos son Fase 4. |
| `continuous` | `false`; este constructor no crea una serie continua de futuros. |
| `funding` | Estado explícito; en Fase 1 no se incluye funding en el CSV. |
| `derived` | CSV remuestreado (por defecto `1D`) con su propio hash; `null` con `--no-resample`. |
| `built_at` / `code_version` | Fecha UTC de construcción y versión del código. |
| `manifest_sha256` | SHA-256 de la serialización canónica del manifiesto sin este campo. |

`manifest_sha256` se calcula con `json.dumps(..., sort_keys=True,
separators=(",", ":"))` sobre el objeto **sin** `manifest_sha256`. El fichero se
escribe después con indentación; el hash no depende del formato del fichero.

## Invariantes

- El checksum del ZIP se comprueba contra el `.CHECKSUM` de Binance; no hay
  modo «sin checksum».
- Los timestamps deben ser estrictamente crecientes. Un duplicado o un salto
  hacia atrás rechaza el dataset.
- Se valida `low <= open, close <= high` y `volume >= 0`.
- Un hueco de más de un día rechaza el dataset; los huecos menores se declaran
  en `gaps` y no se rellenan.
- Los meses se piden completos. Un mes que Binance no publica se convierte en
  un error explícito; no se confunde con un mes vacío.
- En trimestrales se corta en la última barra con volumen. Las barras planas
  con volumen 0 que Binance publica después del vencimiento no forman parte del
  contrato. `contract.expiry` documenta el último viernes a las 08:00 UTC.
- El CSV principal usa timestamps UTC compactos de minuto (`...T00:00Z`), que
  `datetime.fromisoformat` interpreta como UTC, y números sin ceros decimales
  sobrantes; el valor no se redondea.

## Límites de esta fase

Este manifiesto **no** construye la serie continua de trimestrales, no calcula
rolls y no descarga funding ni mark price. Para un trimestral valida un contrato
individual y deja `rolls: []`; la costura continua se implementa en Fase 4. El
campo `funding` lo declara en vez de fingir cobertura.