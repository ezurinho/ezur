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
  refresh: () => void;
}

const StoreContext = createContext<StoreValue>({
  snapshot: null,
  connection: "connecting",
  error: null,
  refresh: () => undefined,
});

export function StoreProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<SnapshotData | null>(null);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    api
      .status()
      .then((message) => {
        if (!cancelled) setSnapshot(message.data);
      })
      .catch((cause: Error) => {
        if (!cancelled) setError(cause.message);
      });

    const disconnect = connectSnapshotStream(
      (data) => {
        setSnapshot(data);
        setError(null);
      },
      (state) => setConnection(state),
    );

    return () => {
      cancelled = true;
      disconnect();
    };
  }, [nonce]);

  const value = useMemo<StoreValue>(
    () => ({ snapshot, connection, error, refresh: () => setNonce((n) => n + 1) }),
    [snapshot, connection, error],
  );

  return <StoreContext.Provider value={value}>{children}</StoreContext.Provider>;
}

export function useStore(): StoreValue {
  return useContext(StoreContext);
}
