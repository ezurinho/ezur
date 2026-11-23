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
  { id: "config", label: "Configuración", hint: "ajustes" },
  { id: "console", label: "Consola", hint: "eventos" },
];

interface Props {
  active: string;
  onSelect: (id: string) => void;
}

export function Sidebar({ active, onSelect }: Props) {
  return (
    <nav className="sidebar" aria-label="Vistas">
      <span className="sidebar-title">consola</span>
      {VIEWS.map((view) => (
        <button
          key={view.id}
          type="button"
          className={active === view.id ? "nav-item active" : "nav-item"}
          onClick={() => onSelect(view.id)}
          aria-current={active === view.id ? "page" : undefined}
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            {ICONS[view.id]}
          </svg>
          {view.label}
        </button>
      ))}
      <div className="sidebar-foot">
        <b>paper</b> · sin broker
        <br />
        adaptador live: pendiente
        <br />
        ADR 0.3
      </div>
    </nav>
  );
}
