/**
 * Los códigos del motor dichos en palabras.
 *
 * Un mismo mapa para los dos modos: el básico lo usa como frase y el avanzado
 * como explicación al lado del código. Si cada modo tuviera su copia, una de
 * las dos acabaría mintiendo.
 */

const WORDS: Record<string, string> = {
  position_open: "Ya tiene una operación abierta. Primero tiene que cerrarse.",
  max_trades_reached: "Ya hizo las operaciones máximas de hoy. Mañana vuelve a empezar.",
  daily_loss_limit: "Hoy ya perdió el máximo permitido. El bot se protege y para.",
  max_drawdown_reached: "La cuenta cayó demasiado desde su punto más alto. Se protege.",
  consecutive_losses:
    "Falló varias veces seguidas y hoy ya no abre más. La racha se reinicia al empezar la próxima sesión (00:00 UTC), no esperando un rato.",
  cooldown_active: "Acaba de cerrar una operación; espera un momento antes de abrir otra.",
  emergency_active: "La parada de emergencia está activada. Desactívala para seguir.",
  order_pending: "Hay una orden en camino; espera a que se ejecute.",
  outside_window: "Está fuera del horario en el que se permite operar.",
  no_price: "Todavía no tiene precio de referencia del mercado.",
  no_signal: "El precio no cumple su regla de entrada ahora mismo.",
  risk_per_trade: "La operación saldría demasiado grande para el riesgo permitido.",
  stop_too_wide: "El stop necesario es más ancho del máximo permitido.",
};

/** Qué haría falta para desbloquearlo. Vacío = se desbloquea solo. */
const UNLOCK: Record<string, string> = {
  position_open: "se desbloquea cuando la operación abierta se cierre",
  max_trades_reached: "se desbloquea en la próxima sesión",
  daily_loss_limit: "se desbloquea en la próxima sesión",
  max_drawdown_reached: "requiere revisar el riesgo o reiniciar la sesión de pruebas",
  consecutive_losses: "se desbloquea en la próxima sesión (00:00 UTC)",
  cooldown_active: "se desbloquea solo en unos minutos",
  emergency_active: "necesita que alguien desactive la parada de emergencia",
  order_pending: "se desbloquea cuando la orden se ejecute o se cancele",
  outside_window: "se desbloquea cuando abra el mercado",
  no_price: "se desbloquea cuando llegue el primer precio",
};

export interface ReasonContext {
  /** minutos de pausa tras la racha; 0 = bloqueo hasta la próxima sesión */
  lossStreakCooldownMin?: number;
}

export function plainReason(code: string | null | undefined, context: ReasonContext = {}): string {
  if (!code) return "Sin bloqueo: puede operar.";
  const cooldown = context.lossStreakCooldownMin ?? 0;
  if (code === "consecutive_losses" && cooldown > 0) {
    return `Falló varias veces seguidas y está en pausa: vuelve a mirar el mercado ${cooldown} minutos después de la última operación. Cada pérdida nueva reinicia la pausa.`;
  }
  return WORDS[code] ?? `Motivo técnico: ${code}`;
}

export function unblockHint(
  code: string | null | undefined,
  context: ReasonContext = {},
): string | null {
  if (!code) return null;
  const cooldown = context.lossStreakCooldownMin ?? 0;
  if (code === "consecutive_losses" && cooldown > 0) {
    return `se desbloquea ${cooldown} min después de la última salida`;
  }
  return UNLOCK[code] ?? null;
}
