// Memory-only request boundary. Never stores credentials or handoff tokens.
type Boundary = "session" | "access";
const listeners = new Set<(kind: Boundary) => void>();
const active = new Set<AbortController>();
let revision = 0;
export function invalidateSecurity(kind: Boundary) {
  revision++;
  for (const controller of active) controller.abort();
  active.clear();
  for (const listener of listeners) listener(kind);
}
export function subscribeSecurity(listener: (kind: Boundary) => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
export function requestBoundary(signal: AbortSignal) {
  const controller = new AbortController();
  const current = revision;
  active.add(controller);
  return {
    signal: AbortSignal.any([signal, controller.signal]),
    valid: () => current === revision && !signal.aborted && !controller.signal.aborted,
    release: () => {
      active.delete(controller);
    },
  };
}
