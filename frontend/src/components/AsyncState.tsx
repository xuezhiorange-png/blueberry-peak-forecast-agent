import type { ReactNode } from "react";

export type AsyncStateKind =
  | "IDLE"
  | "LOADING"
  | "SUBMITTING"
  | "PENDING"
  | "COMPLETED"
  | "EMPTY"
  | "BLOCKED"
  | "ERROR"
  | "UNAVAILABLE";

export function AsyncState({
  state,
  children,
  label,
}: {
  state: AsyncStateKind;
  children?: ReactNode;
  label: string;
}) {
  const busy = state === "LOADING" || state === "SUBMITTING" || state === "PENDING";
  return (
    <div className="async-state" aria-busy={busy} data-state={state}>
      {busy && <span className="sr-only">{label}处理中</span>}
      {children}
    </div>
  );
}
