import { DailyCurve } from "../../components/DailyCurve";
import { ExportButton } from "../../components/ExportButton";
import { PeakSummary } from "../../components/PeakSummary";

const rows = ["数据缺口", "阻断原因", "模型版本", "参数版本", "策略版本"];

export function ForecastResult() {
  return (
    <section className="surface section" aria-labelledby="forecast-result-title">
      <div className="section-header">
        <div>
          <p className="section-index">02 / RESULT</p>
          <h2 id="forecast-result-title">预测结果</h2>
          <p>结果只显示后端权威值，不在浏览器中重算数量或峰值。</p>
        </div>
        <ExportButton />
      </div>
      <DailyCurve />
      <PeakSummary />
      <div className="result-grid" aria-label="预测结果明细">
        {rows.map((label) => (
          <div className="result-line" key={label}>
            <span>{label}</span>
            <span className="dash">—　后端能力未就绪</span>
          </div>
        ))}
      </div>
    </section>
  );
}
