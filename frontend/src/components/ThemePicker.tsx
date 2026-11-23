import { useEffect, useRef, useState } from "react";
import { ACCENT_PRESETS, THEMES, useTheme } from "../theme";

/**
 * Theme picker: swatches, one click, no modal.
 *
 * The swatch shows the theme's own surface and accent, so the choice is visual
 * before it is verbal. Below the themes, the operator can follow the system and
 * pick any accent; both are preferences, so both are remembered.
 * It closes on Escape, on outside click and after picking.
 */
export function ThemePicker() {
  const { theme, choice, setTheme, accent, setAccent, definition } = useTheme();
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

  const currentAccent = accent ?? definition.swatch[1];

  return (
    <div className="theme-picker" ref={rootRef}>
      <button
        type="button"
        className="icon-btn"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-haspopup="true"
        aria-label={`Tema: ${definition.label}${choice === "auto" ? " (automático)" : ""}`}
        title={`Tema: ${definition.label}${choice === "auto" ? " (automático)" : ""}`}
        data-theme-toggle
      >
        <span className="theme-dot" style={{ background: currentAccent }} aria-hidden="true" />
        <span className="theme-dot" style={{ background: definition.swatch[2] }} aria-hidden="true" />
      </button>

      {open ? (
        <div className="theme-popover" role="menu" aria-label="Temas">
          <button
            type="button"
            role="menuitemradio"
            aria-checked={choice === "auto"}
            className={choice === "auto" ? "theme-option active" : "theme-option"}
            onClick={() => {
              setTheme("auto");
              setOpen(false);
            }}
            data-theme-option="auto"
          >
            <span className="theme-swatch" aria-hidden="true">
              <i style={{ background: "#070b11" }} />
              <i style={{ background: "#f4f6fa" }} />
              <i style={{ background: currentAccent }} />
            </span>
            <span className="theme-text">
              <b>Automático</b>
              <small>sigue al sistema · claro de día, oscuro de noche</small>
            </span>
            {choice === "auto" ? <span className="theme-check">✓</span> : null}
          </button>

          {THEMES.map((item) => (
            <button
              key={item.id}
              type="button"
              role="menuitemradio"
              aria-checked={item.id === choice}
              className={item.id === choice ? "theme-option active" : "theme-option"}
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
              {item.id === theme && item.id === choice ? <span className="theme-check">✓</span> : null}
            </button>
          ))}

          <div className="theme-accent" role="group" aria-label="Color de acento">
            <div className="theme-accent-head">
              <span>Acento</span>
              <button
                type="button"
                className="chip"
                onClick={() => setAccent(null)}
                disabled={accent === null}
                data-accent-reset
              >
                restablecer
              </button>
            </div>
            <div className="theme-accent-row">
              {ACCENT_PRESETS.map((preset) => (
                <button
                  key={preset.value}
                  type="button"
                  className={accent === preset.value ? "accent-dot active" : "accent-dot"}
                  style={{ background: preset.value }}
                  aria-label={`Acento ${preset.label}`}
                  aria-pressed={accent === preset.value}
                  title={preset.label}
                  onClick={() => setAccent(preset.value)}
                  data-accent={preset.value}
                />
              ))}
              <label className="accent-custom" title="Cualquier color">
                <input
                  type="color"
                  aria-label="Color de acento personalizado"
                  value={currentAccent}
                  onChange={(event) => setAccent(event.target.value)}
                  data-accent-input
                />
                <span aria-hidden="true">+</span>
              </label>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
