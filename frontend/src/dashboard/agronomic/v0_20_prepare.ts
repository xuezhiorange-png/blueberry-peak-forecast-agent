import vocabulary from "./v0_20_vocabulary.json";
import { zipSync, strToU8 } from "fflate";
import synthetic from "./v0_20_synthetic.json";
import { dateValue, kgValue, sha256 } from "../spreadsheet/preview";
import type { LocalBook } from "../spreadsheet/contracts";
import {
  V0_20_FIELDS,
  V0_20_LIMITS,
  type V020Date,
  type V020Field,
  type V020Package,
  type V020Prepared,
  type V020Record,
  type V020Reference,
  type V020SheetPlan,
  type V020Slot,
  type V020State,
} from "./v0_20_contracts";
import { renderV020, csvV020 } from "./v0_20_report";

const compareText = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);

export function canonicalV020(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return "[" + value.map(canonicalV020).join(",") + "]";
  const o = value as Record<string, unknown>;
  return (
    "{" +
    Object.keys(o)
      .sort()
      .map((k) => JSON.stringify(k) + ":" + canonicalV020(o[k]))
      .join(",") +
    "}"
  );
}
async function hash(value: unknown) {
  return sha256(new TextEncoder().encode(canonicalV020(value)).buffer);
}
const EMPTY_DATE: V020Date = {
  raw: "",
  precision: "UNKNOWN",
  lower_date: null,
  upper_date: null,
  instant: null,
};
export function dateV020(raw: string): V020Date {
  const value = raw.trim();
  const out = { ...EMPTY_DATE, raw };
  if (!value) return out;
  const day = dateValue(value);
  if (day) return { ...out, precision: "DAY", lower_date: day, upper_date: day };
  if (/^(19|20|21)\d{2}$/.test(value))
    return {
      ...out,
      precision: "YEAR",
      lower_date: value + "-01-01",
      upper_date: value + "-12-31",
    };
  const month = /^((?:19|20|21)\d{2})[-年/](0?[1-9]|1[0-2])月?$/.exec(value);
  if (month) {
    const start = month[1] + "-" + month[2].padStart(2, "0") + "-01";
    const end = new Date(Date.UTC(+month[1], +month[2], 0)).toISOString().slice(0, 10);
    return { ...out, precision: "MONTH", lower_date: start, upper_date: end };
  }
  const stamp =
    /^(\d{4}-\d{2}-\d{2})[T ]([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:\.\d{1,9})?)?(Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)?$/.exec(
      value,
    );
  if (stamp && dateValue(stamp[1])) {
    if (!stamp[3])
      return { ...out, precision: "LOCAL_DATETIME", lower_date: stamp[1], upper_date: stamp[1] };
    const instant = new Date(value.replace(" ", "T"));
    if (Number.isFinite(instant.getTime()))
      return {
        ...out,
        precision: "TIMESTAMP",
        lower_date: stamp[1],
        upper_date: stamp[1],
        instant: instant.toISOString(),
      };
  }
  return out;
}
const generic: Record<string, string> = {
  flowering_start_date: "flowering_start_date",
  flowering_peak_date: "flowering_peak_date",
  flowering_end_date: "flowering_end_date",
  开花开始: "flowering_start_date",
  盛花: "flowering_peak_date",
  开花结束: "flowering_end_date",
};
const eventCodes = new Set(vocabulary.event_types.map((e) => e.code));
const stages = new Set(vocabulary.phenology_stages);
const systems = new Set(vocabulary.production_systems);
const fields = new Set(V0_20_FIELDS.map(([k]) => k));
// Explicitly unknown method text is not proof of an operation. Keep raw text in exports.
const methodKnown = (v: string | null) =>
  v !== null &&
  !new Set([
    "",
    "UNKNOWN",
    "UNSPECIFIED",
    "N/A",
    "NA",
    "NULL",
    "NONE",
    "-",
    "未知",
    "不明",
    "不详",
    "未提供",
    "待确认",
  ]).has(v.trim().toUpperCase());
