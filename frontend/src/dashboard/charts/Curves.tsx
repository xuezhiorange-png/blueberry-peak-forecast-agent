import type { DailyRow, SimulationResult } from "../schemas/contracts";
import { useEffect, useRef, useState } from "react";
import { useForecast } from "../context/ForecastContext";
import { designTokens } from "../styles/tokens";

type PlotRow = { date: string; lead: number; values: (string | null)[] };
// All arithmetic here is local SVG geometry only. Values shown in DOM stay exact strings.
export function SeriesChart({
  label,
  rows,
  series,
  selectedDate,
  onSelect,
  backlog = false,
}: {
  label: string;
  rows: PlotRow[];
  series: string[];
  selectedDate?: string | null;
  onSelect?: (date: string) => void;
  backlog?: boolean;
}) {
  const svg = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 960, height: 280 });
  useEffect(() => {
    const measure = () => {
      const box = svg.current?.getBoundingClientRect();
      if (box && box.width > 0 && box.height > 0) setSize({ width: box.width, height: box.height });
    };
    measure();
    if (typeof ResizeObserver === "undefined" || !svg.current) return;
    const observer = new ResizeObserver(measure);
    observer.observe(svg.current);
    return () => observer.disconnect();
  }, []);
  const numeric = rows
    .flatMap((r) => r.values.map((v) => (v === null ? null : Number(v))))
    .filter((v): v is number => v !== null && Number.isFinite(v));
  const scale = Math.max(1, ...numeric);
  const x = (lead: number) => 50 + ((lead - 1) / 14) * (size.width - 80);
  const bottom = size.height - 40;
  const span = size.height - 70;
  const y = (v: string) => bottom - (Number(v) / scale) * span;
  const color = (index: number) =>
    index === 0
      ? backlog
        ? designTokens.data_series.backlog
        : designTokens.data_series.point
      : designTokens.data_series.capacity;
  return (
    <figure className={`d-chart${backlog ? " d-backlog-chart" : ""}`}>
      <figcaption>{label} · kg</figcaption>
      <div className="d-legend">
        {series.map((s, i) => (
          <span key={s} className={`d-series-${i}`}>
            {s}
          </span>
        ))}
      </div>
      <svg
        ref={svg}
        viewBox={`0 0 ${size.width} ${size.height}`}
        role="img"
        aria-label={label}
        preserveAspectRatio="none"
      >
        <title>{label}，精确数据在辅助表中</title>
        {[0, 0.25, 0.5, 0.75, 1].map((f) => (
          <g key={f}>
            <line
              x1="50"
              x2={size.width - 30}
              y1={bottom - f * span}
              y2={bottom - f * span}
              stroke="#d6dfd8"
            />
            <text x="3" y={bottom + 4 - f * span}>
              {(scale * f).toPrecision(3)}
            </text>
          </g>
        ))}
        {series.map((s, index) => {
          let previous: PlotRow | undefined;
          const segments = rows
            .map((r) => {
              const value = r.values[index];
              const valid = value !== null && value !== undefined && Number.isFinite(Number(value));
              const connected =
                valid &&
                previous !== undefined &&
                previous.lead + 1 === r.lead &&
                previous.values[index] !== null;
              const command = valid ? `${connected ? "L" : "M"}${x(r.lead)},${y(value)}` : "";
              previous = r;
              return command;
            })
            .join(" ");
          return (
            <g key={s}>
              <path
                d={segments}
                fill="none"
                stroke={color(index)}
                strokeWidth="3"
                strokeDasharray={index === 0 ? undefined : "6 4"}
                vectorEffect="non-scaling-stroke"
              />
              {rows
                .filter((r) => r.values[index] !== null && Number.isFinite(Number(r.values[index])))
                .map((r) => (
                  <circle
                    key={r.date}
                    cx={x(r.lead)}
                    cy={y(r.values[index]!)}
                    r={r.date === selectedDate ? 6 : 3}
                    fill={color(index)}
                  >
                    <title>
                      {r.date} · {s} {r.values[index]} kg
                    </title>
                  </circle>
                ))}
            </g>
          );
        })}
        {rows
          .filter((_, i) => i === 0 || i === rows.length - 1 || i === 7)
          .map((r) => (
            <text key={r.date} x={x(r.lead) - 18} y={size.height - 12}>
              {r.date.slice(5)}
            </text>
          ))}
      </svg>
      <div className="d-date-strip" aria-label={`${label}日期选择`}>
        {rows.map((r, i) => (
          <button
            key={r.date}
            aria-pressed={r.date === selectedDate}
            onClick={() => onSelect?.(r.date)}
            onKeyDown={(event) => {
              if (event.key === "ArrowRight" || event.key === "ArrowLeft") {
                event.preventDefault();
                const next =
                  rows[(i + (event.key === "ArrowRight" ? 1 : -1) + rows.length) % rows.length];
                onSelect?.(next.date);
                const buttons = event.currentTarget.parentElement?.querySelectorAll("button");
                buttons?.[
                  (i + (event.key === "ArrowRight" ? 1 : -1) + rows.length) % rows.length
                ]?.focus();
              }
            }}
          >
            {r.date.slice(5)}
          </button>
        ))}
      </div>
      <details>
        <summary>图表辅助数据表 · 精确原值</summary>
        <table className="d-data-table">
          <thead>
            <tr>
              <th>日期</th>
              {series.map((s) => (
                <th key={s}>{s} kg</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.date}>
                <td>{r.date}</td>
                {r.values.map((v, i) => (
                  <td key={i}>{v ?? "暂不可用"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </figure>
  );
}
export function ChartDateDetail({ row }: { row: DailyRow | undefined }) {
  return (
    <div className="d-date-detail" aria-live="polite">
      {row
        ? `${row.target_date} · D${row.lead_day} · 预测值 ${row.point_forecast_kg} kg · 两种规划上界暂不可用`
        : "请选择日期查看精确值"}
    </div>
  );
}
export function DailyForecastChart({ rows }: { rows: DailyRow[] }) {
  const { selectedDate, selectDate } = useForecast();
  return (
    <>
      <SeriesChart
        label="逐日预测"
        rows={rows.map((r) => ({
          date: r.target_date,
          lead: r.lead_day,
          values: [r.point_forecast_kg],
        }))}
        series={["预测值 / POINT"]}
        selectedDate={selectedDate}
        onSelect={selectDate}
      />
      <ChartDateDetail row={rows.find((r) => r.target_date === selectedDate)} />
    </>
  );
}
export function DailyForecastTable({ rows }: { rows: DailyRow[] }) {
  const { selectedDate, selectDate } = useForecast();
  return (
    <table className="d-data-table">
      <caption>原始 Decimal 字符串 · 未绑定的上界不作零值</caption>
      <thead>
        <tr>
          <th>日期 / lead</th>
          <th>预测值 kg</th>
          <th className="d-desktop-extra">规划上界</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.target_date} data-selected={selectedDate === r.target_date}>
            <td>
              <button onClick={() => selectDate(r.target_date)}>{r.target_date}</button>
              <small>D{r.lead_day}</small>
            </td>
            <td>{r.point_forecast_kg}</td>
            <td className="d-desktop-extra">NOT_AVAILABLE</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
export function CapacityDemandChart({ result }: { result: SimulationResult }) {
  const { selectedDate, selectDate } = useForecast();
  return (
    <SeriesChart
      label="规划需求与有效处理能力"
      rows={result.daily_rows.map((r, i) => ({
        date: r.date,
        lead: i + 1,
        values: [r.planning_demand_kg, r.effective_capacity_kg],
      }))}
      series={["规划需求", "有效处理能力"]}
      selectedDate={selectedDate}
      onSelect={selectDate}
    />
  );
}
export function BacklogChart({ result }: { result: SimulationResult }) {
  const { selectedDate, selectDate } = useForecast();
  return (
    <SeriesChart
      label="日末积压（非每日不足量）"
      backlog
      rows={result.daily_rows.map((r, i) => ({
        date: r.date,
        lead: i + 1,
        values: [r.closing_backlog_kg],
      }))}
      series={["日末积压"]}
      selectedDate={selectedDate}
      onSelect={selectDate}
    />
  );
}
