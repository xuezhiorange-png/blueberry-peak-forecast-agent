import { useEffect, useRef, useState } from "react";
import vocabulary from "./v0_20_vocabulary.json";
import synthetic from "./v0_20_synthetic.json";
import { Panel } from "../components/presentation";
import { subscribeSecurity } from "../api/security";
import {
  LIMITS,
  type BookSummary,
  type QualityPreview,
  type WorkerReply,
} from "../spreadsheet/contracts";
import {
  V0_20_FIELDS,
  V0_20_LIMITS,
  type V020Field,
  type V020Kind,
  type V020Mapping,
  type V020Prepared,
  type V020Record,
  type V020SheetPlan,
  type V020Slot,
} from "./v0_20_contracts";
import "../styles/spreadsheet.css";
import "./v0_20_agronomic.css";

const initial = (): V020SheetPlan => ({
  sheet: 0,
  header: 0,
  kind: "AREA",
  layout: "WIDE",
  columns: {},
  slots: [],
});
const labels: Record<string, string> = {
  AREA: "品种与面积",
  EVENT: "农事管理",
  PHENOLOGY: "开花物候",
  PLANNED: "计划",
  OBSERVED: "声明实际 / 观测",
  UNKNOWN: "未知",
  DAY: "日",
  MONTH: "月",
  YEAR: "年",
  TIMESTAMP: "带时区时间",
  LOCAL_DATETIME: "无时区时钟",
  VALID_STRUCTURE: "结构齐全",
  PARTIAL: "信息不全",
  CONFLICT: "冲突",
  UNMAPPED: "未匹配权威身份 / 类型",
  SOURCE_AUTHORITY_NOT_PROVEN: "来源权威未证明",
  PIT_NOT_PROVEN: "历史可用时点未证明",
};
const errors: Record<string, string> = {
  V0_20_MAPPING_REQUIRED: "请先加入至少一份工作表映射。",
  V0_20_MAPPING_INVALID: "工作表或表头无效，请重新核对。",
  V0_20_COLUMN_INVALID: "某个列号不在所选工作表内。",
  V0_20_DUPLICATE_SHEET_PLAN: "同一工作表与数据类型只能保留一份当前映射。",
  V0_20_HEADER_CONFLICT: "同一工作表的三类数据请使用同一表头行。",
  V0_20_RECORD_LIMIT: "规范化后超过 20,000 条，请拆分文件；不会静默删除记录。",
  V0_20_PACKAGE_SIZE_LIMIT: "准备包超过 16 MiB，请拆分文件。",
  V0_20_SLOT_INVALID: "宽表日期列或类型配置不合法。",
  V0_20_TIMEOUT: "本地处理超过时间上限，已停止；请减少数据量后重新选择文件。",
  FILE_SIZE_LIMIT: "文件为空或超过 2 MiB。",
  ROW_LIMIT: "文件超过 10,000 行。",
  COLUMN_LIMIT: "文件超过 80 列。",
  FORMULA_FORBIDDEN: "含公式的工作簿已阻断，请另存为纯数值/文本版本。",
  ACTIVE_CONTENT_FORBIDDEN: "含宏或活动对象的工作簿已阻断。",
  EXTERNAL_LINK_FORBIDDEN: "含外部链接的工作簿已阻断，不会访问外部内容。",
  ARCHIVE_SIZE_LIMIT: "工作簿展开内容超过安全上限。",
};
const COMMON: V020Field[] = [
  "base",
  "farm",
  "subfarm",
  "plot",
  "variety",
  "season",
  "production_system",
  "status",
];
const SOURCE: V020Field[] = [
  "source_reference",
  "source_version",
  "recorded_at",
  "known_at",
  "observed_at",
  "logical_id",
  "revision_id",
  "supersedes_revision",
];
const areaFields: V020Field[] = [
  "area_unit",
  "effective_from",
  "effective_to",
  "tree_age_years",
  "planting_year",
];
const eventFields: V020Field[] = [
  "end_date",
  "pruning_type",
  "operation_count",
  "method",
  "intensity_mode",
  "intensity_value",
  "intensity_unit",
  "intensity_denominator",
];
const phenoFields: V020Field[] = ["method", "sample_scope", "quality_status"];

