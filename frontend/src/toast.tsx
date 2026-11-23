import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

export type ToastTone = "info" | "good" | "bad" | "warn";

export interface ToastInput {
  title: string;
  detail?: string;
  tone?: ToastTone;
  /** Milliseconds on screen. 0 keeps it until dismissed. */
  ttl?: number;
}

interface Toast extends ToastInput {
  id: number;
}

interface ToastContextValue {
  push: (toast: ToastInput) => number;
  dismiss: (id: number) => void;
  toasts: Toast[];
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEFAULT_TTL = 4200;

/**
 * Feedback where the eye is, not where the button is.
 *
 * Every control used to report success by doing nothing and failure by growing
 * the button row. A toast says what happened, disappears on its own, and never
 * steals focus (`role="status"`, not `alert`).
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (input: ToastInput) => {
      const id = nextId.current++;
      const toast: Toast = { tone: "info", ttl: DEFAULT_TTL, ...input, id };
      setToasts((current) => [...current.slice(-3), toast]);
      if (toast.ttl && toast.ttl > 0) {
        window.setTimeout(() => dismiss(id), toast.ttl);
      }
      return id;
    },
    [dismiss],
  );

  const value = useMemo<ToastContextValue>(() => ({ push, dismiss, toasts }), [push, dismiss, toasts]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite" aria-atomic="false">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`toast toast-${toast.tone ?? "info"}`}
            role="status"
            data-toast
          >
            <div className="toast-body">
              <strong>{toast.title}</strong>
              {toast.detail ? <span>{toast.detail}</span> : null}
            </div>
            <button
              type="button"
              className="toast-close"
              onClick={() => dismiss(toast.id)}
              aria-label="Cerrar aviso"
            >
              ×
            </button>
            {toast.ttl && toast.ttl > 0 ? (
              <span className="toast-timer" style={{ animationDuration: `${toast.ttl}ms` }} aria-hidden="true" />
            ) : null}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used inside ToastProvider");
  return context;
}
