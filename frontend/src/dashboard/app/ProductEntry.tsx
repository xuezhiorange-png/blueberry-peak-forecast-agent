import { Component, type ReactNode } from "react";
import { useLocation } from "react-router";
import { App } from "../../app/App";
import { Dashboard } from "./Dashboard";

class DashboardBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main className="dashboard" role="alert">
        <h1>页面暂时无法显示</h1>
        <p>请刷新后重试。错误详情不会在浏览器展示。</p>
        <button onClick={() => location.reload()}>刷新页面</button>
      </main>
    ) : (
      this.props.children
    );
  }
}
export function ProductEntry() {
  const { pathname } = useLocation();
  return pathname === "/dashboard" || pathname.startsWith("/dashboard/") ? (
    <DashboardBoundary>
      <Dashboard />
    </DashboardBoundary>
  ) : (
    <App />
  );
}
