import { displayValue } from "../lib/formatters";

const metrics = [
  ["单日峰值", "singleDayPeak"],
  ["连续 7 日峰值", "sustainedSevenDayPeak"],
  ["产季累计量", "seasonTotal"],
  ["成熟库存", "matureInventory"],
  ["未采 backlog", "backlog"],
  ["数据缺口", "dataGap"],
] as const;

export function PeakSummary() {
  return (
    <div className="metric-grid" aria-label="预测摘要">
      {metrics.map(([label, key]) => (
        <div className="metric" key={key}>
          <span className="metric-label">{label}</span>
          <strong className="metric-value muted">{displayValue(null)}</strong>
          <small>后端能力未就绪</small>
        </div>
      ))}
    </div>
  );
}
