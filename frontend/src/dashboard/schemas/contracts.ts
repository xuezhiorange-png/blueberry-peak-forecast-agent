import { z } from "zod";

export const hash = z.string().regex(/^[0-9a-f]{64}$/);
const id = z
  .string()
  .min(1)
  .max(200)
  .refine((v) => v.trim().length > 0);
const date = z.iso.date();
export const quantity = z
  .string()
  .max(64)
  .regex(/^[0-9]+(?:\.[0-9]+)?$/);
// Output allows Decimal scientific notation. Never coerce into a JS number.
const decimal = z.string().regex(/^-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?$/);
const nullableDecimal = decimal.nullable();
export const levels = ["COMPANY", "REGION", "BASE"] as const;
export const planningLevels = [
  "POINT",
  "UPPER_PLANNING_BOUND_80",
  "UPPER_PLANNING_BOUND_90",
] as const;
export const statuses = [
  "LOADING",
  "READY",
  "EMPTY",
  "PARTIAL",
  "NOT_AVAILABLE",
  "ERROR",
  "AUTHORITY_MISMATCH",
  "NO_CURRENT_ACTUAL",
] as const;
export type Status = (typeof statuses)[number];
export const forecastIdentity = z.strictObject({
  source_kind: z.enum(["OPERATIONAL_PEAK", "HIERARCHICAL"]),
  forecast_family: id,
  // Number-safe run IDs only; reject rather than round a 64-bit database identity.
  run_id: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  hierarchy_level: z.enum(levels),
  entity_id: id,
  target_season: z.string().regex(/^\d{4}-\d{4}$/),
  origin_date: date,
  baseline_id: id,
  policy_version: id,
});
export const forecastQuery = forecastIdentity.extend({ expected_source_result_hash: hash });
export type ForecastIdentity = z.infer<typeof forecastIdentity>;
export type ForecastReadQuery = z.infer<typeof forecastQuery>;
const hierarchyIdentity = z.strictObject({
  hierarchy_level: z.enum(levels),
  entity_id: z.string(),
  hierarchy_authority_hash: hash.nullable(),
});
const authorityIdentity = z.strictObject({
  authority_hash: hash,
  source_policy_version: z.string(),
  source_baseline_id: z.string(),
  source_evidence_hashes: z.record(z.string(), hash),
});
export const dailyRow = z.strictObject({
  forecast_run_id: z.number().int().positive().max(Number.MAX_SAFE_INTEGER),
  hierarchy_level: z.enum(levels),
  entity_id: z.string(),
  origin_date: date,
  target_date: date,
  lead_day: z.number().int().min(1).max(15),
  point_forecast_kg: decimal.refine((v) => !v.startsWith("-")),
  source_result_hash: hash,
  status: z.literal("READY"),
});
export type DailyRow = z.infer<typeof dailyRow>;
export const curveData = z.strictObject({
  daily_rows: z.array(dailyRow).max(15),
  data_completeness: z.string(),
  available_day_count: z.number().int().min(0).max(15),
});
export const hierarchyData = curveData.extend({
  reconciliation_method: z.literal("BOTTOM_UP_EXACT_SUM").nullable(),
  source_status: z.string(),
  child_expected_count: z.number().int().nullable(),
  child_included_count: z.number().int().nullable(),
  missing_child_count: z.number().int().nullable(),
});
export const overviewData = z.strictObject({
  forecast_7d_total_kg: nullableDecimal,
  forecast_15d_total_kg: nullableDecimal,
  peak_date: date.nullable(),
  peak_daily_quantity_kg: nullableDecimal,
  peak_scope: z.literal("SAVED_DAILY_CURVE_D1_THROUGH_AVAILABLE_D15"),
  forecast_origin: date,
  forecast_scope: hierarchyIdentity,
  forecast_run_identity: forecastIdentity,
  data_completeness: z.string(),
  forecast_7d_status: z.string(),
  forecast_15d_status: z.string(),
  high_load_dates: z.array(dailyRow).max(15),
  high_load_semantics: z.literal("DESCRIPTIVE_QUANTITY_DESC_DATE_ASC_NO_ALERT_THRESHOLD"),
});
export const coverage = z.strictObject({
  interval: z.enum(["PI80", "PI90", "UPPER80", "UPPER90"]),
  candidate_row_count: z.number().int(),
  computable_row_count: z.number().int(),
  not_computable_row_count: z.number().int(),
  covered_row_count: z.number().int(),
  empirical_coverage: decimal,
  nominal_coverage: decimal,
  observation: z.literal("UNDER_NOMINAL"),
});
export const horizonQuality = z.strictObject({
  horizon: z.enum(["H1", "H3", "H7", "H15"]),
  point_status: z.enum(["READY", "NOT_AVAILABLE"]),
  daily_row_count: z.number().int().nullable(),
  scorable_origin_count: z.number().int().nullable(),
  wape: nullableDecimal,
  mae_kg: nullableDecimal,
  bias_kg: nullableDecimal,
  cumulative_wape: nullableDecimal,
  interval_status: z.enum(["READY", "NOT_AVAILABLE"]),
  interval_coverage: z.array(coverage),
});
export const qualityData = z.strictObject({
  model_id: z.literal("V0_15_S5_M1_RIDGE"),
  source_split: z.literal("EXPOSED_OOT"),
  target_season: z.literal("2025-2026"),
  scope: z.literal("BASE_COHORT_AGGREGATE"),
  horizons: z.array(horizonQuality),
  strict_pit: z.literal(false),
  historical_actual_available_at_proven: z.literal(false),
  retrospective_authority_used: z.literal(true),
  current_season_actual_available: z.literal(false),
  current_actual_message: z.string(),
  production_accuracy_validated: z.literal(false),
  prospective_interval_coverage_validated: z.literal(false),
});
const readBase = z.strictObject({
  schema_version: z.literal("V0_17_FORECAST_INTELLIGENCE_READ_R1"),
  capability: z.enum([
    "GET_FORECAST_OVERVIEW",
    "GET_FORECAST_CURVE",
    "GET_HIERARCHICAL_FORECAST",
    "GET_FORECAST_UNCERTAINTY",
    "GET_FORECAST_ATTRIBUTION",
    "GET_FORECAST_QUALITY",
  ]),
  status: z.enum([
    "READY",
    "PARTIAL",
    "EMPTY",
    "NOT_AVAILABLE",
    "AUTHORITY_MISMATCH",
    "NO_CURRENT_ACTUAL",
    "ERROR",
  ]),
  forecast_identity: forecastIdentity.nullable(),
  hierarchy_identity: hierarchyIdentity.nullable(),
  authority_identity: authorityIdentity.nullable(),
  source_kind: z.string(),
  source_run_id: z.number().int().max(Number.MAX_SAFE_INTEGER).nullable(),
  source_rerun_of_run_id: z.number().int().max(Number.MAX_SAFE_INTEGER).nullable(),
  source_result_hash: hash.nullable(),
  policy_version: z.string(),
  projection_policy_version: z.literal("V0_17_FORECAST_INTELLIGENCE_READ_PROJECTION_R1"),
  evidence_mode: z.enum(["SAVED_FORECAST", "RETROSPECTIVE_OBSERVATION", "NO_CURRENT_ACTUAL"]),
  unavailable_reason: z.string().nullable(),
  point_forecast_is_proven_p50: z.literal(false),
  upper_planning_bound_is_quantile: z.literal(false),
  attribution_is_causal: z.literal(false),
  projection_hash: hash,
});
export function readResponse<T extends z.ZodType>(data: T) {
  return readBase.extend({ data: data.nullable() }).superRefine((raw, ctx) => {
    const v = raw as unknown as { status: string; data: unknown };
    if (
      ["NOT_AVAILABLE", "AUTHORITY_MISMATCH", "NO_CURRENT_ACTUAL", "ERROR"].includes(v.status) &&
      v.data !== null
    )
      ctx.addIssue({ code: "custom", message: "Unavailable data must be null" });
    if (["READY", "PARTIAL"].includes(v.status) && v.data === null)
      ctx.addIssue({ code: "custom", message: "Missing ready data" });
  });
}
export const readSchemas = {
  overview: readResponse(overviewData),
  curve: readResponse(curveData),
  hierarchy: readResponse(hierarchyData),
  uncertainty: readResponse(z.strictObject({})),
  attribution: readResponse(z.strictObject({})),
  quality: readResponse(qualityData),
};
export type CurveData = z.infer<typeof curveData>;
export type OverviewData = z.infer<typeof overviewData>;
export type HierarchyData = z.infer<typeof hierarchyData>;
export type QualityData = z.infer<typeof qualityData>;
export type ReadResponse<T> = z.infer<typeof readBase> & { data: T | null };