const stateMap: Record<string, V020State> = {
  计划: "PLANNED",
  实际: "OBSERVED",
  已执行: "OBSERVED",
  观测: "OBSERVED",
  未知: "UNKNOWN",
  PLANNED: "PLANNED",
  OBSERVED: "OBSERVED",
  UNKNOWN: "UNKNOWN",
};
const state = (s: string): V020State => (Object.hasOwn(stateMap, s) ? stateMap[s] : "UNKNOWN");
const genericStage = (s: string) => (Object.hasOwn(generic, s) ? generic[s] : null);
function issue(
  r: V020Record,
  code: string,
  message: string,
  severity: "ERROR" | "WARNING" | "INFO" = "WARNING",
  field = "",
) {
  if (!r.issues.some((i) => i.code === code && i.field === field))
    r.issues.push({ code, message, severity, field });
}
function mu(v: string) {
  const s = kgValue(v);
  return s === null ? null : BigInt(s.replace(".", ""));
}
function key(r: V020Record) {
  const s = r.scope;
  return JSON.stringify([
    s.base,
    s.farm,
    s.subfarm,
    s.plot,
    s.variety,
    s.season,
    s.production_system,
  ]);
}
type AreaInterval = { record: V020Record; start: string; end: string; value: bigint };
function areaChecks(areas: V020Record[]) {
  const intervals: AreaInterval[] = [];
  for (const r of areas) {
    const a = r.area!;
    const value = a.value === null ? null : mu(a.value);
    if (
      a.effective_from.precision === "DAY" &&
      a.effective_to.precision === "DAY" &&
      a.effective_from.lower_date! <= a.effective_to.upper_date!
    )
      intervals.push({
        record: r,
        start: a.effective_from.lower_date!,
        end: a.effective_to.upper_date!,
        value: value ?? 0n,
      });
  }
  const byBasis = new Map<string, AreaInterval[]>();
  for (const a of intervals) {
    const group = byBasis.get(a.record.area!.basis) ?? [];
    group.push(a);
    byBasis.set(a.record.area!.basis, group);
  }
  for (const rows of byBasis.values()) {
    rows.sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
    let active: AreaInterval | null = null;
    for (const a of rows) {
      if (active && a.start <= active.end)
        for (const item of [a, active])
          issue(
            item.record,
            "AREA_INTERVAL_CONFLICT",
            "同地块/品种/产季、同面积口径的生效区间重叠；不累计或覆盖。",
            "ERROR",
          );
      if (!active || a.end > active.end) active = a;
    }
  }
  const valid = intervals.filter(
    (a) => a.record.area!.unit === "mu" && a.record.area!.value !== null,
  );
  const planted = valid.filter((a) => a.record.area!.basis === "PLANTED");
  const other = valid.filter((a) => ["PRODUCTIVE", "EFFECTIVE"].includes(a.record.area!.basis));
  // Offline suffix range extrema: each area is checked without quadratic pair scans.
  function check(rows: AreaInterval[], queries: AreaInterval[], minimum: boolean) {
    if (!rows.length || !queries.length) return;
    const ends = [...new Set(rows.map((a) => a.end))].sort();
    const positions = new Map(ends.map((e, i) => [e, i]));
    let size = 1;
    while (size < ends.length) size *= 2;
    const tree: (AreaInterval | null)[] = Array(size * 2).fill(null);
    const best = (a: AreaInterval | null, b: AreaInterval | null) =>
      !a ? b : !b ? a : (minimum ? a.value <= b.value : a.value >= b.value) ? a : b;
    const sorted = [...rows].sort((a, b) => (a.start < b.start ? -1 : a.start > b.start ? 1 : 0));
    let cursor = 0;
    for (const q of [...queries].sort((a, b) => (a.end < b.end ? -1 : a.end > b.end ? 1 : 0))) {
      while (cursor < sorted.length && sorted[cursor].start <= q.end) {
        const a = sorted[cursor++];
        let pos = positions.get(a.end)! + size;
        tree[pos] = best(tree[pos], a);
        for (pos = Math.floor(pos / 2); pos > 0; pos = Math.floor(pos / 2))
          tree[pos] = best(tree[pos * 2], tree[pos * 2 + 1]);
      }
      let low = 0,
        high = ends.length;
      while (low < high) {
        const mid = Math.floor((low + high) / 2);
        if (ends[mid] < q.start) low = mid + 1;
        else high = mid;
      }
      let l = low + size,
        r = ends.length + size,
        candidate: AreaInterval | null = null;
      while (l < r) {
        if (l % 2) candidate = best(candidate, tree[l++]);
        if (r % 2) candidate = best(candidate, tree[--r]);
        l = Math.floor(l / 2);
        r = Math.floor(r / 2);
      }
      if (candidate && (minimum ? candidate.value < q.value : candidate.value > q.value))
        for (const a of [candidate, q])
          issue(
            a.record,
            "AREA_BASIS_CONFLICT",
            "重叠有效区间内存在投产/有效面积大于种植面积的声明；保留双方记录待核验。",
            "ERROR",
          );
    }
  }
  check(planted, other, true);
  check(other, planted, false);
}

