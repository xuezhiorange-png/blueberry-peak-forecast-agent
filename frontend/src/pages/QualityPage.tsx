import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { TrialClientError } from "../api/trialClient";
import { ImportLifecycle } from "../features/actualHarvest/ImportLifecycle";
import {
  fileMimeType,
  importApi,
  sha256Hex,
  type ImportInvalidRow,
  type ImportStatus,
  type ImportUploadResponse,
} from "../features/actualHarvest/importApi";
import { forecastApi } from "../features/forecast/forecastApi";
import { QualityReport } from "../features/quality/QualityReport";
import { qualityApi } from "../features/quality/qualityApi";
import type {
  QualityComparison,
  QualityReport as QualityReportData,
} from "../features/quality/qualitySchemas";
import { getOrCreateIdempotencyKey } from "../lib/idempotency";
import { displayFileSize } from "../lib/formatters";

type HashState = "IDLE" | "HASHING" | "COMPLETED" | "ERROR";
type ActionState =
  "IDLE" | "UPLOADING" | "POLLING" | "COMMITTING" | "LOADING" | "CREATING" | "EXPORTING";

function safeErrorMessage(error: unknown): string {
  if (error instanceof TrialClientError) return error.message;
  if (error instanceof Error && error.message === "UNSUPPORTED_FILE")
    return "文件扩展名与 MIME 不受支持，仅允许 CSV 或 XLSX。";
  return "服务暂不可用，请稍后重试。";
}

