import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { api, connectSnapshotStream, type ConnectionState } from "./api";
import type { SnapshotData } from "./types";

interface StoreValue {
  snapshot: SnapshotData | null;
  connection: ConnectionState;
  error: string | null;
  /** Date.now() del último snapshot recibido; null si aún no llegó ninguno. */
  lastUpdate: number | null;
  refresh: () => void;
}

const StoreContext = createContext<StoreValue>({
  snapshot: null,
  connection: "connecting",
  error: null,
  lastUpdate: null,
  refresh: () => undefined,
});

export function StoreProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<SnapshotData | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<number | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const apply = (data: SnapshotData) => {
      setSnapshot(data);
      setLastUpdate(Date.now());
      setError(null);
    };

    api
      .status()
      .then((message) => {
        if (!cancelled) apply(message.data);
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      });

    const disconnect = connectSnapshotStream(apply, (state) => setConnection(state));

    return () => {
      cancelled = true;
      disconnect();
    };
  }, [nonce]);

  const value = useMemo<StoreValue>(
    () => ({ snapshot, connection, error, lastUpdate, refresh: () => setNonce((n) => n + 1) }),
    [snapshot, connection, error, lastUpdate],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  return useContext(StoreContext);
}