function validatePlans(book: LocalBook, plans: V020SheetPlan[]): V020SheetPlan[] {
  if (!plans.length || plans.length > 24) throw Error("V0_20_MAPPING_REQUIRED");
  const seen = new Set<string>();
  const headers = new Map<number, number>();
  let bound = 0;
  for (const p of plans) {
    const sheet = book.sheets[p.sheet];
    if (
      !sheet ||
      !Number.isInteger(p.sheet) ||
      !Number.isInteger(p.header) ||
      p.header < 0 ||
      p.header >= sheet.rows.length ||
      !["AREA", "EVENT", "PHENOLOGY"].includes(p.kind) ||
      !["WIDE", "LONG"].includes(p.layout)
    )
      throw Error("V0_20_MAPPING_INVALID");
    const id = p.sheet + ":" + p.kind;
    if (seen.has(id)) throw Error("V0_20_DUPLICATE_SHEET_PLAN");
    seen.add(id);
    if (headers.has(p.sheet) && headers.get(p.sheet) !== p.header)
      throw Error("V0_20_HEADER_CONFLICT");
    headers.set(p.sheet, p.header);
    const columns = Math.max(...sheet.rows.map((r) => r.length));
    for (const [k, c] of Object.entries(p.columns))
      if (
        !fields.has(k as V020Field) ||
        (c != null && (!Number.isInteger(c) || c < 0 || c >= columns))
      )
        throw Error("V0_20_COLUMN_INVALID");
    if (p.slots.length > 16 || new Set(p.slots.map((s) => s.id)).size !== p.slots.length)
      throw Error("V0_20_SLOT_INVALID");
    for (const s of p.slots)
      if (
        !s.id ||
        s.id.length > 80 ||
        !Number.isInteger(s.column) ||
        s.column < 0 ||
        s.column >= columns ||
        !["PLANNED", "OBSERVED", "UNKNOWN"].includes(s.state) ||
        s.label.length > 200 ||
        s.declared_type.length > 100
      )
        throw Error("V0_20_SLOT_INVALID");
    bound +=
      (sheet.rows.length - p.header - 1) *
      (p.layout === "LONG" ? 1 : p.kind === "AREA" ? 3 : Math.max(1, p.slots.length));
  }
  if (bound > V0_20_LIMITS.records) throw Error("V0_20_RECORD_LIMIT");
  return structuredClone(plans).sort((a, b) => a.sheet - b.sheet || compareText(a.kind, b.kind));
}

