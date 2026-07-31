const columns = ["业务日期", "预测 P50", "预测 P80", "预测 P90", "实际数量", "状态", "原因"];

export function QualityOverlay() {
  return (
    <div className="table-wrap">
      <table className="data-table">
        <caption className="sr-only">预测与实际逐日叠加</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column}>{column}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            {columns.map((column) => (
              <td key={column} className="dash">
                —
              </td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}
