export interface ViewDefinition {
  id: string;
  label: string;
}

export const VIEWS: ViewDefinition[] = [
  { id: "home", label: "Inicio" },
  { id: "chart", label: "Gráfico" },
  { id: "operations", label: "Operaciones" },
  { id: "history", label: "Historial" },
  { id: "stats", label: "Estadísticas" },
  { id: "config", label: "Configuración" },
  { id: "console", label: "Consola" },
];

interface Props {
  active: string;
  onSelect: (id: string) => void;
}

export function Sidebar({ active, onSelect }: Props) {
  return (
    <nav className="sidebar">
      {VIEWS.map((view) => (
        <button
          key={view.id}
          type="button"
          className={active === view.id ? "nav-item active" : "nav-item"}
          onClick={() => onSelect(view.id)}
        >
          {view.label}
        </button>
      ))}
    </nav>
  );
}
