import { Component, type ErrorInfo, type ReactNode } from "react";
import { NavLink } from "react-router";
import { AppRoutes } from "./routes";

type ErrorBoundaryState = { hasError: boolean };

class AppErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(_error: Error, _info: ErrorInfo) {
    void _error;
    void _info;
    // Deliberately keep exception details out of the UI.
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="error-boundary" role="alert">
          <p className="eyebrow">TRIAL / 系统状态</p>
          <h1>页面暂时无法显示</h1>
          <p>请刷新页面后重试。服务端详细错误不会在浏览器中展示。</p>
          <button className="button button-primary" onClick={() => window.location.reload()}>
            刷新页面
          </button>
        </main>
      );
    }
    return this.props.children;
  }
}

function Shell() {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="主导航">
        <NavLink className="brand" to="/trial/forecast" aria-label="返回 Forecast">
          <span className="brand-mark" aria-hidden="true">
            BP
          </span>
          <span>
            <strong>蓝莓产量</strong>
            <small>预测助手 / TRIAL</small>
          </span>
        </NavLink>
        <div className="sidebar-rule" />
        <p className="nav-label">工作台</p>
        <nav className="nav-links">
          <NavLink to="/trial/forecast" className={({ isActive }) => (isActive ? "active" : "")}>
            <span>01</span> 预测试算
          </NavLink>
          <NavLink to="/trial/quality" className={({ isActive }) => (isActive ? "active" : "")}>
            <span>02</span> 质量核验
          </NavLink>
        </nav>
        <div className="sidebar-footer">
          <StatusDot />
          <span>
            <strong>试用环境</strong>
            <small>生产能力按合同开放</small>
          </span>
        </div>
      </aside>
      <header className="mobile-header">
        <NavLink className="brand brand-mobile" to="/trial/forecast">
          <span className="brand-mark" aria-hidden="true">
            BP
          </span>
          <strong>蓝莓产量预测助手</strong>
        </NavLink>
        <nav className="mobile-nav" aria-label="移动端主导航">
          <NavLink to="/trial/forecast">预测</NavLink>
          <NavLink to="/trial/quality">质量</NavLink>
        </nav>
      </header>
      <div className="main-column">
        <div className="top-status" role="status">
          <span className="status-pulse" aria-hidden="true" />
          当前仅开放 Trial 合同能力
          <span className="top-status-separator">·</span>
          预测与质量生产适配器尚未就绪
        </div>
        <AppRoutes />
      </div>
    </div>
  );
}

function StatusDot() {
  return <span className="status-dot" aria-hidden="true" />;
}

export function App() {
  return (
    <AppErrorBoundary>
      <Shell />
    </AppErrorBoundary>
  );
}
