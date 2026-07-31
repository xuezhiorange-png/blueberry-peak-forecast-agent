import { StatusBadge } from "../../components/StatusBadge";

export const IMPORT_STATUSES = [
  "RECEIVED",
  "UPLOADING",
  "SEALED",
  "PARSING",
  "VALIDATING",
  "VALIDATED",
  "COMMITTING",
  "COMMITTED",
] as const;
export const IMPORT_FAILURES = [
  "PARSE_FAILED",
  "VALIDATION_FAILED",
  "COMMIT_FAILED",
  "CANCELLED",
] as const;

export function ImportLifecycle({ status }: { status?: string }) {
  const current = status ?? "RECEIVED";
  const failed = IMPORT_FAILURES.includes(current as (typeof IMPORT_FAILURES)[number]);
  return (
    <div aria-label="实际采摘导入生命周期" className="lifecycle">
      {IMPORT_STATUSES.map((item, index) => (
        <div className={`lifecycle-step ${item === current ? "active" : ""}`} key={item}>
          <span className="step-index">{String(index + 1).padStart(2, "0")}</span>
          {item}
          {item === current && <StatusBadge label="当前" tone="warning" />}
        </div>
      ))}
      {failed && (
        <div className="lifecycle-step failed">
          <span className="step-index">!</span>
          {current}
          <StatusBadge label="失败分支" tone="danger" />
        </div>
      )}
    </div>
  );
}