function createRecord(
  book: LocalBook,
  p: V020SheetPlan,
  rowIndex: number,
  slot: V020Slot | null,
  areaBasis: string | null,
  reference: V020Reference[],
): V020Record {
  const sheet = book.sheets[p.sheet],
    row = sheet.rows[rowIndex];
  const value = (k: V020Field) =>
    p.columns[k] == null ? "" : (row[p.columns[k]!]?.text.trim() ?? "");
  const rawDate = slot ? (row[slot.column]?.text.trim() ?? "") : value("date");
  const declared = slot?.declared_type ?? "";
  const status = value("status") || slot?.state || "UNKNOWN";
  const scope = {
    base: value("base"),
    farm: value("farm"),
    subfarm: value("subfarm"),
    plot: value("plot"),
    variety: value("variety"),
    season: value("season"),
    production_system: value("production_system") || "UNBOUND",
    resolved: null as V020Reference | null,
    plot_authority_id: null,
  };
  const matched = reference.filter((m) =>
    (["base", "farm", "subfarm", "plot", "variety"] as const).every((k) => m[k] === scope[k]),
  );
  if (matched.length === 1) scope.resolved = matched[0];
  const r: V020Record = {
    record_id: `V0_20:${book.sha256}:${p.sheet}:${rowIndex + 1}:${p.kind}:${slot?.id ?? areaBasis ?? "long"}`,
    kind: p.kind,
    source_row_id: `${book.sha256}:${p.sheet}:${rowIndex + 1}`,
    source_sheet: sheet.name,
    source_row: rowIndex + 1,
    source_columns: { ...p.columns },
    slot,
    scope,
    logical_id: value("logical_id") || null,
    revision_id: value("revision_id") || null,
    supersedes_revision: value("supersedes_revision") || null,
    observed_or_planned: state(status),
    source_reference: value("source_reference") || null,
    source_version: value("source_version") || null,
    recorded_at: dateV020(value("recorded_at")),
    known_at: dateV020(value("known_at")),
    business_date: dateV020(rawDate),
    observed_at: dateV020(value("observed_at")),
    area: null,
    event: null,
    phenology: null,
    issues: [],
    states: [],
  };
  for (const k of ["base", "farm", "subfarm", "plot", "variety", "season"] as const)
    if (!scope[k]) issue(r, "IDENTITY_MISSING", "来源身份字段缺失，不猜测成员归属。", "WARNING", k);
  if (!scope.resolved)
    issue(
      r,
      "IDENTITY_UNMAPPED",
      "没有精确身份连接；保留来源编码和原始地块，不建立权威实体。",
      "WARNING",
    );
  issue(r, "PLOT_SOURCE_ONLY", "地块仅是来源标识；没有新建或认定权威地块。", "INFO");
  if (
    !/^\d{4}-\d{4}$/.test(scope.season) ||
    +scope.season.slice(5) !== +scope.season.slice(0, 4) + 1
  )
    issue(r, "SEASON_INVALID", "产季应明确为连续年份，例如 2023-2024。", "ERROR", "season");
  if (!systems.has(scope.production_system))
    issue(r, "PRODUCTION_SYSTEM_UNBOUND", "栽培制度未明确；不由促早或修剪日期推断。", "WARNING");
  if (!r.source_reference || !r.source_version)
    issue(
      r,
      "SOURCE_LINEAGE_MISSING",
      "缺少来源引用或版本，仍可准备但不可认定真实来源。",
      "WARNING",
    );
  if (
    status &&
    !Object.prototype.hasOwnProperty.call(
      { PLANNED: 1, OBSERVED: 1, UNKNOWN: 1, 计划: 1, 实际: 1, 已执行: 1, 观测: 1, 未知: 1 },
      status,
    )
  )
    issue(r, "OBSERVATION_STATUS_UNKNOWN", "未识别的计划/实际声明保持 UNKNOWN。", "WARNING");
  if (r.observed_or_planned === "PLANNED" && r.observed_at.raw)
    issue(
      r,
      "PLANNED_OBSERVED_CONFLICT",
      "计划记录同时填有实际观测时间；不得当作已经执行。",
      "ERROR",
    );
  for (const [field, time] of [
    ["recorded_at", r.recorded_at],
    ["known_at", r.known_at],
    ["observed_at", r.observed_at],
  ] as const) {
    if (!time.raw && field !== "observed_at")
      issue(r, "TIME_MISSING", "时间字段缺失，不用其他时钟替代。", "WARNING", field);
    else if (time.raw && time.precision === "UNKNOWN")
      issue(r, "DATE_INVALID", "无法解析时间，保留原值。", "ERROR", field);
    else if (time.raw && time.precision !== "TIMESTAMP")
      issue(r, "TIME_PRECISION_UNPROVEN", "原始时间精度/时区不足，不补造时分秒。", "INFO", field);
  }
  if (r.recorded_at.instant && r.known_at.instant && r.recorded_at.instant > r.known_at.instant)
    issue(r, "KNOWN_BEFORE_RECORDED", "可见时间早于来源记录时间。", "ERROR");
  if (r.observed_at.instant && r.known_at.instant && r.observed_at.instant > r.known_at.instant)
    issue(r, "KNOWN_BEFORE_OBSERVED", "可见时间早于实际观测时间。", "ERROR");
  if (p.kind === "AREA") {
    const basis = areaBasis ?? value("area_basis");
    const raw = areaBasis
      ? value(
          (
            {
              PLANTED: "planted_area",
              PRODUCTIVE: "productive_area",
              EFFECTIVE: "effective_area",
            } as const
          )[areaBasis as "PLANTED"],
        )
      : value("area_value");
    r.area = {
      basis: basis || "UNKNOWN",
      raw_value: raw,
      value: kgValue(raw),
      unit: ["mu", "亩"].includes(value("area_unit")) ? "mu" : value("area_unit") || "UNKNOWN",
      effective_from: dateV020(value("effective_from")),
      effective_to: dateV020(value("effective_to")),
      tree_age_years: value("tree_age_years") ? kgValue(value("tree_age_years")) : null,
      planting_year: value("planting_year") || null,
    };
    if (!["PLANTED", "PRODUCTIVE", "EFFECTIVE"].includes(basis))
      issue(r, "AREA_BASIS_UNMAPPED", "种植、投产、有效面积口径未明确，不相互代填。", "WARNING");
    if (!raw) issue(r, "AREA_VALUE_MISSING", "面积缺失，不能补零。", "WARNING");
    else if (r.area.value === null)
      issue(r, "AREA_VALUE_INVALID", "面积须是非负、最多六位小数的明确数值。", "ERROR");
    if (r.area.unit !== "mu")
      issue(r, "AREA_UNIT_UNVERIFIED", "单位不是明确的亩；保留原单位，不擅自转换。", "WARNING");
    for (const t of [r.area.effective_from, r.area.effective_to])
      if (!t.lower_date || t.precision !== "DAY")
        issue(
          r,
          "AREA_EFFECTIVE_PERIOD_UNPROVEN",
          "面积生效日期缺失或不是明确业务日；原始时间保留，不猜测日期精度。",
          "WARNING",
        );
    if (
      r.area.effective_from.lower_date &&
      r.area.effective_to.upper_date &&
      r.area.effective_from.lower_date > r.area.effective_to.upper_date
    )
      issue(r, "AREA_INTERVAL_INVALID", "面积生效结束早于开始。", "ERROR");
    if (value("tree_age_years") && r.area.tree_age_years === null)
      issue(r, "TREE_AGE_INVALID", "树龄无效，不根据种植年份或当前时间补算。", "ERROR");
    if (r.area.planting_year && !/^(19|20|21)\d{2}$/.test(r.area.planting_year))
      issue(r, "PLANTING_YEAR_INVALID", "种植年份无效。", "ERROR");
  } else {
    if (!rawDate) {
      r.observed_or_planned = "UNKNOWN";
      issue(r, "DATE_MISSING", "该项日期缺失，不代表没有发生，也不代表已观测。", "WARNING");
    } else if (r.business_date.precision === "UNKNOWN")
      issue(r, "DATE_INVALID", "业务日期无效，保留原文。", "ERROR", "date");
    else if (!["DAY", "TIMESTAMP"].includes(r.business_date.precision))
      issue(
        r,
        "DATE_PRECISION_INSUFFICIENT",
        "保留原始月/年/无时区精度；不能声称精确的观测日或时点。",
        "WARNING",
        "date",
      );
    if (p.kind === "EVENT") {
      const raw = slot
        ? sheet.rows[p.header][slot.column]?.text || slot.label
        : value("event_type");
      const type = declared || value("event_type");
      r.event = {
        raw_type: raw,
        canonical_type: eventCodes.has(type) ? type : null,
        pruning_type: value("pruning_type") || null,
        method: value("method") || null,
        operation_count: value("operation_count") || null,
        intensity_mode: value("intensity_mode") || "PRESENCE_ONLY",
        intensity_value: value("intensity_value") || null,
        intensity_unit: value("intensity_unit") || null,
        intensity_denominator: value("intensity_denominator") || null,
        end_date: dateV020(value("end_date")),
      };
      if (/促早|催早|^FORCING$/i.test(raw) && !methodKnown(r.event.method)) {
        r.event.canonical_type = null;
        issue(
          r,
          "FORCING_METHOD_UNRESOLVED",
          "只有促早日期、没有操作方法，不能推断为加温或休眠解除。",
          "WARNING",
        );
      }
      if (!r.event.canonical_type)
        issue(r, "EVENT_TYPE_UNMAPPED", "原始事件保留，未映射到 V0.9 已登记事件。", "WARNING");
      const registered = vocabulary.event_types.find((e) => e.code === r.event!.canonical_type);
      if (
        registered &&
        systems.has(scope.production_system) &&
        !registered.applicable_systems.includes(scope.production_system)
      )
        issue(
          r,
          "EVENT_SYSTEM_CONFLICT",
          "事件不在原 V0.9 注册表声明的栽培制度适用范围内；保留原事实，不能改变制度或推断效应。",
          "ERROR",
        );
      if (!vocabulary.intensity_modes.includes(r.event.intensity_mode))
        issue(
          r,
          "INTENSITY_MODE_UNMAPPED",
          "强度表达方式未登记，不能套用固定数值等级。",
          "WARNING",
        );
      if (
        ["OBSERVED_VALUE", "PLANNED_VALUE"].includes(r.event.intensity_mode) &&
        (!r.event.intensity_value ||
          kgValue(r.event.intensity_value) === null ||
          !r.event.method ||
          !r.event.intensity_unit ||
          !r.event.intensity_denominator ||
          !r.source_reference)
      )
        issue(
          r,
          "INTENSITY_CONTEXT_MISSING",
          "数值强度需要方法、单位、分母、范围与来源；不补默认系数。",
          "WARNING",
        );
      if (r.observed_or_planned === "OBSERVED" && r.event.intensity_mode === "PLANNED_VALUE")
        issue(r, "PLANNED_OBSERVED_CONFLICT", "实际事件使用计划强度，不能混用。", "ERROR");
      if (
        r.event.operation_count &&
        (!/^\d+$/.test(r.event.operation_count) || +r.event.operation_count < 1)
      )
        issue(r, "OPERATION_COUNT_INVALID", "操作次数须为正整数；不按次数虚构事件。", "ERROR");
      if (
        r.event.end_date.lower_date &&
        r.business_date.lower_date &&
        r.event.end_date.upper_date! < r.business_date.lower_date
      )
        issue(r, "EVENT_INTERVAL_INVALID", "事件结束早于开始。", "ERROR");
    } else {
      const raw = slot ? sheet.rows[p.header][slot.column]?.text || slot.label : value("stage"),
        type = declared || value("stage");
      const planField = genericStage(raw) ?? genericStage(type);
      r.phenology = {
        raw_stage: raw,
        canonical_stage: planField ? null : stages.has(type) ? type : null,
        production_plan_field: planField,
        method: value("method") || null,
        sample_scope: value("sample_scope") || null,
        quality_status: value("quality_status") || null,
      };
      if (planField)
        issue(
          r,
          "GENERIC_BLOOM_NOT_PERCENTILE",
          "开始、盛花、结束是原始业务阶段，不等于 10%、50%、90%。",
          "INFO",
        );
      else if (!r.phenology.canonical_stage)
        issue(
          r,
          "PHENOLOGY_STAGE_UNMAPPED",
          "物候阶段未在现有词汇中明确，保留原始观测。",
          "WARNING",
        );
      if (!r.phenology.method || !r.phenology.sample_scope || !r.phenology.quality_status)
        issue(r, "PHENOLOGY_METHOD_MISSING", "观测方法、样本范围或质量状态不完整。", "WARNING");
    }
  }
  return r;
}

