import { useMemo, useState, type FormEvent } from "react";
import type {
  ForecastInputAuthority,
  ForecastInputAuthorityItem,
  TrialForecastRequest,
} from "./forecastSchemas";

type AuthorityKey =
  | "farm_business_key"
  | "subfarm_business_key_or_null"
  | "season_business_key"
  | "variety_business_key"
  | "destination_factory_business_key";

const authorityFields: Array<[AuthorityKey, string]> = [
  ["destination_factory_business_key", "加工厂"],
  ["season_business_key", "产季"],
  ["farm_business_key", "农场"],
  ["subfarm_business_key_or_null", "分场"],
  ["variety_business_key", "品种"],
];

function authorityItemKey(item: ForecastInputAuthorityItem | null): string | null {
  if (!item) return null;
  return [
    item.farm_business_key,
    item.subfarm_business_key_or_null ?? "",
    item.season_business_key,
    item.variety_business_key,
    item.destination_factory_business_key,
    item.plan_row_hash,
  ].join("\u001f");
}

function confirmationIdentity(
  authority: ForecastInputAuthority | null,
  item: ForecastInputAuthorityItem | null,
): string | null {
  const itemKey = authorityItemKey(item);
  if (!authority || itemKey === null) return null;
  return [authority.forecast_input_authority_hash, itemKey].join("\u001e");
}

