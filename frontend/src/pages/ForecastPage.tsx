import { ForecastForm, ForecastResult } from "../features/forecast";

export function ForecastPage() {
  return (
    <main className="page" data-testid="forecast-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TRIAL / FORECAST</p>
          <h1>
            先看清输入，
            <br />
            再相信预测。
          </h1>
          <p className="lead">
            把加工厂、产季与地块输入放在同一条可追溯链路上。当前先冻结界面契约，等待后端权威能力开放。
          </p>
        </div>
        <div className="heading-meta">
          <strong>V0.2 / S5</strong>前端先行体验
          <br />
          生产数据不会在此页面伪造
        </div>
      </div>
      <div className="stack">
        <ForecastForm />
        <ForecastResult />
      </div>
    </main>
  );
}
