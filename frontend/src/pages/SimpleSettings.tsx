import { useEffect, useState } from "react";
import { api } from "../api";
import { useUiMode } from "../mode";

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
 * The advanced page exposes everything the engine accepts. This one exposes the
 * only three numbers that change what a beginner will actually experience, and
 * explains each in one sentence. Values still go through the same validated
 * PUT /api/config: a bad number is rejected by the server, not by the form.
 */
export function SimpleSettings() {
  const { setMode } = useUiMode();
  const [fields, setFields] = useState<Fields>(DEFAULTS);
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
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const save = async () => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      await api.patchConfig({
        risk: {
          risk_per_trade_pct: Number(fields.risk_per_trade_pct),
          max_daily_loss_pct: Number(fields.max_daily_loss_pct),
          max_trades_per_day: Number(fields.max_trades_per_day),
        },
      });
      setMessage("Guardado. Se aplica en la siguiente operación.");
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const rows: { key: keyof Fields; label: string; help: string; unit: string; step: string }[] = [
    {
      key: "risk_per_trade_pct",
      label: "Cuánto arriesgar en cada operación",
      help: "Porcentaje del dinero de la cuenta que puedes perder si salta el stop. Con 1 % sobre 25.000 son 250.",
      unit: "%",
      step: "0.25",
    },
    {
      key: "max_daily_loss_pct",
      label: "Cuánto puedes perder en un día",
      help: "Si las pérdidas del día llegan a este número, el bot deja de abrir operaciones hasta mañana.",
      unit: "%",
      step: "0.5",
    },
    {
      key: "max_trades_per_day",
      label: "Operaciones máximas al día",
      help: "Un tope para no sobreoperar. Menos operaciones también significa menos comisiones.",
      unit: "ops",
      step: "1",
    },
  ];

  return (
    <div className="page simple">
      <h2>Ajustes</h2>
      <p className="simple-lead">
        Solo lo importante. Si quieres tocar todo lo demás, pásate al modo avanzado.
      </p>

      <section className="card simple-settings">
        {rows.map((row) => (
          <label key={row.key} className="simple-field">
            <span className="simple-field-head">
              <b>{row.label}</b>
              <span className="simple-unit">
                {fields[row.key]} {row.unit}
              </span>
            </span>
            <input
              type="range"
              name={row.key}
              min={row.key === "max_trades_per_day" ? 1 : 0.25}
              max={row.key === "max_trades_per_day" ? 20 : 10}
              step={row.step}
              value={fields[row.key]}
              onChange={(event) => setFields({ ...fields, [row.key]: event.target.value })}
              data-simple-input
            />
            <span className="simple-hint">{row.help}</span>
          </label>
        ))}

        <div className="button-row">
          <button type="button" className="btn btn-start" onClick={save} disabled={busy}>
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
