import { useEffect } from "react";

interface Props {
  open: boolean;
  onClose: () => void;
  views: { label: string; hint: string }[];
}

/**
 * `?` opens the real key map, read from the same view list the sidebar uses.
 *
 * A shortcuts panel that lists keys the app does not implement is worse than no
 * panel: it teaches the operator to distrust the UI.
 */
export function Shortcuts({ open, onClose, views }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="palette-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <div className="palette shortcuts" role="dialog" aria-modal="true" aria-label="Atajos de teclado">
        <header className="shortcuts-head">
          <h3>Atajos</h3>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Cerrar atajos">
            ×
          </button>
        </header>
        <div className="shortcuts-body">
          <div className="shortcuts-group">
            <span className="shortcuts-title">Global</span>
            <Row keys={["Ctrl", "K"]} label="Paleta de comandos" />
            <Row keys={["?"]} label="Esta ayuda" />
            <Row keys={["Esc"]} label="Cerrar capa o diálogo" />
            <Row keys={["Básico", "Avanzado"]} label="Cambiar de densidad (en el HUD)" />
          </div>
          <div className="shortcuts-group">
            <span className="shortcuts-title">Ir a una vista</span>
            {views.map((view, index) => (
              <Row key={view.label} keys={[String(index + 1)]} label={`${view.label} · ${view.hint}`} />
            ))}
          </div>
        </div>
        <footer className="palette-foot">
          <span className="muted">
            Los números funcionan mientras no estés escribiendo en un campo.
          </span>
        </footer>
      </div>
    </div>
  );
}

function Row({ keys, label }: { keys: string[]; label: string }) {
  return (
    <div className="shortcut-row">
      <span className="shortcut-keys">
        {keys.map((key) => (
          <kbd key={key}>{key}</kbd>
        ))}
      </span>
      <span>{label}</span>
    </div>
  );
}
