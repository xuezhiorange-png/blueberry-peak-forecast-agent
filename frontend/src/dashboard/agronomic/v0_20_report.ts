import { V0_20_LIMITS, type V020Kind, type V020Package } from "./v0_20_contracts";
const compareText = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

export function escapeV020(value: unknown): string {
  return String(value ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!,
  );
}
function csvCell(value: unknown) {
  let s = String(value ?? "");
  if (/^[\s\ufeff]*[=+@-]/.test(s)) s = "'" + s;
  return '"' + s.replace(/"/g, '""') + '"';
}
export function csvV020(data: V020Package, kind: V020Kind, packageId: string): string {
  const fields = [
    "package_id",
    "record_id",
    "source_file_sha256",
    "mapping_sha256",
    "source_sheet",
    "source_row",
    "source_columns",
    "base",
    "farm",
    "subfarm",
    "source_plot_id",
    "variety",
    "season",
    "production_system",
    "identity_status",
    "observed_or_planned",
    "logical_id",
    "revision_id",
    "supersedes_revision",
    "business_date_raw",
    "date_precision",
    "observed_at_raw",
    "recorded_at_raw",
    "known_at_raw",
    "source_reference",
    "source_version",
    "area_basis",
    "area_value",
    "area_value_raw",
    "area_unit",
    "effective_from_raw",
    "effective_to_raw",
    "tree_age_years",
    "planting_year",
    "event_type_raw",
    "event_type_canonical",
    "pruning_type",
    "operation_count",
    "intensity_mode",
    "intensity_value",
    "intensity_unit",
    "intensity_denominator",
    "event_end_raw",
    "phenology_raw",
    "phenology_canonical",
    "production_plan_field",
    "method",
    "sample_scope",
    "quality_status",
    "states",
    "reason_codes",
  ];
  const rows = data.records
    .filter((r) => r.kind === kind)
    .map((r) => [
      packageId,
      r.record_id,
      data.source_file_sha256,
      data.mapping_sha256,
      r.source_sheet,
      r.source_row,
      JSON.stringify({ columns: r.source_columns, slot: r.slot }),
      r.scope.base,
      r.scope.farm,
      r.scope.subfarm,
      r.scope.plot,
      r.scope.variety,
      r.scope.season,
      r.scope.production_system,
      r.scope.resolved ? "SYNTHETIC_REFERENCE_ONLY" : "UNMAPPED",
      r.observed_or_planned,
      r.logical_id,
      r.revision_id,
      r.supersedes_revision,
      r.business_date.raw,
      r.business_date.precision,
      r.observed_at.raw,
      r.recorded_at.raw,
      r.known_at.raw,
      r.source_reference,
      r.source_version,
      r.area?.basis,
      r.area?.value,
      r.area?.raw_value,
      r.area?.unit,
      r.area?.effective_from.raw,
      r.area?.effective_to.raw,
      r.area?.tree_age_years,
      r.area?.planting_year,
      r.event?.raw_type,
      r.event?.canonical_type,
      r.event?.pruning_type,
      r.event?.operation_count,
      r.event?.intensity_mode,
      r.event?.intensity_value,
      r.event?.intensity_unit,
      r.event?.intensity_denominator,
      r.event?.end_date.raw,
      r.phenology?.raw_stage,
      r.phenology?.canonical_stage,
      r.phenology?.production_plan_field,
      r.event?.method ?? r.phenology?.method,
      r.phenology?.sample_scope,
      r.phenology?.quality_status,
      r.states.join(";"),
      r.issues.map((i) => i.code).join(";"),
    ]);
  return (
    "\ufeff" + [fields, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n") + "\r\n"
  );
}
export function renderV020(data: V020Package, packageId: string): string {
  const e = escapeV020,
    s = data.summary;
  const cells = (values: unknown[]) =>
    "<tr>" + values.map((v) => "<td>" + e(v) + "</td>").join("") + "</tr>";
  const selected = data.records.slice(0, V0_20_LIMITS.reportRows);
  const area = selected
    .filter((r) => r.area)
    .map((r) =>
      cells([
        r.scope.base,
        r.scope.plot,
        r.scope.variety,
        r.scope.season,
        r.scope.production_system,
        r.area!.basis,
        r.area!.value ?? "未知",
        r.area!.unit,
        r.area!.effective_from.raw + " 至 " + r.area!.effective_to.raw,
        r.states.join(" / "),
      ]),
    )
    .join("");
  const timeline = (kind: V020Kind) =>
    selected
      .filter((r) => r.kind === kind)
      .sort(
        (a, b) =>
          compareText(a.scope.season, b.scope.season) ||
          compareText(a.scope.base, b.scope.base) ||
          compareText(a.business_date.lower_date ?? "~", b.business_date.lower_date ?? "~"),
      )
      .map((r) =>
        cells([
          r.scope.season,
          r.scope.base,
          r.scope.plot,
          r.scope.variety,
          r.business_date.raw || "未知",
          r.business_date.precision,
          r.observed_or_planned,
          r.event?.raw_type ?? r.phenology?.raw_stage,
          r.event?.canonical_type ??
            r.phenology?.canonical_stage ??
            r.phenology?.production_plan_field ??
            "未映射",
          r.event?.method ?? r.phenology?.method ?? "未知",
          r.phenology?.sample_scope ?? "—",
        ]),
      )
      .join("");
  const problems = selected
    .filter((r) => r.issues.length)
    .map((r) =>
      cells([
        r.source_sheet + " 第" + r.source_row + "行",
        r.scope.season,
        r.kind,
        r.issues.map((i) => i.message + " [" + i.code + "]").join("；"),
      ]),
    )
    .join("");
  return (
    '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
    "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'\">" +
    "<title>V0.20 农事历史质量报告</title><style>body{font:16px system-ui;max-width:1180px;margin:auto;padding:20px;color:#183c32}h2{margin-top:28px}table{border-collapse:collapse;min-width:700px;width:100%}td,th{border-bottom:1px solid #dce4de;padding:9px;text-align:left;vertical-align:top}section{overflow:auto}code,pre{white-space:pre-wrap;overflow-wrap:anywhere}.note{padding:14px;background:#fff7e4;border-left:4px solid #b58328}</style>" +
    '<h1>V0.20 蓝莓历史农事数据准备报告</h1><p class="note">' +
    (data.data_class === "SYNTHETIC_TEST_FIXTURE"
      ? "合成历史样例，不代表真实农场或农艺增益。"
      : "用户文件仅在浏览器本地准备，真实来源未核验。") +
    " 不上传、不写生产数据库、不训练、不调整预测。</p>" +
    "<p>本报告说明字段、日期、冲突与覆盖，不是来源批准或模型准入。日/月精度不补时分秒；SOURCE_AUTHORITY_NOT_PROVEN；PIT_NOT_PROVEN。</p>" +
    "<h2>总体及覆盖</h2><p>来源行 " +
    e(s.source_row_count) +
    "；规范化记录 " +
    e(s.record_count) +
    "；基地来源 " +
    e(s.base_count) +
    "；品种来源 " +
    e(s.variety_count) +
    "；结构齐全 " +
    e(s.structurally_complete_count) +
    "；正式研究准入 0。</p>" +
    "<p>面积 " +
    e(s.kind_counts.AREA) +
    "；管理事件 " +
    e(s.kind_counts.EVENT) +
    "；物候 " +
    e(s.kind_counts.PHENOLOGY) +
    "。结构齐全不是训练资格；地块保留原始标识，不创建权威地块。</p>" +
    "<section><table><caption>各产季记录覆盖（不跨季合并）</caption><tr><th>产季</th><th>记录数</th></tr>" +
    Object.entries(s.season_counts)
      .map(([k, v]) => cells([k, v]))
      .join("") +
    "</table></section>" +
    "<h2>面积结构</h2><p>种植、投产、有效面积分别展示；多版本不相加，区间重叠保留冲突。不擅自做单位转换。</p><section><table><tr><th>基地</th><th>来源地块</th><th>品种</th><th>产季</th><th>制度</th><th>口径</th><th>数值</th><th>单位</th><th>有效区间</th><th>状态</th></tr>" +
    area +
    "</table></section>" +
    "<h2>剪枝、促早与其他事件时间线</h2><p>计划与观测分列。促早方式未知时不推断加温或休眠解除；多次操作保留，不按次数复制事实。</p><section><table><tr><th>产季</th><th>基地</th><th>地块</th><th>品种</th><th>原始日期</th><th>精度</th><th>计划/实际</th><th>原事件</th><th>登记类型</th><th>方法</th><th>样本</th></tr>" +
    timeline("EVENT") +
    "</table></section>" +
    "<h2>开花与物候时间线</h2><p>开花开始、盛花、结束不等于 BLOOM_10、BLOOM_50、BLOOM_90。真实阈值观察仍须方法、样本与质量证明。</p><section><table><tr><th>产季</th><th>基地</th><th>地块</th><th>品种</th><th>原始日期</th><th>精度</th><th>计划/实际</th><th>原阶段</th><th>登记状态/业务字段</th><th>方法</th><th>样本</th></tr>" +
    timeline("PHENOLOGY") +
    "</table></section>" +
    "<h2>缺失、冲突及未决项</h2><section><table><tr><th>来源位置</th><th>产季</th><th>对象</th><th>说明及原始原因码</th></tr>" +
    problems +
    "</table></section>" +
    "<p>报告最多展示 " +
    e(V0_20_LIMITS.reportRows) +
    " 条明细；JSON/CSV 保留全部记录和原因，未隐藏困难样本。</p>" +
    "<h2>后续研究缺口</h2><p>需要真实数据责任人提供精确成员和面积权威、事件与观测来源、历史记录/可见时间及相关产量标签。理论机制和相关性不能证明因果增益。所有模型使用权限为 false；不改变 S6–S9。</p>" +
    "<details><summary>版本身份与审计</summary><pre>" +
    e(packageId) +
    "\nSource " +
    e(data.source_file_sha256) +
    "\nMapping " +
    e(data.mapping_sha256) +
    "\nVocabulary " +
    e(data.vocabulary_sha256) +
    "\n" +
    e(JSON.stringify(data.restrictions, null, 2)) +
    "</pre></details></html>"
  );
}
