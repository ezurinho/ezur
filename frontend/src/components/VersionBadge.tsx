import { useEffect, useState } from "react";
import { api } from "../api";
import type { UpdateInfo } from "../api";

const CACHE_KEY = "ezur.update";
const TTL_MS = 10 * 60 * 1000;

function readCache(): UpdateInfo | null {
  try {
    const raw = window.sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { at: number; info: UpdateInfo };
    if (!parsed?.info || Date.now() - parsed.at > TTL_MS) return null;
    return parsed.info;
  } catch {
    return null;
  }
}

function writeCache(info: UpdateInfo): void {
  try {
    window.sessionStorage.setItem(CACHE_KEY, JSON.stringify({ at: Date.now(), info }));
  } catch {
    /* sin sessionStorage se comprueba una vez por carga: no es un fallo */
  }
}

/**
 * La versión que corre, y si hay otra publicada.
 *
 * Comprobar sí, instalar no: el chip enlaza a la página del release y el usuario
 * decide. Descargar y reemplazar un ejecutable en caliente desde la propia app
 * es justo lo que un antivirus tiene razón en marcar.
 *
 * Si la comprobación falla no se muestra nada raro: el chip dice la versión y el
 * motivo queda en el `title`. Una app de trading no debe gritar por no tener red.
 */
export function VersionBadge() {
  const [info, setInfo] = useState<UpdateInfo | null>(readCache);

  useEffect(() => {
    if (info) return;
    let alive = true;
    api
      .update()
      .then((payload) => {
        if (!alive || !payload?.current) return;
        setInfo(payload);
        writeCache(payload);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [info]);

  const current = info?.current ?? "";
  if (info?.available && info.url) {
    return (
      <a
        className="badge badge-update"
        href={info.url}
        target="_blank"
        rel="noreferrer"
        data-version={current}
        data-update="available"
        title={info.latest ? `Hay ${info.latest} publicada` : "Hay una versión nueva"}
      >
        v{current} ↑
      </a>
    );
  }

  return (
    <span
      className="badge"
      data-version={current}
      data-update={info ? "current" : "pending"}
      title={
        info?.error
          ? `No se pudo comprobar si hay versión nueva: ${info.error}`
          : "Versión instalada"
      }
    >
      {current ? `v${current}` : "v—"}
    </span>
  );
}