export const capacityInput = z.discriminatedUnion("capacity_mode", [
  z.strictObject({
    date,
    capacity_mode: z.literal("DIRECT"),
    daily_handling_capacity_kg: quantity,
    buffer_handling_capacity_kg: quantity.nullable().optional(),
  }),
  z.strictObject({
    date,
    capacity_mode: z.literal("WORKFORCE_DERIVED"),
    workforce_count: z.number().int().min(0).max(1000000),
    productivity_kg_per_person_day: quantity,
    buffer_handling_capacity_kg: quantity.nullable().optional(),
  }),
]);
export const scenarioInput = z
  .strictObject({
    scenario_id: id,
    scenario_version: id,
    capacity_rows: z.array(capacityInput).min(1).max(15),
  })
  .superRefine((v, c) => {
    if (new Set(v.capacity_rows.map((r) => r.date)).size !== v.capacity_rows.length)
      c.addIssue({ code: "custom", message: "Duplicate dates" });
  });
export const costSelection = z.strictObject({
  cost_contract_id: id,
  expected_cost_contract_hash: hash,
});
export const decisionSelection = costSelection.extend({
  forecast_selection: forecastIdentity,
  expected_source_result_hash: hash,
  planning_level: z.enum(planningLevels),
});
export const simulationRequest = decisionSelection
  .extend(scenarioInput.shape)
  .superRefine((v, c) => {
    if (new Set(v.capacity_rows.map((r) => r.date)).size !== v.capacity_rows.length)
      c.addIssue({ code: "custom", message: "Duplicate dates" });
  });
