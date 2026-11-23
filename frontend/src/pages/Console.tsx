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

export function ConsolePage() {
  const { connection } = useStore();
  const [events, setEvents] = useState<EventRow[]>([]);
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
          setError(null);
        })
        .catch((cause: Error) => setError(cause.message));
    };
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
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
        <span className="muted small">{connection === "open" ? "en vivo" : connection}</span>
      </h2>

      <div className="console-bar">
        <div className="segmented" role="group" aria-label="Nivel">
          {LEVELS.map((value) => (
            <button
              key={value}
              type="button"
              className={level === value ? "active" : undefined}
              onClick={() => setLevel(value)}
              aria-pressed={level === value}
              data-console-level={value}
            >
              {value} <span className="count">{counts[value] ?? 0}</span>
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
            {events.length === 0 ? "Sin eventos todavía" : "Ningún evento con ese filtro"}
          </p>
        ) : (
          <ul className="event-list">
            {visible.map((event) => (
              <li key={event.id} className={`event event-${event.level}`}>
                <span className="event-ts">{event.ts.slice(11, 19)}</span>
                <span className="event-level">{event.level}</span>
                <span className="event-category">{event.category}</span>
                <span className="event-message">{event.message}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
      <p className="muted small">
        {visible.length} de {events.length} eventos · se refresca cada 3 s salvo que
        pauses o cambies de pestaña
      </p>
    </div>
  );
}
