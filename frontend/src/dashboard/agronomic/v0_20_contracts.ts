import type { BookSummary } from "../spreadsheet/contracts";

export const V0_20_VERSION = "0.20.0";
export const V0_20_LIMITS = {
  records: 20000,
  exportBytes: 16 * 1024 * 1024,
  versions: 5,
  reportRows: 200,
} as const;
export type V020Kind = "AREA" | "EVENT" | "PHENOLOGY";
export type V020State = "PLANNED" | "OBSERVED" | "UNKNOWN";
export type V020PreparationState =
  | "VALID_STRUCTURE"
  | "PARTIAL"
  | "CONFLICT"
  | "UNMAPPED"
  | "SOURCE_AUTHORITY_NOT_PROVEN"
  | "PIT_NOT_PROVEN";
export const V0_20_FIELDS = [
  ["base", "基地来源编码"],
  ["farm", "农场来源编码"],
  ["subfarm", "分场来源编码"],
  ["plot", "原始地块标识"],
  ["variety", "品种来源编码"],
  ["season", "产季"],
  ["production_system", "栽培制度"],
  ["status", "计划 / 实际状态"],
  ["source_reference", "来源证明引用"],
  ["source_version", "来源版本"],
  ["recorded_at", "来源记录时间"],
  ["known_at", "可见时间"],
  ["logical_id", "记录 / 逻辑 ID"],
  ["revision_id", "修订 ID"],
  ["supersedes_revision", "前版修订 ID"],
  ["planted_area", "种植面积"],
  ["productive_area", "投产面积"],
  ["effective_area", "有效面积"],
  ["area_basis", "长表面积口径"],
  ["area_value", "长表面积数值"],
  ["area_unit", "面积单位"],
  ["effective_from", "面积生效开始"],
  ["effective_to", "面积生效结束"],
  ["tree_age_years", "声明树龄（年）"],
  ["planting_year", "种植年份"],
  ["event_type", "长表事件类型"],
  ["date", "长表业务日期"],
  ["end_date", "事件结束日期"],
  ["pruning_type", "剪枝类型"],
  ["operation_count", "声明操作次数"],
  ["intensity_mode", "强度表达方式"],
  ["intensity_value", "强度原始数值 / 等级"],
  ["intensity_unit", "强度单位"],
  ["intensity_denominator", "强度分母"],
  ["stage", "长表物候阶段"],
  ["method", "操作 / 观测方法"],
  ["sample_scope", "样本范围"],
  ["quality_status", "声明质量状态"],
  ["observed_at", "实际观测日期 / 时间"],
] as const;
export type V020Field = (typeof V0_20_FIELDS)[number][0];
export type V020Mapping = Partial<Record<V020Field, number | null>>;
export type V020Slot = {
  id: string;
  column: number;
  declared_type: string;
  label: string;
  state: V020State;
};
export type V020SheetPlan = {
  sheet: number;
  header: number;
  kind: V020Kind;
  layout: "WIDE" | "LONG";
  columns: V020Mapping;
  slots: V020Slot[];
};
export type V020Reference = {
  base: string;
  farm: string;
  subfarm: string;
  plot: string;
  variety: string;
  base_id: string;
  farm_id: number;
  subfarm_id: number;
  variety_id: number;
};
export type V020Date = {
  raw: string;
  precision: "DAY" | "MONTH" | "YEAR" | "TIMESTAMP" | "LOCAL_DATETIME" | "UNKNOWN";
  lower_date: string | null;
  upper_date: string | null;
  instant: string | null;
};
export type V020Issue = {
  code: string;
  severity: "ERROR" | "WARNING" | "INFO";
  message: string;
  field: string;
};
export type V020Record = {
  record_id: string;
  kind: V020Kind;
  source_row_id: string;
  source_sheet: string;
  source_row: number;
  source_columns: V020Mapping;
  slot: V020Slot | null;
  scope: {
    base: string;
    farm: string;
    subfarm: string;
    plot: string;
    variety: string;
    season: string;
    production_system: string;
    resolved: V020Reference | null;
    plot_authority_id: null;
  };
  logical_id: string | null;
  revision_id: string | null;
  supersedes_revision: string | null;
  observed_or_planned: V020State;
  source_reference: string | null;
  source_version: string | null;
  recorded_at: V020Date;
  known_at: V020Date;
  business_date: V020Date;
  observed_at: V020Date;
  area: null | {
    basis: string;
    raw_value: string;
    value: string | null;
    unit: string;
    effective_from: V020Date;
    effective_to: V020Date;
    tree_age_years: string | null;
    planting_year: string | null;
  };
  event: null | {
    raw_type: string;
    canonical_type: string | null;
    pruning_type: string | null;
    method: string | null;
    operation_count: string | null;
    intensity_mode: string;
    intensity_value: string | null;
    intensity_unit: string | null;
    intensity_denominator: string | null;
    end_date: V020Date;
  };
  phenology: null | {
    raw_stage: string;
    canonical_stage: string | null;
    production_plan_field: string | null;
    method: string | null;
    sample_scope: string | null;
    quality_status: string | null;
  };
  issues: V020Issue[];
  states: V020PreparationState[];
};
export type V020Package = {
  schema_version: "V0_20_AGRONOMIC_PREPARATION_R1";
  version: "0.20.0";
  data_class: "SYNTHETIC_TEST_FIXTURE" | "USER_FILE_PREVIEW_UNVERIFIED";
  source_file_sha256: string;
  mapping_sha256: string;
  vocabulary_sha256: string;
  upstream: unknown;
  plans: V020SheetPlan[];
  source_rows: {
    id: string;
    sheet: string;
    sheet_index: number;
    row_number: number;
    headers: string[];
    cells: { text: string; kind: string; temporal_source?: string }[];
  }[];
  records: V020Record[];
  summary: {
    record_count: number;
    source_row_count: number;
    kind_counts: Record<V020Kind, number>;
    state_counts: Record<V020PreparationState, number>;
    season_counts: Record<string, number>;
    issue_counts: Record<string, number>;
    base_count: number;
    variety_count: number;
    structurally_complete_count: number;
    research_admitted_count: 0;
  };
  restrictions: {
    source_authority_proven: false;
    strict_pit_validated: false;
    model_use_authorized: false;
    prediction_adjustment_authorized: false;
    production_database_writes: false;
    real_data_verified: false;
    formal_version_complete: false;
  };
};
export type V020Prepared = {
  package_id: string;
  preparation_sha256: string;
  data: V020Package;
  files: { name: string; sha256: string; content: string }[];
  html: string;
  zip_bytes: Uint8Array;
};
export type V020WorkerRequest = { type: "v0_20_prepare"; id: number; plans: V020SheetPlan[] };
export type V020WorkerReply = { type: "v0_20_prepared"; id: number; prepared: V020Prepared };
export type V020Book = BookSummary;
