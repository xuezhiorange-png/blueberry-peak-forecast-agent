import { useEffect, useRef, useState } from "react";
import { z } from "zod";
import { request, safeError } from "../api/client";
import { subscribeSecurity } from "../api/security";
import { RollingForecastPanel } from "../components/RollingForecastPanel";
import { Panel } from "../components/presentation";
import { useSession } from "../context/SessionContext";
import {
  rollingComparison,
  rollingEnvelope,
  rollingRun,
  type RollingRun,
} from "../schemas/rolling";
import {
  FIELDS,
  LIMITS,
  type BookSummary,
  type Mapping,
  type QualityPreview,
  type WorkerReply,
} from "./contracts";
import "../styles/spreadsheet.css";
import { V020AgronomicPreparation } from "../agronomic/V020AgronomicPreparation";

const PATH = "/api/v1/rolling-forecast-runs";
const assetSchema = z.object({
  data_class: z.literal("SYNTHETIC_TEST_FIXTURE"),
  binding_hash: z.string().regex(/^[a-f0-9]{64}$/),
  file_sha256: z.string().regex(/^[a-f0-9]{64}$/),
  projection_hash: z.string().regex(/^[a-f0-9]{64}$/),
  source_hash: z.string(),
  sheet: z.string(),
  header: z.number().int(),
  mapping: z.record(z.string(), z.number().int()),
  filename: z.string(),
  base64: z.string().max(3000000),
});
const verificationSchema = z.object({
  data_class: z.literal("SYNTHETIC_TEST_FIXTURE"),
  binding_hash: z.string(),
  reason_messages: z.array(z.string()),
  readiness: z.object({
    origin: z.string(),
    status: z.string(),
    m1_feature_readiness: z.string(),
    blockers: z.array(z.string()),
    windows: z.record(
      z.string(),
      z.object({
        required_count: z.number().int(),
        complete_count: z.number().int(),
        status: z.string(),
        missing_dates: z.array(z.string()),
        late_dates: z.array(z.string()),
        partial_member_dates: z.array(z.string()),
        time_unproven_dates: z.array(z.string()),
        conflict_dates: z.array(z.string()),
      }),
    ),
    business_summary_hash: z.string(),
  }),
});
type Asset = z.infer<typeof assetSchema>;
type Comparison = z.infer<typeof rollingComparison>;
const errors: Record<string, string> = {
  FILE_TOO_LARGE: "文件超过 2 MB，请先裁剪为较小的工作簿。",
  FILE_SIZE_LIMIT: "文件为空或超过 2 MB，请先检查文件大小。",
  ROW_LIMIT: "记录超过 10,000 行，请拆分后预览。",
  COLUMN_LIMIT: "列数超过 80 列，请先精简。",
  ARCHIVE_SIZE_LIMIT: "工作簿展开后超过安全上限，请裁剪后重试。",
  FORMULA_FORBIDDEN: "工作簿包含公式，请导出仅包含数值的版本；本页面不会执行公式。",
  ACTIVE_CONTENT_FORBIDDEN: "工作簿包含宏或嵌入对象，请另存为纯数值工作簿。",
  EXTERNAL_LINK_FORBIDDEN: "工作簿包含外部链接，已停止解析，不会加载链接内容。",
  XML_ENTITY_FORBIDDEN: "工作簿含不安全 XML 内容，已停止解析。",
  CELL_LIMIT: "工作簿单元格范围超过 200,000 格，请裁剪空白范围后重试。",
  CELL_TEXT_LIMIT: "单元格文本超过 4,096 字符，请先缩短。",
  SHEET_LIMIT: "工作表超过 8 个，请拆分后重试。",
  CSV_STRUCTURE_INVALID: "CSV 引号或分隔格式不合法，请使用标准 UTF-8 CSV 重新导出。",
  TOO_MANY_ROWS: "记录超过 10,000 行，请拆分后预览。",
  TOO_MANY_COLUMNS: "列数超过 80 列，请先精简。",
  XLSX_UNSAFE_CONTENT: "工作簿包含公式、宏、外部链接或不安全内容，请导出仅包含数值的文件。",
  XLSX_LIMIT_EXCEEDED: "工作簿展开后超过安全上限，请裁剪后重试。",
  PREVIEW_TIMEOUT: "解析超过 8 秒，已停止。请减少数据量后重试。",
  SPREADSHEET_PARSE_FAILED: "文件无法解析，请确认是有效的 CSV 或 XLSX；CSV 请使用 UTF-8 编码。",
};

