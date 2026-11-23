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
  switch (format) {
    case "price":
      return grouped(value, decimals);
    case "pct":
      return `${value.toFixed(Math.min(decimals, 2))}%`;
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
    label: minutes >= 60 ? `parado hace ${Math.round(minutes / 60)} h` : `parado hace ${minutes} min`,
  };
}
