import { useEffect, useState } from "react";
import { api } from "../api";
import { unblockHint } from "../reasons";
import type { SnapshotData } from "../types";

interface EngineEvent {
  ts?: string;
  level?: string;
  category?: string;
  message?: string;
}

function ago(iso: string | undefined, now: number): string | null {
  if (!iso) return null;
  const ts = Date.parse(iso);
  if (Number.isNaN(ts)) return null;
  const seconds = Math.max(0, Math.round((now - ts) / 1000));
  if (seconds < 90) return `hace ${seconds} s`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return `hace ${minutes} min`;
  return `hace ${Math.round(minutes / 60)} h`;
}

/**
 * Motivos que no son un freno: el motor sigue sano y simplemente no toca abrir
 * otra ahora. Pintarlos como «bloqueo de riesgo» en rojo convierte el estado
 * normal de tener una operación viva en una alarma.
 */
const ROUTINE_BLOCK = new Set([
  "position_open",
  "order_pending",
  "cooldown_active",
  "outside_window",
  "excluded_window",
  "no_price",
]);

/**
 * El bloqueo del motor, fechado.
 *
 * Este aviso aporta lo que solo él sabe: cuándo fue el último rechazo y qué
 * desbloquea. El **motivo** en palabras lo pone la tarjeta de razonamiento que
 * va justo debajo; repetirlo aquí eran dos frases idénticas seguidas.
 */
export function BlockedBanner({ snapshot }: { snapshot: SnapshotData }) {
  const risk = snapshot.risk;
  const [lastReject, setLastReject] = useState<EngineEvent | null>(null);

  useEffect(() => {
    if (!risk.blocked) {
      setLastReject(null);
      return;
    }
    let cancelled = false;
    // Sin filtro de nivel: el motor registra el primer rechazo como `warn` y
    // los siguientes como `info`, así que buscar solo en los avisos fechaba
    // el bloqueo con la primera señal, no con la última.
    api
      .events({ limit: 60 })
      .then((rows) => {
        if (cancelled) return;
        const found = (rows as EngineEvent[]).find(
          (row) => row.category === "risk" && (row.message ?? "").includes("rechazada"),
        );
        setLastReject(found ?? null);
      })
      .catch(() => {
        /* sin historial el panel sigue diciendo lo importante: el motivo */
      });
    return () => {
      cancelled = true;
    };
  }, [risk.blocked, risk.block_reason]);

  if (!risk.blocked) {
    return (
      <div className="why-strip why-ok" data-why="open">
        <span className="led led-live" aria-hidden="true" />
        <div>
          <b>Puede operar.</b> No hay bloqueo activo ahora mismo: si llega una señal
          que cumpla las reglas y los límites de sesión, se ejecutará.
        </div>
      </div>
    );
  }

  const when = ago(lastReject?.ts, Date.now());
  const context = { lossStreakCooldownMin: risk.limits.loss_streak_cooldown_min ?? 0 };
  const hint = unblockHint(risk.block_reason, context);
  const routine = risk.block_reason !== null && ROUTINE_BLOCK.has(risk.block_reason);
  return (
    <div
      className={`why-strip ${routine ? "why-hold" : "why-blocked"}`}
      data-why={routine ? "hold" : "blocked"}
      data-block-reason={risk.block_reason}
    >
      <span className={`led ${routine ? "led-hold" : "led-stale"}`} aria-hidden="true" />
      <div>
        <b>{routine ? "Sin entradas nuevas por ahora" : "Bloqueo de riesgo activo"}</b>
        <span className="why-meta">
          {risk.block_count > 0
            ? `${risk.block_count} ${risk.block_count === 1 ? "señal rechazada" : "señales rechazadas"}`
            : "sin señales rechazadas"}
          {when ? ` · la última ${when}` : ""}
          {hint ? ` · ${hint}` : ""}
        </span>
      </div>
    </div>
  );
}
