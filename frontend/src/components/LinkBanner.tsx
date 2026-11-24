import type { LinkBanner as LinkBannerInfo } from "../utils";

/**
 * Cartel fijo mientras el enlace con el servidor está caído. Va fuera del
 * `role="status"` de los toasts a propósito: no caduca, y pulsar «Reintentar»
 * reabre el websocket sin recargar la página.
 */
export function LinkBanner({
  info,
  onRetry,
}: {
  info: LinkBannerInfo;
  onRetry: () => void;
}) {
  return (
    <div
      className={`link-banner link-${info.tone}`}
      role="status"
      aria-live="polite"
      data-link-tone={info.tone}
    >
      <span className={`led led-${info.tone === "bad" ? "stale" : "lag"}`} aria-hidden="true" />
      <p className="link-banner-text">
        <b>{info.title}.</b> {info.detail}
      </p>
      <button type="button" className="btn btn-ghost" onClick={onRetry}>
        Reintentar ahora
      </button>
    </div>
  );
}