function crossChecks(records: V020Record[], plans: V020SheetPlan[]) {
  const groups = new Map<string, V020Record[]>();
  for (const r of records) {
    const k = key(r);
    const a = groups.get(k) ?? [];
    a.push(r);
    groups.set(k, a);
  }
  for (const all of groups.values()) {
    const ids = new Map<string, V020Record[]>();
    for (const r of all) {
      if (!r.logical_id || !r.revision_id) {
        issue(
          r,
          "REVISION_IDENTITY_MISSING",
          "缺少逻辑或修订身份，不能擅自选取有效版本。",
          "WARNING",
        );
        continue;
      }
      // A wide source row explicitly yields distinct facts; the slot/basis is part of that fact identity.
      const k = JSON.stringify([
        r.kind,
        r.source_reference,
        r.logical_id,
        r.revision_id,
        r.slot?.id ?? r.area?.basis ?? "long",
      ]);
      const a = ids.get(k) ?? [];
      a.push(r);
      ids.set(k, a);
    }
    for (const duplicates of ids.values())
      if (duplicates.length > 1)
        for (const r of duplicates)
          issue(
            r,
            "DUPLICATE_REVISION",
            "同一事实的逻辑 ID / 修订 ID 重复；全部保留，不擅自删除或选 Winner。",
            "ERROR",
          );
    const facts = new Map<string, V020Record[]>();
    for (const r of all) {
      if (!r.logical_id || !r.revision_id) continue;
      const f = JSON.stringify([
        r.kind,
        r.source_reference,
        r.logical_id,
        r.slot?.id ?? r.area?.basis ?? "long",
      ]);
      const rows = facts.get(f) ?? [];
      rows.push(r);
      facts.set(f, rows);
    }
    for (const rows of facts.values()) {
      const revisions = new Map(rows.map((r) => [r.revision_id!, r]));
      const referenced = new Set(rows.map((r) => r.supersedes_revision).filter(Boolean));
      const visited = new Set<string>();
      for (const r of rows) {
        if (
          r.supersedes_revision &&
          (r.supersedes_revision === r.revision_id || !revisions.has(r.supersedes_revision))
        )
          issue(r, "REVISION_CHAIN_UNRESOLVED", "前版修订缺失或自引用；保留修订台账。", "ERROR");
        const path: string[] = [],
          positions = new Map<string, number>();
        let id: string | null = r.revision_id;
        while (id && revisions.has(id) && !visited.has(id)) {
          if (positions.has(id)) {
            for (const cycle of path.slice(positions.get(id)!))
              issue(
                revisions.get(cycle)!,
                "REVISION_CYCLE",
                "修订链存在循环；不选择有效版本。",
                "ERROR",
              );
            break;
          }
          positions.set(id, path.length);
          path.push(id);
          id = revisions.get(id)!.supersedes_revision;
        }
        for (const seen of path) visited.add(seen);
      }
      if (
        revisions.size > 1 &&
        [...revisions.keys()].filter((id) => !referenced.has(id)).length !== 1
      )
        for (const r of rows)
          issue(
            r,
            "REVISION_WINNER_UNRESOLVED",
            "存在多个不连通或分叉修订，不能证明唯一有效版本；全部保留。",
            "ERROR",
          );
    }
    areaChecks(all.filter((r) => r.area));
    for (const seq of [
      ["flowering_start_date", "flowering_peak_date", "flowering_end_date"],
      ["BLOOM_10", "BLOOM_50", "BLOOM_90"],
    ]) {
      const rows = all.filter((r) => r.phenology && r.observed_or_planned !== "UNKNOWN");
      for (let i = 0; i < seq.length; i++)
        for (let j = i + 1; j < seq.length; j++) {
          const aa = rows.filter(
            (r) => (r.phenology!.production_plan_field ?? r.phenology!.canonical_stage) === seq[i],
          );
          const bb = rows.filter(
            (r) => (r.phenology!.production_plan_field ?? r.phenology!.canonical_stage) === seq[j],
          );
          const cohorts = new Set(
            [...aa, ...bb]
              .filter((r) => r.phenology?.method && r.phenology.sample_scope)
              .map((r) =>
                JSON.stringify([
                  r.observed_or_planned,
                  r.phenology!.method,
                  r.phenology!.sample_scope,
                  r.source_reference,
                  r.source_version,
                ]),
              ),
          );
          for (const cohort of cohorts) {
            const select = (r: V020Record) =>
              JSON.stringify([
                r.observed_or_planned,
                r.phenology!.method,
                r.phenology!.sample_scope,
                r.source_reference,
                r.source_version,
              ]) === cohort;
            const before = aa.filter(select),
              after = bb.filter(select);
            const starts = before
                .map((r) => r.business_date.lower_date)
                .filter((v): v is string => v !== null)
                .sort(),
              ends = after
                .map((r) => r.business_date.upper_date)
                .filter((v): v is string => v !== null)
                .sort();
            if (starts.length && ends.length && starts.at(-1)! > ends[0])
              for (const r of [
                ...before.filter(
                  (r) =>
                    r.business_date.lower_date !== null && r.business_date.lower_date > ends[0],
                ),
                ...after.filter(
                  (r) =>
                    r.business_date.upper_date !== null &&
                    r.business_date.upper_date < starts.at(-1)!,
                ),
              ])
                issue(
                  r,
                  "PHENOLOGY_ORDER_CONFLICT",
                  "同样本、同方法、同计划/观测状态的物候阶段顺序矛盾；不修改日期。",
                  "ERROR",
                );
          }
        }
    }
  }
  for (const p of plans)
    if (p.kind === "AREA" && p.layout === "WIDE") {
      const cols = [
        p.columns.planted_area,
        p.columns.productive_area,
        p.columns.effective_area,
      ].filter((c) => c != null);
      if (new Set(cols).size !== cols.length)
        for (const r of records.filter(
          (r) =>
            r.kind === "AREA" &&
            r.record_id.startsWith(`V0_20:${r.source_row_id.split(":")[0]}:${p.sheet}:`),
        ))
          issue(
            r,
            "AREA_MAPPING_BASIS_CONFLICT",
            "同一来源面积列映射到多个物理口径；不能自动视为相同。",
            "ERROR",
          );
    }
}

