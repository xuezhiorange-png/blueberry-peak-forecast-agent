import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { useForecast } from "../context/ForecastContext";
import { useResource } from "../context/useResource";
import {
  COSTS,
  cost,
  compare,
  simulate,
  DashboardError,
  safeError,
  type CostId,
} from "../api/client";
import {
  scenarioInput,
  planningLevels,
  type ScenarioInput,
  type SimulationResult,
  type DecisionResponse,
  type ComparisonData,
  type Status,
} from "../schemas/contracts";
import { Heading, ResourceView } from "./ReadPages";
import {
  Panel,
  EmptyState,
  StatusPanel,
  KpiCard,
  AuthorityDetails,
  ScenarioComparison,
  ScenarioResultFreshness,
  DecimalPreview,
} from "../components/presentation";
import { CapacityDemandChart, BacklogChart } from "../charts/Curves";

export type DraftDay = {
  date: string;
  capacity_mode: "DIRECT" | "WORKFORCE_DERIVED";
  direct: string;
  workforce: string;
  productivity: string;
  buffer: string;
};
export type DraftScenario = { scenario_id: string; scenario_version: string; days: DraftDay[] };
export function parseDraft(draft: DraftScenario): ScenarioInput {
  return scenarioInput.parse({
    scenario_id: draft.scenario_id,
    scenario_version: draft.scenario_version,
    capacity_rows: draft.days.map((day) => {
      if (day.capacity_mode === "WORKFORCE_DERIVED" && !/^(0|[1-9]\d*)$/.test(day.workforce))
        throw new DashboardError(422, "WORKFORCE_INVALID");
      return {
        date: day.date,
        capacity_mode: day.capacity_mode,
        ...(day.capacity_mode === "DIRECT"
          ? { daily_handling_capacity_kg: day.direct }
          : {
              workforce_count: Number(day.workforce),
              productivity_kg_per_person_day: day.productivity,
            }),
        ...(day.buffer === "" ? {} : { buffer_handling_capacity_kg: day.buffer }),
      };
    }),
  });
}
export function ScenarioEditor({
  draft,
  onChange,
}: {
  draft: DraftScenario;
  onChange: (draft: DraftScenario) => void;
}) {
  const [dayIndex, setDayIndex] = useState(0);
  const [copyOpen, setCopyOpen] = useState(false);
  const day = draft.days[dayIndex] ?? draft.days[0];
  if (!day) return <StatusPanel status="NOT_AVAILABLE" reason="保存曲线没有日期，不创建输入行。" />;
  const update = (fields: Partial<DraftDay>) =>
    onChange({
      ...draft,
      days: draft.days.map((row, i) => (i === dayIndex ? { ...row, ...fields } : row)),
    });
  let validation: string | undefined;
  try {
    parseDraft(draft);
  } catch (e) {
    validation =
      e instanceof z.ZodError
        ? "请填写所有日期的合法产能；数量为非负 Decimal 字符串，人效无默认。"
        : "人数必须是严格非负整数。";
  }
  return (
    <>
      <div className="d-form-grid">
        <label>
          情景 ID
          <input
            value={draft.scenario_id}
            maxLength={200}
            onChange={(e) => onChange({ ...draft, scenario_id: e.target.value })}
          />
        </label>
        <label>
          情景版本
          <input
            value={draft.scenario_version}
            maxLength={200}
            onChange={(e) => onChange({ ...draft, scenario_version: e.target.value })}
          />
        </label>
        <label>
          逐日编辑日期
          <select
            aria-label="逐日编辑日期"
            value={dayIndex}
            onChange={(e) => {
              setDayIndex(Number(e.target.value));
              setCopyOpen(false);
            }}
          >
            {draft.days.map((d, i) => (
              <option key={d.date} value={i}>
                {d.date} ·{" "}
                {d.capacity_mode === "DIRECT"
                  ? d.direct
                    ? "已填写"
                    : "待填写"
                  : d.workforce && d.productivity
                    ? "已填写"
                    : "待填写"}
              </option>
            ))}
          </select>
        </label>
        <label>
          产能模式
          <select
            value={day.capacity_mode}
            onChange={(e) =>
              update({
                capacity_mode: e.target.value as DraftDay["capacity_mode"],
                direct: "",
                workforce: "",
                productivity: "",
              })
            }
          >
            <option value="DIRECT">DIRECT · 直接处理能力</option>
            <option value="WORKFORCE_DERIVED">WORKFORCE_DERIVED · 人数 × 显式人效</option>
          </select>
        </label>
        {day.capacity_mode === "DIRECT" ? (
          <label>
            直接处理能力 kg/日
            <input
              inputMode="decimal"
              maxLength={64}
              value={day.direct}
              onChange={(e) => update({ direct: e.target.value })}
              aria-describedby="d-capacity-hint"
            />
          </label>
        ) : (
          <>
            <label>
              人数（非负整数）
              <input
                inputMode="numeric"
                maxLength={7}
                value={day.workforce}
                onChange={(e) => update({ workforce: e.target.value })}
                aria-describedby="d-capacity-hint"
              />
            </label>
            <label>
              显式人效 kg/人·日
              <input
                inputMode="decimal"
                maxLength={64}
                value={day.productivity}
                onChange={(e) => update({ productivity: e.target.value })}
                aria-describedby="d-capacity-hint"
              />
            </label>
          </>
        )}
        <label>
          同日额外处理能力 kg/日
          <input
            inputMode="decimal"
            maxLength={64}
            value={day.buffer}
            onChange={(e) => update({ buffer: e.target.value })}
            aria-describedby="d-capacity-hint"
          />
        </label>
      </div>
      <p id="d-capacity-hint" className="d-help">
        buffer 仅是当日处理能力，不是冷库库存，不跨日结转。未配置 buffer
        为显式“不配置”。初始积压固定为 0。人数上限 1,000,000，最多 15 日。
      </p>
      {validation && (
        <p className="d-field-error" role="status">
          {validation}
        </p>
      )}
      <div className="d-actions">
        <button onClick={() => setDayIndex(Math.max(0, dayIndex - 1))} disabled={dayIndex === 0}>
          上一日
        </button>
        <button
          onClick={() => setDayIndex(Math.min(draft.days.length - 1, dayIndex + 1))}
          disabled={dayIndex === draft.days.length - 1}
        >
          下一日
        </button>
        <button onClick={() => setCopyOpen(!copyOpen)}>将本日产能输入应用到全部日期…</button>
      </div>
      {copyOpen && (
        <div className="d-notice">
          <strong>确认复制用户输入，不是计算或推荐</strong>
          <p>目标日期：{draft.days.map((d) => d.date).join("、")}</p>
          <button
            onClick={() => {
              onChange({ ...draft, days: draft.days.map((d) => ({ ...day, date: d.date })) });
              setCopyOpen(false);
            }}
          >
            确认复制至这些日期
          </button>
          <button onClick={() => setCopyOpen(false)}>取消复制</button>
        </div>
      )}
    </>
  );
}
export function SimulationOutput({ result }: { result: SimulationResult }) {
  return (
    <>
      <Panel
        title={`情景 ${result.scenario_id} · 服务端结果`}
        note={`${result.forecast_start_date} 至 ${result.forecast_end_date} · ${result.day_count} 日`}
      >
        <div className="d-kpis">
          <KpiCard label="日处理量不足" value={result.overload_day_count} unit="天" />
          <KpiCard label="累计日不足量" value={result.cumulative_shortfall_kg} unit="kg" />
          <KpiCard label="最大积压" value={result.max_backlog_kg} unit="kg" />
          <KpiCard label="期末积压" value={result.ending_backlog_kg} unit="kg" />
        </div>
        <div className="d-notice">
          每日不足量相对当日新需求；日末积压是跨日队列。累计日不足量不等于期末积压。
        </div>
        <dl>
          <dt>总处理利用率（比例）</dt>
          <dd>
            {result.aggregate_capacity_utilization_decimal === null ? (
              "不可计算：总产能为零（NOT_COMPUTABLE_ZERO_CAPACITY）"
            ) : (
              <>
                <DecimalPreview value={result.aggregate_capacity_utilization_decimal} /> ·
                长表示截取，原值见详情
              </>
            )}
          </dd>
          <dt>利用率 exact authority</dt>
          <dd>
            {result.aggregate_capacity_utilization_numerator_kg} /{" "}
            {result.aggregate_capacity_utilization_denominator_kg} kg
          </dd>
          <dt>派生表示</dt>
          <dd>
            precision={result.aggregate_capacity_utilization_precision} ·{" "}
            {result.aggregate_capacity_utilization_rounding_mode} · rounding_applied=
            {String(result.aggregate_capacity_utilization_rounding_applied)}
          </dd>
          <dt>合成规划缺口损失</dt>
          <dd>{result.total_business_loss} SYNTHETIC_LOSS_UNIT · 不是货币</dd>
        </dl>
        <CapacityDemandChart result={result} />
      </Panel>
      <Panel title="跨日积压">
        <BacklogChart result={result} />
      </Panel>
      <Panel title="每日原始明细">
        <div className="d-daily-results">
          {result.daily_rows.map((row) => (
            <details key={row.date}>
              <summary>
                {row.date} · 处理 {row.processed_kg} kg · 日末积压 {row.closing_backlog_kg} kg
              </summary>
              <AuthorityDetails value={row} />
            </details>
          ))}
        </div>
        <AuthorityDetails value={result} />
      </Panel>
    </>
  );
}
export function CapacityPage() {
  const { verified } = useForecast();
  // A run change remounts all drafts and cancels every outstanding decision request.
  return (
    <>
      <Heading title="产能模拟" description="显式输入条件，比较规划压力；不优化、不排产。" />
      {verified ? <CapacityWorkspace key={verified.key} /> : <EmptyState />}
    </>
  );
}
function CapacityWorkspace() {
  const { verified, leaveGuard } = useForecast();
  const source = verified!;
  const days = source.curve.data?.daily_rows ?? [];
  const newDraft = (): DraftScenario => ({
    scenario_id: "",
    scenario_version: "",
    days: days.map((d) => ({
      date: d.target_date,
      capacity_mode: "DIRECT",
      direct: "",
      workforce: "",
      productivity: "",
      buffer: "",
    })),
  });
  const [drafts, setDrafts] = useState<DraftScenario[]>(() => [newDraft()]);
  const [activeIndex, setActiveIndex] = useState(0);
  const [costId, setCostId] = useState<CostId | "">("");
  const [planning, setPlanning] = useState<(typeof planningLevels)[number]>("POINT");
  const [response, setResponse] = useState<DecisionResponse<SimulationResult> | null>(null);
  const [comparison, setComparison] = useState<DecisionResponse<ComparisonData> | null>(null);
  const [state, setState] = useState<Status>("EMPTY");
  const [reason, setReason] = useState<string>();
  const [stale, setStale] = useState(false);
  const revision = useRef(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    leaveGuard.current = () =>
      revision.current === 0 ||
      window.confirm("切换页面或保存预测会放弃当前情景草稿与结果，确认继续？");
    return () => {
      leaveGuard.current = null;
    };
  }, [leaveGuard]);
  const exposure = useResource(costId || null, (s) => cost(costId as CostId, s));
  function invalidate() {
    controller.current?.abort();
    revision.current++;
    setResponse(null);
    setComparison(null);
    setState("EMPTY");
    setReason(undefined);
    setStale(true);
  }
  useEffect(
    () => () => {
      controller.current?.abort();
      revision.current++;
    },
    [],
  );
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (revision.current > 0) event.preventDefault();
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, []);
  const activeDraft = drafts[activeIndex];
  let activeValid = false;
  let allValid = false;
  try {
    parseDraft(activeDraft);
    activeValid = true;
  } catch {
    /* invalid draft never submitted */
  }
  try {
    drafts.forEach(parseDraft);
    allValid = new Set(drafts.map((d) => d.scenario_id)).size === drafts.length;
  } catch {
    /* comparison does not silently omit invalid scenarios */
  }
  const sourceUsable =
    source.curve.data?.data_completeness !== "INCOMPLETE_CHILD_COVERAGE" &&
    days.length > 0 &&
    days.length <= 15;
  const ready =
    sourceUsable && costId !== "" && exposure.status === "READY" && planning === "POINT";
  async function submit(comparisonMode: boolean) {
    if (!ready || !costId) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    const current = revision.current;
    setState("LOADING");
    setResponse(null);
    setComparison(null);
    setReason(undefined);
    const { expected_source_result_hash, ...forecast_selection } = source.query;
    const common = {
      forecast_selection,
      expected_source_result_hash,
      planning_level: planning,
      cost_contract_id: costId,
      expected_cost_contract_hash: COSTS[costId],
    };
    try {
      if (comparisonMode) {
        const value = await compare(
          { ...common, scenarios: drafts.map(parseDraft) },
          request.signal,
        );
        if (!request.signal.aborted && current === revision.current) {
          setComparison(value);
          setState(value.status);
          setReason(value.unavailable_reason ?? undefined);
          setStale(false);
        }
      } else {
        const value = await simulate({ ...common, ...parseDraft(activeDraft) }, request.signal);
        if (!request.signal.aborted && current === revision.current) {
          setResponse(value);
          setState(value.status);
          setReason(value.unavailable_reason ?? undefined);
          setStale(false);
        }
      }
    } catch (error) {
      if (!request.signal.aborted && current === revision.current) {
        setState(
          error instanceof DashboardError && error.status === 409 ? "AUTHORITY_MISMATCH" : "ERROR",
        );
        setReason(safeError(error));
      }
    }
  }
  return (
    <>
      <Panel title="设置情景条件" note={`${days.length} 个保存日期 · 初始积压固定 0`}>
        <div className="d-notice d-state-PARTIAL">
          <strong>SYNTHETIC_COST · 非公司真实成本</strong>
          <p>SYNTHETIC_LOSS_UNIT · canonical_company_cost=false · real_roi_validated=false</p>
        </div>
        {!sourceUsable && (
          <StatusPanel
            status="NOT_AVAILABLE"
            reason="子节点覆盖不完整或无合法日曲线，不能进入模拟。"
          />
        )}
        <div className="d-form-grid">
          <label>
            规划水平
            <select
              value={planning}
              onChange={(e) => {
                invalidate();
                setPlanning(e.target.value as typeof planning);
              }}
            >
              <option value="POINT">POINT · 预测值</option>
              <option disabled value="UPPER_PLANNING_BOUND_80">
                80%规划上界 · NOT_AVAILABLE
              </option>
              <option disabled value="UPPER_PLANNING_BOUND_90">
                90%规划上界 · NOT_AVAILABLE
              </option>
            </select>
          </label>
          <label>
            显式选择成本合同（无默认）
            <select
              value={costId}
              onChange={(e) => {
                invalidate();
                setCostId(e.target.value as CostId | "");
              }}
            >
              <option value="">请选择合成成本合同</option>
              {Object.keys(COSTS).map((id) => (
                <option key={id}>{id}</option>
              ))}
            </select>
          </label>
        </div>
        {costId && (
          <ResourceView resource={exposure}>
            {(v) => (
              <>
                <p className="d-help">合同已核验：{v.cost_contract_id} · SYNTHETIC_LOSS_UNIT</p>
                <AuthorityDetails value={v} />
              </>
            )}
          </ResourceView>
        )}
        <div className="d-tabs" aria-label="情景选择">
          {drafts.map((d, i) => (
            <button key={i} aria-pressed={i === activeIndex} onClick={() => setActiveIndex(i)}>
              情景 {d.scenario_id || i + 1}
            </button>
          ))}
          <button
            disabled={drafts.length >= 20}
            onClick={() => {
              invalidate();
              setDrafts([...drafts, newDraft()]);
              setActiveIndex(drafts.length);
            }}
          >
            新增空情景
          </button>
        </div>
        <ScenarioEditor
          key={activeIndex}
          draft={activeDraft}
          onChange={(draft) => {
            invalidate();
            setDrafts(drafts.map((d, i) => (i === activeIndex ? draft : d)));
          }}
        />
        <div className="d-actions">
          <button
            disabled={drafts.length === 1}
            onClick={() => {
              if (window.confirm("确认放弃并删除当前情景草稿？")) {
                invalidate();
                setDrafts(drafts.filter((_, i) => i !== activeIndex));
                setActiveIndex(0);
              }
            }}
          >
            删除当前情景…
          </button>
          <button
            className="d-primary"
            disabled={!ready || !activeValid || state === "LOADING"}
            onClick={() => void submit(false)}
          >
            模拟当前情景
          </button>
          <button
            disabled={!ready || !allValid || drafts.length < 2 || state === "LOADING"}
            onClick={() => void submit(true)}
          >
            比较全部情景
          </button>
          {state === "LOADING" && <button onClick={invalidate}>取消请求</button>}
        </div>
        <p className="d-help">
          提交前须完整合法身份、明确成本、全部日期合法输入。比较最少 2 个、最多 20
          个；每个草稿独立校验。输入修改会废止旧结果与排名。
        </p>
      </Panel>
      <ScenarioResultFreshness stale={stale} />
      {state !== "EMPTY" && (
        <StatusPanel
          status={state}
          reason={reason}
          retry={state === "ERROR" ? () => void submit(false) : undefined}
        />
      )}
      {response?.data && !stale && (
        <>
          <SimulationOutput result={response.data} />
          <AuthorityDetails value={response} />
        </>
      )}
      {comparison?.data && !stale && (
        <>
          <ScenarioComparison data={comparison.data} />
          <AuthorityDetails value={comparison} />
        </>
      )}
    </>
  );
}
