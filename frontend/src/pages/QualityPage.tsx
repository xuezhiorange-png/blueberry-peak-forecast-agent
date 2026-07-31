import { useState } from "react";
import { AsyncState } from "../components/AsyncState";
import { ErrorState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import { ImportLifecycle } from "../features/actualHarvest/ImportLifecycle";
import { QualityReport } from "../features/quality";
import { displayFileSize } from "../lib/formatters";

const importChainAvailable = false;

export function QualityPage() {
  const [file, setFile] = useState<File | null>(null);
  return (
    <main className="page" data-testid="quality-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">TRIAL / QUALITY</p>
          <h1>
            把每一行事实，
            <br />
            放回它的上下文。
          </h1>
          <p className="lead">
            导入实际采摘后，系统会把预测、事实与质量指标绑定到同一份可追溯证据。当前保留完整结构，等待生产能力开放。
          </p>
        </div>
        <div className="heading-meta">
          <strong>校验工作台</strong>文件 transport 与质量报告
          <br />
          按后端合同独立开放
        </div>
      </div>
      <div className="stack">
        <section className="surface section" aria-labelledby="import-title">
          <div className="section-header">
            <div>
              <p className="section-index">01 / ACTUAL HARVEST</p>
              <h2 id="import-title">实际采摘文件导入</h2>
              <p>前端只读取文件字节并计算 SHA-256，业务解析与校验由服务端完成。</p>
            </div>
            <StatusBadge label="链路未就绪" tone="warning" />
          </div>
          <ErrorState
            title="实际采摘上传链路尚未就绪"
            message="当前合同尚未完成可用于本页面的完整 create / upload / validate / readback / commit 生产验证。上传和提交保持禁用。"
          />
          <div className="upload-drop" style={{ marginTop: 18 }}>
            <input
              aria-label="选择 CSV 或 XLSX 文件"
              id="actual-harvest-file"
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
              disabled={!importChainAvailable}
            />
            <label htmlFor="actual-harvest-file">
              <strong>{file ? file.name : "选择 CSV 或 XLSX 文件"}</strong>
              <span>
                {file
                  ? `${displayFileSize(file.size)} · ${file.type || "未知类型"}`
                  : "文件选择保留，上传能力尚未开放"}
              </span>
            </label>
          </div>
          <dl className="file-meta" aria-label="文件元数据">
            {[
              "文件名",
              "文件类型",
              "文件大小",
              "SHA-256",
              "source system",
              "source dataset",
              "source version",
              "external batch id",
              "expected record count",
            ].map((label) => (
              <div key={label}>
                <dt>{label}</dt>
                <dd>
                  {label === "文件名" && file
                    ? file.name
                    : label === "文件大小" && file
                      ? displayFileSize(file.size)
                      : "—"}
                </dd>
              </div>
            ))}
          </dl>
          <AsyncState state="UNAVAILABLE" label="文件导入">
            <div className="state-row" role="status">
              <StatusBadge label="UNAVAILABLE" tone="warning" />
              <span>实际采摘上传链路尚未就绪</span>
            </div>
          </AsyncState>
          <ImportLifecycle />
          <div className="result-grid" aria-label="导入结果">
            <div className="result-line">
              <span>校验状态</span>
              <span className="dash">—</span>
            </div>
            <div className="result-line">
              <span>有效行数 / 无效行数</span>
              <span className="dash">— / —</span>
            </div>
            <div className="result-line">
              <span>错误行列表</span>
              <span className="dash">—</span>
            </div>
            <div className="result-line">
              <span>commit 状态</span>
              <span className="dash">—</span>
            </div>
          </div>
          <div className="button-row">
            <button
              className="button button-primary"
              disabled
              aria-describedby="import-disabled-reason"
            >
              上传并校验
            </button>
            <button
              className="button button-secondary"
              disabled
              aria-describedby="import-disabled-reason"
            >
              提交导入
            </button>
            <span id="import-disabled-reason" className="disabled-reason">
              TRIAL_IMPORT_FULL_CHAIN_AVAILABLE=false；不会发起 mutation。
            </span>
          </div>
        </section>
        <QualityReport />
      </div>
    </main>
  );
}
