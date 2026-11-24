import { useEffect, useState } from "react";
import { api } from "../api";
import { useToast } from "../toast";
import { useStore } from "../store";
import { KvPanel } from "../components/KvPanel";
import { effectiveRiskNote } from "../effectiveRisk";

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

type ParamDef = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
};

/**
 * El formulario arranca con los valores que el motor usa ahora, no con los
 * defaults del esquema: enseñar el default cuando el motor corre con otra cosa
 * convierte la pantalla en una mentira sobre lo que está pasando.
 */
export function paramsForm(
  properties: Record<string, ParamDef> | undefined,
  current: Record<string, unknown> | undefined,
): Record<string, string> {
  const form: Record<string, string> = {};
  for (const [name, def] of Object.entries(properties ?? {})) {
    const value = current?.[name] ?? def.default;
    form[name] = value === undefined || value === null ? "" : String(value);
  }
  return form;
}

/**
 * El payload que entiende el motor. Un campo vacío conserva el valor actual:
 * omitirlo dejaría que Pydantic pusiera el default del esquema y el operador
 * vería otro número del que dejó escrito. La coma decimal se acepta porque el
 * formulario es de aquí.
 */
export function paramsPayload(
  properties: Record<string, ParamDef> | undefined,
  form: Record<string, string>,
  current: Record<string, unknown> | undefined,
): Record<string, number | string> {
  const payload: Record<string, number | string> = {};
  for (const [name, def] of Object.entries(properties ?? {})) {
    const raw = (form[name] ?? "").trim();
    const source = raw !== "" ? raw.replace(",", ".") : current?.[name];
    if (source === undefined || source === null || source === "") continue;
    payload[name] =
      def.type === "integer" || def.type === "number" ? Number(source) : String(source);
  }
  return payload;
}

function strategyParams(config: Record<string, unknown> | null): Record<string, unknown> | undefined {
  const strategy = config?.strategy as Record<string, unknown> | undefined;
  const params = strategy?.params;
  return params && typeof params === "object" ? (params as Record<string, unknown>) : undefined;
}

/**
 * La ficha completa de un instrumento tal como la guarda el servidor.
 *
 * `snapshot.instruments` no trae ni la plaza ni la plantilla de sesión, así que
 * la tabla se pinta desde la configuración: es lo que se va a guardar de verdad.
 */
export interface InstrumentDraft {
  symbol: string;
  role: "primary" | "context";
  venue_symbol: string | null;
  enabled: boolean;
  tick_size: number;
  tick_value: number;
  point_value: number | null;
  currency: string;
  decimals: number;
  session_template: string;
}

export function instrumentsFromConfig(
  config: Record<string, unknown> | null,
): InstrumentDraft[] | null {
  const group = config?.instruments as { items?: unknown } | undefined;
  return Array.isArray(group?.items) ? (group.items as InstrumentDraft[]) : null;
}

/**
 * Instrumento nuevo a partir del primario.
 *
 * El contrato (tick, valor del tick, decimales, divisa y plantilla) se copia
 * del primario porque no hay otra fuente: solo el primario ejecuta órdenes, así
 * que mientras este siga siendo de contexto esos números no mueven dinero.
 * Devuelve el motivo en texto cuando el símbolo no sirve, para no guardar nada.
 */
export function withContextInstrument(
  items: InstrumentDraft[],
  symbol: string,
  venue: string,
): { items: InstrumentDraft[] } | { error: string } {
  const clean = symbol.trim();
  if (clean === "") return { error: "Escribe el símbolo del instrumento." };
  if (items.some((item) => item.symbol.toUpperCase() === clean.toUpperCase())) {
    return { error: `Ya hay un instrumento con el símbolo ${clean}.` };
  }
  const primary = items.find((item) => item.role === "primary");
  if (!primary) return { error: "No hay instrumento primario al que copiar el contrato." };
  const item: InstrumentDraft = {
    ...primary,
    symbol: clean,
    role: "context",
    venue_symbol: venue.trim() === "" ? null : venue.trim(),
    enabled: true,
  };
  return { items: [...items, item] };
}

interface RiskFields {
  risk_per_trade_pct: string;
  max_daily_loss_pct: string;
  max_trades_per_day: string;
  max_units_per_trade: string;
  cooldown_minutes: string;
  no_trade_after_consecutive_losses: string;
  loss_streak_cooldown_min: string;
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
  no_trade_after_consecutive_losses: "Freno tras N pérdidas seguidas (0 = sin freno)",
  loss_streak_cooldown_min: "Duración del freno por racha (0 = hasta la próxima sesión)",
};

const SCHEDULE_LABELS: Record<keyof ScheduleFields, string> = {
  trade_window_start: "Inicio de ventana de entradas",
  trade_window_end: "Fin de ventana de entradas",
  session_close_time: "Cierre de sesión",
};

