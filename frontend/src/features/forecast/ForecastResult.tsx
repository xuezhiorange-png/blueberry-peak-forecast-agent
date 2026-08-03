import { DailyCurve } from "../../components/DailyCurve";
import { ExportButton } from "../../components/ExportButton";
import { PeakSummary } from "../../components/PeakSummary";
import { formatHash, formatReasons, formatTimestamp } from "../../lib/formatters";
import type { ForecastDailyCurve, ForecastSummary } from "./forecastSchemas";

export function ForecastResult({
  summary,
  daily,
  onExport,
  exporting,
  errorMessage,
}: {
  summary: ForecastSummary | null;
  daily: ForecastDailyCurve | null;
  onExport: () => Promise<void>;
  exporting: boolean;
  errorMessage: string | null;
}) {
  return (
    <section className="surface section" aria-labelledby="forecast-result-title">
      <div className="section-header">
        <div>
          <p className="section-index">02 / PERSISTED RESULT</p>
          <h2 id="forecast-result-title">预测结果</h2>
          <p>POST 成功后重新读取 persisted summary 与 daily curve，浏览器不重算指标。</p>
        </div>
        <ExportButton
          disabled={!summary || !daily || Boolean(errorMessage)}
          label="导出 Forecast CSV"
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
            <strong>预测结果不可用</strong>
            {errorMessage}
          </div>
        </div>
      )}
      {summary ? (
        <>
          <div className="result-grid" aria-label="预测证据身份">
            <div className="result-line">
              <span>Forecast run ID</span>
              <span className="hash-value" data-testid="forecast-run-id">
                {formatHash(summary.run_id)}
              </span>
            </div>
            <div className="result-line">
              <span>状态</span>
              <span>{summary.status}</span>
            </div>
            <div className="result-line">
              <span>预测截止时间</span>
              <span>{formatTimestamp(summary.forecast_cutoff_at)}</span>
            </div>
            <div className="result-line">
              <span>模型 / 参数 / 策略</span>
              <span>
                {summary.model_version} · {summary.parameter_version} ·{" "}
                {summary.policy_versions.forecast}
              </span>
            </div>
          </div>
          <DailyCurve rows={daily?.rows ?? summary.daily_p50_series} />
          <PeakSummary summary={summary} />
          <div className="result-grid" aria-label="预测结果明细">
            <div className="result-line">
              <span>数据缺口</span>
              <span>{formatReasons(summary.data_gap_summaries)}</span>
            </div>
            <div className="result-line">
              <span>阻断原因</span>
              <span>{formatReasons(summary.blocker_summaries)}</span>
            </div>
            <div className="result-line">
              <span>参数 identity</span>
              <span className="hash-value">{formatHash(summary.parameter_identity)}</span>
            </div>
            <div className="result-line">
              <span>结果 hash</span>
              <span className="hash-value">{formatHash(summary.result_hash)}</span>
            </div>
          </div>
        </>
      ) : (
        <div className="empty-state" role="status">
          选择 authority 范围并生成预测后，这里展示服务端持久化结果。
        </div>
      )}
    </section>
  );
}
