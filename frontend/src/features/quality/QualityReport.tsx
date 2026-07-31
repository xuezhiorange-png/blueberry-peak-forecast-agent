import { ExportButton } from "../../components/ExportButton";
import { QualityOverlay } from "./QualityOverlay";

const metrics = [
  "日级误差",
  "累计误差",
  "单日峰值误差",
  "连续 7 日峰值误差",
  "P80 coverage",
  "P90 coverage",
  "区间指标",
  "naive baseline comparison",
];
const horizons = ["7 天指标", "14 天指标", "21 天指标"];

export function QualityReport() {
  return (
    <section className="surface section" aria-labelledby="quality-report-title">
      <div className="section-header">
        <div>
          <p className="section-index">02 / QUALITY RESULT</p>
          <h2 id="quality-report-title">Forecast versus actual</h2>
          <p>逐日事实与指标均应由同一份后端证据返回。</p>
        </div>
        <ExportButton label="导出质量 CSV" />
      </div>
      <QualityOverlay />
      <div className="metric-grid" aria-label="质量指标">
        {metrics.map((label) => (
          <div className="metric" key={label}>
            <span className="metric-label">{label}</span>
            <strong className="metric-value muted">—</strong>
            <small>后端能力未就绪</small>
          </div>
        ))}
      </div>
      <div className="result-grid" aria-label="正式 horizon 指标">
        {horizons.map((label) => (
          <div className="result-line" key={label}>
            <span>{label}</span>
            <span className="dash">—　后端能力未就绪</span>
          </div>
        ))}
      </div>
      <div className="button-row">
        <button
          className="button button-primary"
          disabled
          aria-describedby="quality-disabled-reason"
        >
          生成质量报告
        </button>
        <button
          className="button button-secondary"
          disabled
          aria-describedby="quality-disabled-reason"
        >
          查询报告
        </button>
        <button
          className="button button-secondary"
          disabled
          aria-describedby="quality-disabled-reason"
        >
          对比模型
        </button>
        <span id="quality-disabled-reason" className="disabled-reason">
          Quality 生产适配器与逐日 overlay 尚未就绪，不会发起网络请求。
        </span>
      </div>
    </section>
  );
}