function download(content: BlobPart, type: string, name: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function RowSource({ record }: { record: V020Record }) {
  return (
    <details>
      <summary>源行及原因</summary>
      <p>
        {record.source_sheet} · 第 {record.source_row} 行 · {record.logical_id ?? "逻辑ID缺失"} /{" "}
        {record.revision_id ?? "修订缺失"}
      </p>
      <ul>
        {record.issues.map((i) => (
          <li key={i.code + i.field}>
            {i.message} <code>{i.code}</code>
          </li>
        ))}
      </ul>
    </details>
  );
}
function nextSlotId(slots: V020Slot[]) {
  let i = 1;
  while (slots.some((s) => s.id === `column-${i}`)) i++;
  return `column-${i}`;
}

export function V020AgronomicPreparation() {
  const [book, setBook] = useState<BookSummary | null>(null),
    [preview, setPreview] = useState<QualityPreview | null>(null);
  const [editing, setEditing] = useState<V020SheetPlan>(initial),
    [plans, setPlans] = useState<V020SheetPlan[]>([]),
    [dirty, setDirty] = useState(false);
  const [versions, setVersions] = useState<V020Prepared[]>([]),
    [selected, setSelected] = useState<V020Prepared | null>(null);
  const versionsRef = useRef<V020Prepared[]>([]);
  const [filename, setFilename] = useState(""),
    [scenario, setScenario] = useState<"wide" | "long" | "negative">("wide"),
    [format, setFormat] = useState<"xlsx" | "csv">("xlsx");
  const [busy, setBusy] = useState<"parse" | "prepare" | null>(null),
    [message, setMessage] = useState(""),
    [code, setCode] = useState("");
  const [seasonFilter, setSeasonFilter] = useState(""),
    [baseFilter, setBaseFilter] = useState("");
  const worker = useRef<Worker | null>(null),
    serial = useRef(0),
    parseId = useRef(-1),
    previewId = useRef(-1),
    activeJob = useRef(-1),
    wantedJob = useRef(-1),
    lifetime = useRef(0),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sourceBusy = useRef(false);
  function invalidate() {
    wantedJob.current = -1;
    setSelected(null);
    setMessage("");
    setCode("");
  }
  function stop() {
    worker.current?.terminate();
    worker.current = null;
    if (timer.current) clearTimeout(timer.current);
    sourceBusy.current = false;
    activeJob.current = -1;
    setBusy(null);
  }
  function clear(all = true) {
    lifetime.current++;
    stop();
    setBook(null);
    setPreview(null);
    setFilename("");
    setEditing(initial());
    setPlans([]);
    setDirty(false);
    invalidate();
    setSeasonFilter("");
    setBaseFilter("");
    if (all) {
      versionsRef.current = [];
      setVersions([]);
    }
  }
  useEffect(() => {
    const off = subscribeSecurity(() => clear());
    return () => {
      off();
      lifetime.current++;
      worker.current?.terminate();
      if (timer.current) clearTimeout(timer.current);
    };
  }, []);
  function fail(raw: string) {
    const c = /^[A-Z][A-Z0-9_]+$/.test(raw) ? raw : "V0_20_PARSE_FAILED";
    setCode(c);
    setMessage(errors[c] ?? "无法完成本地处理，请核对文件、映射或技术原因。CSV 需使用 UTF-8。");
  }
  function watch(ms: number) {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      stop();
      setBook(null);
      setPreview(null);
      invalidate();
      fail("V0_20_TIMEOUT");
    }, ms);
  }
  function open(
    buffer: ArrayBuffer,
    name: string,
    kind: "csv" | "xlsx",
    suggested?: V020SheetPlan[],
  ) {
    stop();
    setBusy("parse");
    setFilename(name);
    const w = new Worker(new URL("../spreadsheet/preview.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.current = w;
    w.onmessage = (event: MessageEvent<WorkerReply>) => {
      if (worker.current !== w) return;
      const m = event.data;
      if (m.type === "parsed" && m.id === parseId.current) {
        if (timer.current) clearTimeout(timer.current);
        setBusy(null);
        setBook(m.book);
        setEditing(suggested?.[0] ? structuredClone(suggested[0]) : initial());
        return;
      }
      if (m.type === "analyzed" && m.id === previewId.current) {
        setPreview(m.report);
        return;
      }
      if (m.id === activeJob.current) {
        sourceBusy.current = false;
        setBusy(null);
        if (timer.current) clearTimeout(timer.current);
        if (m.id !== wantedJob.current) return;
        if (m.type === "v0_20_prepared") {
          const p = m.prepared;
          const existing = versionsRef.current.find((v) => v.package_id === p.package_id);
          if (!existing && versionsRef.current.length >= V0_20_LIMITS.versions) {
            setSelected(null);
            setMessage("已保留五个版本，请先下载并明确清空后再继续；旧版本没有被覆盖。");
            return;
          }
          if (!existing) {
            versionsRef.current = [...versionsRef.current, p];
            setVersions(versionsRef.current);
          }
          setSelected(existing ?? p);
          setSeasonFilter("");
          setBaseFilter("");
          setMessage("本地规范化与检查完成。结构齐全不代表来源已授权或能够训练。");
          return;
        }
      }
      if (
        m.type === "error" &&
        (m.id === parseId.current || m.id === previewId.current || m.id === wantedJob.current)
      ) {
        setBusy(null);
        sourceBusy.current = false;
        if (timer.current) clearTimeout(timer.current);
        fail(m.code);
      }
    };
    w.onerror = () => {
      stop();
      setBook(null);
      setPreview(null);
      fail("V0_20_PARSE_FAILED");
    };
    parseId.current = ++serial.current;
    watch(LIMITS.timeoutMs);
    w.postMessage(
      { type: "parse", id: parseId.current, buffer, format: kind, v0_20_preserve_time: true },
      [buffer],
    );
  }
  useEffect(() => {
    if (!book || !worker.current) return;
    setPreview(null);
    previewId.current = ++serial.current;
    worker.current.postMessage({
      type: "analyze",
      id: previewId.current,
      sheet: editing.sheet,
      header: editing.header,
      mapping: {},
    });
  }, [book, editing.sheet, editing.header]);
  async function choose(file: File | undefined) {
    clear(false);
    if (!file) return;
    const life = lifetime.current;
    try {
      if (file.size > LIMITS.fileBytes) throw Error("FILE_SIZE_LIMIT");
      const kind = file.name.toLowerCase().endsWith(".csv")
        ? "csv"
        : file.name.toLowerCase().endsWith(".xlsx")
          ? "xlsx"
          : null;
      if (!kind) throw Error("V0_20_FILE_TYPE");
      const bytes = await file.arrayBuffer();
      if (life === lifetime.current) open(bytes, file.name, kind);
    } catch (e) {
      if (life === lifetime.current) fail(e instanceof Error ? e.message : "");
    }
  }
  const asset = synthetic[scenario].assets[format];
  const exactAsset = book?.sha256 === asset.sha256;
  function sample() {
    clear(false);
    const bytes = Uint8Array.from(atob(asset.base64), (c) => c.charCodeAt(0));
    open(bytes.buffer, asset.filename, format, asset.plans as V020SheetPlan[]);
  }
  function edit(next: V020SheetPlan) {
    invalidate();
    setEditing(next);
    setDirty(true);
  }
  function applySuggestions() {
    if (!exactAsset) return;
    invalidate();
    setPlans(structuredClone(asset.plans as V020SheetPlan[]));
    setEditing(structuredClone(asset.plans[0] as V020SheetPlan));
    setDirty(false);
  }
  function savePlan() {
    invalidate();
    setPlans((previous) =>
      [
        ...previous.filter((p) => !(p.sheet === editing.sheet && p.kind === editing.kind)),
        structuredClone(editing),
      ].sort((a, b) => a.sheet - b.sheet),
    );
    setDirty(false);
    setMessage("该表映射已加入；只声明列与语义，不批准真实来源。");
  }
  function generate() {
    if (!worker.current || sourceBusy.current || dirty || !plans.length) return;
    invalidate();
    sourceBusy.current = true;
    setBusy("prepare");
    activeJob.current = wantedJob.current = ++serial.current;
    watch(20000);
    worker.current.postMessage({ type: "v0_20_prepare", id: activeJob.current, plans });
  }
  function mapping(
    keys: V020Field[],
    columns: V020Mapping = editing.columns,
    onChange = (next: V020Mapping) => edit({ ...editing, columns: next }),
  ) {
    return (
      <div className="d-sheet-mapping">
        {keys.map((key) => (
          <label key={key}>
            {V0_20_FIELDS.find(([k]) => k === key)![1]}
            <select
              aria-label={V0_20_FIELDS.find(([k]) => k === key)![1]}
              value={columns[key] ?? ""}
              onChange={(e) =>
                onChange({
                  ...columns,
                  [key]: e.target.value === "" ? null : Number(e.target.value),
                })
              }
            >
              <option value="">未映射</option>
              {preview?.columns.map((c) => (
                <option key={c.index} value={c.index}>
                  {c.index + 1}. {c.name}
                </option>
              ))}
            </select>
          </label>
        ))}
      </div>
    );
  }
  function updateSlot(index: number, change: Partial<V020Slot>) {
    edit({
      ...editing,
      slots: editing.slots.map((s, i) => (i === index ? { ...s, ...change } : s)),
    });
  }
  const shown =
    selected?.data.records.filter(
      (r) =>
        (!seasonFilter || r.scope.season === seasonFilter) &&
        (!baseFilter || r.scope.base === baseFilter),
    ) ?? [];
  const areas = shown.filter((r) => r.area).slice(0, 200),
    events = shown
      .filter((r) => r.event)
      .sort((a, b) =>
        (a.business_date.lower_date ?? "~") < (b.business_date.lower_date ?? "~") ? -1 : 1,
      )
      .slice(0, 200),
    phenology = shown
      .filter((r) => r.phenology)
      .sort((a, b) =>
        (a.business_date.lower_date ?? "~") < (b.business_date.lower_date ?? "~") ? -1 : 1,
      )
      .slice(0, 200);
  return (
    <section className="d-spreadsheet v020-agronomic" aria-label="V0.20 历史农事准备">
      <Panel title="历史农事数据 · V0.20" note="浏览器本地准备，不上传、不写生产数据库、不改变预测">
        <ol className="d-sheet-steps">
          <li>选择历史表格</li>
          <li>核对数据与映射</li>
          <li>检查并导出准备版本</li>
        </ol>
        <p>
          支持面积、管理事件和物候三类。没有真实农事来源授权；合成示例仅验证数据通道。日精度不补时分秒，剪枝/促早/开花日期不会直接改变产量或高峰。
        </p>
        <label>
          选择农事电子表格{" "}
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
            农事合成场景{" "}
            <select
              value={scenario}
              onChange={(e) => {
                clear(false);
                setScenario(e.target.value as typeof scenario);
              }}
            >
              <option value="wide">两产季宽表</option>
              <option value="long">两产季长表</option>
              <option value="negative">含缺失与冲突</option>
            </select>
          </label>
          <label>
            农事示例格式{" "}
            <select
              value={format}
              onChange={(e) => {
                clear(false);
                setFormat(e.target.value as typeof format);
              }}
            >
              <option value="xlsx">XLSX 多工作表</option>
              <option value="csv">CSV 面积长表</option>
            </select>
          </label>
          <button disabled={busy !== null} onClick={sample}>
            加载农事合成示例
          </button>
          <button onClick={() => clear()}>清空农事文件与所有版本</button>
        </div>
        <p>
          上限：2 MiB、8 张表、10,000 行、80 列；规范化 20,000 条、导出合计 16 MiB、内存保留 5
          个版本。原文件从不覆盖。
        </p>
        {filename && <p>当前文件：{filename}</p>}
        {busy && <p role="status">{busy === "parse" ? "本地解析表格…" : "本地规范化与检查…"}</p>}
        {message && <p role="status">{message}</p>}
        {code && (
          <details>
            <summary>技术原因</summary>
            <code>{code}</code>
          </details>
        )}
        {book && (
          <>
            <h3>工作表与字段</h3>
            <div className="d-sheet-controls">
              <label>
                农事工作表{" "}
                <select
                  value={editing.sheet}
                  onChange={(e) =>
                    edit({ ...initial(), sheet: Number(e.target.value), kind: editing.kind })
                  }
                >
                  {book.sheets.map((s, i) => (
                    <option key={i} value={i}>
                      {s.name} · {s.rowCount}行
                    </option>
                  ))}
                </select>
              </label>
              <label>
                农事表头行{" "}
                <input
                  type="number"
                  min={1}
                  max={book.sheets[editing.sheet].rowCount}
                  value={editing.header + 1}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (n >= 1 && n <= book.sheets[editing.sheet].rowCount)
                      edit({ ...editing, header: n - 1, columns: {}, slots: [] });
                  }}
                />
              </label>
              <label>
                农事数据类型{" "}
                <select
                  value={editing.kind}
                  onChange={(e) =>
                    edit({ ...editing, kind: e.target.value as V020Kind, columns: {}, slots: [] })
                  }
                >
                  {(["AREA", "EVENT", "PHENOLOGY"] as const).map((k) => (
                    <option key={k} value={k}>
                      {labels[k]}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                表格布局{" "}
                <select
                  value={editing.layout}
                  onChange={(e) =>
                    edit({ ...editing, layout: e.target.value as "WIDE" | "LONG", slots: [] })
                  }
                >
                  <option value="WIDE">宽表：多个记录列</option>
                  <option value="LONG">长表：一行一个事实</option>
                </select>
              </label>
              <button disabled={!exactAsset || busy !== null} onClick={applySuggestions}>
                应用农事合成映射建议
              </button>
            </div>
            <p>
              列名映射只是准备声明，不是权威身份映射。原始地块标识保留，不自动建立地块。中文/英文表头均由人工选列；空白不补零。
            </p>
            {mapping(COMMON)}
            <details>
              <summary>来源、时间及修订列</summary>
              {mapping(SOURCE)}
            </details>
            {editing.kind === "AREA" &&
              mapping([
                ...(editing.layout === "WIDE"
                  ? (["planted_area", "productive_area", "effective_area"] as V020Field[])
                  : (["area_basis", "area_value"] as V020Field[])),
                ...areaFields,
              ])}
            {editing.kind !== "AREA" && (
              <>
                {editing.layout === "LONG" &&
                  mapping([editing.kind === "EVENT" ? "event_type" : "stage", "date"])}
                {mapping(editing.kind === "EVENT" ? eventFields : phenoFields)}
                {editing.layout === "WIDE" && (
                  <div className="v020-slots">
                    <p>
                      为每一个原始日期列指定对象。多次剪枝分别加列；方式不明的促早选“未映射原始事件”，不能推断成加温。
                    </p>
                    {editing.slots.map((s, i) => (
                      <fieldset key={s.id}>
                        <legend>日期列 {i + 1}</legend>
                        <label>
                          原始日期列{" "}
                          <select
                            aria-label={`日期列 ${i + 1}`}
                            value={s.column}
                            onChange={(e) =>
                              updateSlot(i, {
                                column: Number(e.target.value),
                                label:
                                  preview?.columns.find((c) => c.index === Number(e.target.value))
                                    ?.name ?? "原始业务事件",
                              })
                            }
                          >
                            {preview?.columns.map((c) => (
                              <option key={c.index} value={c.index}>
                                {c.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          登记类型{" "}
                          <select
                            aria-label={`登记类型 ${i + 1}`}
                            value={s.declared_type}
                            onChange={(e) => updateSlot(i, { declared_type: e.target.value })}
                          >
                            <option value="">未映射原始事件 / 阶段</option>
                            {(editing.kind === "EVENT"
                              ? vocabulary.event_types.map((e) => e.code)
                              : [
                                  "flowering_start_date",
                                  "flowering_peak_date",
                                  "flowering_end_date",
                                  ...vocabulary.phenology_stages,
                                ]
                            ).map((c) => (
                              <option key={c} value={c}>
                                {c}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          列级状态（未映射状态列时使用）{" "}
                          <select
                            value={s.state}
                            onChange={(e) =>
                              updateSlot(i, { state: e.target.value as V020Slot["state"] })
                            }
                          >
                            {(["UNKNOWN", "PLANNED", "OBSERVED"] as const).map((c) => (
                              <option key={c} value={c}>
                                {labels[c]}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          onClick={() =>
                            edit({ ...editing, slots: editing.slots.filter((_, j) => j !== i) })
                          }
                        >
                          移除此列映射
                        </button>
                      </fieldset>
                    ))}
                    <button
                      disabled={!preview || editing.slots.length >= 16}
                      onClick={() =>
                        edit({
                          ...editing,
                          slots: [
                            ...editing.slots,
                            {
                              id: nextSlotId(editing.slots),
                              column: 0,
                              label: preview?.columns[0]?.name ?? "",
                              declared_type: "",
                              state: "UNKNOWN",
                            },
                          ],
                        })
                      }
                    >
                      增加宽表日期列
                    </button>
                  </div>
                )}
              </>
            )}
            <button disabled={!preview || busy !== null} onClick={savePlan}>
              加入或更新本表映射
            </button>
            {dirty && <p>当前修改尚未加入映射；旧检查结果已失效。</p>}
            <div className="d-table-wrap">
              <table>
                <caption>农事原表预览 · 前50行，原值不修改</caption>
                <thead>
                  <tr>
                    {preview?.columns.map((c) => (
                      <th key={c.index}>{c.name}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {preview?.preview.map((row, i) => (
                    <tr key={i}>
                      {row.map((v, j) => (
                        <td key={j}>{v}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <h3>待规范化的映射</h3>
            <ul>
              {plans.map((p) => (
                <li key={p.sheet + p.kind}>
                  {book.sheets[p.sheet]?.name} · {labels[p.kind]} · {p.layout} · 表头第
                  {p.header + 1}行{" "}
                  <button
                    onClick={() => {
                      invalidate();
                      setEditing(structuredClone(p));
                      setDirty(false);
                    }}
                  >
                    编辑
                  </button>{" "}
                  <button
                    onClick={() => {
                      invalidate();
                      setPlans(plans.filter((a) => a !== p));
                    }}
                  >
                    移除
                  </button>
                </li>
              ))}
            </ul>
            <button disabled={!plans.length || busy !== null || dirty} onClick={generate}>
              规范化并检查农事数据
            </button>
            <details>
              <summary>文件技术身份</summary>
              <code>{book.sha256}</code>
              <p>列与样例匹配不会赋予真实来源、模型训练或预测权限。</p>
            </details>
          </>
        )}
      </Panel>
      {versions.length > 0 && (
        <Panel
          title="本地准备版本"
          note="版本仅在本页内存中保留；请下载备份。清空或退出后不会恢复。"
        >
          <label>
            选择准备版本{" "}
            <select
              value={selected?.package_id ?? ""}
              onChange={(e) => {
                wantedJob.current = -1;
                setSelected(versions.find((v) => v.package_id === e.target.value) ?? null);
                setBaseFilter("");
                setSeasonFilter("");
              }}
            >
              <option value="">请选择（不自动导出旧文件结果）</option>
              {versions.map((v, i) => (
                <option key={v.package_id} value={v.package_id}>
                  版本{i + 1} · 来源 {v.data.source_file_sha256.slice(0, 10)} ·{" "}
                  {v.data.summary.record_count}条
                </option>
              ))}
            </select>
          </label>
        </Panel>
      )}
      {selected && (
        <>
          <Panel title="农事准备总体与覆盖" note="状态可并存，计数为受影响记录；不是可训练样本比例">
            <p className="d-sheet-notice">
              {selected.data.data_class === "SYNTHETIC_TEST_FIXTURE"
                ? "合成历史示例，不代表真实基地或农艺效果。"
                : "用户本地文件，真实来源未核验。"}{" "}
              SOURCE_AUTHORITY_NOT_PROVEN · PIT_NOT_PROVEN · 模型准入 0。
            </p>
            {book && book.sha256 !== selected.data.source_file_sha256 && (
              <p>正在查看以前文件的显式选择版本，当前文件映射不改变该版本。</p>
            )}
            <dl className="d-sheet-stats">
              <div>
                <dt>原始来源行</dt>
                <dd>{selected.data.summary.source_row_count}</dd>
              </div>
              <div>
                <dt>面积记录</dt>
                <dd>{selected.data.summary.kind_counts.AREA}</dd>
              </div>
              <div>
                <dt>管理事件</dt>
                <dd>{selected.data.summary.kind_counts.EVENT}</dd>
              </div>
              <div>
                <dt>物候记录</dt>
                <dd>{selected.data.summary.kind_counts.PHENOLOGY}</dd>
              </div>
              <div>
                <dt>基地 / 品种来源</dt>
                <dd>
                  {selected.data.summary.base_count} / {selected.data.summary.variety_count}
                </dd>
              </div>
              <div>
                <dt>结构齐全 / 正式研究准入</dt>
                <dd>{selected.data.summary.structurally_complete_count} / 0</dd>
              </div>
            </dl>
            <p>
              各产季：
              {Object.entries(selected.data.summary.season_counts)
                .map(([k, v]) => `${k}：${v}条`)
                .join("；")}
              。没有记录不等于没有农事操作。
            </p>
            <div className="d-sheet-controls">
              <label>
                展示产季{" "}
                <select value={seasonFilter} onChange={(e) => setSeasonFilter(e.target.value)}>
                  <option value="">全部产季（分项展示）</option>
                  {Object.keys(selected.data.summary.season_counts).map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
              <label>
                展示基地{" "}
                <select value={baseFilter} onChange={(e) => setBaseFilter(e.target.value)}>
                  <option value="">全部基地来源</option>
                  {[...new Set(selected.data.records.map((r) => r.scope.base))].map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </label>
            </div>
            <p>
              筛选只影响展示，不删除准备包中的任何记录。下表最多显示200条；JSON/CSV
              保留全部原始位置、映射和问题。
            </p>
            <div className="d-actions">
              <button
                onClick={() =>
                  download(
                    selected.zip_bytes as Uint8Array<ArrayBuffer>,
                    "application/zip",
                    selected.package_id + ".zip",
                  )
                }
              >
                下载版本准备包 ZIP
              </button>
              {selected.files.map((f) => (
                <button
                  key={f.name}
                  onClick={() =>
                    download(
                      f.content,
                      f.name.endsWith("html")
                        ? "text/html;charset=utf-8"
                        : f.name.endsWith("csv")
                          ? "text/csv;charset=utf-8"
                          : "application/json",
                      f.name,
                    )
                  }
                >
                  下载 {f.name}
                </button>
              ))}
            </div>
            <details>
              <summary>版本与权限技术身份</summary>
              <code>{selected.package_id}</code>
              <p>
                Source {selected.data.source_file_sha256}
                <br />
                Mapping {selected.data.mapping_sha256}
                <br />
                Vocabulary {selected.data.vocabulary_sha256}
              </p>
              <pre>{JSON.stringify(selected.data.restrictions, null, 2)}</pre>
            </details>
          </Panel>
          <Panel
            title="面积结构"
            note="种植、投产、有效面积分列；不合计冲突版本，不将种植面积代填为投产面积"
          >
            <div className="d-table-wrap">
              <table>
                <caption>V0.20 基地 / 品种 / 产季面积</caption>
                <thead>
                  <tr>
                    <th>基地 / 来源地块</th>
                    <th>品种 / 产季</th>
                    <th>制度</th>
                    <th>面积口径</th>
                    <th>规范值 / 原值</th>
                    <th>单位 / 有效区间</th>
                    <th>状态及源行</th>
                  </tr>
                </thead>
                <tbody>
                  {areas.map((r) => (
                    <tr key={r.record_id}>
                      <td>
                        {r.scope.base} / {r.scope.plot}
                      </td>
                      <td>
                        {r.scope.variety} / {r.scope.season}
                      </td>
                      <td>{r.scope.production_system}</td>
                      <td>
                        {new Map([
                          ["PLANTED", "种植"],
                          ["PRODUCTIVE", "投产"],
                          ["EFFECTIVE", "有效"],
                        ]).get(r.area!.basis) ?? "未映射"}
                      </td>
                      <td>
                        {r.area!.value ?? "未知"} / {r.area!.raw_value || "空白"}
                      </td>
                      <td>
                        {r.area!.unit}
                        <br />
                        {r.area!.effective_from.raw || "未知"} 至{" "}
                        {r.area!.effective_to.raw || "未知"}
                      </td>
                      <td>
                        {r.states.map((s) => labels[s]).join(" / ")}
                        <RowSource record={r} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          {(
            [
              ["EVENT", events, "剪枝及促早时间线"],
              ["PHENOLOGY", phenology, "开花及物候时间线"],
            ] as const
          ).map(([kind, rows, title]) => (
            <Panel
              key={kind}
              title={title}
              note="计划、观测和未知分开保留；原始日期精度不升级，不推断对产量的影响"
            >
              <div className="v020-timeline">
                {rows.map((r) => (
                  <article key={r.record_id} data-state={r.observed_or_planned}>
                    <div>
                      <strong>{r.business_date.raw || "日期未知"}</strong> ·{" "}
                      {labels[r.business_date.precision] ?? r.business_date.precision} ·{" "}
                      {labels[r.observed_or_planned]}
                    </div>
                    <p>
                      {r.scope.season} · {r.scope.base} · {r.scope.plot} · {r.scope.variety} ·{" "}
                      {r.scope.production_system}
                    </p>
                    <p>
                      {r.event?.raw_type ?? r.phenology?.raw_stage} →{" "}
                      {r.event?.canonical_type ??
                        r.phenology?.production_plan_field ??
                        r.phenology?.canonical_stage ??
                        "未映射，保留原事件 / 阶段"}
                    </p>
                    <p>
                      方法：{r.event?.method ?? r.phenology?.method ?? "未知"} · 样本：
                      {r.phenology?.sample_scope ?? "未声明 / 不适用"}
                    </p>
                    <RowSource record={r} />
                  </article>
                ))}
              </div>
            </Panel>
          ))}
          <Panel
            title="缺失、冲突与未来研究缺口"
            note="需要真实来源、精确主数据连接、历史时间权威与产量标签；本包不直接进入模型"
          >
            <div className="d-table-wrap">
              <table>
                <caption>V0.20 数据准备状态</caption>
                <thead>
                  <tr>
                    <th>状态</th>
                    <th>受影响记录数</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(selected.data.summary.state_counts).map(([k, v]) => (
                    <tr key={k}>
                      <td>
                        {labels[k]} <code>{k}</code>
                      </td>
                      <td>{v}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p>
              品种/地块身份、面积有效性、完整观测方法、可见时间和真实来源仍须逐项证明。理论机制不能代替因果或精度验证。
            </p>
            <details>
              <summary>全部问题原因计数</summary>
              <pre>{JSON.stringify(selected.data.summary.issue_counts, null, 2)}</pre>
            </details>
          </Panel>
          <Panel title="本地 HTML 质量报告" note="沙箱静态报告，无脚本或外部网络内容">
            <iframe
              title="V0.20 农事质量报告"
              sandbox=""
              srcDoc={selected.html}
              key={selected.package_id}
            />
          </Panel>
        </>
      )}
    </section>
  );
}
