import { formatDecimal, formatReasons } from "../lib/formatters";
import type { ForecastDailyRow } from "../features/forecast/forecastSchemas";

export function DailyCurve({
  rows = [],
  title = "P50 / P80 / P90 日曲线",
}: {
  rows?: readonly ForecastDailyRow[];
  title?: string;
}) {
  return (
    <div className="chart-shell" aria-label={title} data-testid="daily-curve">
      <div className="chart-title">
        <strong>{title}</strong>
        <span>{rows.length > 0 ? `${rows.length} 个服务端日序列点` : "暂无服务端日序列"}</span>
      </div>
      {rows.length === 0 ? (
        <div className="empty-chart">暂无可展示的逐日证据</div>
      ) : (
        <div className="table-wrap curve-table-wrap">
          <table className="data-table curve-table">
            <caption className="sr-only">服务端返回的 P50、P80、P90 逐日预测</caption>
            <thead>
              <tr>
                <th>日期</th>
                <th>P50 kg</th>
                <th>P80 kg</th>
                <th>P90 kg</th>
                <th>状态 / 原因</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.target_date}>
                  <td>{row.target_date}</td>
                  <td>{formatDecimal(row.p50_value_kg)}</td>
                  <td>{formatDecimal(row.p80_value_kg)}</td>
                  <td>{formatDecimal(row.p90_value_kg)}</td>
                  <td>
                    <span>{row.row_status}</span>
                    <small className="table-reasons">{formatReasons(row.reason_codes)}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
