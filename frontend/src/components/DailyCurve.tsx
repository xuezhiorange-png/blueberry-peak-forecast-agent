export function DailyCurve({ title = "P50 / P80 / P90 日曲线" }: { title?: string }) {
  return (
    <div className="chart-shell" aria-label={title}>
      <div className="chart-title">
        <strong>{title}</strong>
        <span>数据待后端提供</span>
      </div>
      <div className="empty-chart">—　后端能力未就绪</div>
    </div>
  );
}