export function SpreadsheetPreparation() {
  const session = useSession();
  const [mode, setMode] = useState<"inbound" | "agronomic">("inbound");
  return (
    <>
      <div role="tablist" aria-label="电子表格准备模式" className="v020-modes">
        <button role="tab" aria-selected={mode === "inbound"} onClick={() => setMode("inbound")}>
          入库与预测演示
        </button>
        <button
          role="tab"
          aria-selected={mode === "agronomic"}
          onClick={() => setMode("agronomic")}
        >
          历史农事数据
        </button>
      </div>
      {mode === "inbound" ? (
        <Workspace key={session?.user.principal_id ?? "none"} />
      ) : (
        <V020AgronomicPreparation key={session?.user.principal_id ?? "none"} />
      )}
    </>
  );
}

function Workspace() {
  const [book, setBook] = useState<BookSummary | null>(null);
  const [quality, setQuality] = useState<QualityPreview | null>(null);
  const [sheet, setSheet] = useState(0);
  const [header, setHeader] = useState(0);
  const [mapping, setMapping] = useState<Mapping>({});
  const [unit, setUnit] = useState("UNKNOWN");
  const [basis, setBasis] = useState("UNKNOWN");
  const [filename, setFilename] = useState("");
  const [scenario, setScenario] = useState("complete");
  const [format, setFormat] = useState<"xlsx" | "csv">("xlsx");
  const [asset, setAsset] = useState<Asset | null>(null);
  const [verified, setVerified] = useState<z.infer<typeof verificationSchema> | null>(null);
  const [run, setRun] = useState<RollingRun | null>(null);
  const [savedRuns, setSavedRuns] = useState<RollingRun[]>([]);
  const [comparison, setComparison] = useState<Comparison | null>(null);
  const [origin, setOrigin] = useState("2026-11-05");
  const [message, setMessage] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const worker = useRef<Worker | null>(null);
  const generation = useRef(0);
  const requestId = useRef(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const active = useRef<AbortController | null>(null);
  const first = useRef<RollingRun | null>(null);

  function invalidate() {
    generation.current++;
    active.current?.abort();
    setVerified(null);
    setRun(null);
    setSavedRuns([]);
    setComparison(null);
    first.current = null;
    setBusy(false);
  }
  function stopWorker() {
    worker.current?.terminate();
    worker.current = null;
    if (timer.current) clearTimeout(timer.current);
  }
  function clear() {
    invalidate();
    stopWorker();
    setBook(null);
    setQuality(null);
    setAsset(null);
    setMapping({});
    setSheet(0);
    setHeader(0);
    setFilename("");
    setMessage("");
    setCode("");
    setUnit("UNKNOWN");
    setBasis("UNKNOWN");
    setOrigin("2026-11-05");
  }
  useEffect(() => {
    const unsubscribe = subscribeSecurity(clear);
    return () => {
      unsubscribe();
      generation.current++;
      active.current?.abort();
      stopWorker();
    };
  }, []);

  function fail(error: unknown) {
    const value = error instanceof Error ? error.message : "SPREADSHEET_PARSE_FAILED";
    const safe = /^[A-Z][A-Z0-9_]+$/.test(value) ? value : "SPREADSHEET_PARSE_FAILED";
    setCode(safe);
    setMessage(errors[safe] ?? "无法完成当前检查，请查看技术原因并调整文件。");
    setBusy(false);
  }
  function timeout() {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      stopWorker();
      setBook(null);
      setQuality(null);
      invalidate();
      fail(Error("PREVIEW_TIMEOUT"));
    }, LIMITS.timeoutMs);
  }
  function parse(buffer: ArrayBuffer, kind: "xlsx" | "csv", name: string) {
    stopWorker();
    setBook(null);
    setQuality(null);
    setFilename(name);
    setBusy(true);
    const instance = new Worker(new URL("./preview.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.current = instance;
    instance.onmessage = (event: MessageEvent<WorkerReply>) => {
      if (instance !== worker.current || event.data.id !== requestId.current) return;
      if (timer.current) clearTimeout(timer.current);
      setBusy(false);
      if (event.data.type === "error") {
        stopWorker();
        fail(Error(event.data.code));
      } else if (event.data.type === "parsed") setBook(event.data.book);
      else if (event.data.type === "analyzed") setQuality(event.data.report);
    };
    instance.onerror = () => {
      stopWorker();
      fail(Error("SPREADSHEET_PARSE_FAILED"));
    };
    timeout();
    instance.postMessage({ type: "parse", id: ++requestId.current, buffer, format: kind }, [
      buffer,
    ]);
  }
  useEffect(() => {
    if (!book || !worker.current) return;
    invalidate();
    setQuality(null);
    setMessage("");
    setCode("");
    timeout();
    worker.current.postMessage({
      type: "analyze",
      id: ++requestId.current,
      sheet,
      header,
      mapping,
    });
  }, [book, sheet, header, mapping]);

  async function choose(file: File | undefined) {
    clear();
    if (!file) return;
    const id = generation.current;
    try {
      if (file.size > LIMITS.fileBytes) throw Error("FILE_TOO_LARGE");
      const kind = file.name.toLowerCase().endsWith(".csv")
        ? "csv"
        : file.name.toLowerCase().endsWith(".xlsx")
          ? "xlsx"
          : null;
      if (!kind) throw Error("UNSUPPORTED_FILE_TYPE");
      const bytes = await file.arrayBuffer();
      if (id === generation.current) {
        setFormat(kind);
        parse(bytes, kind, file.name);
      }
    } catch (error) {
      if (id === generation.current) fail(error);
    }
  }
  async function loadExample() {
    clear();
    const id = generation.current;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    try {
      const response = await request(
        `${PATH}/spreadsheet-demo`,
        rollingEnvelope(assetSchema),
        controller.signal,
        { scenario, format },
      );
      if (id !== generation.current || controller.signal.aborted) return;
      const selected = response.data;
      const bytes = Uint8Array.from(atob(selected.base64), (c) => c.charCodeAt(0));
      if (bytes.byteLength > LIMITS.fileBytes) throw Error("FILE_TOO_LARGE");
      setAsset(selected);
      setHeader(selected.header);
      setSheet(format === "xlsx" ? 1 : 0);
      // Suggestions are not accepted mappings until the user explicitly applies them.
      parse(bytes.buffer, format, selected.filename);
    } catch (error) {
      if (id === generation.current && !controller.signal.aborted) {
        setMessage(safeError(error));
        setBusy(false);
      }
    }
  }
  const fixed =
    !!book &&
    !!quality &&
    !!asset &&
    book.sha256 === asset.file_sha256 &&
    quality.projectionHash === asset.projection_hash &&
    book.sheets[sheet]?.name === asset.sheet &&
    header === asset.header &&
    FIELDS.every(([k]) => mapping[k] === asset.mapping[k]) &&
    unit === "kg" &&
    basis === "RECORDED_INBOUND_WEIGHT";
  function payload(selectedOrigin = origin) {
    return {
      scenario,
      format,
      binding_hash: asset!.binding_hash,
      file_sha256: book!.sha256,
      projection_hash: quality!.projectionHash,
      sheet: book!.sheets[sheet].name,
      header,
      mapping,
      declared_unit: unit,
      declared_basis: basis,
      origin: selectedOrigin,
    };
  }
  async function verify() {
    if (!fixed) return;
    invalidate();
    const id = generation.current;
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    try {
      const response = await request(
        `${PATH}/spreadsheet-demo/verify`,
        rollingEnvelope(verificationSchema),
        controller.signal,
        undefined,
        payload(),
      );
      if (id !== generation.current || controller.signal.aborted) return;
      if (response.data.binding_hash !== asset!.binding_hash) throw Error("DEMO_IDENTITY_MISMATCH");
      setVerified(response.data);
      setMessage(
        response.data.readiness.m1_feature_readiness === "COMPUTABLE"
          ? "合成来源检查通过，可以运行已登记示例。"
          : "来源尚不能计算 M1，请补齐下列问题。",
      );
    } catch (error) {
      if (id === generation.current && !controller.signal.aborted) setMessage(safeError(error));
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }
  async function generate() {
    if (!fixed || verified?.readiness.m1_feature_readiness !== "COMPUTABLE") return;
    const previous = first.current;
    setRun(null);
    setComparison(null);
    const id = ++generation.current;
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setBusy(true);
    try {
      const issued = await request(
        `${PATH}/spreadsheet-demo/issue`,
        rollingEnvelope(rollingRun),
        controller.signal,
        undefined,
        payload(),
      );
      const saved = await request(
        `${PATH}/${issued.data.run_id}`,
        rollingEnvelope(rollingRun),
        controller.signal,
      );
      if (
        saved.data.result_hash !== issued.data.result_hash ||
        saved.data.run_id !== issued.data.run_id ||
        saved.data.origin_date !== origin ||
        saved.data.input.issue.observation_snapshot_reference !==
          `SYNTHETIC-WORKBOOK-${asset!.binding_hash}`
      )
        throw Error("SAVED_RUN_IDENTITY_MISMATCH");
      let compared: Comparison | null = null;
      if (previous && previous.run_id !== saved.data.run_id) {
        const value = await request(
          `${PATH}/compare`,
          rollingEnvelope(rollingComparison),
          controller.signal,
          { left_run_id: previous.run_id, right_run_id: saved.data.run_id },
        );
        if (
          value.data.left_result_hash !== previous.result_hash ||
          value.data.right_result_hash !== saved.data.result_hash
        )
          throw Error("COMPARISON_IDENTITY_MISMATCH");
        compared = value.data;
      }
      if (id !== generation.current || controller.signal.aborted) return;
      // Keep the first record when displaying a pair, so its report can include the comparison.
      setSavedRuns(compared && previous ? [previous, saved.data] : [saved.data]);
      setRun(compared ? previous : saved.data);
      setComparison(compared);
      first.current = saved.data;
      setMessage(`已保存并重载 Origin ${origin} 的合成预测。未执行实际业务评分。`);
    } catch (error) {
      if (id === generation.current && !controller.signal.aborted) {
        setRun(null);
        setComparison(null);
        first.current = null;
        setMessage(safeError(error));
      }
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }
  return (
    <section className="d-spreadsheet" aria-label="电子表格准备">
      <Panel title="电子表格准备" note="文件本地预览 · 固定合成示例可演示计算 · 不导入业务数据">
        <ol className="d-sheet-steps">
          <li>选择文件</li>
          <li>核对字段</li>
          <li>查看质量 / 合成预测</li>
        </ol>
        <h3>1. 选择文件</h3>
        <p>
          CSV / XLSX 仅在此浏览器解析，不上传、不保存到数据库。最多 2 MB、10,000 行、80 列；预览前
          50 行。公式、宏和外部链接不执行。
        </p>
        <label>
          选择电子表格{" "}
          <input
            type="file"
            accept=".csv,.xlsx"
            onChange={(e) => {
              void choose(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
        <div className="d-sheet-controls">
          <label>
            合成场景{" "}
            <select
              value={scenario}
              onChange={(e) => {
                clear();
                setScenario(e.target.value);
              }}
            >
              <option value="complete">完整来源</option>
              <option value="missing-day">缺失一天</option>
              <option value="late-record">晚到记录</option>
              <option value="basis-conflict">重量口径不符</option>
            </select>
          </label>
          <label>
            示例格式{" "}
            <select
              value={format}
              onChange={(e) => {
                clear();
                setFormat(e.target.value as "xlsx" | "csv");
              }}
            >
              <option value="xlsx">Excel XLSX</option>
              <option value="csv">CSV</option>
            </select>
          </label>
          <button disabled={busy} onClick={() => void loadExample()}>
            加载合成示例
          </button>
          <button onClick={clear}>清空文件与预测</button>
        </div>
        {filename && <p>当前文件：{filename}</p>}
        {busy && <p role="status">正在解析或核对，请稍候…</p>}
        {message && <p role="status">{message}</p>}
        {code && (
          <details>
            <summary>技术原因</summary>
            <code>{code}</code>
          </details>
        )}
        {book && (
          <>
            <h3>2. 核对字段</h3>
            <div className="d-sheet-controls">
              <label>
                工作表{" "}
                <select
                  value={sheet}
                  onChange={(e) => {
                    setSheet(Number(e.target.value));
                    setHeader(0);
                    setMapping({});
                  }}
                >
                  {book.sheets.map((s, i) => (
                    <option key={i} value={i}>
                      {s.name} · {s.rowCount} 行
                    </option>
                  ))}
                </select>
              </label>
              <label>
                表头所在行{" "}
                <input
                  type="number"
                  min={1}
                  max={book.sheets[sheet].rowCount}
                  value={header + 1}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    if (v >= 1 && v <= book.sheets[sheet].rowCount) {
                      setHeader(v - 1);
                      setMapping({});
                    }
                  }}
                />
              </label>
              {asset && (
                <button
                  onClick={() => {
                    setSheet(format === "xlsx" ? 1 : 0);
                    setHeader(asset.header);
                    setMapping(asset.mapping);
                  }}
                >
                  应用合成示例列建议
                </button>
              )}
            </div>
            <p>
              列名对应只表示找到了列，不证明重量口径、成员权威或可用于预测。映射仅留在当前页面内存。
            </p>
            <div className="d-sheet-mapping">
              {FIELDS.map(([key, label]) => (
                <label key={key}>
                  {label}
                  <select
                    aria-label={label}
                    value={mapping[key] ?? ""}
                    onChange={(e) =>
                      setMapping({
                        ...mapping,
                        [key]: e.target.value === "" ? null : Number(e.target.value),
                      })
                    }
                  >
                    <option value="">未映射 UNMAPPED</option>
                    {quality?.columns.map((c) => (
                      <option key={c.index} value={c.index}>
                        {c.index + 1}. {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
            <div className="d-sheet-controls">
              <label>
                声明重量单位{" "}
                <select
                  value={unit}
                  onChange={(e) => {
                    invalidate();
                    setUnit(e.target.value);
                  }}
                >
                  <option value="UNKNOWN">未证明</option>
                  <option value="kg">kg</option>
                  <option value="tonne">吨（不自动换算）</option>
                </select>
              </label>
              <label>
                声明业务口径{" "}
                <select
                  value={basis}
                  onChange={(e) => {
                    invalidate();
                    setBasis(e.target.value);
                  }}
                >
                  <option value="UNKNOWN">未证明</option>
                  <option value="FIELD_HARVEST_WEIGHT">田间采收重量</option>
                  <option value="RECORDED_INBOUND_WEIGHT">原始入库记录重量</option>
                  <option value="INBOUND_NET_WEIGHT">入库净重</option>
                </select>
              </label>
            </div>
            {quality && (
              <>
                <h3>3. 查看数据质量 / 合成预测演示</h3>
                <p className="d-sheet-notice">
                  本地文件预览，尚未核验来源权威。空白不是 0 kg；缺失日期不会补零。
                </p>
                <dl className="d-sheet-stats">
                  <div>
                    <dt>记录行数</dt>
                    <dd>{quality.recordCount}</dd>
                  </div>
                  <div>
                    <dt>日期范围</dt>
                    <dd>
                      {quality.dateStart ?? "未映射"} — {quality.dateEnd ?? "未映射"}
                    </dd>
                  </div>
                  <div>
                    <dt>空白 / 非法重量</dt>
                    <dd>
                      {mapping.weight == null
                        ? "未映射"
                        : `${quality.blankWeight} / ${quality.invalidWeight}`}
                    </dd>
                  </div>
                  <div>
                    <dt>合法零值</dt>
                    <dd>{mapping.weight == null ? "未映射" : quality.zeroWeight}</dd>
                  </div>
                  <div>
                    <dt>空白 / 非法日期</dt>
                    <dd>
                      {mapping.date == null
                        ? "未映射"
                        : `${quality.blankDate} / ${quality.invalidDate}`}
                    </dd>
                  </div>
                  <div>
                    <dt>重复风险 ID / 整行</dt>
                    <dd>
                      {mapping.record_id == null ? "ID未映射" : quality.duplicateIds} /{" "}
                      {quality.duplicateRows}
                    </dd>
                  </div>
                </dl>
                <p>
                  未映射字段：
                  {quality.unmapped.map((k) => FIELDS.find(([key]) => key === k)?.[1]).join("、") ||
                    "无"}
                  。成员空白：
                  {Object.entries(quality.missingMembers)
                    .map(
                      ([k, v]) =>
                        `${FIELDS.find(([key]) => key === k)?.[1] ?? k}: ${mapping[k as keyof Mapping] == null ? "未映射" : v}`,
                    )
                    .join("；") || "尚未映射"}
                  。
                </p>
                <p>
                  来源时间缺失 {quality.sourceTimeMissing}，非法 {quality.sourceTimeInvalid}
                  ；有效时间戳仍不等于可用性证明。日期区间缺口 {quality.missingDateCount}：
                  {quality.missingDates.join("、") || "无 / 未映射"}。
                </p>
                <p>
                  品级取舍待确认：{quality.grades.join("、") || "未映射"}。单位列：
                  {quality.units.join("、") || "未映射"}。M1 的 7/14/28 日和产季完整性：未证明。
                </p>
                <div className="d-table-wrap">
                  <table>
                    <caption>本地列检查</caption>
                    <thead>
                      <tr>
                        <th>列名</th>
                        <th>空值</th>
                        <th>类型提示</th>
                      </tr>
                    </thead>
                    <tbody>
                      {quality.columns.map((c) => (
                        <tr key={c.index}>
                          <td>{c.name}</td>
                          <td>{c.empty}</td>
                          <td>{c.types.join(" / ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="d-table-wrap">
                  <table className="d-sheet-preview-table">
                    <caption>本地内容预览 · 最多50行</caption>
                    <thead>
                      <tr>
                        {quality.columns.map((c) => (
                          <th key={c.index}>{c.name}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {quality.preview.map((r, i) => (
                        <tr key={i}>
                          {quality.columns.map((c) => (
                            <td key={c.index}>{r[c.index] ?? ""}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <details>
                  <summary>技术身份与原始状态</summary>
                  <p>{quality.status}</p>
                  <p className="d-hash">
                    File {book.sha256}
                    <br />
                    Projection {quality.projectionHash ?? "字段未全部映射"}
                  </p>
                </details>
                <p>
                  只有登记工作簿、全部映射、单位和口径与固定合成来源一致时才能演示。任意用户文件不能生成预测。
                </p>
                <button disabled={!fixed || busy} onClick={() => void verify()}>
                  核验固定合成来源
                </button>
                {verified && (
                  <div aria-label="合成来源检查结果">
                    <p>
                      S9 核验时点 {verified.readiness.origin} · 完整性：{verified.readiness.status}
                      ；M1：
                      {verified.readiness.m1_feature_readiness}
                    </p>
                    {verified.readiness.blockers.length > 0 && (
                      <p>请补齐来源：{verified.reason_messages.join("；")}</p>
                    )}
                    <div className="d-table-wrap">
                      <table>
                        <caption>S9 历史窗口完整性</caption>
                        <thead>
                          <tr>
                            <th>窗口</th>
                            <th>完整 / 要求日数</th>
                            <th>问题日期</th>
                          </tr>
                        </thead>
                        <tbody>
                          {Object.entries(verified.readiness.windows).map(([key, w]) => (
                            <tr key={key}>
                              <td>
                                {{
                                  past_7d_harvest_kg: "最近7日",
                                  past_14d_harvest_kg: "最近14日",
                                  past_28d_harvest_kg: "最近28日",
                                  season_to_date_harvest_kg: "产季至 D−1",
                                }[key] ?? key}
                              </td>
                              <td>
                                {w.complete_count} / {w.required_count} · {w.status}
                              </td>
                              <td>
                                缺失 {w.missing_dates.join("、") || "无"}；晚到{" "}
                                {w.late_dates.join("、") || "无"}；成员不全{" "}
                                {w.partial_member_dates.join("、") || "无"}；时间未证明{" "}
                                {w.time_unproven_dates.join("、") || "无"}；冲突{" "}
                                {w.conflict_dates.join("、") || "无"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <details>
                      <summary>合成来源技术原因</summary>
                      {verified.readiness.blockers.join("；") || "无阻断"} ·{" "}
                      {verified.readiness.business_summary_hash}
                    </details>
                    <label>
                      合成预测 Origin{" "}
                      <select
                        value={origin}
                        onChange={(e) => {
                          setOrigin(e.target.value);
                          setRun(null);
                          setComparison(null);
                          active.current?.abort();
                          generation.current++;
                          setBusy(false);
                        }}
                      >
                        <option value="2026-11-05">2026-11-05</option>
                        <option value="2026-11-06">2026-11-06</option>
                      </select>
                    </label>
                    <button
                      disabled={
                        !fixed || busy || verified.readiness.m1_feature_readiness !== "COMPUTABLE"
                      }
                      onClick={() => void generate()}
                    >
                      计算并保存合成预测
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </Panel>
      {run && (
        <>
          <label>
            查看已保存合成 Origin{" "}
            <select
              value={run.run_id}
              onChange={(e) =>
                setRun(savedRuns.find((r) => r.run_id === Number(e.target.value)) ?? null)
              }
            >
              {savedRuns.map((r) => (
                <option key={r.run_id} value={r.run_id}>
                  {r.origin_date} · 记录 {r.run_id}
                </option>
              ))}
            </select>
          </label>
          <p className="d-sheet-notice">
            合成示例，不代表实际产量。未读取真实业务数据，未执行实际标签评分。
          </p>
          <RollingForecastPanel
            readOnly
            suppliedRun={run}
            suppliedComparison={comparison}
            onAccessDenied={clear}
          />
        </>
      )}
    </section>
  );
}
