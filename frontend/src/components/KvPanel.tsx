import type { KvEntry } from "../types";
import { formatEntry, groupEntries, toneClass } from "../utils";

interface Props {
  entries: Record<string, KvEntry>;
  decimals?: number;
  emptyLabel?: string;
}

export function KvPanel({ entries, decimals = 2, emptyLabel = "Sin datos" }: Props) {
  const rows = Object.entries(entries);
  if (rows.length === 0) {
    return <p className="empty" data-kv-empty>{emptyLabel}</p>;
  }
  const groups = groupEntries(entries);
  return (
    <div className="kv-panel" data-kv-panel>
      {groups.map(([group, items]) => (
        <section key={group || "default"}>
          {group ? <h4>{group}</h4> : null}
          <dl>
            {items.map((entry, index) => (
              <div
                key={`${entry.label}-${index}`}
                className={`kv-row ${toneClass(entry.tone)}`}
                data-kv
                data-format={entry.format}
              >
                <dt>{entry.label}</dt>
                <dd>{formatEntry(entry, decimals)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ))}
    </div>
  );
}
