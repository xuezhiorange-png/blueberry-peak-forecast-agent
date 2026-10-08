import { useEffect, useRef } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router";
import { ForecastProvider, useForecast } from "../context/ForecastContext";
import { AuthorizedSavedRunSelector } from "../components/AuthorizedSavedRunSelector";
import { OverviewPage, ForecastPage, AttributionPage, QualityPage } from "../pages/ReadPages";
import { CapacityPage } from "../pages/CapacityPage";
import "../styles/dashboard.css";

export const pages = [
  ["overview", "总览"],
  ["forecast", "预测"],
  ["attribution", "影响因素"],
  ["capacity", "产能模拟"],
  ["quality", "预测质量"],
] as const;
export function PrimaryNavigation() {
  const { leaveGuard } = useForecast();
  const location = useLocation();
  return (
    <nav aria-label="Dashboard 主导航">
      {pages.map(([path, title], i) => (
        <NavLink
          to={`/dashboard/${path}`}
          key={path}
          onClick={(event) => {
            if (
              location.pathname !== `/dashboard/${path}` &&
              leaveGuard.current &&
              !leaveGuard.current()
            )
              event.preventDefault();
          }}
        >
          <span>{String(i + 1).padStart(2, "0")}</span>
          {title}
        </NavLink>
      ))}
    </nav>
  );
}
export function GlobalForecastContext() {
  const { verified, openSelector } = useForecast();
  return (
    <header className="d-context">
      <div>
        <p className="d-eyebrow">已保存预测 · 已核验上下文</p>
        <div className="d-context-title">
          {verified?.query.entity_id ?? "请选择已保存预测"}
          {verified && <span className="d-badge">{verified.query.hierarchy_level}</span>}
        </div>
        <p>
          {verified
            ? `预测起点 ${verified.query.origin_date} · 保存记录 ${verified.query.run_id} · ${verified.curve.data?.available_day_count} 日 · ${verified.curve.status}`
            : "暂无已核验保存记录 · 不自动选择最新"}
        </p>
      </div>
      <button onClick={openSelector}>选择已保存预测</button>
    </header>
  );
}
export function AppShell() {
  const location = useLocation();
  const main = useRef<HTMLElement>(null);
  useEffect(() => {
    main.current?.focus();
  }, [location.pathname]);
  return (
    <div className="dashboard">
      <a className="d-skip" href="#dashboard-main">
        跳到主要内容
      </a>
      <div className="d-shell">
        <aside className="d-sidebar">
          <div className="d-brand">
            <b>BLUEBERRY</b>
            <span>预测智能 / 决策支持</span>
          </div>
          <PrimaryNavigation />
          <div className="d-sidebar-note">
            研究与工程能力
            <br />
            非生产批准
            <br />
            V0.17 / DASHBOARD
          </div>
        </aside>
        <div className="d-workspace">
          <GlobalForecastContext />
          <main id="dashboard-main" ref={main} tabIndex={-1}>
            <Routes>
              <Route path="overview" element={<OverviewPage />} />
              <Route path="forecast" element={<ForecastPage />} />
              <Route path="attribution" element={<AttributionPage />} />
              <Route path="capacity" element={<CapacityPage />} />
              <Route path="quality" element={<QualityPage />} />
              <Route path="*" element={<Navigate to="overview" replace />} />
            </Routes>
            <footer>
              产品化不等于生产验证。Point 不是已证明 P50；规划上界不是已证明 P80/P90
              分位数；历史覆盖率不保证未来覆盖。
              <br />
              正常业务发现及生产多用户资源授权仍待解决。
            </footer>
          </main>
        </div>
      </div>
      <AuthorizedSavedRunSelector />
    </div>
  );
}
export function Dashboard() {
  return (
    <ForecastProvider>
      <Routes>
        <Route path="/dashboard/*" element={<AppShell />} />
      </Routes>
    </ForecastProvider>
  );
}
