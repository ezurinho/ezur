/**
 * Los códigos del motor dichos en palabras.
 *
 * Un mismo mapa para los dos modos: el básico lo usa como frase y el avanzado
 * como explicación al lado del código. Si cada modo tuviera su copia, una de
 * las dos acabaría mintiendo.
 */

const WORDS: Record<string, string> = {
  position_open: "Ya tiene una operación abierta. Primero tiene que cerrarse.",
  max_trades_reached:
    "Ya hizo las operaciones máximas de hoy. El siguiente día de la sesión vuelve a empezar.",
  daily_loss_limit:
    "Hoy ya perdió el máximo permitido. Deja de abrir operaciones hasta la próxima sesión.",
  max_drawdown_reached: "La cuenta cayó demasiado desde su punto más alto. Se protege.",
  consecutive_losses:
    "Falló varias veces seguidas y hoy ya no abre más. La racha se reinicia al empezar la próxima sesión, no esperando un rato.",
  cooldown_active: "Acaba de cerrar una operación; espera un momento antes de abrir otra.",
  emergency_active: "La parada de emergencia está activada. Desactívala para seguir.",
  order_pending: "Hay una orden en camino; espera a que se ejecute.",
  outside_window: "Está fuera del horario en el que se permite operar.",
  excluded_window: "Está dentro de la franja horaria que el perfil excluye (por ejemplo, apertura de mercado).",
  no_price: "Todavía no tiene precio de referencia del mercado.",
  stale_data: "El mercado lleva demasiado tiempo sin entregar velas nuevas. No abre operaciones con datos obsoletos.",
  stale_order: "La orden pendiente tardó demasiado y se canceló: no ejecuta una señal antigua.",
  stale_signal: "La señal venció antes de llegar a riesgo: no abre una operación con una entrada antigua.",
  below_min_notional: "La orden no alcanza el valor mínimo del instrumento y se rechazó.",
  gap_through_stop: "La apertura ya atravesó el stop: la orden se rechaza en vez de abrir una operación inválida.",
  gap_through_target: "La apertura ya alcanzó el objetivo: no abre una operación que nacería cerrada.",
  no_signal: "El precio no cumple su regla de entrada ahora mismo.",
  risk_per_trade: "La operación saldría demasiado grande para el riesgo permitido.",
  stop_too_wide: "El stop necesario es más ancho del máximo permitido.",
  stop_too_tight:
    "El stop necesario es más estrecho que el mínimo permitido: el ruido del mercado lo barrería antes de que la idea se cumpla.",
  invalid_stop: "El stop de la señal cae justo sobre la entrada: no protegería nada.",
  daily_profit_limit:
    "Hoy ya ganó el máximo configurado. Deja de abrir operaciones para no devolverlo.",
  size_below_minimum:
    "Con el riesgo y la cuenta actuales, la operación saldría por debajo de un lote. No merece la pena abrirla.",
  invalid_stop_side:
    "La señal pide el stop del lado equivocado: no protegería nada. Es un fallo de la estrategia, no del mercado.",
  invalid_target_side:
    "La señal pide el objetivo detrás de la entrada: se cerraría sola en la primera vela. Es un fallo de la estrategia.",
  edge_below_cost:
    "La esperanza medida del marco no supera el coste por operación: cada entrada pagaría más de lo que la ventaja aporta. El motor no abre hasta que la evidencia lo demuestre.",
};

/** Qué haría falta para desbloquearlo. Vacío = se desbloquea solo. */
const UNLOCK: Record<string, string> = {
  position_open: "se desbloquea cuando la operación abierta se cierre",
  max_trades_reached: "se desbloquea en la próxima sesión",
  daily_loss_limit: "se desbloquea en la próxima sesión",
  daily_profit_limit: "se desbloquea en la próxima sesión",
  max_drawdown_reached: "requiere revisar el riesgo o reiniciar la sesión de pruebas",
  consecutive_losses: "se desbloquea al empezar la próxima sesión",
  cooldown_active: "se desbloquea solo en unos minutos",
  emergency_active: "necesita que alguien desactive la parada de emergencia",
  order_pending: "se desbloquea cuando la orden se ejecute o se cancele",
  outside_window: "se desbloquea cuando abra el mercado",
  excluded_window: "se desbloquea al terminar la franja excluida",
  no_price: "se desbloquea cuando llegue el primer precio",
  stale_data: "se desbloquea cuando vuelvan a llegar velas frescas",
  stale_order: "se desbloquea con una nueva señal",
  stale_signal: "se desbloquea con una nueva señal",
  below_min_notional: "se desbloquea con una orden de mayor tamaño",
  gap_through_stop: "se desbloquea con una nueva señal",
  gap_through_target: "se desbloquea con una nueva señal",
  stop_too_tight: "se desbloquea cuando la volatilidad dé un stop más ancho o se baje el mínimo del perfil",
  edge_below_cost:
    "requiere una evidencia nueva con esperanza medida por encima del coste por operación",
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

/**
 * El motivo de riesgo que más veces ha frenado al bot, con su recuento.
 *
 * El estado del motor solo trae el último rechazo; los totales de la corrida
 * dicen cuál pesa de verdad. Sin esto, un `no_price` de hace diez minutos
 * taparía un `stop_too_wide` que se repite cien veces al día.
 */
export function dominantRejection(
  counts: Record<string, number> | undefined,
): { code: string; count: number } | null {
  if (!counts) return null;
  let top: { code: string; count: number } | null = null;
  for (const [code, count] of Object.entries(counts)) {
    if (!Number.isFinite(count) || count <= 0) continue;
    if (!top || count > top.count) top = { code, count };
  }
  return top;
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
