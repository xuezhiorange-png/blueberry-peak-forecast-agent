import { formatDecimal, formatReasons } from "../../lib/formatters";
import type { QualityReport } from "./qualitySchemas";

const columns = ["业务日期", "预测 P50", "预测 P80", "预测 P90", "实际数量", "状态", "原因"];

export function QualityOverlay({
  report,
  horizonDays = 7,
}: {
  report: QualityReport | null;
  horizonDays?: 7 | 14 | 21;
}) {
  const horizon = report?.horizons.find((item) => item.horizon_days === horizonDays);
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption className="sr-only">服务端持久化的预测与实际逐日叠加</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {horizon?.daily_overlay.length ? (
            horizon.daily_overlay.map((row) => (
              <tr key={row.business_date}>
                <td>{row.business_date}</td>
                <td>{formatDecimal(row.forecast_p50_kg_or_null)}</td>
                <td>{formatDecimal(row.forecast_p80_kg_or_null)}</td>
                <td>{formatDecimal(row.forecast_p90_kg_or_null)}</td>
                <td>{formatDecimal(row.actual_quantity_kg_or_null)}</td>
                <td>{row.coverage_state}</td>
                <td>{formatReasons(row.exclusion_reason_codes)}</td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length} className="dash">
                {report
                  ? "服务端未返回该 horizon 的 overlay 行"
                  : "创建质量报告后展示服务端 overlay"}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
