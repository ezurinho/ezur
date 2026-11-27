import type { ConnectionState } from "../api";
import type { SnapshotData } from "../types";
import { Logo } from "./Logo";
import { useClock } from "./Sparkline";
import { marketFreshness, phaseLabel, qualityLabel, sessionWindow, statusLabel } from "../utils";
import { useUiMode } from "../mode";
import { ThemePicker } from "./ThemePicker";
import { VersionBadge } from "./VersionBadge";
import { AnimatedNumber } from "./AnimatedNumber";
import { usePrevious } from "../motion";

interface Props {
  snapshot: SnapshotData | null;
  connection: ConnectionState;
  onOpenPalette: () => void;
}

function money(value: number, signed = false): string {
  const sign = signed && value > 0 ? "+" : "";
  return `${sign}${value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

/** The primary quote, flashing on change so a tick is visible without reading. */
function PriceFlash({ price }: { price: number | undefined }) {
  const previous = usePrevious(price);
  if (price === undefined) return null;
  const direction =
    previous === undefined || previous === price ? "" : price > previous ? "up" : "down";
  return (
    <div className="hud-group price-flash" data-price-flash>
      <span className="hud-label">precio</span>
      <span key={price} className={`hud-value hud-price ${direction ? `flash-${direction}` : ""}`}>
        {price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </span>
    </div>
  );
}

export function TopBar({ snapshot, connection, onOpenPalette }: Props) {
  // Antes del primer estado no se sabe si el motor corre ni en qué modo está:
  // «stopped» y «paper» serían dos afirmaciones inventadas, justo debajo de una
  // conexión que aún dice «conectando».
  const loaded = snapshot !== null;
  const status = snapshot?.status ?? "stopped";
  const mode = snapshot?.mode ?? "paper";
  const session = snapshot?.session;
  const sessionHours = session ? sessionWindow(session.open_ts, session.close_ts) : null;
  const quality = snapshot?.data.quality ?? "unknown";
  // Antes del primer snapshot no hay equidad que enseñar: un 0,00 en el HUD se
  // lee como «la cuenta está a cero», no como «todavía no sé».
  const equity = snapshot?.risk.equity ?? null;
  const dailyPnl = snapshot?.risk.daily_pnl ?? null;
  const now = useClock();
  const fresh = marketFreshness(snapshot?.data.last_bar_ts ?? null, now.getTime());
  const { isSimple, setMode } = useUiMode();
  const primary = snapshot?.instruments.find((item) => item.role === "primary")?.symbol;
  const price = primary ? (snapshot?.quotes[primary]?.last ?? undefined) : undefined;

  return (
    <header className="top-bar">
      <div className="top-bar-left">
        <div className="brand">
          <span className="brand-mark">
            <Logo size={30} />
          </span>
          <span className="brand-text">
            <span className="brand-name">ezur bot</span>
            <span className="brand-sub">trading terminal</span>
          </span>
        </div>

        <div className="hud-group status-group" title={loaded ? undefined : "Esperando el primer estado del motor"}>
          <span className={`led${loaded ? ` led-${status}` : ""}`} aria-hidden="true" />
          <span className="hud-value">{loaded ? statusLabel(status) : "—"}</span>
        </div>

        <span className="badge badge-mode" title={loaded ? `modo ${mode}` : "Esperando el primer estado del motor"}>
          {loaded ? mode : "—"}
        </span>
        <span className="hud-sep" aria-hidden="true" />
        <div className="hud-group">
          <span className="hud-label">equity</span>
          {equity === null ? (
            <span className="hud-value hud-value-lg" title="Esperando el primer estado del motor">
              —
            </span>
          ) : (
            <AnimatedNumber
              value={equity}
              className={`hud-value hud-value-lg ${dailyPnl !== null && dailyPnl > 0 ? "tone-good" : dailyPnl !== null && dailyPnl < 0 ? "tone-bad" : ""}`}
            />
          )}
        </div>
        <div className="hud-group">
          <span className="hud-label">p&amp;l día</span>
          {dailyPnl === null ? (
            <span className="hud-value hud-value-lg" title="Esperando el primer estado del motor">
              —
            </span>
          ) : (
            <AnimatedNumber
              value={dailyPnl}
              format={(value) => money(value, true)}
              className={`hud-value hud-value-lg ${dailyPnl > 0 ? "tone-good" : dailyPnl < 0 ? "tone-bad" : ""}`}
            />
          )}
        </div>
        <PriceFlash price={price} />
      </div>

      <div className="top-bar-right">
        <div className="mode-switch" role="group" aria-label="Nivel de detalle">
          <span className="mode-thumb" data-mode={isSimple ? "simple" : "advanced"} aria-hidden="true" />
          <button
            type="button"
            className={isSimple ? "mode-option active" : "mode-option"}
            onClick={() => setMode("simple")}
            aria-pressed={isSimple}
            data-mode-option="simple"
          >
            Básico
          </button>
          <button
            type="button"
            className={!isSimple ? "mode-option active" : "mode-option"}
            onClick={() => setMode("advanced")}
            aria-pressed={!isSimple}
            data-mode-option="advanced"
          >
            Avanzado
          </button>
        </div>
        <span className="hud-sep" aria-hidden="true" />
        <div
          className="hud-group session-group"
          title={
            session && sessionHours
              ? `${session.label}: ${sessionHours.local} (${sessionHours.utc} UTC)`
              : undefined
          }
        >
          <span className="hud-label">sesión</span>
          <span className="hud-value">
            {!loaded ? "—" : session ? `${session.label} · ${phaseLabel(session.phase)}` : "sin sesión"}
          </span>
        </div>
        <span className={`badge badge-quality-${quality}`} title={`calidad del feed: ${quality}`}>
          {qualityLabel(quality)}
        </span>
        {!isSimple ? (
          <span
            className={`fresh-chip fresh-${fresh.tone}`}
            title="Antigüedad de la última vela recibida del mercado"
            data-freshness={fresh.tone}
          >
            {fresh.label}
          </span>
        ) : null}
        <span className={`badge badge-connection-${connection}`} data-connection={connection}>
          <span
            className={`led led-${connection === "open" ? "running" : connection === "closed" ? "stopped" : "paused"}`}
            aria-hidden="true"
          />
          {connection === "open" ? "en línea" : connection === "closed" ? "sin conexión" : "conectando"}
        </span>
        <span className="hud-sep" aria-hidden="true" />
        <span className="hud-clock" aria-label="hora local">
          {now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </span>
        <button
          type="button"
          className="icon-btn palette-trigger"
          onClick={onOpenPalette}
          aria-label="Abrir paleta de comandos"
          title="Paleta de comandos (Ctrl+K)"
          data-palette-trigger
        >
          <kbd>⌘</kbd>
          <kbd>K</kbd>
        </button>
        <VersionBadge />
        <ThemePicker />
      </div>
    </header>
  );
}
