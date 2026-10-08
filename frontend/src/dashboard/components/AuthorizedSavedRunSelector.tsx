import { useCallback, useEffect, useRef, useState } from "react";
import { forecastIdentity, forecastQuery, levels } from "../schemas/contracts";
import { DashboardError, read, safeError } from "../api/client";
import { useForecast } from "../context/ForecastContext";
import { StatusPanel } from "./presentation";

export function HierarchySelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      层级
      <select name="hierarchy_level" value={value} onChange={(e) => onChange(e.target.value)}>
        {levels.map((level) => (
          <option key={level}>{level}</option>
        ))}
      </select>
    </label>
  );
}
export function AuthorizedSavedRunSelector() {
  const { selectorOpen, closeSelector, commit } = useForecast();
  const dialog = useRef<HTMLDialogElement>(null);
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const [level, setLevel] = useState("BASE");
  const [error, setError] = useState<string>();
  const [mismatch, setMismatch] = useState(false);
  const [busy, setBusy] = useState(false);
  const cancelRequest = useCallback((resetBusy = true) => {
    active.current?.abort();
    active.current = null;
    generation.current++;
    if (resetBusy) setBusy(false);
  }, []);
  function close() {
    cancelRequest();
    closeSelector();
  }
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    if (selectorOpen) dialog.current?.showModal();
    else {
      cancelRequest();
      dialog.current?.close();
    }
    return () => {
      // Invalidate work on unmount/StrictMode cleanup without updating UI state.
      cancelRequest(false);
      // A closed-state cleanup must not steal focus from the next opener.
      if (selectorOpen) previous?.focus();
    };
  }, [selectorOpen, cancelRequest]);
  async function validate(form: HTMLFormElement) {
    cancelRequest();
    const controller = new AbortController();
    active.current = controller;
    const current = ++generation.current;
    setBusy(true);
    setError(undefined);
    setMismatch(false);
    try {
      const fields = Object.fromEntries(new FormData(form));
      const runId = String(fields.run_id);
      if (!/^[1-9]\d*$/.test(runId)) throw new DashboardError(422, "INVALID_RUN_ID");
      const query = forecastQuery.parse({ ...fields, run_id: Number(runId) });
      const curve = await read("curve", query, controller.signal);
      if (!["READY", "PARTIAL"].includes(curve.status) || !curve.data?.daily_rows.length)
        throw new DashboardError(409, "SAVED_CURVE_UNAVAILABLE");
      if (!controller.signal.aborted && generation.current === current && dialog.current?.open)
        commit({
          query,
          curve,
          key:
            JSON.stringify(forecastIdentity.parse(curve.forecast_identity)) +
            ":" +
            query.expected_source_result_hash,
        });
    } catch (failure) {
      if (!controller.signal.aborted && generation.current === current && dialog.current?.open) {
        setError(safeError(failure));
        setMismatch(failure instanceof DashboardError && failure.status === 409);
      }
    } finally {
      if (
        !controller.signal.aborted &&
        generation.current === current &&
        active.current === controller
      ) {
        active.current = null;
        setBusy(false);
      }
    }
  }
  return (
    <dialog
      className="d-dialog"
      ref={dialog}
      onCancel={close}
      onClose={close}
      aria-labelledby="d-selector-title"
    >
      <div className="d-panel-heading">
        <h2 id="d-selector-title">选择已保存预测</h2>
        <button autoFocus onClick={close}>
          关闭
        </button>
      </div>
      <div className="d-notice">
        <strong>路径 A · 可信授权上下文交接尚未接入</strong>
        <p>
          BUSINESS_RUN_SELECTOR_BACKEND_READY=false。没有“最新预测”列表；不使用旧 LIST 猜测记录。
        </p>
      </div>
      <h3>路径 B · 高级完整身份核验</h3>
      <p>供技术人员使用。输入身份不是授权证明，现有 HTTP 权限不代表逐用户、逐基地隔离。</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void validate(e.currentTarget);
        }}
        onChange={() => {
          cancelRequest();
          setError(undefined);
        }}
      >
        <div className="d-form-grid">
          <label>
            来源类型
            <select name="source_kind" required>
              <option value="OPERATIONAL_PEAK">OPERATIONAL_PEAK</option>
              <option value="HIERARCHICAL">HIERARCHICAL</option>
            </select>
          </label>
          <HierarchySelector value={level} onChange={setLevel} />
          {[
            "forecast_family",
            "run_id",
            "entity_id",
            "target_season",
            "origin_date",
            "baseline_id",
            "policy_version",
            "expected_source_result_hash",
          ].map((field) => (
            <label key={field}>
              {field}
              <input
                name={field}
                required
                maxLength={field === "expected_source_result_hash" ? 64 : 200}
                type={field === "origin_date" ? "date" : "text"}
                inputMode={field === "run_id" ? "numeric" : undefined}
                autoComplete="off"
                aria-describedby="d-selector-hint"
              />
            </label>
          ))}
        </div>
        <p id="d-selector-hint" className="d-help">
          完整身份与返回的来源 hash 必须匹配；失败不会替换上一份已核验上下文。超出安全整数范围的 run
          ID 拒绝，不静默舍入。
        </p>
        {error && <StatusPanel status={mismatch ? "AUTHORITY_MISMATCH" : "ERROR"} reason={error} />}
        <button className="d-primary" disabled={busy} type="submit">
          {busy ? "正在核验…" : "核验并使用保存预测"}
        </button>
      </form>
    </dialog>
  );
}
