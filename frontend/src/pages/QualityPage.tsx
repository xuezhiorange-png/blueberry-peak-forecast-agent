import { useEffect, useRef, useState, type ChangeEvent } from "react";
import { TrialClientError } from "../api/trialClient";
import { ImportLifecycle } from "../features/actualHarvest/ImportLifecycle";
import {
  fileMimeType,
  importApi,
  sha256Hex,
  type ImportInvalidRow,
  type ImportInvalidRowsResponse,
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

const MAX_IMPORT_POLL_ATTEMPTS = 12;
const MAX_INVALID_ROW_PAGES = 100;
const IMPORT_POLL_INTERVAL_MS = 500;

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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

function isTerminalImportStatus(status: ImportStatus["status"]): boolean {
  return [
    "VALIDATED",
    "VALIDATION_FAILED",
    "PARSE_FAILED",
    "COMMITTED",
    "COMMIT_FAILED",
    "CANCELLED",
  ].includes(status);
}

export function qualityReportRequestScope(values: {
  forecastRunId: string;
  importId: string;
  forecastCutoffAt: string;
  labelCutoffAt: string;
  horizons: readonly number[];
}): string {
  return [
    "quality-report",
    values.forecastRunId,
    values.importId,
    values.forecastCutoffAt,
    values.labelCutoffAt,
    values.horizons.join(","),
  ].join("|");
}

export function actualHarvestCreateRequestScope(values: {
  sourceSystem: string;
  sourceDataset: string;
  sourceVersion: string;
  externalBatchId: string;
  expectedRecordCountOrNull: number | null;
}): string {
  return `actual-harvest-create|${JSON.stringify([
    values.sourceSystem.trim(),
    values.sourceDataset.trim(),
    values.sourceVersion.trim(),
    values.externalBatchId.trim(),
    values.expectedRecordCountOrNull === null ? "<null>" : values.expectedRecordCountOrNull,
  ])}`;
}

type InvalidRowPage = ImportInvalidRowsResponse;

export type InvalidRowEvidenceExpectation = {
  importId: string;
  validationIdentity: string;
};

export type PollImportStatusResult = {
  status: ImportStatus;
  timedOut: boolean;
};

function createAbortError(): DOMException {
  return new DOMException("The operation was aborted", "AbortError");
}

export async function pollImportStatus(
  loadStatus: () => Promise<ImportStatus>,
  options: {
    initialStatus?: ImportStatus;
    wait?: () => Promise<void>;
    maxAttempts?: number;
    signal?: AbortSignal;
    onStatus?: (status: ImportStatus) => void;
  } = {},
): Promise<PollImportStatusResult> {
  const maxAttempts = options.maxAttempts ?? MAX_IMPORT_POLL_ATTEMPTS;
  if (maxAttempts < 1) throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  let current = options.initialStatus;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    if (options.signal?.aborted) throw createAbortError();
    current = current ?? (await loadStatus());
    if (options.signal?.aborted) throw createAbortError();
    options.onStatus?.(current);
    if (isTerminalImportStatus(current.status)) return { status: current, timedOut: false };
    if (attempt === maxAttempts - 1) return { status: current, timedOut: true };
    await (options.wait ?? (() => wait(IMPORT_POLL_INTERVAL_MS)))();
    current = undefined;
  }
  throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
}

