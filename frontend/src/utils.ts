import type { KvEntry, MetricFormat } from "./types";

const DASH = "—";

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
      return value.toFixed(decimals);
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
