import { useState } from "react";

const KEY = "ezur.ui.onboarding";

/**
 * Three sentences for someone who has never seen this screen.
 *
 * It appears only in basic mode, once, and disappears for good when dismissed:
 * a tutorial that comes back every reload is an apology, not a feature.
 */
export function Onboarding() {
  const [visible, setVisible] = useState(() => {
    try {
      return window.localStorage.getItem(KEY) !== "dismissed";
    } catch {
      return true;
    }
  });

  if (!visible) return null;

  const dismiss = () => {
    setVisible(false);
    try {
      window.localStorage.setItem(KEY, "dismissed");
    } catch {
      /* if storage is blocked the card simply shows again next time */
    }
  };

  return (
    <section className="onboarding" aria-label="Cómo funciona">
      <div className="onboarding-steps">
        <div>
          <span className="onboarding-num">1</span>
          <b>Solo, sin ti</b>
          <p>Arranca al abrir y opera en papel con precios reales. No mueve dinero tuyo.</p>
        </div>
        <div>
          <span className="onboarding-num">2</span>
          <b>Con límites</b>
          <p>Si pierde lo máximo del día, se para. Tú decides ese máximo en Ajustes.</p>
        </div>
        <div>
          <span className="onboarding-num">3</span>
          <b>Sin humo</b>
          <p>La estrategia incluida está sin validar: puede perder, y lo dice en Inicio.</p>
        </div>
      </div>
      <button type="button" className="btn btn-ghost onboarding-close" onClick={dismiss}>
        Entendido
      </button>
    </section>
  );
}
