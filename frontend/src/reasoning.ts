/**
 * El razonamiento del motor, dicho en pasos.
 *
 * No hay ningún modelo detrás: cada frase sale de un campo del snapshot
 * (`strategy.state`, `risk.block_reason`, `signal`, `rejection`…) y de los
 * códigos ya traducidos en `reasons.ts`. Eso es una ventaja, no una carencia:
 * se puede auditar paso a paso y nunca dice algo que los datos no digan. Por
 * eso la tarjeta lleva el sello «determinista».
 *
 * Lo que la tarjeta sí añade frente a la consola es el orden: la decisión
 * primero, el porqué después, y explícito lo que el motor **no** hizo.
 */

import { plainReason } from "./reasons";
import { phaseLabel, qualityLabel, sideLabel } from "./utils";
import type { SnapshotData } from "./types";

export type StepStatus = "pass" | "fail" | "warn" | "idle";

export interface ReasoningStep {
  key: string;
  label: string;
  status: StepStatus;
  detail: string;
}

export interface Conviction {
  label: "alta" | "media" | "baja";
  /** 0..1 tal como lo publica la estrategia; nunca inventado. */
  value: number;
}

export interface Reasoning {
  tone: "good" | "warn" | "bad" | "neutral";
  /** Dos o tres palabras: el estado de la decisión. */
  headline: string;
  /** Una frase con el motivo principal. */
  verdict: string;
  conviction: Conviction | null;
  steps: ReasoningStep[];
  /** Lo que el motor decidió no hacer, si consta. */
  veto: string | null;
}

const STRATEGY_STATES: Record<string, StepStatus> = {
  disabled: "fail",
  warmup: "warn",
  scanning: "pass",
  armed: "pass",
};

function band(value: number | null): Conviction | null {
  if (value === null || Number.isNaN(value)) return null;
  const label = value >= 0.7 ? "alta" : value >= 0.45 ? "media" : "baja";
  return { label, value };
}

