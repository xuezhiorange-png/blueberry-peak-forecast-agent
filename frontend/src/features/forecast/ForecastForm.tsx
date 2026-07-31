const authorityFields = ["加工厂", "产季", "农场", "分场", "品种"];
const inputFields = [
  ["预测日期", "date"],
  ["种植面积（亩）", "text"],
  ["开花日期", "date"],
  ["成熟阶段", "text"],
  ["已采摘数量（kg）", "text"],
] as const;

export function ForecastForm() {
  return (
    <section className="surface section" aria-labelledby="forecast-input-title">
      <div className="section-header">
        <div>
          <p className="section-index">01 / INPUT</p>
          <h2 id="forecast-input-title">预测输入</h2>
          <p>正式权威范围开放后，输入将进入同一 Trial 合同。</p>
        </div>
        <span className="eyebrow-tag">未就绪</span>
      </div>
      <div className="notice" role="status">
        <span className="notice-icon" aria-hidden="true">
          i
        </span>
        <div>
          <strong>预测后端能力未就绪</strong>
          当前页面已完成输入、结果及异常状态结构。后端生产适配器完成后才会开放预测提交和结果读取。
        </div>
      </div>
      <div className="form-grid" style={{ marginTop: 20 }}>
        {authorityFields.map((label) => (
          <div className="field" key={label}>
            <label htmlFor={`authority-${label}`}>{label}</label>
            <select
              id={`authority-${label}`}
              disabled
              aria-describedby="forecast-disabled-reason"
              defaultValue=""
            >
              <option value="">等待后端提供可选范围</option>
            </select>
          </div>
        ))}
        {inputFields.map(([label, type]) => (
          <div className="field" key={label}>
            <label htmlFor={`input-${label}`}>{label}</label>
            <input
              id={`input-${label}`}
              type={type}
              disabled
              placeholder="预测输入能力尚未就绪"
              aria-describedby="forecast-disabled-reason"
            />
          </div>
        ))}
      </div>
      <div className="button-row">
        <button
          className="button button-primary"
          disabled
          aria-describedby="forecast-disabled-reason"
        >
          生成预测
        </button>
        <button
          className="button button-secondary"
          disabled
          aria-describedby="forecast-disabled-reason"
        >
          查询预测
        </button>
        <span id="forecast-disabled-reason" className="disabled-reason">
          预测输入权威与生产预测适配器尚未就绪，不会发起网络请求。
        </span>
      </div>
    </section>
  );
}
