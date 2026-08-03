import { useState } from "react";
import { ExportButton } from "../../components/ExportButton";
import { formatDecimal, formatReasons, formatTimestamp } from "../../lib/formatters";
import { QualityOverlay } from "./QualityOverlay";
import type { QualityComparison, QualityReport } from "./qualitySchemas";

const horizons = [7, 14, 21] as const;

export function QualityReport({
  forecastRunId,
  onForecastRunIdChange,
  forecastCutoffAt,
  labelCutoffAt,
  onLabelCutoffAtChange,
  onLoadForecast,
  loadingForecast,
  committedImportId,
  onCreateReport,
  report,
  comparison,
  creating,
  onExport,
  exporting,
  errorMessage,
}: {
  forecastRunId: string;
  onForecastRunIdChange: (value: string) => void;
  forecastCutoffAt: string | null;
  labelCutoffAt: string;
  onLabelCutoffAtChange: (value: string) => void;
  onLoadForecast: () => Promise<void>;
  loadingForecast: boolean;
  committedImportId: string | null;
  onCreateReport: () => Promise<void>;
  report: QualityReport | null;
  comparison: QualityComparison | null;
  creating: boolean;
  onExport: () => Promise<void>;
  exporting: boolean;
  errorMessage: string | null;
}) {
  const [horizonDays, setHorizonDays] = useState<7 | 14 | 21>(7);
  const selectedHorizon = report?.horizons.find((item) => item.horizon_days === horizonDays);
  return (
    <section className="surface section" aria-labelledby="quality-report-title">
      <div className="section-header">
        <div>
          <p className="section-index">02 / QUALITY RESULT</p>
          <h2 id="quality-report-title">Forecast versus actual</h2>
          <p>Quality scope 来自 persisted Forecast 与 committed Actual Harvest evidence。</p>
        </div>
        <ExportButton
          disabled={!report || !comparison || !selectedHorizon}
          label="导出质量 CSV"
          onClick={() => void onExport()}
          busy={exporting}
        />
      </div>
      {errorMessage && (
        <div className="notice notice-danger" role="alert">
          <span className="notice-icon" aria-hidden="true">
            !
          </span>
          <div>
            <strong>质量链路未完成</strong>
            {errorMessage}
          </div>
        </div>
      )}
      <div className="form-grid">
        <div className="field field-full">
          <label htmlFor="quality-forecast-run-id">Forecast public run ID</label>
          <input
            id="quality-forecast-run-id"
            value={forecastRunId}
            onChange={(event) => onForecastRunIdChange(event.target.value)}
            placeholder="64 位 lowercase SHA-256"
            autoComplete="off"
          />
          <span className="field-hint">
            只接受公开 Forecast ID，不接受数据库 ID 或 owner identity。
          </span>
        </div>
        <div className="field">
          <label htmlFor="quality-label-cutoff-at">Label observation cutoff</label>
          <input
            id="quality-label-cutoff-at"
            type="datetime-local"
            value={labelCutoffAt}
            onChange={(event) => onLabelCutoffAtChange(event.target.value)}
            disabled={creating}
          />
        </div>
        <div className="field">
          <label>Persisted Forecast cutoff</label>
          <input
            value={formatTimestamp(forecastCutoffAt)}
            readOnly
            aria-label="Persisted Forecast cutoff"
          />
        </div>
      </div>
      <div className="button-row">
        <button
          className="button button-secondary"
          type="button"
          onClick={() => void onLoadForecast()}
          disabled={!forecastRunId || loadingForecast || creating}
        >
          {loadingForecast ? "读取中…" : "读取 Forecast"}
        </button>
        <button
          className="button button-primary"
          type="button"
          onClick={() => void onCreateReport()}
          disabled={!forecastCutoffAt || !committedImportId || !labelCutoffAt || creating}
        >
          {creating ? "生成中…" : "生成质量报告"}
        </button>
        <span className="disabled-reason">
          {committedImportId
            ? `已绑定 committed import ${committedImportId}`
            : "请先完成同一 actor 下的 Actual Harvest commit。"}
        </span>
      </div>
      {report ? (
        <>
          <div className="result-grid" aria-label="质量报告身份">
            <div className="result-line">
              <span>Quality report ID</span>
              <span className="hash-value">{report.report_id}</span>
            </div>
            <div className="result-line">
              <span>状态</span>
              <span>{report.computability_status}</span>
            </div>
            <div className="result-line">
              <span>Forecast cutoff</span>
              <span>{formatTimestamp(report.forecast_cutoff_at)}</span>
            </div>
            <div className="result-line">
              <span>Label cutoff</span>
              <span>{formatTimestamp(report.label_observation_cutoff_at)}</span>
            </div>
          </div>
          <div className="horizon-tabs" role="tablist" aria-label="质量 horizon">
            {horizons.map((horizon) => (
              <button
                key={horizon}
                className={`button ${horizon === horizonDays ? "button-primary" : "button-secondary"}`}
                type="button"
                role="tab"
                aria-selected={horizon === horizonDays}
                onClick={() => setHorizonDays(horizon)}
              >
                {horizon} 天
              </button>
            ))}
          </div>
          {selectedHorizon ? (
            <>
              <QualityOverlay report={report} horizonDays={horizonDays} />
              <div className="metric-grid" aria-label={`质量指标 ${horizonDays} 天`}>
                {[
                  [
                    "日级指标",
                    selectedHorizon.daily_metrics[0]?.metric_value_or_null ?? null,
                    selectedHorizon.daily_metrics[0]?.metric_status,
                  ],
                  [
                    "累计指标",
                    selectedHorizon.cumulative_metric.metric_value_or_null,
                    selectedHorizon.cumulative_metric.metric_status,
                  ],
                  [
                    "P80 coverage",
                    selectedHorizon.p80_coverage.coverage_ratio_or_null,
                    selectedHorizon.p80_coverage.metric_status,
                  ],
                  [
                    "P90 coverage",
                    selectedHorizon.p90_coverage.coverage_ratio_or_null,
                    selectedHorizon.p90_coverage.metric_status,
                  ],
                  [
                    "单日峰值",
                    selectedHorizon.single_day_peak.metric_value_or_null,
                    selectedHorizon.single_day_peak.metric_status,
                  ],
                  [
                    "连续 7 日峰值",
                    selectedHorizon.sustained_seven_day_peak.metric_value_or_null,
                    selectedHorizon.sustained_seven_day_peak.metric_status,
                  ],
                ].map(([label, value, status]) => (
                  <div className="metric" key={label}>
                    <span className="metric-label">{label}</span>
                    <strong className="metric-value">
                      {formatDecimal(value as string | null)}
                    </strong>
                    <small>状态：{status}</small>
                  </div>
                ))}
              </div>
              <div className="result-grid" aria-label="覆盖与区间状态">
                <div className="result-line">
                  <span>P80 状态 / 原因</span>
                  <span>
                    {selectedHorizon.p80_coverage.metric_status} ·{" "}
                    {formatReasons(selectedHorizon.p80_coverage.reason_codes)}
                  </span>
                </div>
                <div className="result-line">
                  <span>P90 状态 / 原因</span>
                  <span>
                    {selectedHorizon.p90_coverage.metric_status} ·{" "}
                    {formatReasons(selectedHorizon.p90_coverage.reason_codes)}
                  </span>
                </div>
                <div className="result-line">
                  <span>区间下界</span>
                  <span>
                    {selectedHorizon.interval_metric.lower_bound_available
                      ? formatDecimal(selectedHorizon.interval_metric.lower_bound_value_or_null)
                      : "不可用"}
                  </span>
                </div>
                <div className="result-line">
                  <span>coverage counts</span>
                  <span>
                    total {selectedHorizon.coverage_counts.total} · comparable{" "}
                    {selectedHorizon.coverage_counts.comparable} · covered{" "}
                    {selectedHorizon.coverage_counts.covered}
                  </span>
                </div>
                <div className="result-line">
                  <span>excluded rows</span>
                  <span>
                    {selectedHorizon.excluded_row_counts.excluded} · not computable{" "}
                    {selectedHorizon.excluded_row_counts.not_computable}
                  </span>
                </div>
                <div className="result-line">
                  <span>原因</span>
                  <span>{formatReasons(selectedHorizon.reason_codes)}</span>
                </div>
              </div>
              {comparison && (
                <div className="comparison-panel" aria-label="baseline comparison">
                  <h3>Persisted baseline comparison</h3>
                  {comparison.model_baseline_deltas.map((delta) => (
                    <div className="result-line" key={delta.comparison_key_hash}>
                      <span>
                        {delta.comparison_name} / {delta.forecast_horizon_days} 天
                      </span>
                      <span>
                        {delta.comparison_availability} · {formatDecimal(delta.delta_value_or_null)}{" "}
                        · {formatReasons(delta.reason_codes)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="notice notice-danger" role="alert">
              当前选择的 {horizonDays} 天 horizon 未返回，已停止展示其他 horizon 或顶层指标。
            </div>
          )}
        </>
      ) : (
        <div className="empty-state" role="status">
          完成 Forecast 读取与 Actual Harvest commit 后生成质量报告。
        </div>
      )}
    </section>
  );
}
