import { useState, type ReactNode } from "react";
import { useForecast } from "../context/ForecastContext";
import { useResource, type Resource } from "../context/useResource";
import { read, quality } from "../api/client";
import { DailyForecastChart, DailyForecastTable } from "../charts/Curves";
import {
  Panel,
  EmptyState,
  LoadingSkeleton,
  ErrorState,
  StatusPanel,
  UnavailableState,
  AuthorityDetails,
  KpiGrid,
  ContributionPanel,
  HighLoadDateList,
  HierarchyCompletenessPanel,
  AttributionAuthorityPanel,
  ContributionChart,
  HistoricalScopeSummary,
  QualityMetricPanel,
  CoverageComparisonChart,
} from "../components/presentation";

export function Heading({ title, description }: { title: string; description: string }) {
  return (
    <div className="d-page-heading">
      <div>
        <p className="d-eyebrow">FORECAST INTELLIGENCE</p>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
    </div>
  );
}
export function ResourceView<T>({
  resource,
  children,
  independent = false,
}: {
  resource: Resource<T>;
  children: (value: T) => ReactNode;
  independent?: boolean;
}) {
  const { openSelector } = useForecast();
  if (resource.status === "EMPTY" && resource.value === null)
    return independent ? (
      <StatusPanel
        status="EMPTY"
        reason="暂无冻结历史质量结果，不使用所选预测替代。"
        retry={resource.retry}
      />
    ) : (
      <EmptyState />
    );
  if (resource.status === "LOADING") return <LoadingSkeleton />;
  if (resource.status === "ERROR" || resource.status === "AUTHORITY_MISMATCH")
    return (
      <ErrorState
        status={resource.status}
        reason={resource.reason}
        retry={
          resource.status === "AUTHORITY_MISMATCH" && !independent ? openSelector : resource.retry
        }
      />
    );
  return (
    <>
      {resource.status !== "READY" && (
        <StatusPanel status={resource.status} reason={resource.reason} retry={resource.retry} />
      )}
      {resource.value && children(resource.value)}
    </>
  );
}
function BoundsPanel() {
  const { verified } = useForecast();
  const bound = useResource(verified?.key ?? null, (signal) =>
    read("uncertainty", verified!.query, signal),
  );
  return (
    <Panel title="规划上界可用性">
      <ResourceView resource={bound}>
        {(v) => (
          <>
            <p>80%规划上界 / 90%规划上界：{v.status}。不回退 POINT。</p>
            <AuthorityDetails value={v} />
          </>
        )}
      </ResourceView>
    </Panel>
  );
}
export function OverviewPage() {
  const { verified } = useForecast();
  const overview = useResource(verified?.key ?? null, (s) => read("overview", verified!.query, s));
  const curve = useResource(verified?.key ?? null, (s) => read("curve", verified!.query, s));
  const hierarchy = useResource(verified?.key ?? null, (s) =>
    read("hierarchy", verified!.query, s),
  );
  return (
    <>
      <Heading title="总览" description="从保存的预测出发，先看数量，再看规划压力。" />
      <ResourceView resource={overview}>
        {(v) =>
          v.data && (
            <>
              <KpiGrid data={v.data} />
              <AuthorityDetails
                value={{
                  forecast_identity: v.forecast_identity,
                  source_result_hash: v.source_result_hash,
                  projection_hash: v.projection_hash,
                }}
              />
            </>
          )
        }
      </ResourceView>
      {verified && (
        <>
          <Panel title="逐日预测" note="保存曲线，不是相对今天的未来预测">
            <ResourceView resource={curve}>
              {(v) => v.data && <DailyForecastChart rows={v.data.daily_rows} />}
            </ResourceView>
          </Panel>
          <BoundsPanel />
          <div className="d-columns">
            <ContributionPanel />
            {overview.value?.data && (
              <HighLoadDateList rows={overview.value.data.high_load_dates} />
            )}
          </div>
          <ResourceView resource={hierarchy}>
            {(v) => v.data && <HierarchyCompletenessPanel data={v.data} />}
          </ResourceView>
          <Panel title="能力与数据范围">
            <p>
              Forecast：按保存记录可用 · Uncertainty / Attribution：未绑定 · ForecastOps：仅历史 ·
              Current Actual：NOT_AVAILABLE
            </p>
          </Panel>
        </>
      )}
    </>
  );
}
export function ForecastPage() {
  const { verified } = useForecast();
  const [horizon, setHorizon] = useState(15);
  const curve = useResource(verified?.key ?? null, (s) => read("curve", verified!.query, s));
  const hierarchy = useResource(verified?.key ?? null, (s) =>
    read("hierarchy", verified!.query, s),
  );
  return (
    <>
      <Heading title="预测" description="核对日期、每日数量与保存预测的完整性。" />
      <ResourceView resource={curve}>
        {(v) =>
          v.data && (
            <>
              <Panel
                title="保存预测日曲线"
                note={`可用 ${v.data.available_day_count} 日 · ${v.data.data_completeness}`}
              >
                <div className="d-tabs" aria-label="日期显示窗口">
                  {[1, 3, 7, 15].map((h) => (
                    <button key={h} aria-pressed={h === horizon} onClick={() => setHorizon(h)}>
                      H{h}
                    </button>
                  ))}
                </div>
                <p className="d-help">
                  H{horizon} = D1..D{horizon} 前缀，不是单日；只截取已有日期，不计算新的累计指标。
                </p>
                <DailyForecastChart rows={v.data.daily_rows.filter((r) => r.lead_day <= horizon)} />
                <AuthorityDetails value={v} />
              </Panel>
              <BoundsPanel />
              <Panel title="每日预测明细">
                <DailyForecastTable rows={v.data.daily_rows.filter((r) => r.lead_day <= horizon)} />
              </Panel>
            </>
          )
        }
      </ResourceView>
      {verified && (
        <ResourceView resource={hierarchy}>
          {(v) => v.data && <HierarchyCompletenessPanel data={v.data} />}
        </ResourceView>
      )}
    </>
  );
}
export function AttributionPage() {
  const { verified } = useForecast();
  const result = useResource(verified?.key ?? null, (s) => read("attribution", verified!.query, s));
  return (
    <>
      <Heading title="影响因素" description="先确认解释来源，再阅读模型贡献。" />
      <ResourceView resource={result}>
        {(v) => (
          <>
            <AttributionAuthorityPanel value={v} />
            <ContributionChart />
            {v.status === "READY" && (
              <UnavailableState reason="READY 归因 payload 尚未获 Schema 授权，不启用图表。" />
            )}
          </>
        )}
      </ResourceView>
    </>
  );
}
export function QualityPage() {
  const history = useResource("historical-quality-M1", (s) => quality(s));
  const current = useResource("current-quality-availability", (s) => quality(s, true));
  return (
    <>
      <Heading
        title="预测质量"
        description="历史验证，不是当前生产表现；不跟随全局保存记录重标。"
      />
      <Panel title="当前产季">
        <ResourceView resource={current} independent>
          {() => null}
        </ResourceView>
      </Panel>
      <ResourceView resource={history} independent>
        {(v) =>
          v.data && (
            <>
              <HistoricalScopeSummary data={v.data} />
              <QualityMetricPanel data={v.data} />
              <CoverageComparisonChart data={v.data} />
              <AuthorityDetails
                value={{
                  source_result_hash: v.source_result_hash,
                  projection_hash: v.projection_hash,
                  authority_identity: v.authority_identity,
                  exact_historical_values: v.data,
                }}
              />
            </>
          )
        }
      </ResourceView>
    </>
  );
}
