import { useEffect, useState } from "react";
import { api } from "../api";
import { useStore } from "../store";

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
  const [tab, setTab] = useState<Tab>("instrumentos");
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [schema, setSchema] = useState<Schema | null>(null);
  const [risk, setRisk] = useState<RiskFields | null>(null);
  const [schedule, setSchedule] = useState<ScheduleFields | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
