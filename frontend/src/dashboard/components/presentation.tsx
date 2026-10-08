import type { ReactNode } from "react";
import type {
  Status,
  OverviewData,
  HierarchyData,
  DailyRow,
  QualityData,
  ComparisonData,
  ReadResponse,
} from "../schemas/contracts";
import { useForecast } from "../context/ForecastContext";

export function Panel({
  title,
  note,
  children,
  className = "",
}: {
  title: string;
  note?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`d-panel ${className}`}>
      <div className="d-panel-heading">
        <div>
          <h2>{title}</h2>
          {note && <p>{note}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}
const copy: Record<Status, string> = {
  LOADING: "正在读取已验证来源",
  READY: "数据就绪（仅适用于已绑定模块）",
  EMPTY: "请选择已保存预测",
  PARTIAL: "部分数据：可用日期不足或子节点覆盖不完整",
  NOT_AVAILABLE: "当前权威来源不支持此能力",
  ERROR: "暂时无法读取，请重试",
  AUTHORITY_MISMATCH: "来源身份不一致，已停止展示受影响结果",
  NO_CURRENT_ACTUAL: "当前产季暂无可用于正式评分的实际采收数据。",
};
export function StatusPanel({
  status,
  reason,
  retry,
}: {
  status: Status;
  reason?: string;
  retry?: () => void;
}) {
  return (
    <div
      className={`d-notice d-state-${status}`}
      role="status"
      aria-busy={status === "LOADING"}
      data-state={status}
    >
      <strong>{copy[status]}</strong>
      {reason && <p>{reason}</p>}
      {retry && status !== "LOADING" && (
        <button onClick={retry}>
          {status === "AUTHORITY_MISMATCH" || status === "EMPTY" ? "重新核验保存记录" : "重试"}
        </button>
      )}
    </div>
  );
}
export function LoadingSkeleton() {
  return (
    <div className="d-skeleton" aria-busy="true">
      <StatusPanel status="LOADING" />
      <div className="d-kpis">
        {[1, 2, 3, 4].map((n) => (
          <div key={n} />
        ))}
      </div>
    </div>
  );
}
export function ErrorState({
  status = "ERROR",
  reason,
  retry,
}: {
  status?: Status;
  reason?: string;
  retry: () => void;
}) {
  return <StatusPanel status={status} reason={reason} retry={retry} />;
}
export function UnavailableState({ reason }: { reason: string }) {
  return <StatusPanel status="NOT_AVAILABLE" reason={reason} />;
}
export function EmptyState() {
  const { openSelector } = useForecast();
  return (
    <Panel title="请选择已保存预测">
      <p>正常业务发现尚未接入；不会自动猜测最新记录。</p>
      <StatusPanel
        status="EMPTY"
        reason="高级完整身份输入用于技术核验，不是访问授权。"
        retry={openSelector}
      />
    </Panel>
  );
}
export function AuthorityDetails({ value }: { value: unknown }) {
  return (
    <details className="d-authority">
      <summary>权威来源详情</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function DecimalPreview({ value }: { value: string | null }) {
  // Text excerpt only: no numeric conversion, rounding, quantization or feedback.
  return value === null ? (
    <>暂不可用</>
  ) : (
    <span title={value} aria-label={value}>
      {value.length > 16 ? `${value.slice(0, 12)}…` : value}
    </span>
  );
}
export function KpiCard({
  label,
  value,
  unit,
  note,
  displayValue,
}: {
  label: string;
  value: string | number | null;
  unit?: string;
  note?: string;
  displayValue?: string;
}) {
  return (
    <article className="d-kpi">
      <div className="d-kpi-label">{label}</div>
      <div className="d-kpi-value" title={value === null ? undefined : String(value)}>
        {displayValue ??
          (value === null
            ? "—"
            : typeof value === "string" && unit
              ? value.replace(/(\.\d*?[1-9])0+$|\.0+$/, "$1")
              : value)}{" "}
        {unit && <small>{unit}</small>}
      </div>
      <div className="d-help">
        {note ?? (value === null ? "暂不可用，不作零值" : "服务端权威值")}
      </div>
    </article>
  );
}
export function KpiGrid({ data }: { data: OverviewData }) {
  return (
    <div className="d-kpis" aria-label="核心四项指标">
      <KpiCard
        label="预测起点后 7 日累计量"
        value={data.forecast_7d_total_kg}
        unit="kg"
        note={
          data.forecast_7d_status === "COMPUTABLE_FULL_WINDOW"
            ? "D1–D7 · 完整保存窗口"
            : data.forecast_7d_status
        }
      />
      <KpiCard
        label="预测起点后 15 日累计量"
        value={data.forecast_15d_total_kg}
        unit="kg"
        note={
          data.forecast_15d_status === "COMPUTABLE_FULL_WINDOW"
            ? "D1–D15 · 完整保存窗口"
            : data.forecast_15d_status
        }
      />
      <KpiCard
        label="保存曲线高峰日期"
        value={data.peak_date}
        displayValue={data.peak_date?.slice(5)}
        note={data.peak_date ? `${data.peak_date.slice(0, 4)}年 · 已保存曲线范围` : undefined}
      />
      <KpiCard label="高峰日预测量" value={data.peak_daily_quantity_kg} unit="kg" />
    </div>
  );
}
export function HighLoadDateList({ rows }: { rows: DailyRow[] }) {
  const { selectDate } = useForecast();
  return (
    <Panel title="较高预测量日期" note="相对关注顺序 · 不代表生产告警">
      <ol className="d-high-list">
        {rows.slice(0, 5).map((r) => (
          <li key={r.target_date}>
            <button onClick={() => selectDate(r.target_date)}>{r.target_date}</button>
            <strong>{r.point_forecast_kg} kg</strong>
            <span>关注</span>
          </li>
        ))}
      </ol>
    </Panel>
  );
}
export function HierarchyCompletenessPanel({ data }: { data: HierarchyData }) {
  return (
    <Panel title="子节点覆盖">
      <p>
        {data.source_status} · {data.available_day_count} 个保存日期
      </p>
      {data.child_expected_count !== null && (
        <dl>
          <dt>预期子节点</dt>
          <dd>{data.child_expected_count}</dd>
          <dt>已包含</dt>
          <dd>{data.child_included_count}</dd>
          <dt>缺失</dt>
          <dd>{data.missing_child_count}</dd>
        </dl>
      )}
      <p className="d-help">缺失不作零；不读取当前 registry 改写历史层级。</p>
    </Panel>
  );
}
export function ContributionPanel() {
  return (
    <Panel title="区域 / 基地贡献" className="d-unavailable">
      <UnavailableState reason="服务端尚无同源子实体贡献比例合同；浏览器不计算比例。" />
    </Panel>
  );
}
export function ContributionChart() {
  return (
    <Panel title="影响因素贡献暂不可用" className="d-unavailable">
      <p>没有合法归因 authority，就不展示因素排名或贡献柱形。</p>
      <div className="d-notice">
        <strong>模型归因，不是因果解释</strong>
        <p>不能把一般特征重要性冒充本次预测的解释。</p>
      </div>
    </Panel>
  );
}
export function AttributionAuthorityPanel({
  value,
}: {
  value: ReadResponse<Record<string, never>>;
}) {
  return (
    <Panel title="本次预测的解释 authority">
      <StatusPanel status={value.status} reason={value.unavailable_reason ?? undefined} />
      <AuthorityDetails value={value} />
    </Panel>
  );
}
export function ScenarioResultFreshness({ stale }: { stale: boolean }) {
  return stale ? (
    <StatusPanel
      status="PARTIAL"
      reason="输入已修改，结果已过期。当前输入没有有效结果或排名，请重新提交。"
    />
  ) : null;
}
export function ScenarioComparison({ data }: { data: ComparisonData }) {
  return (
    <Panel title="给定条件下的情景排序" note="仅限相同保存预测、规划水平、日期与成本合同">
      <div className="d-rank-list">
        {data.comparison.rankings.map((rank) => {
          const result = data.scenario_results.find((r) => r.scenario_id === rank.scenario_id);
          return (
            <article key={rank.scenario_id}>
              <h3>
                #{rank.scenario_rank} · {rank.scenario_id}
              </h3>
              {result && (
                <dl>
                  <dt>合成损失</dt>
                  <dd>{result.total_business_loss} SYNTHETIC_LOSS_UNIT</dd>
                  <dt>最大积压 kg</dt>
                  <dd>{result.max_backlog_kg}</dd>
                  <dt>累计日不足 kg</dt>
                  <dd>{result.cumulative_shortfall_kg}</dd>
                  <dt>期末积压 kg</dt>
                  <dd>{result.ending_backlog_kg}</dd>
                </dl>
              )}
              <AuthorityDetails value={rank} />
            </article>
          );
        })}
      </div>
      <p className="d-help">{data.comparison.ranking_semantics}。不是优化、排产或公司真实收益。</p>
      <AuthorityDetails value={data.comparison} />
    </Panel>
  );
}
export function HistoricalScopeSummary({ data }: { data: QualityData }) {
  return (
    <Panel title="历史验证范围" note="独立于所选 Operational Peak 保存预测">
      <div className="d-scope">
        {[data.model_id, data.source_split, data.target_season, data.scope].map((v) => (
          <span key={v} className="d-badge">
            {v}
          </span>
        ))}
      </div>
      <p className="d-help">
        HISTORICAL_VALIDATION · RETROSPECTIVE_OBSERVATION · STRICT_PIT=false ·
        production_accuracy_validated=false · prospective_interval_coverage_validated=false
      </p>
    </Panel>
  );
}
export function QualityMetricPanel({ data }: { data: QualityData }) {
  return (
    <Panel title="历史点预测指标" note="非当前生产表现；长数值截取展示，精确原值见来源详情">
      <div className="d-quality-grid">
        {data.horizons.map((h) => (
          <article key={h.horizon}>
            <h3>
              {h.horizon} · {h.point_status}
            </h3>
            <dl>
              <dt>WAPE（比例）</dt>
              <dd>
                <DecimalPreview value={h.wape} />
              </dd>
              <dt>MAE kg</dt>
              <dd>
                <DecimalPreview value={h.mae_kg} />
              </dd>
              <dt>Bias kg</dt>
              <dd>
                <DecimalPreview value={h.bias_kg} />
              </dd>
              <dt>累计 WAPE（比例）</dt>
              <dd>
                <DecimalPreview value={h.cumulative_wape} />
              </dd>
              <dt>日行数 / 可评分起点</dt>
              <dd>
                {h.daily_row_count ?? "—"} / {h.scorable_origin_count ?? "—"}
              </dd>
            </dl>
          </article>
        ))}
      </div>
    </Panel>
  );
}
export function CoverageComparisonChart({ data }: { data: QualityData }) {
  return (
    <Panel title="区间与规划上界历史覆盖" note="RETROSPECTIVE_OBSERVATION · 不是未来覆盖保证">
      <div className="d-notice d-state-PARTIAL">
        <strong>历史覆盖率低于名义水平</strong>
        <p>保留负面观察，不解释为达到 80% / 90% 目标。</p>
      </div>
      {data.horizons.map((h) => (
        <section key={h.horizon}>
          <h3>
            {h.horizon} · {h.interval_status}
          </h3>
          {h.interval_status === "NOT_AVAILABLE" ? (
            <UnavailableState reason="该窗口没有冻结的区间覆盖证据，不推算。" />
          ) : (
            h.interval_coverage.map((c) => (
              <article className="d-coverage" key={c.interval}>
                <h4>{c.interval} · UNDER_NOMINAL</h4>
                <div
                  className="d-coverage-bar"
                  role="img"
                  aria-label={`观察比例 ${c.empirical_coverage}；名义比例 ${c.nominal_coverage}`}
                >
                  <div
                    style={{
                      width: `${Math.max(0, Math.min(1, Number(c.empirical_coverage))) * 100}%`,
                    }}
                  />
                  <i
                    style={{
                      left: `${Math.max(0, Math.min(1, Number(c.nominal_coverage))) * 100}%`,
                    }}
                  />
                </div>
                <dl>
                  <dt>历史观察比例</dt>
                  <dd>
                    <DecimalPreview value={c.empirical_coverage} />
                  </dd>
                  <dt>名义比例</dt>
                  <dd>{c.nominal_coverage}</dd>
                  <dt>候选 / 可计算 / 不可计算 / 覆盖</dt>
                  <dd>
                    {c.candidate_row_count} / {c.computable_row_count} /{" "}
                    {c.not_computable_row_count} / {c.covered_row_count}
                  </dd>
                </dl>
              </article>
            ))
          )}
        </section>
      ))}
    </Panel>
  );
}
