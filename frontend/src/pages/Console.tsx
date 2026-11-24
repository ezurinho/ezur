import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";

interface EventRow {
  id: number;
  ts: string;
  level: string;
  category: string;
  message: string;
}

const LEVELS = ["todos", "info", "warn", "error"] as const;
type Level = (typeof LEVELS)[number];

/**
 * La hora del evento en tu reloj, como el resto de la app.
 *
 * El servidor manda ISO en UTC; enseñar el recorte crudo ponía la consola dos
 * horas por detrás del «hace 3 min» del aviso. La fecha solo aparece cuando el
 * evento no es de hoy, para no creer que lo de ayer pasó ahora.
 */
export function localStamp(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(11, 19);
  const time = date.toLocaleTimeString(undefined, { hour12: false });
  if (date.toDateString() === now.toDateString()) return time;
  const day = date.toLocaleDateString(undefined, { day: "2-digit", month: "2-digit" });
  return `${day} ${time}`;
}

export interface ConsoleEmptyState {
  events: number;
  loaded: boolean;
  paused: boolean;
  hidden: boolean;
}

/**
 * «Sin eventos» solo cuando de verdad no hay eventos.
 *
 * Antes de la primera lectura, o con la lista en pausa, o con la pestaña en
 * segundo plano, el array está vacío por construcción: decir «sin eventos»
 * entonces afirmaba algo que no se ha comprobado.
 */
export function consoleEmptyText(state: ConsoleEmptyState): string {
  if (state.events > 0) return "Ningún evento con ese filtro";
  if (state.paused) return "Lista en pausa: los eventos se cargan al reanudarla.";
  if (state.hidden) return "Pestaña en segundo plano: la consola no se refresca mientras está oculta.";
  if (!state.loaded) return "Leyendo los últimos eventos…";
  return "El servidor no tiene eventos registrados todavía.";
}

export function ConsolePage() {
  const { connection } = useStore();
  const [events, setEvents] = useState<EventRow[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [tabHidden, setTabHidden] = useState(
    () => typeof document !== "undefined" && document.visibilityState === "hidden",
  );
  const [error, setError] = useState<string | null>(null);
  const [level, setLevel] = useState<Level>("todos");
  const [category, setCategory] = useState("todas");
  const [query, setQuery] = useState("");
  const [paused, setPaused] = useState(false);
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    const load = () => {
      // Pausar no detiene el bot: detiene la lista. Es lo que hace falta para
      // leer una traza sin que se mueva bajo el cursor.
      if (pausedRef.current || document.visibilityState === "hidden") return;
      api
        .events(300)
        .then((rows) => {
          setEvents(rows as unknown as EventRow[]);
          setLoaded(true);
          setError(null);
        })
        .catch((cause: Error) => setError(cause.message));
    };
    // Al volver a la pestaña se carga de inmediato: esperar hasta 3 s con la
    // lista vieja en pantalla parece que la consola se ha quedado atrás.
    const onVisibility = () => {
      const hidden = document.visibilityState === "hidden";
      setTabHidden(hidden);
      if (!hidden) load();
    };
    load();
    const timer = setInterval(load, 3000);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  const counts = useMemo(() => {
    const base: Record<string, number> = { todos: events.length, info: 0, warn: 0, error: 0 };
    for (const event of events) {
      base[event.level] = (base[event.level] ?? 0) + 1;
    }
    return base;
  }, [events]);

  const categories = useMemo(
    () => ["todas", ...Array.from(new Set(events.map((event) => event.category))).sort()],
    [events],
  );

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return events.filter((event) => {
      if (level !== "todos" && event.level !== level) return false;
      if (category !== "todas" && event.category !== category) return false;
      if (needle && !event.message.toLowerCase().includes(needle)) return false;
      return true;
    });
  }, [events, level, category, query]);

  return (
    <div className="page">
      <h2 className="page-title">
        Consola
        <span className="muted small">
          {connection === "open"
            ? "en vivo"
            : connection === "connecting"
              ? "conectando"
              : "sin conexión · sin eventos nuevos"}
        </span>
      </h2>

      <div className="console-bar">
        <div
          className="segmented"
          role="group"
          aria-label="Nivel"
          title="Las cuentas cubren solo los últimos 300 eventos cargados"
        >
          {LEVELS.map((value) => (
            <button
              key={value}
              type="button"
              className={level === value ? "active" : undefined}
              onClick={() => setLevel(value)}
              aria-pressed={level === value}
              data-console-level={value}
            >
              {value} <span className="count">{loaded ? counts[value] ?? 0 : "…"}</span>
            </button>
          ))}
        </div>
        <label className="console-field">
          <span className="sr-only">Categoría</span>
          <select value={category} onChange={(event) => setCategory(event.target.value)}>
            {categories.map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label className="console-field">
          <span className="sr-only">Buscar en los mensajes</span>
          <input
            type="search"
            placeholder="buscar…"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <button
          type="button"
          className={`btn ${paused ? "btn-warn" : ""}`}
          onClick={() => setPaused((value) => !value)}
          aria-pressed={paused}
        >
          {paused ? "Seguir leyendo (en pausa)" : "Pausar la lista"}
        </button>
      </div>

      {error ? <p className="tone-bad">{error}</p> : null}

      <section className="card console" aria-live="off">
        {visible.length === 0 ? (
          <p className="empty">
            {consoleEmptyText({
              events: events.length,
              loaded,
              paused,
              hidden: tabHidden,
            })}
          </p>
        ) : (
          <ul className="event-list">
            {visible.map((event) => (
              <li key={event.id} className={`event event-${event.level}`}>
                <span className="event-ts" title={new Date(event.ts).toLocaleString()}>
                  {localStamp(event.ts)}
                </span>
                <span className="event-level">{event.level}</span>
                <span className="event-category">{event.category}</span>
                <span className="event-message">{event.message}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="muted small">
        {loaded
          ? `${visible.length} visibles de los últimos ${events.length} eventos`
          : "Sin lectura todavía"}{" "}
        · se refresca cada 3 s salvo que pauses o cambies de pestaña
      </p>
    </div>
  );
}
