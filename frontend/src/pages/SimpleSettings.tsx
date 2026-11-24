import { useEffect, useState } from "react";
import { api } from "../api";
import { useUiMode } from "../mode";
import { useToast } from "../toast";
import { useStore } from "../store";
import { effectiveRiskNote } from "../effectiveRisk";

interface Fields {
  risk_per_trade_pct: string;
  max_daily_loss_pct: string;
  max_trades_per_day: string;
}

const DEFAULTS: Fields = {
  risk_per_trade_pct: "1",
  max_daily_loss_pct: "3",
  max_trades_per_day: "3",
};

/**
 * Three knobs, in words a beginner can act on.
 *
 * The advanced page has more of the engine's limits and the raw configuration;
 * this one exposes only the three numbers that change what a beginner will
 * actually experience, and explains each in one sentence. Values still go
 * through the same validated PUT /api/config: a bad number is rejected by the
 * server, not by the form.
 */
/**
 * La ayuda del riesgo usa la equidad real, no un 25.000 fijo.
 *
 * El motor dimensiona sobre el dinero actual de la cuenta, así que la cifra
 * que enseña esta frase debe salir de esa misma base: con 25.000 iniciales y
 * 24.416 ahora, «1 % son 250» ya no es lo que arriesga. Sin dato, se explica
 * sin inventar un número.
 */
