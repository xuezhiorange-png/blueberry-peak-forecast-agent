import { useCallback, useEffect, useRef, useState } from "react";
import {
  businessEnvelope,
  listSchema,
  scopeSchema,
  selectionSchema,
  type RunList,
  type SavedRun,
} from "../schemas/business";
import { levels } from "../schemas/contracts";
import { DashboardError, identityMatches, read, request, safeError } from "../api/client";
import { useForecast } from "../context/ForecastContext";
import { StatusPanel } from "./presentation";
import { invalidateSecurity } from "../api/security";

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
        <option value="">全部已授权层级</option>
        {levels.map((level) => (
          <option key={level}>{level}</option>
        ))}
      </select>
    </label>
  );
}
const emptyFilters = {
  target_season: "",
  hierarchy_level: "",
  entity_id: "",
  forecast_family: "",
  origin_from: "",
  origin_to: "",
};
export function AuthorizedSavedRunSelector() {
  const { selectorOpen, closeSelector, commit } = useForecast();
  const dialog = useRef<HTMLDialogElement>(null);
  const active = useRef<AbortController | null>(null);
  const generation = useRef(0);
  const [filters, setFilters] = useState(emptyFilters);
  const [scope, setScope] = useState<ReturnType<typeof scopeSchema.parse> | null>(null);
  const [listing, setListing] = useState<RunList | null>(null);
  const [error, setError] = useState<string>();
  const [busy, setBusy] = useState(false);
  const cancel = useCallback((reset = true) => {
    active.current?.abort();
    active.current = null;
    generation.current++;
    if (reset) setBusy(false);
  }, []);
  const start = useCallback(() => {
    cancel();
    const controller = new AbortController();
    active.current = controller;
    const current = ++generation.current;
    setBusy(true);
    setError(undefined);
    return {
      controller,
      valid: () =>
        !controller.signal.aborted && generation.current === current && !!dialog.current?.open,
    };
  }, [cancel]);
  const load = useCallback(
    async (values = emptyFilters, cursor?: string) => {
      const task = start();
      setListing(null);
      try {
        const authorized = await request(
          "/api/v1/business-access/scope",
          businessEnvelope(scopeSchema),
          task.controller.signal,
        );
        const params = Object.fromEntries(Object.entries(values).filter(([, v]) => v !== ""));
        const result = await request(
          "/api/v1/business-access/saved-runs",
          businessEnvelope(listSchema),
          task.controller.signal,
          { ...params, page_size: 20, ...(cursor ? { cursor } : {}) },
        );
        if (
          authorized.data.grant_revision !== result.data.grant_revision ||
          authorized.data.catalog_snapshot !== result.data.catalog_snapshot
        )
          throw new DashboardError(409, "DIRECTORY_CHANGED");
        if (task.valid()) {
          setScope(authorized.data);
          setListing(result.data);
        }
      } catch (failure) {
        if (task.valid()) setError(safeError(failure));
      } finally {
        if (task.valid()) {
          active.current = null;
          setBusy(false);
        }
      }
    },
    [start],
  );
  function close() {
    cancel();
    setListing(null);
    setScope(null);
    closeSelector();
  }
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    if (selectorOpen) {
      dialog.current?.showModal();
      setFilters(emptyFilters);
      void load();
    } else {
      cancel();
      dialog.current?.close();
    }
    return () => {
      cancel(false);
      if (selectorOpen) previous?.focus();
    };
  }, [selectorOpen, cancel, load]);
  async function select(item: SavedRun) {
    if (!listing) return;
    const task = start();
    const startedAt = Date.now();
    try {
      const { data } = await request(
        "/api/v1/business-access/selection",
        businessEnvelope(selectionSchema),
        task.controller.signal,
        undefined,
        {
          forecast_identity: item.forecast_identity,
          expected_source_result_hash: item.expected_source_result_hash,
          grant_revision: listing.grant_revision,
          catalog_snapshot: listing.catalog_snapshot,
        },
      );
      if (!task.valid()) return;
      if (
        !identityMatches(data.forecast_identity, item.forecast_identity) ||
        data.expected_source_result_hash !== item.expected_source_result_hash
      )
        throw new DashboardError(409, "HANDOFF_MISMATCH");
      const query = {
        ...item.forecast_identity,
        expected_source_result_hash: item.expected_source_result_hash,
      };
      const curve = await read("curve", query, task.controller.signal);
      if (!task.valid()) return;
      if (
        curve.projection_hash !== data.projection_hash ||
        !["READY", "PARTIAL"].includes(curve.status) ||
        !curve.data?.daily_rows.length ||
        Date.now() >= startedAt + data.expires_in * 1000
      )
        throw new DashboardError(409, "HANDOFF_EXPIRED_OR_MISMATCH");
      if (task.valid())
        commit({
          query,
          curve,
          entityName: item.entity_name,
          key: JSON.stringify(query),
          handoff: { token: data.handoff_token, expiresAt: startedAt + data.expires_in * 1000 },
        });
    } catch (failure) {
      if (task.valid()) {
        if (failure instanceof DashboardError && failure.status === 409)
          invalidateSecurity("access");
        else setError(safeError(failure));
      }
    } finally {
      if (task.valid()) {
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
      <p>仅列出当前账号获准查看的保存记录。不自动选择最新记录。</p>
      {scope && (
        <p>
          已授权范围：
          {scope.entities.map((e) => `${e.entity_name}（${e.hierarchy_level}）`).join("、") ||
            "没有预测范围"}{" "}
          · {scope.data_types.join("、")}
        </p>
      )}
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void load(filters);
        }}
      >
        <div className="d-form-grid">
          <label>
            产季
            <input
              value={filters.target_season}
              placeholder="2025-2026"
              maxLength={9}
              onChange={(e) => {
                cancel();
                setListing(null);
                setFilters({ ...filters, target_season: e.target.value });
              }}
            />
          </label>
          <HierarchySelector
            value={filters.hierarchy_level}
            onChange={(v) => {
              cancel();
              setListing(null);
              setFilters({ ...filters, hierarchy_level: v, entity_id: "" });
            }}
          />
          <label>
            实体
            <select
              value={filters.entity_id}
              onChange={(e) => {
                cancel();
                setListing(null);
                setFilters({ ...filters, entity_id: e.target.value });
              }}
            >
              <option value="">全部已授权实体</option>
              {scope?.entities
                .filter(
                  (e) => !filters.hierarchy_level || filters.hierarchy_level === e.hierarchy_level,
                )
                .map((e) => (
                  <option key={`${e.hierarchy_level}:${e.entity_id}`} value={e.entity_id}>
                    {e.entity_name}
                  </option>
                ))}
            </select>
          </label>
          <label>
            预测类型
            <input
              value={filters.forecast_family}
              maxLength={200}
              onChange={(e) => {
                cancel();
                setListing(null);
                setFilters({ ...filters, forecast_family: e.target.value });
              }}
            />
          </label>
          {(["origin_from", "origin_to"] as const).map((field) => (
            <label key={field}>
              {field === "origin_from" ? "预测起点从" : "预测起点至"}
              <input
                type="date"
                value={filters[field]}
                onChange={(e) => {
                  cancel();
                  setListing(null);
                  setFilters({ ...filters, [field]: e.target.value });
                }}
              />
            </label>
          ))}
        </div>
        <button disabled={busy}>查询授权记录</button>
      </form>
      {busy && <StatusPanel status="LOADING" reason="正在核验授权及保存记录…" />}
      {error && <StatusPanel status="ERROR" reason={error} retry={() => void load(filters)} />}
      {!busy && listing?.items.length === 0 && (
        <StatusPanel
          status="EMPTY"
          reason="当前筛选下没有已授权保存记录。请调整筛选或联系管理员。"
        />
      )}
      <div className="d-saved-runs">
        {listing?.items.map((item) => (
          <article
            className="d-panel"
            data-run-id={item.forecast_identity.run_id}
            data-source-kind={item.forecast_identity.source_kind}
            key={JSON.stringify(item.forecast_identity)}
          >
            <h3>
              {item.entity_name} · {item.forecast_identity.hierarchy_level}
            </h3>
            <p>
              {item.forecast_identity.target_season} · 预测起点 {item.origin_date}
            </p>
            <p>
              {item.forecast_family} · 保存于 {item.saved_at} · {item.completeness_status}
            </p>
            <button disabled={busy} className="d-primary" onClick={() => void select(item)}>
              {busy ? "正在核验…" : "核验并使用保存预测"}
            </button>
          </article>
        ))}
      </div>
      {listing?.next_cursor && (
        <button disabled={busy} onClick={() => void load(filters, listing.next_cursor!)}>
          下一页
        </button>
      )}
    </dialog>
  );
}
