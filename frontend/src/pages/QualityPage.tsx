import { useRef, useState, type ChangeEvent } from "react";
import { AsyncState } from "../components/AsyncState";
import { ErrorState } from "../components/ErrorState";
import { StatusBadge } from "../components/StatusBadge";
import { ImportLifecycle } from "../features/actualHarvest/ImportLifecycle";
import { sha256Hex } from "../features/actualHarvest/importApi";
import { QualityReport } from "../features/quality";
import { displayFileSize } from "../lib/formatters";

const importChainAvailable = false;

type HashState = "IDLE" | "HASHING" | "COMPLETED" | "ERROR";

export function QualityPage() {
  const [file, setFile] = useState<File | null>(null);
  const [hash, setHash] = useState<string | null>(null);
  const [hashState, setHashState] = useState<HashState>("IDLE");
  const [fileError, setFileError] = useState<string | null>(null);
  const selectionId = useRef(0);

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    const currentSelection = ++selectionId.current;
    setFile(selected);
    setHash(null);
    setFileError(null);
    setHashState("IDLE");
    if (!selected) return;

    const lowerName = selected.name.toLowerCase();
    if (!lowerName.endsWith(".csv") && !lowerName.endsWith(".xlsx")) {
      setFileError("不支持的文件类型，仅允许 .csv 或 .xlsx。文件未上传。");
      setHashState("ERROR");
      return;
    }

    setHashState("HASHING");
    try {
      const calculatedHash = await sha256Hex(selected);
      if (currentSelection !== selectionId.current) return;
      setHash(calculatedHash);
      setHashState("COMPLETED");
    } catch {
      if (currentSelection !== selectionId.current) return;
      setHashState("ERROR");
      setFileError("文件校验暂时无法完成，文件未上传。");
    }
  }

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
              accept=".csv,.xlsx"
              onChange={handleFileChange}
            />
            <label htmlFor="actual-harvest-file">
              <strong>{file ? file.name : "选择 CSV 或 XLSX 文件"}</strong>
              <span>
                {file
                  ? `${displayFileSize(file.size)} · ${file.type || "未知 MIME type"}`
                  : "文件选择可用，上传能力尚未开放"}
              </span>
            </label>
          </div>
          {fileError && <ErrorState title="本地文件未就绪" message={fileError} />}
          <div className="state-row" role="status" aria-busy={hashState === "HASHING"}>
            <StatusBadge
              label={hashState === "HASHING" ? "HASHING" : "LOCAL"}
              tone={hashState === "ERROR" ? "danger" : "neutral"}
            />
            <span>
              {hashState === "HASHING"
                ? "SHA-256 计算中…"
                : hashState === "COMPLETED"
                  ? "SHA-256 已完成"
                  : "等待文件选择"}
            </span>
          </div>
          <dl className="file-meta" aria-label="文件元数据">
            {[
              "文件名",
              "MIME type",
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
                    : label === "MIME type" && file
                      ? file.type || "未知 MIME type"
                      : label === "文件大小" && file
                        ? displayFileSize(file.size)
                        : label === "SHA-256" && hashState === "HASHING"
                          ? "计算中…"
                          : label === "SHA-256" && hash
                            ? hash
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
              disabled={!importChainAvailable}
              aria-describedby="import-disabled-reason"
            >
              上传并校验
            </button>
            <button
              className="button button-secondary"
              disabled={!importChainAvailable}
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
