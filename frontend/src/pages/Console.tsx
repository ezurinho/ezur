import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";

interface EventRow {
  id: number;
  ts: string;
  level: string;
  category: string;
  message: string;
}

export function ConsolePage() {
  const { connection } = useStore();
  const [events, setEvents] = useState<EventRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => {
      api
        .events(200)
        .then((rows) => setEvents(rows as unknown as EventRow[]))
        .catch((cause: Error) => setError(cause.message));
    };
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="page">
      <h2>Consola</h2>
      <p className="muted small">WebSocket: {connection}</p>
      {error ? <p className="tone-bad">{error}</p> : null}
      <section className="card console">
        {events.length === 0 ? (
          <p className="empty">Sin eventos</p>
        ) : (
          <ul className="event-list">
            {events.map((event) => (
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
    </div>
  );
}