export function ForecastForm({
  authority,
  selectedItem,
  onSelectItem,
  onSubmit,
  submitting,
  errorMessage,
}: {
  authority: ForecastInputAuthority | null;
  selectedItem: ForecastInputAuthorityItem | null;
  onSelectItem: (item: ForecastInputAuthorityItem) => void;
  onSubmit: (request: TrialForecastRequest) => Promise<void>;
  submitting: boolean;
  errorMessage: string | null;
}) {
  const [forecastCutoffAt, setForecastCutoffAt] = useState("2026-02-28T00:00");
  const [floweringDate, setFloweringDate] = useState("");
  const [maturityStage, setMaturityStage] = useState("");
  const [alreadyPicked, setAlreadyPicked] = useState("");
  const [confirmedConfirmationIdentity, setConfirmedConfirmationIdentity] = useState<string | null>(
    null,
  );
  const selectedConfirmationIdentity = confirmationIdentity(authority, selectedItem);
  const confirmedArea =
    selectedConfirmationIdentity !== null &&
    selectedConfirmationIdentity === confirmedConfirmationIdentity;

  const optionsByField = useMemo(() => {
    const output = new Map<AuthorityKey, string[]>();
    for (const [key] of authorityFields) {
      const values = new Set<string>();
      for (const item of authority?.items ?? []) {
        const value = item[key];
        if (value !== null) values.add(value);
        else if (key === "subfarm_business_key_or_null") values.add("");
      }
      output.set(key, [...values].sort());
    }
    return output;
  }, [authority]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!authority || !selectedItem || !confirmedArea) return;
    const cutoff = new Date(forecastCutoffAt);
    if (Number.isNaN(cutoff.getTime())) return;
    await onSubmit({
      farm_business_key: selectedItem.farm_business_key,
      subfarm_business_key_or_null: selectedItem.subfarm_business_key_or_null,
      variety_business_key: selectedItem.variety_business_key,
      season_business_key: selectedItem.season_business_key,
      destination_factory_business_key: selectedItem.destination_factory_business_key,
      forecast_cutoff_at: cutoff.toISOString(),
      forecast_input_authority_hash: authority.forecast_input_authority_hash,
      plan_row_hash: selectedItem.plan_row_hash,
      planting_area_mu: selectedItem.planting_area_mu,
      flowering_date_or_null: null,
      maturity_stage_or_null: null,
      already_picked_quantity_kg_or_null: null,
    });
  }

  function changeField(key: AuthorityKey, value: string) {
    const requestedValue = key === "subfarm_business_key_or_null" && value === "" ? null : value;
    const candidates = (authority?.items ?? []).filter((item) => item[key] === requestedValue);
    if (candidates.length === 0) return;
    const candidate = [...candidates].sort((left, right) => {
      const score = (item: ForecastInputAuthorityItem) =>
        authorityFields.reduce(
          (total, [field]) =>
            total + (field === key || item[field] === selectedItem?.[field] ? 1 : 0),
          0,
        );
      return score(right) - score(left);
    })[0];
    setConfirmedConfirmationIdentity(null);
    onSelectItem(candidate);
  }

  return (
    <section className="surface section" aria-labelledby="forecast-input-title">
      <div className="section-header">
        <div>
          <p className="section-index">01 / INPUT AUTHORITY</p>
          <h2 id="forecast-input-title">预测输入</h2>
          <p>范围、面积、策略和证据身份均来自服务端 authority。</p>
        </div>
        <span className="eyebrow-tag">{authority ? "已连接" : "读取中"}</span>
      </div>
      {errorMessage && (
        <div className="notice notice-danger" role="alert">
          <span className="notice-icon" aria-hidden="true">
            !
          </span>
          <div>
            <strong>输入权威不可用</strong>
            {errorMessage}
          </div>
        </div>
      )}
      {!authority && !errorMessage && (
        <div className="notice" role="status" aria-busy="true">
          <span className="notice-icon" aria-hidden="true">
            i
          </span>
          <div>
            <strong>正在读取输入权威</strong>不会使用静态范围或演示数据。
          </div>
        </div>
      )}
      {authority && authority.items.length === 0 && (
        <div className="notice" role="status">
          <span className="notice-icon" aria-hidden="true">
            i
          </span>
          <div>
            <strong>暂无可用输入范围</strong>服务端没有返回可创建预测的 authority。
          </div>
        </div>
      )}
      <form onSubmit={submit}>
        <div className="form-grid form-grid-spaced">
          {authorityFields.map(([key, label]) => {
            const values = optionsByField.get(key) ?? [];
            const current = selectedItem?.[key] ?? "";
            return (
              <div className="field" key={key}>
                <label htmlFor={`authority-${key}`}>{label}</label>
                <select
                  id={`authority-${key}`}
                  value={current ?? ""}
                  onChange={(event) => changeField(key, event.target.value)}
                  disabled={!authority || values.length === 0 || submitting}
                >
                  <option value="">选择服务端范围</option>
                  {values.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </select>
              </div>
            );
          })}
          <div className="field">
            <label htmlFor="forecast-cutoff-at">预测截止时间</label>
            <input
              id="forecast-cutoff-at"
              type="datetime-local"
              value={forecastCutoffAt}
              onChange={(event) => setForecastCutoffAt(event.target.value)}
              disabled={!authority || submitting}
            />
            <span className="field-hint">将按 RFC3339 aware timestamp 发送。</span>
          </div>
          <div className="field">
            <label htmlFor="forecast-planting-area">权威种植面积（亩）</label>
            <input
              id="forecast-planting-area"
              value={selectedItem?.planting_area_mu ?? ""}
              readOnly
              disabled={!selectedItem}
            />
            <label className="checkbox-field" htmlFor="forecast-area-confirmed">
              <input
                id="forecast-area-confirmed"
                type="checkbox"
                checked={confirmedArea}
                onChange={(event) =>
                  setConfirmedConfirmationIdentity(
                    event.target.checked ? selectedConfirmationIdentity : null,
                  )
                }
                disabled={!selectedItem || submitting}
              />
              我确认使用服务端权威面积
            </label>
          </div>
          <div className="field">
            <label htmlFor="forecast-flowering-date">开花日期（可选）</label>
            <input
              id="forecast-flowering-date"
              type="date"
              value={floweringDate}
              onChange={(event) => setFloweringDate(event.target.value)}
              disabled
              aria-disabled="true"
            />
          </div>
          <div className="field">
            <label htmlFor="forecast-maturity-stage">成熟阶段（可选）</label>
            <input
              id="forecast-maturity-stage"
              value={maturityStage}
              onChange={(event) => setMaturityStage(event.target.value)}
              disabled
              aria-disabled="true"
              placeholder="按服务端合同填写"
            />
          </div>
          <div className="field">
            <label htmlFor="forecast-picked-quantity">已采摘数量 kg（可选）</label>
            <input
              id="forecast-picked-quantity"
              value={alreadyPicked}
              onChange={(event) => setAlreadyPicked(event.target.value)}
              disabled
              aria-disabled="true"
              placeholder="canonical Decimal string"
              inputMode="decimal"
            />
          </div>
        </div>
        <div className="button-row">
          <button
            className="button button-primary"
            disabled={!authority || !selectedItem || !confirmedArea || submitting}
            type="submit"
          >
            {submitting ? "生成中…" : "生成预测"}
          </button>
          <span className="disabled-reason">
            {selectedItem
              ? `plan ${selectedItem.plan_version} · authority ${authority?.authority_version}`
              : "请选择服务端返回的完整范围，并确认权威面积。"}
          </span>
        </div>
      </form>
    </section>
  );
}