function toIsoTimestamp(value: string): string | null {
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

function wait(milliseconds: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

export function QualityPage() {
  const [file, setFile] = useState<File | null>(null);
  const [hash, setHash] = useState<string | null>(null);
  const [hashState, setHashState] = useState<HashState>("IDLE");
  const [fileError, setFileError] = useState<string | null>(null);
  const [actionState, setActionState] = useState<ActionState>("IDLE");
  const [importError, setImportError] = useState<string | null>(null);
  const [importId, setImportId] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<ImportStatus | null>(null);
  const [uploadResult, setUploadResult] = useState<ImportUploadResponse | null>(null);
  const [invalidRows, setInvalidRows] = useState<ImportInvalidRow[]>([]);
  const [sourceSystem, setSourceSystem] = useState("trial-api");
  const [sourceDataset, setSourceDataset] = useState("daily-harvest");
  const [sourceVersion, setSourceVersion] = useState("2026-01");
  const [externalBatchId, setExternalBatchId] = useState("trial-harvest-batch");
  const [forecastRunId, setForecastRunId] = useState("");
  const [forecastCutoffAt, setForecastCutoffAt] = useState<string | null>(null);
  const [labelCutoffAt, setLabelCutoffAt] = useState("2026-03-10T12:00");
  const [report, setReport] = useState<QualityReportData | null>(null);
  const [comparison, setComparison] = useState<QualityComparison | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const selectionId = useRef(0);
  const actionAbort = useRef<AbortController | null>(null);

  useEffect(() => () => actionAbort.current?.abort(), []);

  function startAction(state: ActionState): AbortController {
    actionAbort.current?.abort();
    const controller = new AbortController();
    actionAbort.current = controller;
    setActionState(state);
    return controller;
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    const currentSelection = ++selectionId.current;
    setFile(selected);
    setHash(null);
    setFileError(null);
    setUploadResult(null);
    setImportError(null);
    setHashState("IDLE");
    if (!selected) return;
    if (!fileMimeType(selected)) {
      setFileError("不支持的文件类型或 MIME，仅允许 .csv 或 .xlsx。文件未上传。");
      setHashState("ERROR");
      return;
    }
    setHashState("HASHING");
    try {
      const calculatedHash = await sha256Hex(selected);
      if (currentSelection !== selectionId.current) return;
      setHash(calculatedHash);
      setExternalBatchId(`trial-harvest-${calculatedHash.slice(0, 12)}`);
      setHashState("COMPLETED");
    } catch {
      if (currentSelection !== selectionId.current) return;
      setHashState("ERROR");
      setFileError("文件校验暂时无法完成，文件未上传。");
    }
  }

  async function refreshImport(
    currentImportId: string,
    controller: AbortController,
    initialStatus?: ImportStatus,
  ): Promise<void> {
    let current =
      initialStatus ?? (await importApi.status(currentImportId, undefined, controller.signal));
    for (let attempt = 0; attempt < 12; attempt += 1) {
      if (controller.signal.aborted) return;
      setImportStatus(current);
      if (
        [
          "VALIDATED",
          "VALIDATION_FAILED",
          "PARSE_FAILED",
          "COMMITTED",
          "COMMIT_FAILED",
          "CANCELLED",
        ].includes(current.status)
      )
        break;
      await wait(500);
      current = await importApi.status(currentImportId, undefined, controller.signal);
    }
    setImportStatus(current);
    if (current.status === "VALIDATION_FAILED") {
      const errors = await importApi.errors(
        currentImportId,
        undefined,
        undefined,
        controller.signal,
      );
      setInvalidRows([...errors.rows]);
    }
  }

  async function uploadAndValidate(): Promise<void> {
    if (!file || !hash || hashState !== "COMPLETED") return;
    const controller = startAction("UPLOADING");
    setImportError(null);
    setInvalidRows([]);
    try {
      const created = await importApi.create(
        {
          source_system: sourceSystem.trim(),
          source_dataset: sourceDataset.trim(),
          source_version: sourceVersion.trim(),
          external_batch_id: externalBatchId.trim(),
          expected_record_count_or_null: null,
          request_idempotency_key: getOrCreateIdempotencyKey(`actual-harvest-${hash}`),
        },
        undefined,
        controller.signal,
      );
      setImportId(created.import_id);
      setActionState("UPLOADING");
      const uploaded = await importApi.upload(
        created.import_id,
        file,
        hash,
        undefined,
        controller.signal,
      );
      setUploadResult(uploaded);
      setActionState("POLLING");
      await refreshImport(created.import_id, controller);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setImportError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function commitImport(): Promise<void> {
    const evidenceIdentity = uploadResult?.validation_run_instance_identity_hash_or_null;
    if (!importId || !evidenceIdentity || importStatus?.status !== "VALIDATED") return;
    const controller = startAction("COMMITTING");
    setImportError(null);
    try {
      await importApi.commit(importId, evidenceIdentity, undefined, controller.signal);
      await refreshImport(importId, controller);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setImportError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function loadForecast(): Promise<void> {
    if (!forecastRunId) return;
    const controller = startAction("LOADING");
    setQualityError(null);
    try {
      const forecast = await forecastApi.read(forecastRunId.trim(), undefined, controller.signal);
      if (!forecast.forecast_cutoff_at) throw new TrialClientError("EVIDENCE_CONFLICT", 409);
      setForecastRunId(forecast.run_id);
      setForecastCutoffAt(forecast.forecast_cutoff_at);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setQualityError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function createQualityReport(): Promise<void> {
    const cutoff = toIsoTimestamp(labelCutoffAt);
    if (!importId || importStatus?.status !== "COMMITTED" || !forecastCutoffAt || !cutoff) return;
    const controller = startAction("CREATING");
    setQualityError(null);
    try {
      const request = {
        forecast_run_id: forecastRunId.trim(),
        actual_harvest_import_id: importId,
        forecast_cutoff_at: forecastCutoffAt,
        label_observation_cutoff_at: cutoff,
        requested_horizons_days: [7, 14, 21] as [7, 14, 21],
        request_idempotency_key: getOrCreateIdempotencyKey("quality-report"),
      };
      const created = await qualityApi.create(request, undefined, controller.signal);
      const persisted = await qualityApi.read(created.report_id, undefined, controller.signal);
      if (persisted.report_id !== created.report_id)
        throw new TrialClientError("EVIDENCE_CONFLICT", 409);
      const persistedComparison = await qualityApi.comparison(
        persisted.report_id,
        undefined,
        controller.signal,
      );
      if (persistedComparison.report_id !== persisted.report_id)
        throw new TrialClientError("EVIDENCE_CONFLICT", 409);
      setReport(persisted);
      setComparison(persistedComparison);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setQualityError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function exportQuality(): Promise<void> {
    if (!report) return;
    const controller = startAction("EXPORTING");
    setQualityError(null);
    try {
      const download = await qualityApi.export(report.report_id, undefined, controller.signal);
      const url = URL.createObjectURL(download.blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = download.filename;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        setQualityError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
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
            Actual Harvest 只上传原始字节；Quality 只读取同一 actor 下的 Forecast、committed import
            与 persisted evidence。
          </p>
        </div>
        <div className="heading-meta">
          <strong>V0.2 / S5</strong>Actual Harvest + Quality integration
          <br />
          服务端拥有校验和指标公式
        </div>
      </div>
      <div className="stack">
        <section className="surface section" aria-labelledby="import-title">
          <div className="section-header">
            <div>
              <p className="section-index">01 / ACTUAL HARVEST</p>
              <h2 id="import-title">实际采摘文件导入</h2>
              <p>CREATE → raw bytes → poll → invalid rows → COMMIT。</p>
            </div>
            <span className="eyebrow-tag">{importStatus?.status ?? "待开始"}</span>
          </div>
          {importError && (
            <div className="notice notice-danger" role="alert">
              <span className="notice-icon" aria-hidden="true">
                !
              </span>
              <div>
                <strong>导入操作未完成</strong>
                {importError}
              </div>
            </div>
          )}
          <div className="upload-drop upload-drop-ready">
            <input
              aria-label="选择 CSV 或 XLSX 文件"
              id="actual-harvest-file"
              type="file"
              accept=".csv,.xlsx"
              onChange={handleFileChange}
              disabled={actionState !== "IDLE"}
            />
            <label htmlFor="actual-harvest-file">
              <strong>{file ? file.name : "选择 CSV 或 XLSX 文件"}</strong>
              <span>
                {file
                  ? `${displayFileSize(file.size)} · ${file.type || "按扩展名识别 MIME"}`
                  : "服务端将验证文件名、MIME、大小与 SHA-256"}
              </span>
            </label>
          </div>
          {fileError && (
            <div className="notice notice-danger compact-notice" role="alert">
              <span className="notice-icon" aria-hidden="true">
                !
              </span>
              <div>{fileError}</div>
            </div>
          )}
          <div className="state-row" role="status" aria-busy={hashState === "HASHING"}>
            <span
              className="status-badge"
              data-tone={
                hashState === "ERROR" ? "danger" : hashState === "COMPLETED" ? "success" : "neutral"
              }
            >
              {hashState}
            </span>
            <span>
              {hashState === "HASHING"
                ? "SHA-256 计算中…"
                : hashState === "COMPLETED"
                  ? "SHA-256 已完成"
                  : "等待文件选择"}
            </span>
          </div>
          <div className="form-grid form-grid-spaced">
            <div className="field">
              <label htmlFor="import-source-system">source system</label>
              <input
                id="import-source-system"
                value={sourceSystem}
                onChange={(event) => setSourceSystem(event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
            <div className="field">
              <label htmlFor="import-source-dataset">source dataset</label>
              <input
                id="import-source-dataset"
                value={sourceDataset}
                onChange={(event) => setSourceDataset(event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
            <div className="field">
              <label htmlFor="import-source-version">source version</label>
              <input
                id="import-source-version"
                value={sourceVersion}
                onChange={(event) => setSourceVersion(event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
            <div className="field">
              <label htmlFor="import-external-batch">external batch id</label>
              <input
                id="import-external-batch"
                value={externalBatchId}
                onChange={(event) => setExternalBatchId(event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
          </div>
          <dl className="file-meta" aria-label="文件元数据">
            <div>
              <dt>文件名</dt>
              <dd>{file?.name ?? "—"}</dd>
            </div>
            <div>
              <dt>MIME type</dt>
              <dd>{file ? (fileMimeType(file) ?? "不支持") : "—"}</dd>
            </div>
            <div>
              <dt>文件大小</dt>
              <dd>{displayFileSize(file?.size)}</dd>
            </div>
            <div>
              <dt>SHA-256</dt>
              <dd className="hash-value">{hash ?? "—"}</dd>
            </div>
            <div>
              <dt>Import ID</dt>
              <dd className="hash-value">{importId ?? "—"}</dd>
            </div>
          </dl>
          <ImportLifecycle status={importStatus?.status ?? uploadResult?.server_status} />
          {invalidRows.length > 0 && (
            <div className="invalid-rows" aria-label="服务端 invalid rows">
              <h3>服务端校验错误行</h3>
              {invalidRows.map((row) => (
                <div className="result-line" key={`${row.record_index}-${row.error_code}`}>
                  <span>
                    {row.record_index ?? "—"} · {row.field_path ?? "row"}
                  </span>
                  <span>
                    {row.error_code} · {row.message_template_id}
                  </span>
                </div>
              ))}
              <p className="field-hint">
                错误由服务端验证 evidence 返回，浏览器不重新校验业务数据。
              </p>
            </div>
          )}
          <div className="button-row">
            <button
              className="button button-primary"
              type="button"
              onClick={() => void uploadAndValidate()}
              disabled={!file || !hash || hashState !== "COMPLETED" || actionState !== "IDLE"}
            >
              {actionState === "UPLOADING" || actionState === "POLLING" ? "处理中…" : "上传并校验"}
            </button>
            <button
              className="button button-secondary"
              type="button"
              onClick={() => void commitImport()}
              disabled={
                !importId ||
                importStatus?.status !== "VALIDATED" ||
                !uploadResult?.validation_run_instance_identity_hash_or_null ||
                actionState !== "IDLE"
              }
            >
              {actionState === "COMMITTING" ? "提交中…" : "提交导入"}
            </button>
            <span className="disabled-reason">
              只有服务端 VALIDATED 且存在 validation identity 时才允许 commit。
            </span>
          </div>
        </section>
        <QualityReport
          forecastRunId={forecastRunId}
          onForecastRunIdChange={setForecastRunId}
          forecastCutoffAt={forecastCutoffAt}
          labelCutoffAt={labelCutoffAt}
          onLabelCutoffAtChange={setLabelCutoffAt}
          onLoadForecast={loadForecast}
          loadingForecast={actionState === "LOADING"}
          committedImportId={importStatus?.status === "COMMITTED" ? importId : null}
          onCreateReport={createQualityReport}
          report={report}
          comparison={comparison}
          creating={actionState === "CREATING"}
          onExport={exportQuality}
          exporting={actionState === "EXPORTING"}
          errorMessage={qualityError}
        />
      </div>
    </main>
  );
}