export function riskHelp(pct: number, equity: number | null): string {
  const base = "Porcentaje del dinero actual de la cuenta que puedes perder si salta el stop.";
  if (equity === null || !Number.isFinite(equity) || equity <= 0) return base;
  const amount = ((equity * pct) / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  const shownPct = pct.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return `${base} Con ${shownPct} % sobre ${equity.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} son ${amount}.`;
}

/** 0.25 → «0,25» en español: el valor del control sigue en punto para el input. */
function shownNumber(raw: string): string {
  const value = Number(raw);
  return Number.isFinite(value)
    ? value.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : raw;
}

export function SimpleSettings() {
  const { setMode } = useUiMode();
  const { push } = useToast();
  const { snapshot } = useStore();
  const equity = snapshot?.risk.equity ?? null;
  const effectiveRisk = snapshot?.risk.limits.risk_per_trade_pct;
  // Sin la configuración del servidor no se pinta el formulario: unos sliders
  // con valores de ejemplo se leen como los reales y «Guardar» los escribiría.
  const [fields, setFields] = useState<Fields | null>(null);
  const effectiveNote = fields
    ? effectiveRiskNote(fields.risk_per_trade_pct, effectiveRisk)
    : null;
  const [loadError, setLoadError] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api
      .config()
      .then((payload) => {
        if (!alive) return;
        const risk = (payload.risk ?? {}) as Record<string, unknown>;
        setFields({
          risk_per_trade_pct: String(risk.risk_per_trade_pct ?? DEFAULTS.risk_per_trade_pct),
          max_daily_loss_pct: String(risk.max_daily_loss_pct ?? DEFAULTS.max_daily_loss_pct),
          max_trades_per_day: String(risk.max_trades_per_day ?? DEFAULTS.max_trades_per_day),
        });
        setLoadError(false);
      })
      .catch(() => {
        if (alive) setLoadError(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const save = async () => {
    if (fields === null) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await api.patchConfig({
        risk: {
          risk_per_trade_pct: Number(fields.risk_per_trade_pct),
          max_daily_loss_pct: Number(fields.max_daily_loss_pct),
          max_trades_per_day: Number(fields.max_trades_per_day),
        },
      });
      // La respuesta es la configuración que quedó guardada: si el servidor
      // normaliza una cifra, la pantalla enseña esa y no la que se escribió.
      const saved = (updated?.risk ?? {}) as Record<string, unknown>;
      if (
        typeof saved.risk_per_trade_pct === "number" &&
        typeof saved.max_daily_loss_pct === "number" &&
        typeof saved.max_trades_per_day === "number"
      ) {
        setFields({
          risk_per_trade_pct: String(saved.risk_per_trade_pct),
          max_daily_loss_pct: String(saved.max_daily_loss_pct),
          max_trades_per_day: String(saved.max_trades_per_day),
        });
      }
      setMessage("Guardado. Se aplica en la siguiente operación.");
      push({ title: "Ajustes guardados", detail: "Se aplican en la siguiente operación.", tone: "good" });
    } catch (cause) {
      const detail = (cause as Error).message;
      setError(detail);
      push({ title: "No se pudo guardar", detail, tone: "bad" });
    } finally {
      setBusy(false);
    }
  };

  const rows: { key: keyof Fields; label: string; help: string; unit: string; step: string }[] = fields
    ? [
        {
          key: "risk_per_trade_pct",
          label: "Cuánto arriesgar en cada operación",
          help: riskHelp(Number(fields.risk_per_trade_pct), equity),
          unit: "%",
          step: "0.25",
        },
        {
          key: "max_daily_loss_pct",
          label: "Cuánto puedes perder en un día",
          // La hora del reinicio depende de la plantilla de sesión; decir
          // «00:00 UTC» a secas sería falso fuera de la plantilla CRYPTO24.
          help: "Si las pérdidas del día llegan a este número, el bot deja de abrir operaciones hasta que empiece la siguiente sesión.",
          unit: "%",
          // El paso tiene que dar con el valor real del servidor: con 0,5 desde
          // 0,25 el 3 % del motor caía fuera de la rejilla y el control enseñaba 3,25.
          step: "0.25",
        },
        {
          key: "max_trades_per_day",
          label: "Operaciones máximas al día",
          help: "Un tope para no sobreoperar. Menos operaciones también significa menos comisiones.",
          unit: "ops",
          step: "1",
        },
      ]
    : [];

  return (
    <div className="page simple">
      <h2>Ajustes</h2>
      <p className="simple-lead">
        Solo lo importante. Si quieres más control, pásate al modo avanzado.
      </p>

      <section className="card simple-settings">
        {fields === null ? (
          <p className={loadError ? "tone-bad small" : "muted small"}>
            {loadError
              ? "No se pudo leer la configuración actual del bot. Sin ese dato, guardar escribiría números que no son los tuyos."
              : "Leyendo la configuración actual del bot…"}
          </p>
        ) : (
          rows.map((row) => {
            const numeric = Number(fields[row.key]) || 0;
            const floor = row.key === "max_trades_per_day" ? 1 : 0.25;
            const ceiling = row.key === "max_trades_per_day" ? 20 : 10;
            return (
              <label key={row.key} className="simple-field">
                <span className="simple-field-head">
                  <b>{row.label}</b>
                  <span className="simple-unit">
                    {shownNumber(fields[row.key])} {row.unit}
                  </span>
                </span>
                <input
                  type="range"
                  name={row.key}
                  // El rango habitual es 1–20 (o 0,25–10 %); si el motor ya corre
                  // fuera de él, el control se estira hasta ese valor en vez de
                  // pintar el pomo al tope con otra cifra escrita al lado.
                  min={Math.min(floor, numeric)}
                  max={Math.max(ceiling, Math.ceil(numeric))}
                  step={row.step}
                  value={fields[row.key]}
                  onChange={(event) => setFields({ ...fields, [row.key]: event.target.value })}
                  data-simple-input
                />
                <span className="simple-hint">{row.help}</span>
              </label>
            );
          })
        )}

        {effectiveNote ? (
          <p className="simple-hint" data-effective-risk>
            {effectiveNote}
          </p>
        ) : null}

        <div className="button-row">
          <button
            type="button"
            className="btn btn-start"
            onClick={save}
            disabled={busy || fields === null}
          >
            {busy ? "Guardando…" : "Guardar ajustes"}
          </button>
          <button type="button" className="btn btn-ghost" onClick={() => setMode("advanced")}>
            Modo avanzado
          </button>
        </div>
        {message ? <p className="tone-good small">{message}</p> : null}
        {error ? <p className="tone-bad small">{error}</p> : null}
      </section>

      <section className="card">
        <header className="card-header">
          <h3>Lo que este bot no hace</h3>
        </header>
        <ul className="simple-facts">
          <li>No mueve dinero real: opera en papel, con precios reales de mercado.</li>
          <li>No garantiza ganancias. La estrategia incluida está sin validar a propósito.</li>
          <li>No es asesoramiento financiero. Si no entiendes una operación, no la harías tú.</li>
        </ul>
      </section>
    </div>
  );
}
