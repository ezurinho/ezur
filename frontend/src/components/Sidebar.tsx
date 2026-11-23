import type { JSX } from "react";

export interface ViewDefinition {
  id: string;
  label: string;
  hint: string;
}

const ICONS: Record<string, JSX.Element> = {
  home: (
    <path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4v-5H9v5H5a1 1 0 0 1-1-1z" />
  ),
  chart: (
    <>
      <path d="M4 4v16h16" />
      <path d="M8 15l3.5-4.5L15 13l4-6.5" />
    </>
  ),
  operations: (
    <>
      <path d="M5 7h14M5 12h9M5 17h5" />
      <circle cx="18" cy="16" r="2.5" />
    </>
  ),
  history: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  stats: (
    <>
      <path d="M4 20V9M10 20V4M16 20v-7M22 20H2" />
    </>
  ),
  lab: (
    <>
      <path d="M9 3h6M10 3v5.5L5.5 17a3 3 0 0 0 2.7 4h7.6a3 3 0 0 0 2.7-4L14 8.5V3" />
      <path d="M7.5 14h9" />
    </>
  ),
  config: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3v2.5M12 18.5V21M4.2 7.5l2.2 1.3M17.6 15.2l2.2 1.3M19.8 7.5l-2.2 1.3M6.4 15.2l-2.2 1.3" />
    </>
  ),
  console: (
    <>
      <rect x="3" y="4.5" width="18" height="15" rx="2" />
      <path d="M7 10l2.5 2L7 14M12.5 14.5H17" />
    </>
  ),
};

export const VIEWS: ViewDefinition[] = [
  { id: "home", label: "Inicio", hint: "estado" },
  { id: "chart", label: "Gráfico", hint: "precio" },
  { id: "operations", label: "Operaciones", hint: "órdenes" },
  { id: "history", label: "Historial", hint: "trades" },
  { id: "stats", label: "Estadísticas", hint: "métricas" },
  { id: "lab", label: "Laboratorio", hint: "backtest" },
  { id: "config", label: "Configuración", hint: "ajustes" },
  { id: "console", label: "Consola", hint: "eventos" },
];

/** Four views for a beginner: what is happening, the price, the history, the knobs. */
export const SIMPLE_VIEWS: ViewDefinition[] = [
  { id: "home", label: "Inicio", hint: "resumen" },
  { id: "chart", label: "Gráfico", hint: "precio" },
  { id: "history", label: "Historial", hint: "resultados" },
  { id: "settings", label: "Ajustes", hint: "básico" },
];

const SIMPLE_ICONS: Record<string, JSX.Element> = {
  settings: (
    <>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </>
  ),
};

interface Props {
  active: string;
  onSelect: (id: string) => void;
  simple?: boolean;
}

export function Sidebar({ active, onSelect, simple = false }: Props) {
  const views = simple ? SIMPLE_VIEWS : VIEWS;
  return (
    <nav className="sidebar" aria-label="Vistas" data-mode={simple ? "simple" : "advanced"}>
      <span className="sidebar-title">{simple ? "básico" : "consola"}</span>
      <span
        className="nav-rail"
        aria-hidden="true"
        style={{ transform: `translateY(${views.findIndex((item) => item.id === active) * 39}px)` }}
      />
      {views.map((view, index) => (
        <button
          key={view.id}
          type="button"
          className={active === view.id ? "nav-item active" : "nav-item"}
          onClick={() => onSelect(view.id)}
          aria-current={active === view.id ? "page" : undefined}
          data-shortcut={index + 1}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {ICONS[view.id] ?? SIMPLE_ICONS[view.id]}
          </svg>
          <span className="nav-label">{view.label}</span>
          <kbd className="nav-key">{index + 1}</kbd>
        </button>
      ))}
      <div className="sidebar-foot">
        {simple ? (
          <>
            <b>modo básico</b>
            <br />
            solo lo importante
            <br />
            cambia a Avanzado arriba
          </>
        ) : (
          <>
            <b>paper</b> · sin broker
            <br />
            adaptador live: pendiente
            <br />
            ADR 0.3
          </>
        )}
      </div>
    </nav>
  );
}
