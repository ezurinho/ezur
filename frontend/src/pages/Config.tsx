import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast } from "../toast";
import { KvPanel } from "../components/KvPanel";
import { useStore } from "../store";

function kv(
  label: string,
  value: number | string | boolean | null,
  tone: "neutral" | "good" | "bad" | "warn" = "neutral",
  format: "text" | "number" = "text",
) {
  return { label, value, format, unit: null, tone, group: null } as const;
}

const TABS = ["instrumentos", "estrategia", "riesgo", "horarios", "avanzado"] as const;
type Tab = (typeof TABS)[number];

type Schema = { properties?: Record<string, unknown>; type?: string };

interface RiskFields {
  risk_per_trade_pct: string;
  max_daily_loss_pct: string;
  max_trades_per_day: string;
  max_units_per_trade: string;
  cooldown_minutes: string;
}

interface ScheduleFields {
  trade_window_start: string;
  trade_window_end: string;
  session_close_time: string;
}

const RISK_LABELS: Record<keyof RiskFields, string> = {
  risk_per_trade_pct: "Riesgo por operación (%)",
  max_daily_loss_pct: "Pérdida diaria máxima (%)",
  max_trades_per_day: "Operaciones máximas por día",
  max_units_per_trade: "Unidades máximas por operación",
  cooldown_minutes: "Cooldown tras salida (min)",
};

const SCHEDULE_LABELS: Record<keyof ScheduleFields, string> = {
  trade_window_start: "Inicio de ventana de entradas",
  trade_window_end: "Fin de ventana de entradas",
  session_close_time: "Cierre de sesión",
};

