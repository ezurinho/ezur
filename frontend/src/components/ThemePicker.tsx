import { useEffect, useRef, useState } from "react";
import { THEMES, useTheme } from "../theme";

/**
 * Theme picker: five swatches, one click, no modal.
 *
 * The swatch shows the theme's own surface and accent, so the choice is visual
 * before it is verbal. It closes on Escape, on outside click and after picking.
 */
export function ThemePicker() {
  const { theme, setTheme, definition } = useTheme();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="theme-picker" ref={rootRef}>
      <button
        type="button"
        className="icon-btn"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={`Tema: ${definition.label}`}
        title={`Tema: ${definition.label}`}
        data-theme-toggle
      >
        <span className="theme-dot" style={{ background: definition.swatch[1] }} aria-hidden="true" />
        <span className="theme-dot" style={{ background: definition.swatch[2] }} aria-hidden="true" />
      </button>

      {open ? (
        <div className="theme-popover" role="menu" aria-label="Temas">
          {THEMES.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitemradio"
              aria-checked={item.id === theme}
              className={item.id === theme ? "theme-option active" : "theme-option"}
              onClick={() => {
                setTheme(item.id);
                setOpen(false);
              }}
              data-theme-option={item.id}
            >
              <span className="theme-swatch" aria-hidden="true">
                <i style={{ background: item.swatch[0] }} />
                <i style={{ background: item.swatch[1] }} />
                <i style={{ background: item.swatch[2] }} />
              </span>
              <span className="theme-text">
                <b>{item.label}</b>
                <small>{item.hint}</small>
              </span>
              {item.id === theme ? <span className="theme-check">✓</span> : null}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