export async function prepareV020(book: LocalBook, input: V020SheetPlan[]): Promise<V020Prepared> {
  const plans = validatePlans(book, input);
  const view = await hash(
    book.sheets.map((s) => ({
      name: s.name,
      rows: s.rows.map((r) => {
        const text = r.map((c) => c.text);
        while (text.length && !text.at(-1)) text.pop();
        return text;
      }),
    })),
  );
  const binding = Object.values(synthetic).find((s) =>
    Object.values(s.assets).some((a) => a.sha256 === book.sha256 && a.view_sha256 === view),
  );
  const reference: V020Reference[] = binding ? binding.scope_reference : [];
  const records: V020Record[] = [];
  const sourceRows = new Map<string, V020Package["source_rows"][number]>();
  for (const p of plans) {
    const sheet = book.sheets[p.sheet];
    for (let i = p.header + 1; i < sheet.rows.length; i++) {
      const row = sheet.rows[i];
      if (row.every((c) => !c.text.trim())) continue;
      const rowid = `${book.sha256}:${p.sheet}:${i + 1}`;
      sourceRows.set(rowid, {
        id: rowid,
        sheet: sheet.name,
        sheet_index: p.sheet,
        row_number: i + 1,
        headers: sheet.rows[p.header].map((c) => c.text),
        cells: structuredClone(row),
      });
      if (p.layout === "LONG") records.push(createRecord(book, p, i, null, null, reference));
      else if (p.kind === "AREA") {
        const mapped = (
          [
            ["PLANTED", "planted_area"],
            ["PRODUCTIVE", "productive_area"],
            ["EFFECTIVE", "effective_area"],
          ] as const
        ).filter(([, k]) => p.columns[k] != null);
        for (const [basis] of mapped.length ? mapped : ([["UNKNOWN", "planted_area"]] as const))
          records.push(createRecord(book, p, i, null, basis, reference));
      } else if (p.slots.length)
        for (const slot of p.slots) records.push(createRecord(book, p, i, slot, null, reference));
      else records.push(createRecord(book, p, i, null, null, reference));
    }
  }
  crossChecks(records, plans);
  const summary: V020Package["summary"] = {
    record_count: records.length,
    source_row_count: sourceRows.size,
    kind_counts: { AREA: 0, EVENT: 0, PHENOLOGY: 0 },
    state_counts: {
      VALID_STRUCTURE: 0,
      PARTIAL: 0,
      CONFLICT: 0,
      UNMAPPED: 0,
      SOURCE_AUTHORITY_NOT_PROVEN: 0,
      PIT_NOT_PROVEN: 0,
    },
    season_counts: Object.create(null) as Record<string, number>,
    issue_counts: {},
    base_count: 0,
    variety_count: 0,
    structurally_complete_count: 0,
    research_admitted_count: 0,
  };
  for (const r of records) {
    r.states = ["SOURCE_AUTHORITY_NOT_PROVEN", "PIT_NOT_PROVEN"];
    if (
      !r.scope.resolved ||
      !r.scope.plot_authority_id ||
      r.issues.some((i) => i.code.includes("UNMAPPED") || i.code === "FORCING_METHOD_UNRESOLVED")
    )
      r.states.push("UNMAPPED");
    const errors = r.issues.some((i) => i.severity === "ERROR"),
      warnings = r.issues.some((i) => i.severity === "WARNING");
    r.states.push(errors ? "CONFLICT" : warnings ? "PARTIAL" : "VALID_STRUCTURE");
    r.issues.sort((a, b) => compareText(a.code, b.code) || compareText(a.field, b.field));
    summary.kind_counts[r.kind]++;
    summary.season_counts[r.scope.season || "UNKNOWN"] =
      (summary.season_counts[r.scope.season || "UNKNOWN"] ?? 0) + 1;
    for (const s of r.states) summary.state_counts[s]++;
    for (const i of r.issues)
      summary.issue_counts[i.code] = (summary.issue_counts[i.code] ?? 0) + 1;
    if (!errors && !warnings) summary.structurally_complete_count++;
  }
  summary.base_count = new Set(records.map((r) => r.scope.base).filter(Boolean)).size;
  summary.variety_count = new Set(records.map((r) => r.scope.variety).filter(Boolean)).size;
  const data: V020Package = {
    schema_version: "V0_20_AGRONOMIC_PREPARATION_R1",
    version: "0.20.0",
    data_class: binding ? "SYNTHETIC_TEST_FIXTURE" : "USER_FILE_PREVIEW_UNVERIFIED",
    source_file_sha256: book.sha256,
    mapping_sha256: await hash(plans),
    vocabulary_sha256: await hash(vocabulary),
    upstream: vocabulary,
    plans,
    source_rows: [...sourceRows.values()],
    records,
    summary,
    restrictions: {
      source_authority_proven: false,
      strict_pit_validated: false,
      model_use_authorized: false,
      prediction_adjustment_authorized: false,
      production_database_writes: false,
      real_data_verified: false,
      formal_version_complete: false,
    },
  };
  const preparation_sha256 = await hash(data);
  const package_id = "V0_20-" + preparation_sha256;
  const html = renderV020(data, package_id);
  const other = [
    { name: "agronomic-area.csv", content: csvV020(data, "AREA", package_id) },
    { name: "agronomic-events.csv", content: csvV020(data, "EVENT", package_id) },
    { name: "agronomic-phenology.csv", content: csvV020(data, "PHENOLOGY", package_id) },
    { name: "agronomic-quality-report.html", content: html },
  ];
  const files = [];
  for (const f of other)
    files.push({ ...f, sha256: await sha256(new TextEncoder().encode(f.content).buffer) });
  const manifest = {
    ...data,
    package_id,
    preparation_sha256,
    artifact_sha256: Object.fromEntries(files.map((f) => [f.name, f.sha256])),
  };
  const content = JSON.stringify(manifest, null, 2) + "\n";
  files.unshift({
    name: "agronomic-preparation.json",
    content,
    sha256: await sha256(new TextEncoder().encode(content).buffer),
  });
  let size = 0;
  for (const f of files) size += new TextEncoder().encode(f.content).byteLength;
  if (size > V0_20_LIMITS.exportBytes) throw Error("V0_20_PACKAGE_SIZE_LIMIT");
  const zip_bytes = zipSync(
    Object.fromEntries(files.map((f) => [package_id + "/" + f.name, strToU8(f.content)])),
    { level: 6, mtime: new Date(2000, 0, 1) },
  );
  return { package_id, preparation_sha256, data, files, html, zip_bytes };
}