function money(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function seconds(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return "sin dato";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = Math.round(ms / 1000);
  if (s < 90) return `${s} s`;
  return `${Math.round(s / 60)} min`;
}

/**
 * `context.lossStreakCooldownMin` sale de `risk.limits`, igual que en el resto
 * de la UI: la misma frase para el mismo código en todas las pantallas.
 */
export function buildReasoning(snapshot: SnapshotData): Reasoning {
  const { strategy, risk, position, orders, session, data, status } = snapshot;
  const context = { lossStreakCooldownMin: risk.limits?.loss_streak_cooldown_min ?? 0 };
  const signal = strategy.signal;

  const maxTrades = risk.limits?.max_trades_per_day ?? 0;
  const maxLossPct = risk.limits?.max_daily_loss_pct ?? 0;
  // El muro sale del servidor porque el motor lo aplica sobre el capital
  // inicial; calcularlo aquí sobre la equidad del día daría otro número y la
  // misma pantalla diría dos límites distintos. El cálculo local es el respaldo.
  const initialCapital = risk.limits?.initial_capital ?? null;
  const budget =
    risk.limits?.daily_loss_limit ??
    (initialCapital !== null && maxLossPct > 0 ? (initialCapital * maxLossPct) / 100 : null);

  const steps: ReasoningStep[] = [
    {
      key: "data",
      label: "Datos",
      // Un motor detenido no tiene feed: eso no es un fallo de datos, es el
      // estado que pidió el operador. El rojo se reserva para el motor vivo
      // que se quedó sin mercado.
      status:
        status === "stopped" && data.bars_available === 0
          ? "idle"
          : data.quality === "ok" && data.bars_available > 0
            ? "pass"
            : data.bars_available > 0
              ? "warn"
              : "fail",
      detail:
        data.bars_available > 0
          ? `${data.provider} · ${data.bars_available} velas · última hace ${seconds(data.staleness_ms)} · calidad ${qualityLabel(data.quality)}`
          : status === "stopped"
            ? `${data.provider} · motor detenido: sin feed en vivo`
            : `${data.provider} · sin velas: no hay mercado que evaluar`,
    },
    {
      key: "session",
      label: "Sesión",
      status: session.is_open ? "pass" : "fail",
      detail: `${session.label || "sin sesión"} · fase ${phaseLabel(session.phase)}${session.is_open ? "" : " · operativa cerrada"}`,
    },
    {
      key: "strategy",
      label: "Estrategia",
      status: STRATEGY_STATES[strategy.state] ?? "idle",
      detail: `${strategy.name || strategy.id} · ${strategy.state_label || strategy.state}`,
    },
    {
      key: "signal",
      label: "Señal",
      status: signal ? "pass" : strategy.rejection ? "fail" : "idle",
      detail: signal
        ? `${sideLabel(signal.side)} · ${signal.reason ?? "regla cumplida"} · stop ${money(signal.stop_price)}${signal.target_price !== null ? ` · objetivo ${money(signal.target_price)}` : ""}`
        : strategy.rejection
          ? `${strategy.rejection.code}: ${strategy.rejection.message ?? "rechazada"}`
          : "ninguna regla de entrada se cumple en esta vela",
    },
    {
      key: "risk",
      label: "Riesgo",
      status: risk.blocked ? "fail" : "pass",
      // Solo medidas: el motivo en palabras va en el veredicto, una vez. Si el
      // veto nace de una regla que no aparece en esta fila (posición abierta,
      // cooldown…), se avisa: un ✗ junto a cifras sanas se lee como un fallo.
      detail:
        `${risk.daily_trades}${maxTrades ? `/${maxTrades}` : ""} operaciones hoy · pérdida diaria ${money(Math.min(0, risk.daily_pnl))} ${budget === null ? "· límite sin dato" : `de ${money(budget)}`}` +
        (risk.blocked &&
        risk.block_reason !== "max_trades_reached" &&
        risk.block_reason !== "daily_loss_limit"
          ? " · el veto viene de otra regla de riesgo"
          : ""),
    },
    {
      key: "execution",
      label: "Ejecución",
      status: position || orders.length ? "pass" : "idle",
      detail: position
        ? `${sideLabel(position.side)} abierta en ${position.symbol} · ${position.units} u · riesgo ${money(risk.open_risk)}`
        : orders.length
          ? `${orders.length} orden(es) en curso`
          : "nada en curso",
    },
  ];

  // Con el bloqueo activo el recuento ya lo da el aviso fechado de arriba;
  // aquí solo aporta cuando el bloqueo ya no está y queda el historial del día.
  const veto =
    !risk.blocked && risk.block_count > 0
      ? `Rechazó ${risk.block_count} ${risk.block_count === 1 ? "señal" : "señales"} hoy por riesgo.`
      : null;

  const base = { conviction: band(signal?.strength ?? null), steps, veto };

  if (status !== "running") {
    const paused = status === "paused";
    return {
      ...base,
      tone: status === "error" ? "bad" : "neutral",
      headline: status === "error" ? "Con error" : paused ? "En pausa" : "Parado",
      verdict: paused
        ? "En pausa: no mira el mercado hasta que se reanude, así que ninguna señal se evalúa."
        : "No evalúa el mercado mientras no está corriendo: cualquier señal que llegue ahora se descarta sin ejecutarse.",
    };
  }

  if (strategy.state === "disabled") {
    return {
      ...base,
      tone: "warn",
      headline: "Sin estrategia",
      verdict:
        "El motor está vivo pero no tiene regla que aplicar: no hay estrategia cargada, así que no puede haber señal.",
    };
  }

  if (risk.blocked) {
    // Un bloqueo no cierra la posición abierta: si la hay, se dice, o el
    // operador creería que no queda nada gestionándose.
    const managing = position
      ? ` La ${sideLabel(position.side)} abierta en ${position.symbol} sigue gestionándose con su stop.`
      : "";
    return {
      ...base,
      tone: "warn",
      headline: "Bloqueado",
      verdict: plainReason(risk.block_reason, context) + managing,
    };
  }

  if (position) {
    return {
      ...base,
      tone: "good",
      headline: "En posición",
      verdict: `Decisión activa: gestionar la ${sideLabel(position.side)} abierta en ${position.symbol}. Entrada ${money(position.entry_price)}, stop ${money(position.stop_price)}${position.target_price !== null ? `, objetivo ${money(position.target_price)}` : ""}.`,
    };
  }

  if (orders.length > 0) {
    return {
      ...base,
      tone: "neutral",
      headline: "Orden en curso",
      verdict: `${orders.length === 1 ? "Una orden" : `${orders.length} órdenes`} en camino: no se abre otra hasta que se ejecute o se cancele.`,
    };
  }

  if (signal) {
    return {
      ...base,
      tone: "good",
      headline: "Señal",
      verdict: `${signal.reason ?? "Regla cumplida"}: ${sideLabel(signal.side)} con stop en ${money(signal.stop_price)}${signal.target_price !== null ? ` y objetivo en ${money(signal.target_price)}` : ""}.`,
    };
  }

  if (strategy.rejection) {
    return {
      ...base,
      tone: "warn",
      headline: "Rechazada",
      verdict: `${strategy.rejection.code}: ${strategy.rejection.message ?? "la estrategia descartó la señal"}`,
    };
  }

  return {
    ...base,
    tone: "neutral",
    headline: "Vigilando",
    verdict: "Ninguna regla de entrada se cumple ahora mismo. No hacer nada también es una decisión: esperar es el trabajo.",
  };
}
