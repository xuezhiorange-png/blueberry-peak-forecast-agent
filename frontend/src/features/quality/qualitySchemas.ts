import { z } from "zod";
import {
  dateSchema,
  decimalSchema,
  nonNegativeDecimalSchema,
  sha256Schema,
  timestampSchema,
} from "../forecast/forecastSchemas";

const decimalOrNull = decimalSchema.nullable();
const nonNegativeDecimalOrNull = nonNegativeDecimalSchema.nullable();
const nonNegativeInt = z.number().int().nonnegative();
const status = z.string().min(1);
const reasonCodes = z.array(z.string()).readonly();

const qualityEvidenceIdentitySchema = z
  .object({
    forecast_run_id: sha256Schema,
    actual_harvest_import_id: z.string().min(1),
    actual_label_snapshot_identity: sha256Schema,
    s2_run_identity: sha256Schema,
    s2_manifest_identity: sha256Schema,
    s2_binding_row_set_hash: sha256Schema,
    evaluation_request_hash: sha256Schema,
    evaluation_instance_hash: sha256Schema,
    quality_manifest_hash: sha256Schema,
    metric_result_set_hash: sha256Schema,
    breakdown_result_set_hash: sha256Schema,
    baseline_result_set_hash: sha256Schema,
    comparison_result_set_hash: sha256Schema,
    metric_policy_version: z.string().min(1),
    baseline_policy_version: z.string().min(1),
    comparison_policy_version_or_null: z.string().min(1).nullable(),
    model_identity: z.string().min(1),
  })
  .strict();

const dailyOverlayRowSchema = z
  .object({
    business_date: dateSchema,
    forecast_p50_kg_or_null: nonNegativeDecimalOrNull,
    forecast_p80_kg_or_null: nonNegativeDecimalOrNull,
    forecast_p90_kg_or_null: nonNegativeDecimalOrNull,
    actual_quantity_kg_or_null: nonNegativeDecimalOrNull,
    actual_available: z.boolean(),
    coverage_state: z.enum(["AVAILABLE", "EXCLUDED", "NOT_COMPUTABLE"]),
    exclusion_reason_codes: reasonCodes,
  })
  .strict();

const metricSchema = z
  .object({
    metric_name: z.string().min(1),
    metric_status: status,
    metric_value_or_null: decimalOrNull,
    numerator_or_null: decimalOrNull,
    denominator_or_null: decimalOrNull,
    reason_codes: reasonCodes,
  })
  .strict();

const peakMetricSchema = z
  .object({
    metric_status: status,
    metric_value_or_null: decimalOrNull,
    business_date_or_null: dateSchema.nullable(),
    window_start_date_or_null: dateSchema.nullable(),
    window_end_date_or_null: dateSchema.nullable(),
    reason_codes: reasonCodes,
    quantile: z.enum(["P50", "P80", "P90"]),
    forecast_horizon_days: z.union([z.literal(7), z.literal(14), z.literal(21)]),
  })
  .strict();

const coverageMetricSchema = z
  .object({
    quantile: z.enum(["P80", "P90"]),
    metric_status: status,
    covered_count_or_null: nonNegativeInt.nullable(),
    total_count: nonNegativeInt,
    coverage_ratio_or_null: nonNegativeDecimalOrNull,
    reason_codes: reasonCodes,
    forecast_horizon_days: z.union([z.literal(7), z.literal(14), z.literal(21)]),
  })
  .strict();

const intervalMetricSchema = z
  .object({
    metric_status: status,
    lower_bound_available: z.boolean(),
    lower_bound_value_or_null: decimalOrNull,
    upper_bound_value_or_null: decimalOrNull,
    metric_value_or_null: decimalOrNull,
    reason_codes: reasonCodes,
    quantile: z.enum(["P80", "P90"]),
    forecast_horizon_days: z.union([z.literal(7), z.literal(14), z.literal(21)]),
  })
  .strict();

const breakdownIdentitySchema = z
  .object({
    forecast_horizon_days: z.union([z.literal(7), z.literal(14), z.literal(21)]),
    farm_business_key: z.string(),
    subfarm_business_key: z.string(),
    variety_business_key: z.string(),
    season_business_key: z.string(),
    model_identity: z.string().min(1),
  })
  .strict();

const metricValuesSchema = z
  .object({
    daily_mae: decimalOrNull,
    daily_wape: decimalOrNull,
    daily_smape: decimalOrNull,
    daily_mape: decimalOrNull,
    daily_bias_kg: decimalOrNull,
    daily_relative_bias: decimalOrNull,
    daily_absolute_error_sum_kg: decimalOrNull,
  })
  .strict();

