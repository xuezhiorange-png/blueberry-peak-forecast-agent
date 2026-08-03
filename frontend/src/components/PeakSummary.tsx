import { formatDecimal, formatReasons } from "../lib/formatters";
import type { ForecastSummary } from "../features/forecast/forecastSchemas";

export function PeakSummary({ summary }: { summary: ForecastSummary | null }) {
  const metrics = summary
    ? [
        ["单日峰值", `${formatDecimal(summary.single_day_peak.quantity_kg)} kg`],
        ["单日峰值日期", summary.single_day_peak.date],
        [
          "连续 7 日累计",
          `${formatDecimal(summary.sustained_seven_day_peak.cumulative_quantity_kg)} kg`,
        ],
        [
          "连续 7 日窗口",
          `${summary.sustained_seven_day_peak.start_date} → ${summary.sustained_seven_day_peak.end_date}`,
        ],
        [
          "成熟库存（开 / 闭）",
          `${formatDecimal(summary.mature_inventory_summary.opening_quantity_kg)} / ${formatDecimal(summary.mature_inventory_summary.closing_quantity_kg)} kg`,
        ],
        ["未采 backlog", `${formatDecimal(summary.backlog_summary.quantity_kg)} kg`],
      ]
    : [];
  return (
    <div className="metric-grid" aria-label="预测摘要">
      {metrics.length === 0 ? (
        <div className="metric metric-empty">
          <span className="metric-label">预测摘要</span>
          <strong className="metric-value muted">—</strong>
          <small>创建预测后展示服务端证据</small>
        </div>
      ) : (
        metrics.map(([label, value]) => (
          <div className="metric" key={label}>
            <span className="metric-label">{label}</span>
            <strong className="metric-value">{value}</strong>
            <small>服务端持久化投影</small>
          </div>
        ))
      )}
      {summary &&
        (summary.data_gap_summaries.length > 0 || summary.blocker_summaries.length > 0) && (
          <div className="metric metric-wide" data-testid="forecast-gaps">
            <span className="metric-label">阻断与数据缺口</span>
            <strong className="metric-value">
              {summary.blocker_summaries.length > 0 ? "BLOCKED" : "GAPS"}
            </strong>
            <small>
              {formatReasons([...summary.blocker_summaries, ...summary.data_gap_summaries])}
            </small>
          </div>
        )}
    </div>
  );
}