/**
 * Un campo vacío no es un cero.
 *
 * `Number("")` es 0, y guardar 0 ahí no es un no-op: deja el bot sin
 * operaciones o sin margen de pérdida. Se nombra el campo que falta en vez de
 * escribir un número que el operador no escribió.
 */
export function numericError(
  fields: object,
  labels: Record<string, string>,
): string | null {
  for (const [key, raw] of Object.entries(fields) as [string, string][]) {
    const label = labels[key] ?? key;
    const value = raw.trim().replace(",", ".");
    if (value === "") return `«${label}» está vacío: escríbelo antes de guardar.`;
    const number = Number(value);
    if (!Number.isFinite(number)) return `«${label}» no es un número.`;
    if (number < 0) return `«${label}» no puede ser negativo.`;
  }
  return null;
}

/** El motor parte estas horas por ":" al decidir: una hora mal escrita lo para. */
export function scheduleError(
  fields: object,
  labels: Record<string, string>,
): string | null {
  for (const [key, raw] of Object.entries(fields) as [string, string][]) {
    const label = labels[key] ?? key;
    const match = /^(\d{1,2}):(\d{2})$/.exec(raw.trim());
    if (!match) return `«${label}» debe ir como HH:MM (por ejemplo 09:30).`;
    const hours = Number(match[1]);
    const minutes = Number(match[2]);
    if (hours > 23 || minutes > 59) return `«${label}» no es una hora válida (00:00–23:59).`;
  }
  return null;
}

