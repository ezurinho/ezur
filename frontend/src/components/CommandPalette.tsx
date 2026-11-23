import { useEffect, useMemo, useRef, useState } from "react";

export interface PaletteItem {
  id: string;
  label: string;
  hint?: string;
  group: string;
  keywords?: string;
  run: () => void;
}

interface Props {
  open: boolean;
  items: PaletteItem[];
  onClose: () => void;
}

function score(item: PaletteItem, query: string): number {
  if (!query) return 1;
  const haystack = `${item.label} ${item.hint ?? ""} ${item.keywords ?? ""}`.toLowerCase();
  const needle = query.toLowerCase();
  if (haystack.includes(needle)) return 3;
  // "par" should still find "pausar": subsequence match, cheap and forgiving.
  let cursor = 0;
  for (const char of haystack) {
    if (char === needle[cursor]) cursor += 1;
    if (cursor === needle.length) return 1;
  }
  return 0;
}

/**
 * Ctrl/Cmd+K: jump to a view or run a control from the keyboard.
 *
 * The sidebar answers "where am I"; the palette answers "take me there" without
 * a mouse. Filtering is substring first, subsequence second, so a beginner can
 * type "para" and still hit "Pausar".
 */
export function CommandPalette({ open, items, onClose }: Props) {
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const results = useMemo(() => {
    const ranked = items
      .map((item) => ({ item, weight: score(item, query) }))
      .filter((entry) => entry.weight > 0)
      .sort((a, b) => b.weight - a.weight);
    return ranked.map((entry) => entry.item);
  }, [items, query]);

  useEffect(() => {
    if (!open) return;
    setQuery("");
    setActive(0);
    const focus = window.setTimeout(() => inputRef.current?.focus(), 20);
    return () => window.clearTimeout(focus);
  }, [open]);

  useEffect(() => {
    setActive((current) => (current >= results.length ? 0 : current));
  }, [results.length]);

  if (!open) return null;

  const runAt = (index: number) => {
    const item = results[index];
    if (!item) return;
    item.run();
    onClose();
  };

  return (
    <div
      className="palette-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="palette" role="dialog" aria-modal="true" aria-label="Paleta de comandos">
        <input
          ref={inputRef}
          className="palette-input"
          value={query}
          placeholder="Ir a… o escribe una acción (detener, reanudar, tema)"
          onChange={(event) => setQuery(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              onClose();
            } else if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((current) => (results.length ? (current + 1) % results.length : 0));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((current) =>
                results.length ? (current - 1 + results.length) % results.length : 0,
              );
            } else if (event.key === "Enter") {
              event.preventDefault();
              runAt(active);
            }
          }}
          aria-label="Buscar vista o acción"
          data-palette-input
        />
        <ul className="palette-list" role="listbox" aria-label="Resultados">
          {results.length === 0 ? <li className="palette-empty">Nada coincide con «{query}»</li> : null}
          {results.map((item, index) => (
            <li key={item.id} role="option" aria-selected={index === active}>
              <button
                type="button"
                className={index === active ? "palette-item active" : "palette-item"}
                onMouseEnter={() => setActive(index)}
                onClick={() => runAt(index)}
                data-palette-item={item.id}
              >
                <span className="palette-group">{item.group}</span>
                <span className="palette-label">{item.label}</span>
                {item.hint ? <span className="palette-hint">{item.hint}</span> : null}
              </button>
            </li>
          ))}
        </ul>
        <footer className="palette-foot">
          <span>
            <kbd>↑</kbd>
            <kbd>↓</kbd> mover
          </span>
          <span>
            <kbd>Enter</kbd> abrir
          </span>
          <span>
            <kbd>Esc</kbd> cerrar
          </span>
          <span className="muted">? atajos · ⌘K / Ctrl+K</span>
        </footer>
      </div>
    </div>
  );
}