const rowCountsSchema = z
  .object({
    total: nonNegativeInt,
    comparable: nonNegativeInt,
    covered: nonNegativeInt,
    excluded: nonNegativeInt,
    not_computable: nonNegativeInt,
  })
  .strict();

const breakdownSchema = z
  .object({
    breakdown_identity: breakdownIdentitySchema,
    metric_status: status,
    coverage_ratio_or_null: nonNegativeDecimalOrNull,
    comparable_row_count: nonNegativeInt,
    excluded_row_count: nonNegativeInt,
    not_computable_row_count: nonNegativeInt,
    metric_values: metricValuesSchema,
    reason_codes: reasonCodes,
  })
  .strict();

const baselineResultSchema = z
  .object({
    baseline_quantile: z.string().min(1),
    metric_status: status,
    baseline_value_kg_or_null: nonNegativeDecimalOrNull,
    comparison_availability: status,
    analog_date_or_null: dateSchema.nullable(),
    reason_codes: reasonCodes,
  })
  .strict();

const horizonSchema = z
  .object({
    horizon_days: z.union([z.literal(7), z.literal(14), z.literal(21)]),
    daily_overlay: z.array(dailyOverlayRowSchema).readonly(),
    daily_metrics: z.array(metricSchema).readonly(),
    cumulative_metric: metricSchema,
    single_day_peak: peakMetricSchema,
    sustained_seven_day_peak: peakMetricSchema,
    p80_coverage: coverageMetricSchema,
    p90_coverage: coverageMetricSchema,
    interval_metric: intervalMetricSchema,
    coverage_counts: rowCountsSchema,
    excluded_row_counts: rowCountsSchema,
    reason_codes: reasonCodes,
    single_day_peaks: z.array(peakMetricSchema).readonly(),
    sustained_seven_day_peaks: z.array(peakMetricSchema).readonly(),
    interval_metrics: z.array(intervalMetricSchema).readonly(),
  })
  .strict();

const comparisonDeltaSchema = z
  .object({
    comparison_name: z.string().min(1),
    comparison_availability: status,
    metric_status: status,
    model_value_or_null: decimalOrNull,
    baseline_value_or_null: decimalOrNull,
    delta_value_or_null: decimalOrNull,
    forecast_horizon_days: z.number().int().nonnegative(),
    common_comparable_row_count: nonNegativeInt,
    model_only_row_count: nonNegativeInt,
    baseline_only_row_count: nonNegativeInt,
    excluded_row_count: nonNegativeInt,
    not_computable_row_count: nonNegativeInt,
    reason_codes: reasonCodes,
    baseline_member_set_hash: sha256Schema,
    comparison_key_hash: sha256Schema,
    canonical_hash: sha256Schema,
  })
  .strict();

export const qualityReportSchema = z
  .object({
    report_id: sha256Schema,
    forecast_identity: qualityEvidenceIdentitySchema,
    actual_label_snapshot_identity: sha256Schema,
    forecast_cutoff_at: timestampSchema,
    label_observation_cutoff_at: timestampSchema,
    requested_horizons_days: z
      .array(z.union([z.literal(7), z.literal(14), z.literal(21)]))
      .refine((value) => value.length === 3 && value.join(",") === "7,14,21"),
    horizons: z.array(horizonSchema).readonly(),
    daily_metrics: z.array(metricSchema).readonly(),
    cumulative_error: metricSchema,
    single_day_peak: peakMetricSchema,
    sustained_seven_day_peak: peakMetricSchema,
    p80_coverage: coverageMetricSchema,
    p90_coverage: coverageMetricSchema,
    interval_metric: intervalMetricSchema,
    breakdowns: z.array(breakdownSchema).readonly(),
    naive_baseline_results: z.array(baselineResultSchema).readonly(),
    computability_status: status,
    reason_codes: reasonCodes,
    coverage_counts: rowCountsSchema,
    excluded_row_counts: rowCountsSchema,
  })
  .strict();

export const qualityComparisonSchema = z
  .object({
    report_id: sha256Schema,
    comparison_availability: status,
    comparison_status: status,
    comparison_policy_version: z.string().min(1),
    model_baseline_deltas: z.array(comparisonDeltaSchema).readonly(),
    reason_codes: reasonCodes,
    comparison_public_hash: sha256Schema,
  })
  .strict();

export type QualityReport = z.infer<typeof qualityReportSchema>;
export type QualityComparison = z.infer<typeof qualityComparisonSchema>;
export type QualityOverlayRow = z.infer<typeof dailyOverlayRowSchema>;
export type QualityHorizon = z.infer<typeof horizonSchema>;
export type QualityImportReportRequest = {
  forecast_run_id: string;
  actual_harvest_import_id: string;
  forecast_cutoff_at: string;
  label_observation_cutoff_at: string;
  requested_horizons_days: [7, 14, 21];
  request_idempotency_key: string;
};