export function ConfigPage() {
  const { push } = useToast();
  const { snapshot } = useStore();
  const [testing, setTesting] = useState(false);
  const [alertForm, setAlertForm] = useState({ enabled: false, url: "", min_level: "warn" });
  const [alertDirty, setAlertDirty] = useState(false);
  const [tab, setTab] = useState<Tab>("instrumentos");
  const [config, setConfig] = useState<Record<string, unknown> | null>(null);
  const [schema, setSchema] = useState<Awaited<ReturnType<typeof api.strategySchema>> | null>(
    null,
  );
  const [paramForm, setParamForm] = useState<Record<string, string> | null>(null);
  const [paramDirty, setParamDirty] = useState(false);
  const [risk, setRisk] = useState<RiskFields | null>(null);
  const [schedule, setSchedule] = useState<ScheduleFields | null>(null);
  const [newSymbol, setNewSymbol] = useState("");
  const [newVenue, setNewVenue] = useState("");
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
            no_trade_after_consecutive_losses: String(
              riskGroup.no_trade_after_consecutive_losses ?? "",
            ),
            loss_streak_cooldown_min: String(riskGroup.loss_streak_cooldown_min ?? ""),
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
      .then((payload) => setSchema(payload))
      .catch(() => undefined);
  }, []);

  const save = async (patch: Record<string, unknown>, done: string) => {
    setError(null);
    setMessage(null);
    try {
      const updated = await api.patchConfig(patch);
      setConfig(updated);
      setMessage(done);
      return updated;
    } catch (cause) {
      setError((cause as Error).message);
      return null;
    }
  };

  const strategyProperties = (schema?.params_schema?.properties ?? undefined) as
    | Record<string, ParamDef>
    | undefined;

  useEffect(() => {
    if (!schema || !config || paramDirty) return;
    setParamForm(paramsForm(strategyProperties, strategyParams(config)));
  }, [schema, config, paramDirty, strategyProperties]);

  const saveParams = async () => {
    const payload = paramsPayload(strategyProperties, paramForm ?? {}, strategyParams(config));
    const updated = await save({ strategy: { params: payload } }, "Parámetros guardados y aplicados");
    if (updated) {
      setParamDirty(false);
      setParamForm(paramsForm(strategyProperties, strategyParams(updated)));
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
      "Alertas guardadas y aplicadas",
    );
    setAlertDirty(false);
    try {
      setAlerts(await api.alerts());
    } catch {
      /* el panel se refrescará en la próxima visita */
    }
  };

  const instrumentItems = instrumentsFromConfig(config);
  const riskNote = risk
    ? effectiveRiskNote(risk.risk_per_trade_pct, snapshot?.risk.limits.risk_per_trade_pct)
    : null;

  const saveRisk = () => {
    if (!risk) return;
    const problem = numericError(risk, RISK_LABELS);
    if (problem) {
      setMessage(null);
      setError(problem);
      return;
    }
    const patch = Object.fromEntries(
      Object.entries(risk).map(([key, value]) => [key, Number(value.trim().replace(",", "."))]),
    );
    void save({ risk: patch }, "Riesgo guardado y aplicado");
  };

  const saveSchedule = () => {
    if (!schedule) return;
    const problem = scheduleError(schedule, SCHEDULE_LABELS);
    if (problem) {
      setMessage(null);
      setError(problem);
      return;
    }
    const patch = Object.fromEntries(
      Object.entries(schedule).map(([key, value]) => [key, value.trim()]),
    );
    void save({ risk: patch }, "Horarios guardados y aplicados");
  };

  const addInstrument = async () => {
    if (!instrumentItems) return;
    const result = withContextInstrument(instrumentItems, newSymbol, newVenue);
    if ("error" in result) {
      setMessage(null);
      setError(result.error);
      return;
    }
    const symbol = newSymbol.trim();
    const updated = await save(
      { instruments: { items: result.items } },
      `${symbol} añadido como contexto. El feed se reinicia con la lista nueva.`,
    );
    if (updated) {
      setNewSymbol("");
      setNewVenue("");
    }
  };

  const removeInstrument = async (symbol: string) => {
    if (!instrumentItems) return;
    const target = instrumentItems.find((item) => item.symbol === symbol);
    if (!target || target.role === "primary") return;
    await save(
      { instruments: { items: instrumentItems.filter((item) => item.symbol !== symbol) } },
      `${symbol} quitado. El feed se reinicia con la lista nueva.`,
    );
  };

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
            <h3>Instrumentos</h3>
            <span className="muted small">
              {instrumentItems ? instrumentItems.length : "—"}
            </span>
          </header>
          {instrumentItems === null ? (
            <p className="muted small">
              {error
                ? "No se pudo leer la configuración de instrumentos."
                : "Leyendo la configuración de instrumentos…"}
            </p>
          ) : (
            <>
              <table className="symbols-table">
                <thead>
                  <tr>
                    <th>Símbolo</th>
                    <th>Plaza</th>
                    <th>Rol</th>
                    <th>Plantilla</th>
                    <th>Tick</th>
                    <th>Valor tick</th>
                    <th>Decimales</th>
                    <th>Divisa</th>
                    <th aria-label="Quitar" />
                  </tr>
                </thead>
                <tbody>
                  {instrumentItems.map((instrument) => (
                    <tr key={instrument.symbol}>
                      <td>{instrument.symbol}</td>
                      <td>{instrument.venue_symbol ?? instrument.symbol}</td>
                      <td>{instrument.role}</td>
                      <td>{instrument.session_template}</td>
                      <td>{instrument.tick_size}</td>
                      <td>{instrument.tick_value}</td>
                      <td>{instrument.decimals}</td>
                      <td>{instrument.currency}</td>
                      <td>
                        {instrument.role === "context" ? (
                          <button
                            type="button"
                            className="btn btn-ghost"
                            onClick={() => removeInstrument(instrument.symbol)}
                            data-remove-instrument={instrument.symbol}
                          >
                            Quitar
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="instrument-add">
                <label className="lab-field">
                  <span>Símbolo nuevo</span>
                  <input
                    name="instrument_symbol"
                    placeholder="ETH-USDT"
                    value={newSymbol}
                    onChange={(event) => setNewSymbol(event.target.value)}
                  />
                </label>
                <label className="lab-field">
                  <span>Plaza (opcional)</span>
                  <input
                    name="instrument_venue"
                    placeholder="igual que el símbolo"
                    value={newVenue}
                    onChange={(event) => setNewVenue(event.target.value)}
                  />
                </label>
                <button
                  type="button"
                  className="btn"
                  onClick={addInstrument}
                  disabled={newSymbol.trim() === ""}
                  data-add-instrument
                >
                  Añadir como contexto
                </button>
              </div>
              <p className="muted small">
                El instrumento nuevo copia tick, valor del tick, decimales, divisa y
                plantilla del primario. Solo el primario ejecuta órdenes: el añadido sirve
                para ver su precio en el panel. Al guardar, el feed se reconstruye y las
                velas cargadas se descartan, así que el bot vuelve a calentar antes de
                decidir. Si la plaza no sirve ese símbolo, puede dejar de llegar el resto
                de velas hasta que lo quites. El primario no se puede quitar desde aquí.
              </p>
            </>
          )}
        </section>
      ) : null}

      {tab === "estrategia" ? (
        <section className="card">
          <header className="card-header">
            <h3>Parámetros de estrategia</h3>
            <span className="muted small" data-strategy-active>
              {schema ? `activa: ${schema.active}` : ""}
            </span>
          </header>
          <p className="muted small">
            Formulario generado desde el esquema que declara el plugin activo. Se abre con
            lo que el motor usa ahora; los valores fuera de rango los rechaza el servidor.
            {schema && schema.available.length > 1 ? (
              <>
                {" "}
                Instaladas: {schema.available.join(", ")}. Desde aquí solo se edita la
                activa.
              </>
            ) : null}
          </p>
          {schema?.params_schema?.properties ? (
            paramForm === null ? (
              <p className="muted small">
                {error
                  ? "No se pudo leer la configuración actual: el formulario no se abre con números de ejemplo."
                  : "Leyendo los parámetros que el motor usa ahora…"}
              </p>
            ) : (
              <>
              <div className="form-grid">
                {Object.entries(schema.params_schema.properties as Record<string, ParamDef>).map(
                  ([name, definition]) => {
                    const numeric =
                      definition.type === "integer" || definition.type === "number";
                    return (
                      <label key={name}>
                        <span>{definition.title ?? name}</span>
                        <input
                          name={name}
                          type="text"
                          inputMode={numeric ? "decimal" : "text"}
                          value={paramForm?.[name] ?? ""}
                          placeholder={
                            definition.default === undefined
                              ? ""
                              : String(definition.default)
                          }
                          onChange={(event) => {
                            setParamDirty(true);
                            setParamForm({ ...(paramForm ?? {}), [name]: event.target.value });
                          }}
                        />
                        {definition.description ? (
                          <small className="muted">{definition.description}</small>
                        ) : null}
                      </label>
                    );
                  },
                )}
              </div>
              <div className="button-row" style={{ marginTop: 12 }}>
                <button type="button" className="btn" onClick={saveParams} disabled={!paramDirty}>
                  Guardar parámetros
                </button>
              </div>
              <p className="muted small">
                Al guardar, el motor aplica los valores en caliente y descarta la señal en
                curso: la próxima evaluación ya usa estos números. Un campo vacío conserva
                el valor actual.
              </p>
              </>
            )
          ) : (
            <p className="empty">La estrategia activa no declara parámetros</p>
          )}
        </section>
      ) : null}

      {tab === "riesgo" ? (
        risk ? (
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
              <button type="button" className="btn" onClick={saveRisk}>
                Guardar riesgo
              </button>
            </div>
            {riskNote ? (
              <p className="muted small" data-effective-risk>
                {riskNote}
              </p>
            ) : null}
            <p className="muted small">
              Con el freno por racha en 0, la racha dura hasta la próxima sesión. Con
              minutos, el motor vuelve a mirar el mercado pasado ese tiempo. Si los frenos
              suaves están activos, la racha reduce el tamaño; si no, bloquea la entrada.
              Este formulario cubre los límites del día a día; el capital inicial, los
              frenos suaves, la concurrencia, las exclusiones de entrada y el objetivo
              diario de beneficio se ajustan en la configuración del servidor.
            </p>
          </section>
        ) : (
          <section className="card">
            <p className="muted small">
              {error
                ? "No se pudo leer la configuración de riesgo."
                : "Leyendo los límites que el motor usa ahora…"}
            </p>
          </section>
        )
      ) : null}

      {tab === "horarios" ? (
        schedule ? (
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
              <button type="button" className="btn" onClick={saveSchedule}>
                Guardar horarios
              </button>
            </div>
          </section>
        ) : (
          <section className="card">
            <p className="muted small">
              {error
                ? "No se pudo leer la configuración de horarios."
                : "Leyendo la ventana y el cierre que el motor usa ahora…"}
            </p>
          </section>
        )
      ) : null}

      {tab === "avanzado" ? (
        <section className="card">
          <header className="card-header">
            <h3>Alertas externas</h3>
            <span
              className={`badge ${alerts === null ? "" : alerts.enabled ? "tone-good" : ""}`}
              data-alerts-state={alerts === null ? "unknown" : alerts.enabled ? "on" : "off"}
            >
              {alerts === null ? "consultando…" : alerts.enabled ? "activas" : "apagadas"}
            </span>
          </header>
          {alerts ? (
            <KvPanel
              decimals={0}
              entries={Object.fromEntries(
                [
                  kv("Webhook", alerts.enabled ? "configurado" : alerts.reason ?? "sin configurar", alerts.enabled ? "good" : "neutral"),
                  kv("Nivel mínimo", alerts.min_level ?? "—"),
                  // Sin webhook el servidor no devuelve contadores: un 0 haría
                  // creer que hubo intentos y ninguno salió.
                  kv("Enviadas", alerts.sent ?? "—", "neutral", "number"),
                  kv(
                    "Fallidas",
                    alerts.failed ?? "—",
                    alerts.failed && alerts.failed > 0 ? "bad" : "neutral",
                    "number",
                  ),
                  kv(
                    "Descartadas",
                    alerts.dropped ?? "—",
                    alerts.dropped && alerts.dropped > 0 ? "warn" : "neutral",
                    "number",
                  ),
                  kv("Duplicadas filtradas", alerts.deduped ?? "—", "neutral", "number"),
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
                disabled={!config}
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
                disabled={!config}
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
                disabled={!config}
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
            <button
              type="button"
              className="btn"
              onClick={saveAlerts}
              disabled={!alertDirty || !config}
            >
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