export function ConfigPage() {
  const { snapshot } = useStore();
  const { push } = useToast();
  const [testing, setTesting] = useState(false);
  const [alertForm, setAlertForm] = useState({ enabled: false, url: "", min_level: "warn" });
  const [alertDirty, setAlertDirty] = useState(false);
  const [tab, setTab] = useState<Tab>("instrumentos");
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [schema, setSchema] = useState<Schema | null>(null);
  const [risk, setRisk] = useState<RiskFields | null>(null);
  const [schedule, setSchedule] = useState<ScheduleFields | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<Awaited<ReturnType<typeof api.alerts>> | null>(
    null,
  );

  const sendTestAlert = async () => {
    setTesting(true);
    try {
      const result = await api.alertsTest();
      push({
        title: result.sent ? "Alerta de prueba entregada" : "La alerta no llegó",
        detail: result.sent ? "El webhook respondió correctamente." : result.reason ?? "sin motivo",
        tone: result.sent ? "good" : "bad",
      });
      const refreshed = await api.alerts();
      setAlerts(refreshed);
    } catch (cause) {
      push({ title: "No se pudo probar la alerta", detail: (cause as Error).message, tone: "bad" });
    } finally {
      setTesting(false);
    }
  };

  useEffect(() => {
    let alive = true;
    api
      .alerts()
      .then((payload) => {
        if (alive) setAlerts(payload);
      })
      .catch(() => {
        /* el panel de alertas es informativo: si falla, no rompe la página */
      });
    return () => {
      alive = false;
    };
  }, [tab]);

  useEffect(() => {
    api
      .config()
      .then((payload) => {
        setConfig(payload);
        const riskGroup = payload.risk as Record<string, unknown> | undefined;
        if (riskGroup) {
          setRisk({
            risk_per_trade_pct: String(riskGroup.risk_per_trade_pct ?? ""),
            max_daily_loss_pct: String(riskGroup.max_daily_loss_pct ?? ""),
            max_trades_per_day: String(riskGroup.max_trades_per_day ?? ""),
            max_units_per_trade: String(riskGroup.max_units_per_trade ?? ""),
            cooldown_minutes: String(riskGroup.cooldown_minutes ?? ""),
          });
          setSchedule({
            trade_window_start: String(riskGroup.trade_window_start ?? ""),
            trade_window_end: String(riskGroup.trade_window_end ?? ""),
            session_close_time: String(riskGroup.session_close_time ?? ""),
          });
        }
      })
      .catch((cause: Error) => setError(cause.message));
    api
      .strategySchema()
      .then((payload) => setSchema(payload.params_schema as Schema))
      .catch(() => undefined);
  }, []);

  const save = async (patch: Record<string, unknown>, label: string) => {
    setError(null);
    setMessage(null);
    try {
      const updated = await api.patchConfig(patch);
      setConfig(updated);
      setMessage(`${label} guardado y aplicado`);
    } catch (cause) {
      setError((cause as Error).message);
    }
  };

  useEffect(() => {
    if (!config || alertDirty) return;
    const alerts = (config.alerts ?? {}) as Record<string, unknown>;
    setAlertForm({
      enabled: Boolean(alerts.enabled),
      url: String(alerts.webhook_url ?? ""),
      min_level: String(alerts.min_level ?? "warn"),
    });
  }, [config, alertDirty]);

  const saveAlerts = async () => {
    await save(
      {
        alerts: {
          enabled: alertForm.enabled,
          webhook_url: alertForm.url.trim(),
          min_level: alertForm.min_level,
        },
      },
      "Alertas",
    );
    setAlertDirty(false);
    try {
      setAlerts(await api.alerts());
    } catch {
      /* el panel se refrescará en la próxima visita */
    }
  };

  const instruments = snapshot?.instruments ?? [];

  return (
    <div className="page">
      <h2>Configuración</h2>
      <div className="button-row">
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            className={value === tab ? "btn active" : "btn"}
            onClick={() => setTab(value)}
          >
            {value}
          </button>
        ))}
      </div>
      {error ? <p className="tone-bad">{error}</p> : null}
      {message ? <p className="tone-good">{message}</p> : null}

      {tab === "instrumentos" ? (
        <section className="card">
          <header className="card-header">
            <h3>Instrumentos configurados</h3>
            <span className="muted small">{instruments.length}</span>
          </header>
          <table className="symbols-table">
            <thead>
              <tr>
                <th>Símbolo</th>
                <th>Rol</th>
                <th>Tick</th>
                <th>Valor tick</th>
                <th>Decimales</th>
                <th>Divisa</th>
              </tr>
            </thead>
            <tbody>
              {instruments.map((instrument) => (
                <tr key={instrument.symbol}>
                  <td>{instrument.symbol}</td>
                  <td>{instrument.role}</td>
                  <td>{instrument.tick_size}</td>
                  <td>{instrument.tick_value}</td>
                  <td>{instrument.decimals}</td>
                  <td>{instrument.currency}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted small">
            Añadir o quitar un instrumento es un cambio de configuración: la interfaz y el
            feed se adaptan sin tocar código.
          </p>
        </section>
      ) : null}

      {tab === "estrategia" ? (
        <section className="card">
          <header className="card-header">
            <h3>Parámetros de estrategia</h3>
          </header>
          <p className="muted small">
            Formulario generado desde el esquema que declara el plugin activo.
          </p>
          {schema?.properties ? (
            <div className="form-grid">
              {Object.entries(schema.properties).map(([name, definition]) => (
                <label key={name}>
                  <span>{name}</span>
                  <input name={name} placeholder={JSON.stringify(definition)} />
                </label>
              ))}
            </div>
          ) : (
            <p className="empty">La estrategia activa no declara parámetros</p>
          )}
        </section>
      ) : null}

      {tab === "riesgo" && risk ? (
        <section className="card">
          <header className="card-header">
            <h3>Límites de riesgo</h3>
          </header>
          <div className="form-grid">
            {(Object.keys(RISK_LABELS) as (keyof RiskFields)[]).map((field) => (
              <label key={field}>
                <span>{RISK_LABELS[field]}</span>
                <input
                  name={field}
                  value={risk[field]}
                  onChange={(event) =>
                    setRisk({ ...risk, [field]: event.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <div className="button-row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="btn"
              onClick={() =>
                save(
                  {
                    risk: {
                      risk_per_trade_pct: Number(risk.risk_per_trade_pct),
                      max_daily_loss_pct: Number(risk.max_daily_loss_pct),
                      max_trades_per_day: Number(risk.max_trades_per_day),
                      max_units_per_trade: Number(risk.max_units_per_trade),
                      cooldown_minutes: Number(risk.cooldown_minutes),
                    },
                  },
                  "Riesgo",
                )
              }
            >
              Guardar riesgo
            </button>
          </div>
        </section>
      ) : null}

      {tab === "horarios" && schedule ? (
        <section className="card">
          <header className="card-header">
            <h3>Ventana y cierre</h3>
          </header>
          <div className="form-grid">
            {(Object.keys(SCHEDULE_LABELS) as (keyof ScheduleFields)[]).map((field) => (
              <label key={field}>
                <span>{SCHEDULE_LABELS[field]}</span>
                <input
                  name={field}
                  value={schedule[field]}
                  onChange={(event) =>
                    setSchedule({ ...schedule, [field]: event.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <div className="button-row" style={{ marginTop: 12 }}>
            <button
              type="button"
              className="btn"
              onClick={() => save({ risk: { ...schedule } }, "Horarios")}
            >
              Guardar horarios
            </button>
          </div>
        </section>
      ) : null}

      {tab === "avanzado" ? (
        <section className="card">
          <header className="card-header">
            <h3>Alertas externas</h3>
            <span className={`badge ${alerts?.enabled ? "tone-good" : ""}`}>
              {alerts?.enabled ? "activas" : "apagadas"}
            </span>
          </header>
          {alerts ? (
            <KvPanel
              decimals={0}
              entries={Object.fromEntries(
                [
                  kv("Webhook", alerts.enabled ? "configurado" : alerts.reason ?? "sin configurar", alerts.enabled ? "good" : "neutral"),
                  kv("Nivel mínimo", alerts.min_level ?? "—"),
                  kv("Enviadas", alerts.sent ?? 0, "neutral", "number"),
                  kv("Fallidas", alerts.failed ?? 0, (alerts.failed ?? 0) > 0 ? "bad" : "neutral", "number"),
                  kv("Descartadas", alerts.dropped ?? 0, (alerts.dropped ?? 0) > 0 ? "warn" : "neutral", "number"),
                  kv("Duplicadas filtradas", alerts.deduped ?? 0, "neutral", "number"),
                ].map((entry) => [entry.label, entry]),
              )}
            />
          ) : (
            <p className="muted small">Consultando estado de alertas…</p>
          )}
          <div className="alert-form">
            <label className="lab-check">
              <input
                type="checkbox"
                checked={alertForm.enabled}
                onChange={(event) => {
                  setAlertDirty(true);
                  setAlertForm({ ...alertForm, enabled: event.target.checked });
                }}
              />
              <span>
                Activar alertas
                <small>se envían a un webhook propio; si está caído, no detiene el motor</small>
              </span>
            </label>
            <label className="lab-field">
              <span>URL del webhook</span>
              <input
                type="url"
                placeholder="https://hooks.tuservicio.com/…"
                value={alertForm.url}
                onChange={(event) => {
                  setAlertDirty(true);
                  setAlertForm({ ...alertForm, url: event.target.value });
                }}
              />
            </label>
            <label className="lab-field">
              <span>Nivel mínimo</span>
              <select
                value={alertForm.min_level}
                onChange={(event) => {
                  setAlertDirty(true);
                  setAlertForm({ ...alertForm, min_level: event.target.value });
                }}
              >
                <option value="info">info · todo</option>
                <option value="warn">warn · avisos y errores</option>
                <option value="error">error · solo fallos</option>
              </select>
            </label>
            <button type="button" className="btn" onClick={saveAlerts} disabled={!alertDirty}>
              Guardar alertas
            </button>
          </div>

          <div className="button-row">
            <button
              type="button"
              className="btn"
              onClick={sendTestAlert}
              disabled={!alerts?.enabled || testing}
              data-alert-test
            >
              {testing ? "Enviando…" : "Enviar alerta de prueba"}
            </button>
            <span className="muted small">
              Entrega una alerta real y responde si llegó. Un «encolada» no es una prueba.
            </span>
          </div>
          <p className="muted small">
            Un webhook caído o una cola llena se cuentan aquí y dejan un evento en la
            consola: nunca detienen el motor.
          </p>
          <pre className="code-block">{JSON.stringify(config, null, 2)}</pre>
          <p className="muted small">
            La configuración se valida en el servidor: un valor fuera de rango se rechaza
            con 422 y no se aplica.
          </p>
        </section>
      ) : null}
    </div>
  );
}
