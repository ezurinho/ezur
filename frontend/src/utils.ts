import type { KvEntry, MetricFormat } from "./types";

const DASH = "—";

const GROUPS = (() => {
  try {
    return new Intl.NumberFormat(navigator.language || "en", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  } catch {
    return null;
  }
})();

/** 24426.72 → 24.426,72 en español, 24,426.72 en inglés: lo decide el navegador. */
function grouped(value: number, decimals: number): string {
  if (decimals !== 2 || !GROUPS) return value.toFixed(decimals);
  return GROUPS.format(value);
}

export function formatValue(
  value: number | string | boolean | null,
  format: MetricFormat,
  decimals = 2,
): string {
  if (value === null || value === undefined) return DASH;
  if (typeof value === "boolean") return value ? "sí" : "no";
  if (typeof value === "string") return value;
  // Un NaN o un Infinity pintado tal cual parece un número medido; es un dato
  // roto. Mismo criterio que un campo ausente.
  if (!Number.isFinite(value)) return DASH;
  switch (format) {
    case "price":
      return grouped(value, decimals);
    case "pct":
      // El separador decimal lo pone el navegador, como en los precios: con el
      // punto fijo, un 0.43 % convive en pantalla con 60.371,20.
      return `${grouped(value, Math.min(decimals, 2))}%`;
    case "ratio":
      return value.toFixed(2);
    case "duration":
      return `${Math.round(value)}m`;
    case "number":
      return value.toFixed(Math.min(decimals, 2));
    default:
      return String(value);
  }
}

/** `Number(null)` es 0: para los datos del servidor, ausente sigue ausente. */
export function toFinite(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatEntry(entry: KvEntry, decimals = 2): string {
  const text = formatValue(entry.value, entry.format, decimals);
  return entry.unit ? `${text} ${entry.unit}` : text;
}

export function toneClass(tone: KvEntry["tone"]): string {
  return `tone-${tone}`;
}

export function formatClock(iso: string | null): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export function formatDate(iso: string | null): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleDateString();
}

/** Trades need the clock: two stops on different bars look identical by date. */
export function formatDateTime(iso: string | null): string {
  if (!iso) return DASH;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return DASH;
  return date.toLocaleString(undefined, {
    year: "2-digit",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function groupEntries(
  entries: Record<string, KvEntry>,
): Array<[string, KvEntry[]]> {
  const groups = new Map<string, KvEntry[]>();
  for (const entry of Object.values(entries)) {
    const key = entry.group ?? "";
    const bucket = groups.get(key) ?? [];
    bucket.push(entry);
    groups.set(key, bucket);
  }
  return Array.from(groups.entries());
}

/**
 * ¿La última vela es de ahora o de hace media hora?
 *
 * Un gráfico que dice «en vivo» con datos de hace 20 minutos es peor que uno
 * que dice «parado». El umbral es 150 s porque la vela de 1m siempre llega algo
 * tarde.
 */
export type Freshness = { tone: "live" | "lag" | "stale" | "none"; label: string };

export function marketFreshness(
  lastBarTs: string | null | undefined,
  nowMs: number = Date.now(),
): Freshness {
  if (!lastBarTs) return { tone: "none", label: "sin datos" };
  const ts = Date.parse(lastBarTs);
  if (Number.isNaN(ts)) return { tone: "none", label: "sin datos" };
  const ageSeconds = Math.max(0, (nowMs - ts) / 1000);
  if (ageSeconds <= 150) return { tone: "live", label: "en vivo" };
  const minutes = Math.round(ageSeconds / 60);
  if (ageSeconds <= 900) return { tone: "lag", label: `retrasado ${minutes} min` };
  return {
    tone: "stale",
    label:
      minutes >= 60
        ? `última vela hace ${Math.round(minutes / 60)} h`
        : `última vela hace ${minutes} min`,
  };
}

export interface StallNotice {
  title: string;
  detail?: string;
  tone: "good" | "bad";
}

/**
 * ¿Hay que avisar de un cambio en la salud del feed?
 *
 * Solo en la transición: un aviso por cada minuto parado sería ruido y el
 * operador acabaría cerrando el que importa. La primera observación no avisa
 * (al abrir la app no se sabe si el feed llevaba rato caído).
 */
export function stallNotice(
  previous: Freshness["tone"] | undefined,
  next: Freshness["tone"],
  label: string,
): StallNotice | null {
  if (previous === undefined) return null;
  const wasStalled = previous === "stale";
  const isStalled = next === "stale";
  if (isStalled && !wasStalled) {
    return {
      title: "El mercado dejó de llegar",
      detail: `Sin velas nuevas (${label}). El bot no puede decidir hasta que vuelva el feed.`,
      tone: "bad",
    };
  }
  if (wasStalled && !isStalled && next !== "none") {
    return { title: "El feed ha vuelto", detail: "Vuelven a llegar velas: el bot reanuda sus decisiones.", tone: "good" };
  }
  return null;
}

/**
 * ¿Se perdió la conexión con el servidor?
 *
 * Si el websocket cae, el snapshot deja de llegar y la pantalla sigue
 * mostrando el último estado como si fuera actual: eso es peor que un error
 * visible. Se avisa una vez al caer y otra al volver; los reintentos
 * intermedios (connecting ↔ closed) no repiten nada. `down` es el pestillo
 * que guarda el estado para no anunciar la misma caída en cada intento.
 */
export type LinkState = "connecting" | "open" | "closed";

/** 42 000 → «hace 42 s»; nunca «hace 0 min». */
export function ageLabel(ms: number): string {
  const seconds = Math.round(Math.max(0, ms) / 1000);
  if (seconds < 5) return "hace un instante";
  if (seconds < 90) return `hace ${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `hace ${minutes} min`;
  return `hace ${Math.round(minutes / 60)} h`;
}

export interface LinkBanner {
  tone: "bad" | "warn";
  title: string;
  detail: string;
}

/**
 * El aviso **permanente** de enlace caído.
 *
 * El toast de `connectionNotice` dura ocho segundos; después la pantalla seguía
 * enseñando el último snapshot sin decir que ya no se actualizaba. Este cartel
 * se queda mientras dure la caída y fecha los datos:
 *  - `closed` → rojo: no hay conexión, nada se refresca.
 *  - `connecting` con datos previos → ámbar: reintentando, cifras congeladas.
 *  - `connecting` sin datos → nada: es la primera carga y las páginas ya
 *    enseñan su esqueleto; un cartel de error aquí sería prematuro.
 */
export function linkBanner(
  connection: LinkState,
  lastUpdateMs: number | null,
  nowMs: number,
): LinkBanner | null {
  if (connection === "open") return null;
  const age = lastUpdateMs === null ? null : Math.max(0, nowMs - lastUpdateMs);
  if (connection === "closed") {
    return {
      tone: "bad",
      title: "Sin conexión con ezur",
      detail:
        age === null
          ? "Aún no ha llegado ningún dato del motor: no hay nada que enseñar."
          : `Los datos de la pantalla son de ${ageLabel(age)}: nada se está actualizando.`,
    };
  }
  if (age === null) return null;
  return {
    tone: "warn",
    title: "Reconectando con ezur",
    detail: `Los datos de la pantalla son de ${ageLabel(age)}. Se reintenta solo; hasta que vuelva, nada se actualiza.`,
  };
}

export function connectionNotice(
  down: boolean,
  next: LinkState,
): { notice: StallNotice | null; down: boolean } {
  if (next === "closed" && !down) {
    return {
      notice: {
        title: "Sin conexión con ezur",
        detail: "No llegan datos nuevos: lo que ves puede estar desactualizado.",
        tone: "bad",
      },
      down: true,
    };
  }
  if (next === "open" && down) {
    return {
      notice: {
        title: "Conexión restaurada con ezur",
        detail: "Vuelven a llegar datos en vivo.",
        tone: "good",
      },
      down: false,
    };
  }
  return { notice: null, down };
}

/**
 * Los límites llegan del servidor con su nombre interno (`daily_loss_limit`).
 * Enseñarlos tal cual obliga a traducir en la cabeza y deja números sin
 * unidad. Aquí se nombran y se formatean; una clave nueva cae en la versión
 * legible, nunca se oculta.
 */
const LIMIT_LABELS: Record<string, string> = {
  daily_loss_limit: "Muro de pérdida diaria",
  soft_brake_at: "Freno suave (mitad de tamaño)",
  initial_capital: "Capital inicial",
  risk_per_trade_pct: "Riesgo por operación",
  max_daily_loss_pct: "Pérdida diaria máxima",
  max_trades_per_day: "Máximo de operaciones al día",
  loss_streak_cooldown_min: "Duración del freno por racha",
  no_trade_after_consecutive_losses: "Freno tras N pérdidas",
};

const MONEY_LIMITS = new Set(["daily_loss_limit", "soft_brake_at", "initial_capital"]);
const PCT_LIMITS = new Set(["risk_per_trade_pct", "max_daily_loss_pct"]);
const MINUTE_LIMITS = new Set(["loss_streak_cooldown_min"]);
// «5.00 operaciones» se lee como una cifra medida de otra cosa.
const COUNT_LIMITS = new Set(["max_trades_per_day", "no_trade_after_consecutive_losses"]);

export function limitEntries(
  limits: Record<string, number>,
): { key: string; label: string; value: string }[] {
  return Object.entries(limits).map(([key, value]) => ({
    key,
    label: LIMIT_LABELS[key] ?? key.replace(/_/g, " "),
    value: MONEY_LIMITS.has(key)
      ? formatValue(value, "price")
      : PCT_LIMITS.has(key)
        ? formatValue(value, "pct")
        : MINUTE_LIMITS.has(key)
          ? `${value} min`
          : COUNT_LIMITS.has(key)
            ? String(Math.round(value))
            : formatValue(value, "number"),
  }));
}

/**
 * El servidor nombra la fase de la sesión en su inglés interno (`open`,
 * `pre`, `close`, `closed`). La pantalla habla español: se traduce aquí, una
 * vez, en vez de dejar la misma palabra en dos idiomas según la vista.
 */
const SESSION_PHASE: Record<string, string> = {
  pre: "antes de abrir",
  open: "abierta",
  close: "cerrando",
  closed: "cerrada",
};

export function phaseLabel(phase: string): string {
  return SESSION_PHASE[phase] ?? phase;
}

/**
 * `long`/`short` son las claves del motor. En pantalla se dice qué hizo:
 * comprar o vender. Un mapa por vista acababa enseñando «long» en una y
 * «compra» en otra.
 */
const SIDE_WORD: Record<string, string> = { long: "compra", short: "venta" };

export function sideLabel(side: string): string {
  return SIDE_WORD[side] ?? side;
}

/**
 * La calidad del feed llega como clave (`degraded`, `stale`). En el HUD y la
 * ficha de sesión se lee como frase; la clave cruda se queda para los tests y
 * para el CSS, que la usa de clase.
 */
const QUALITY_WORD: Record<string, string> = {
  ok: "ok",
  degraded: "con retraso",
  stale: "obsoleta",
  unknown: "sin dato",
};

export function qualityLabel(quality: string): string {
  return QUALITY_WORD[quality] ?? quality;
}

/**
 * El estado del motor llega como clave (`running`, `stopped`). El HUD no debe
 * mezclar inglés y español: la clave se queda para la lógica y el CSS.
 */
const STATUS_WORD: Record<string, string> = {
  idle: "en espera",
  running: "corriendo",
  paused: "en pausa",
  stopped: "detenido",
  error: "error",
};

export function statusLabel(status: string): string {
  return STATUS_WORD[status] ?? status;
}

/**
 * La sesión del motor empieza a las 00:00 UTC, no a la medianoche del reloj
 * que el usuario tiene en pantalla. Sin decirlo, «hoy» y el badge de sesión
 * se leen con el huso equivocado. Se devuelven las dos horas.
 */
export function sessionWindow(
  openIso: string | null | undefined,
  closeIso: string | null | undefined,
): { utc: string; local: string } | null {
  const open = openIso ? Date.parse(openIso) : NaN;
  const close = closeIso ? Date.parse(closeIso) : NaN;
  if (!Number.isFinite(open) || !Number.isFinite(close)) return null;
  const pad = (value: number) => String(value).padStart(2, "0");
  const clock = (ms: number) => {
    const date = new Date(ms);
    return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`;
  };
  const local = (ms: number) =>
    new Date(ms).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  // Si el cierre cae en otro día local, un rango «18:00 → 17:59» parece
  // hacia atrás: el sufijo dice cuántos días cruza.
  const dayOf = (ms: number) => {
    const date = new Date(ms);
    return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate());
  };
  const days = Math.round((dayOf(close) - dayOf(open)) / 86_400_000);
  const suffix = days > 0 ? ` (+${days} día${days === 1 ? "" : "s"})` : "";
  return {
    utc: `${clock(open)} → ${clock(close)}`,
    local: `${local(open)} → ${local(close)}${suffix}`,
  };
}