export async function collectInvalidRows(
  loadPage: (pageToken?: string, signal?: AbortSignal) => Promise<InvalidRowPage>,
  expected: InvalidRowEvidenceExpectation,
  signal?: AbortSignal,
  maxPages = MAX_INVALID_ROW_PAGES,
): Promise<ImportInvalidRow[]> {
  if (!expected.importId || !expected.validationIdentity || maxPages < 1)
    throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  const rows: ImportInvalidRow[] = [];
  const seenTokens = new Set<string>();
  let pageToken: string | undefined;
  for (let page = 0; page < maxPages; page += 1) {
    if (signal?.aborted) throw createAbortError();
    const response = await loadPage(pageToken, signal);
    if (signal?.aborted) throw createAbortError();
    if (
      response.import_id !== expected.importId ||
      response.validation_status !== "VALIDATION_FAILED" ||
      response.validation_run_instance_identity_hash_or_null !== expected.validationIdentity
    ) {
      throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
    }
    rows.push(...response.rows);
    if (response.next_page_token === null) return rows;
    const nextToken = response.next_page_token;
    if (!nextToken || seenTokens.has(nextToken)) {
      throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
    }
    seenTokens.add(nextToken);
    pageToken = nextToken;
  }
  throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
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
  const [pollingTimedOut, setPollingTimedOut] = useState(false);
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
  const [qualityExportError, setQualityExportError] = useState<string | null>(null);
  const selectionId = useRef(0);
  const actionAbort = useRef<AbortController | null>(null);
  const previousCommittedImportId = useRef<string | null | undefined>(undefined);
  const committedImportId = importStatus?.status === "COMMITTED" ? importId : null;

  useEffect(() => () => actionAbort.current?.abort(), []);

  useEffect(() => {
    if (
      previousCommittedImportId.current !== undefined &&
      previousCommittedImportId.current !== committedImportId
    ) {
      setReport(null);
      setComparison(null);
      setQualityExportError(null);
    }
    previousCommittedImportId.current = committedImportId;
  }, [committedImportId]);

  function startAction(state: ActionState): AbortController {
    actionAbort.current?.abort();
    const controller = new AbortController();
    actionAbort.current = controller;
    setActionState(state);
    return controller;
  }

  function cancelCurrentAction(): void {
    actionAbort.current?.abort();
    actionAbort.current = null;
    setActionState("IDLE");
  }

  function clearImportEvidence(): void {
    cancelCurrentAction();
    setImportId(null);
    setImportStatus(null);
    setUploadResult(null);
    setInvalidRows([]);
    setPollingTimedOut(false);
    setImportError(null);
    setReport(null);
    setComparison(null);
    setQualityError(null);
    setQualityExportError(null);
  }

  function changeImportMetadata(setter: (value: string) => void, value: string): void {
    clearImportEvidence();
    setter(value);
  }

  async function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const selected = event.target.files?.[0] ?? null;
    const currentSelection = ++selectionId.current;
    cancelCurrentAction();
    setFile(selected);
    setHash(null);
    setFileError(null);
    setImportId(null);
    setImportStatus(null);
    setUploadResult(null);
    setInvalidRows([]);
    setPollingTimedOut(false);
    setImportError(null);
    setReport(null);
    setComparison(null);
    setQualityError(null);
    setQualityExportError(null);
    setHashState("IDLE");
    setActionState("IDLE");
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
    validationIdentity = uploadResult?.validation_run_instance_identity_hash_or_null,
  ): Promise<void> {
    const result = await pollImportStatus(
      () => importApi.status(currentImportId, undefined, controller.signal),
      {
        initialStatus,
        signal: controller.signal,
        onStatus: setImportStatus,
      },
    );
    if (result.timedOut) {
      setPollingTimedOut(true);
      setImportError("状态读取超时，未自动重新创建或上传。请重新读取状态。");
      return;
    }
    setPollingTimedOut(false);
    if (result.status.status === "VALIDATION_FAILED")
      await readAllInvalidRows(currentImportId, controller, validationIdentity);
  }

  async function readAllInvalidRows(
    currentImportId: string,
    controller: AbortController,
    validationIdentity: string | null | undefined,
  ): Promise<void> {
    if (!validationIdentity) throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
    setInvalidRows([]);
    const rows = await collectInvalidRows(
      (pageToken, signal) => importApi.errors(currentImportId, pageToken, undefined, signal, 100),
      { importId: currentImportId, validationIdentity },
      controller.signal,
    );
    if (!controller.signal.aborted) setInvalidRows(rows);
  }

  async function retryImportStatus(): Promise<void> {
    if (!importId) return;
    const controller = startAction("POLLING");
    setPollingTimedOut(false);
    setImportError(null);
    try {
      await refreshImport(
        importId,
        controller,
        undefined,
        uploadResult?.validation_run_instance_identity_hash_or_null,
      );
    } catch (error) {
      if (!isAbortError(error)) setImportError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function uploadAndValidate(): Promise<void> {
    if (!file || !hash || hashState !== "COMPLETED") return;
    const controller = startAction("UPLOADING");
    setImportError(null);
    setImportId(null);
    setImportStatus(null);
    setUploadResult(null);
    setInvalidRows([]);
    setPollingTimedOut(false);
    setReport(null);
    setComparison(null);
    setQualityError(null);
    setQualityExportError(null);
    try {
      const createBody = {
        source_system: sourceSystem.trim(),
        source_dataset: sourceDataset.trim(),
        source_version: sourceVersion.trim(),
        external_batch_id: externalBatchId.trim(),
        expected_record_count_or_null: null,
      } as const;
      const created = await importApi.create(
        {
          ...createBody,
          request_idempotency_key: getOrCreateIdempotencyKey(
            actualHarvestCreateRequestScope({
              sourceSystem: createBody.source_system,
              sourceDataset: createBody.source_dataset,
              sourceVersion: createBody.source_version,
              externalBatchId: createBody.external_batch_id,
              expectedRecordCountOrNull: createBody.expected_record_count_or_null,
            }),
          ),
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
      await refreshImport(
        created.import_id,
        controller,
        undefined,
        uploaded.validation_run_instance_identity_hash_or_null,
      );
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
    setPollingTimedOut(false);
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
    setQualityExportError(null);
    setForecastCutoffAt(null);
    setReport(null);
    setComparison(null);
    try {
      const forecast = await forecastApi.read(forecastRunId.trim(), undefined, controller.signal);
      if (!forecast.forecast_cutoff_at) throw new TrialClientError("EVIDENCE_CONFLICT", 409);
      setForecastRunId(forecast.run_id);
      setForecastCutoffAt(forecast.forecast_cutoff_at);
    } catch (error) {
      if (!isAbortError(error)) {
        setForecastCutoffAt(null);
        setReport(null);
        setComparison(null);
        setQualityError(safeErrorMessage(error));
      }
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function createQualityReport(): Promise<void> {
    const cutoff = toIsoTimestamp(labelCutoffAt);
    if (!importId || importStatus?.status !== "COMMITTED" || !forecastCutoffAt || !cutoff) return;
    const controller = startAction("CREATING");
    setQualityError(null);
    setQualityExportError(null);
    setReport(null);
    setComparison(null);
    try {
      const requestScope = qualityReportRequestScope({
        forecastRunId: forecastRunId.trim(),
        importId,
        forecastCutoffAt,
        labelCutoffAt: cutoff,
        horizons: [7, 14, 21],
      });
      const request = {
        forecast_run_id: forecastRunId.trim(),
        actual_harvest_import_id: importId,
        forecast_cutoff_at: forecastCutoffAt,
        label_observation_cutoff_at: cutoff,
        requested_horizons_days: [7, 14, 21] as [7, 14, 21],
        request_idempotency_key: getOrCreateIdempotencyKey(requestScope),
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
      if (!isAbortError(error)) {
        setReport(null);
        setComparison(null);
        setQualityError(safeErrorMessage(error));
      }
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  async function exportQuality(): Promise<void> {
    if (!report || !comparison) return;
    const controller = startAction("EXPORTING");
    setQualityExportError(null);
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
        setQualityExportError(safeErrorMessage(error));
    } finally {
      if (actionAbort.current === controller) setActionState("IDLE");
    }
  }

  function handleForecastRunIdChange(value: string): void {
    cancelCurrentAction();
    setForecastRunId(value);
    setForecastCutoffAt(null);
    setReport(null);
    setComparison(null);
    setQualityError(null);
    setQualityExportError(null);
  }

  function handleLabelCutoffChange(value: string): void {
    cancelCurrentAction();
    setLabelCutoffAt(value);
    setReport(null);
    setComparison(null);
    setQualityExportError(null);
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
            <span className="eyebrow-tag">
              {pollingTimedOut ? "POLLING_TIMEOUT" : (importStatus?.status ?? "待开始")}
            </span>
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
          {pollingTimedOut && (
            <div className="notice notice-danger compact-notice" role="alert">
              <span className="notice-icon" aria-hidden="true">
                !
              </span>
              <div>
                <strong>状态读取超时</strong>未自动重新创建或上传；可以重新读取当前 import 状态。
                <button
                  className="button button-secondary"
                  type="button"
                  onClick={() => void retryImportStatus()}
                  disabled={!importId || actionState !== "IDLE"}
                >
                  重新读取状态
                </button>
              </div>
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
                onChange={(event) => changeImportMetadata(setSourceSystem, event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
            <div className="field">
              <label htmlFor="import-source-dataset">source dataset</label>
              <input
                id="import-source-dataset"
                value={sourceDataset}
                onChange={(event) => changeImportMetadata(setSourceDataset, event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
            <div className="field">
              <label htmlFor="import-source-version">source version</label>
              <input
                id="import-source-version"
                value={sourceVersion}
                onChange={(event) => changeImportMetadata(setSourceVersion, event.target.value)}
                disabled={actionState !== "IDLE"}
              />
            </div>
            <div className="field">
              <label htmlFor="import-external-batch">external batch id</label>
              <input
                id="import-external-batch"
                value={externalBatchId}
                onChange={(event) => changeImportMetadata(setExternalBatchId, event.target.value)}
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
              {invalidRows.map((row, index) => (
                <div className="result-line" key={`${row.record_index}-${row.error_code}-${index}`}>
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
              disabled={
                !file ||
                !hash ||
                hashState !== "COMPLETED" ||
                pollingTimedOut ||
                actionState !== "IDLE"
              }
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
          onForecastRunIdChange={handleForecastRunIdChange}
          forecastCutoffAt={forecastCutoffAt}
          labelCutoffAt={labelCutoffAt}
          onLabelCutoffAtChange={handleLabelCutoffChange}
          onLoadForecast={loadForecast}
          loadingForecast={actionState === "LOADING"}
          committedImportId={committedImportId}
          onCreateReport={createQualityReport}
          report={report}
          comparison={comparison}
          creating={actionState === "CREATING"}
          onExport={exportQuality}
          exporting={actionState === "EXPORTING"}
          errorMessage={qualityError}
          exportErrorMessage={qualityExportError}
        />
      </div>
    </main>
  );
}
