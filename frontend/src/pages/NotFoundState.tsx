import { Link } from "react-router";

export function NotFoundState() {
  return (
    <main className="page">
      <div className="not-found">
        <p className="eyebrow">404 / NOT FOUND</p>
        <h1>
          这条路径
          <br />
          还没有页面。
        </h1>
        <p className="lead">请从 Trial 工作台选择一个已开放的页面。</p>
        <div className="button-row">
          <Link className="button button-primary" to="/trial/forecast">
            回到预测试算
          </Link>
        </div>
      </div>
    </main>
  );
}