export const comparisonRequest = decisionSelection
  .extend({ scenarios: z.array(scenarioInput).min(2).max(20) })
  .superRefine((v, c) => {
    if (new Set(v.scenarios.map((s) => s.scenario_id)).size !== v.scenarios.length)
      c.addIssue({ code: "custom", message: "Duplicate scenarios" });
  });
export type ScenarioInput = z.infer<typeof scenarioInput>;
export type SimulationRequest = z.infer<typeof simulationRequest>;
export type ComparisonRequest = z.infer<typeof comparisonRequest>;
// Explicit fields keep TS inference precise as well as runtime validation.
const utilization = z.strictObject({
  capacity_utilization_numerator_kg: decimal,
  capacity_utilization_denominator_kg: decimal,
  capacity_utilization_decimal: nullableDecimal,
  capacity_utilization_precision: z.literal(50),
  capacity_utilization_rounding_mode: z.literal("ROUND_HALF_EVEN"),
  capacity_utilization_rounding_applied: z.boolean(),
  capacity_utilization_status: z.enum(["COMPUTABLE", "NOT_COMPUTABLE_ZERO_CAPACITY"]),
});
const dailySimulation = utilization.extend({
  date,
  capacity_mode: z.enum(["DIRECT", "WORKFORCE_DERIVED"]),
  workforce_count: z.number().int().nullable(),
  productivity_kg_per_person_day: nullableDecimal,
  buffer_supplied: z.boolean(),
  buffer_handling_capacity_kg: decimal,
  daily_handling_capacity_kg: decimal,
  planning_level: z.enum(planningLevels),
  planning_demand_kg: decimal,
  effective_capacity_kg: decimal,
  opening_backlog_kg: decimal,
  workload_kg: decimal,
  processed_kg: decimal,
  closing_backlog_kg: decimal,
  daily_overload_kg: decimal,
  daily_over_capacity_kg: decimal,
  under_capacity_kg: decimal,
  over_capacity_kg: decimal,
  under_capacity_loss: decimal,
  over_capacity_loss: decimal,
  scenario_business_loss: decimal,
  row_hash: hash,
});
export const simulationResult = z.strictObject({
  saved_forecast_hash: hash,
  forecast_curve_hash: hash,
  forecast_source_hash: hash,
  forecast_origin: z.string(),
  hierarchy_level: z.enum(levels),
  hierarchy_entity_id: z.string(),
  hierarchy_authority_hash: hash,
  planning_level: z.enum(planningLevels),
  cost_contract_hash: hash,
  loss_unit: z.literal("SYNTHETIC_LOSS_UNIT"),
  dates: z.array(date).max(15),
  initial_backlog_kg: z.literal("0"),
  backlog_policy_version: z.string(),
  scenario_id: z.string(),
  scenario_hash: hash,
  scenario_status: z.literal("COMPLETE"),
  loss_semantics: z.literal("ASYMMETRIC_PLANNING_GAP_LOSS"),
  decision_evidence_class: z.literal("SYNTHETIC_DECISION_LOSS"),
  forecast_start_date: date,
  forecast_end_date: date,
  day_count: z.number().int().min(1).max(15),
  overload_dates: z.array(date),
  backlog_dates: z.array(date),
  overload_day_count: z.number().int(),
  backlog_day_count: z.number().int(),
  cumulative_shortfall_kg: decimal,
  max_backlog_kg: decimal,
  ending_backlog_kg: decimal,
  total_planning_demand_kg: decimal,
  total_base_handling_capacity_kg: decimal,
  total_buffer_capacity_kg: decimal,
  total_effective_capacity_kg: decimal,
  total_processed_kg: decimal,
  under_capacity_kg: decimal,
  over_capacity_kg: decimal,
  under_capacity_loss: decimal,
  over_capacity_loss: decimal,
  total_business_loss: decimal,
  daily_rows: z.array(dailySimulation).min(1).max(15),
  aggregate_capacity_utilization_numerator_kg: decimal,
  aggregate_capacity_utilization_denominator_kg: decimal,
  aggregate_capacity_utilization_decimal: nullableDecimal,
  aggregate_capacity_utilization_precision: z.literal(50),
  aggregate_capacity_utilization_rounding_mode: z.literal("ROUND_HALF_EVEN"),
  aggregate_capacity_utilization_rounding_applied: z.boolean(),
  aggregate_capacity_utilization_status: z.enum(["COMPUTABLE", "NOT_COMPUTABLE_ZERO_CAPACITY"]),
  result_hash: hash,
});
export const comparisonData = z.strictObject({
  comparison: z.strictObject({
    scenario_comparison_status: z.literal("COMPARABLE"),
    comparison_authority_hash: hash,
    ranking_semantics: z.literal("DESCRIPTIVE_ORDER_UNDER_GIVEN_INPUTS_AND_COST_CONTRACT"),
    rankings: z
      .array(
        z.strictObject({
          scenario_id: z.string(),
          scenario_hash: hash,
          result_hash: hash,
          scenario_rank: z.number().int().positive(),
        }),
      )
      .max(20),
    comparison_hash: hash,
  }),
  scenario_results: z.array(simulationResult).max(20),
});
export const businessLoss = z.strictObject({
  cost_contract: z.strictObject({
    contract_id: z.string(),
    policy_version: z.string(),
    contract_version: z.string(),
    authority_type: z.literal("EXPLICIT_SYNTHETIC_SCENARIO"),
    authority_reference: z.string(),
    c_under_per_kg: decimal,
    c_over_per_kg: decimal,
    loss_unit: z.literal("SYNTHETIC_LOSS_UNIT"),
    synthetic: z.literal(true),
    canonical_company_cost: z.literal(false),
    contract_hash: hash,
  }),
  formula: z.string(),
  s5_semantics: z.literal("ACTUAL_VS_FORECAST_LOSS"),
  simulation_semantics: z.literal("ASYMMETRIC_PLANNING_GAP_LOSS"),
  total_business_loss: z.null(),
  loss_amount_status: z.literal("NOT_COMPUTED_NO_SCENARIO"),
});
const decisionBase = z.strictObject({
  schema_version: z.literal("V0_17_S2_DECISION_SUPPORT_API_R1"),
  capability: z.enum(["BUSINESS_LOSS_EXPOSURE", "SIMULATE_CAPACITY", "COMPARE_CAPACITY_SCENARIOS"]),
  status: z.enum(["READY", "PARTIAL", "NOT_AVAILABLE"]),
  forecast_identity: forecastIdentity.nullable(),
  hierarchy_identity: hierarchyIdentity.nullable(),
  authority_identity: authorityIdentity.nullable(),
  source_result_hash: hash.nullable(),
  source_rerun_of_run_id: z.number().int().max(Number.MAX_SAFE_INTEGER).nullable(),
  source_read_projection_hash: hash.nullable(),
  adapter_policy_version: z.literal("V0_17_S2_SAVED_FORECAST_DECISION_ADAPTER_R1"),
  adapter_authority_hash: hash.nullable(),
  adapter_authority_kind: z.string().nullable(),
  adapter_authority_binding: z
    .record(z.string(), z.union([z.string(), z.number().int().max(Number.MAX_SAFE_INTEGER)]))
    .nullable(),
  adapter_saved_forecast_hash: hash.nullable(),
  origin_date: date.nullable(),
  origin_anchor: z.string().nullable(),
  origin_anchor_policy: z.literal("V0_17_S2_SHANGHAI_DATE_ANCHOR_R1"),
  date_anchor_not_issuance_timestamp: z.literal(true),
  data_completeness: z.string().nullable(),
  available_day_count: z.number().int().nullable(),
  planning_level: z.enum(planningLevels).nullable(),
  cost_contract_id: z.string(),
  cost_contract_hash: hash,
  loss_unit: z.literal("SYNTHETIC_LOSS_UNIT"),
  synthetic: z.literal(true),
  canonical_company_cost: z.literal(false),
  real_roi_validated: z.literal(false),
  point_forecast_is_proven_p50: z.literal(false),
  upper_planning_bound_is_quantile: z.literal(false),
  fine_grained_entity_authorization_established: z.literal(false),
  engine_policy_versions: z.record(z.string(), z.string()),
  engine_result_hash: hash.nullable(),
  unavailable_reason: z.string().nullable(),
  projection_hash: hash,
});
export function decisionResponse<T extends z.ZodType>(data: T) {
  return decisionBase.extend({ data: data.nullable() }).superRefine((raw, c) => {
    const v = raw as unknown as { status: string; data: unknown };
    if ((v.status === "NOT_AVAILABLE") !== (v.data === null))
      c.addIssue({ code: "custom", message: "Decision status/data mismatch" });
  });
}
export const decisionSchemas = {
  "business-loss": decisionResponse(businessLoss),
  "simulate-capacity": decisionResponse(simulationResult),
  "compare-capacity-scenarios": decisionResponse(comparisonData),
};
export type SimulationResult = z.infer<typeof simulationResult>;
export type ComparisonData = z.infer<typeof comparisonData>;
export type DecisionResponse<T> = z.infer<typeof decisionBase> & { data: T | null };
