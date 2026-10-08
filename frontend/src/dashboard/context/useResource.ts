import { useEffect, useRef, useState } from "react";
import { DashboardError, safeError } from "../api/client";
import type { Status } from "../schemas/contracts";

export type Resource<T> = { status: Status; value: T | null; reason?: string; retry: () => void };
export function useResource<T extends { status: string; unavailable_reason?: string | null }>(
  key: string | null,
  load: (signal: AbortSignal) => Promise<T>,
): Resource<T> {
  const loader = useRef(load);
  loader.current = load;
  const generation = useRef(0);
  const [revision, setRevision] = useState(0);
  const [state, setState] = useState<{
    key: string | null;
    status: Status;
    value: T | null;
    reason?: string;
  }>({ key: null, status: "EMPTY", value: null });
  useEffect(() => {
    const controller = new AbortController();
    const current = ++generation.current;
    if (key !== null) {
      loader
        .current(controller.signal)
        .then((value) => {
          if (!controller.signal.aborted && current === generation.current)
            setState({
              key,
              status: value.status as Status,
              value,
              reason: value.unavailable_reason ?? undefined,
            });
        })
        .catch((error: unknown) => {
          if (!controller.signal.aborted && current === generation.current)
            setState({
              key,
              status:
                error instanceof DashboardError && error.status === 409
                  ? "AUTHORITY_MISMATCH"
                  : "ERROR",
              value: null,
              reason: safeError(error),
            });
        });
    }
    return () => {
      controller.abort();
      generation.current++;
    };
  }, [key, revision]);
  const retry = () => {
    setState({ key: null, status: "LOADING", value: null });
    setRevision((v) => v + 1);
  };
  if (key === null) return { status: "EMPTY", value: null, retry };
  if (state.key !== key) return { status: "LOADING", value: null, retry };
  return { ...state, retry };
}
