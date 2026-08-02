import { z } from "zod";

const SHA256 = /^[0-9a-f]{64}$/;
const DECIMAL = /^-?(?:0|[1-9]\d*)(?:\.\d{1,6})?$/;
const NON_NEGATIVE_DECIMAL = /^(?:0|[1-9]\d*)(?:\.\d{1,6})?$/;
const DATE = /^\d{4}-\d{2}-\d{2}$/;
const RFC3339 = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/;

export const sha256Schema = z.string().regex(SHA256);
export const decimalSchema = z.string().regex(DECIMAL);
export const nonNegativeDecimalSchema = z.string().regex(NON_NEGATIVE_DECIMAL);
export const dateSchema = z.string().regex(DATE);
export const timestampSchema = z.string().regex(RFC3339);

const optionalText = z.string().min(1).nullable();

const forecastScopeSchema = z
  .object({
    farm_business_key: z.string().min(1),
    subfarm_business_key_or_null: optionalText,
    season_business_key: z.string().min(1),
    variety_business_key: z.string().min(1),
    destination_factory_business_key: z.string().min(1),
  })
  .strict();

const forecastDailyRowSchema = z
  .object({
    target_date: dateSchema,
    p50_value_kg: nonNegativeDecimalSchema.nullable(),
    p80_value_kg: nonNegativeDecimalSchema.nullable(),
    p90_value_kg: nonNegativeDecimalSchema.nullable(),
    row_status: z.string().min(1),
    reason_codes: z.array(z.string()).readonly(),
  })
  .strict();

export const forecastInputAuthorityItemSchema = z
  .object({
    farm_business_key: z.string().min(1),
    subfarm_business_key_or_null: optionalText,
    season_business_key: z.string().min(1),
    variety_business_key: z.string().min(1),
    destination_factory_business_key: z.string().min(1),
    plan_version: z.string().min(1),
    plan_row_hash: sha256Schema,
    planting_area_mu: nonNegativeDecimalSchema,
  })
  .strict();

export const forecastInputAuthoritySchema = z
  .object({
    forecast_input_authority_hash: sha256Schema,
    authority_available_at: timestampSchema,
    items: z.array(forecastInputAuthorityItemSchema).readonly(),
    authority_version: z.string().min(1),
  })
  .strict();

export const singleDayPeakSchema = z
  .object({
    date: dateSchema,
    quantity_kg: nonNegativeDecimalSchema,
    tie_break: z.literal("EARLIEST_DATE"),
  })
  .strict();

export const sustainedSevenDayPeakSchema = z
  .object({
    start_date: dateSchema,
    end_date: dateSchema,
    cumulative_quantity_kg: nonNegativeDecimalSchema,
    daily_average_kg_per_day: nonNegativeDecimalSchema,
    window_days: z.literal(7),
    metric: z.literal("ROLLING_CUMULATIVE"),
    date_continuity: z.literal("STRICT_CALENDAR_DAYS"),
    tie_break: z.literal("EARLIEST_START_DATE"),
  })
  .strict();

export const inventorySummarySchema = z
  .object({
    opening_quantity_kg: nonNegativeDecimalSchema,
    closing_quantity_kg: nonNegativeDecimalSchema,
  })
  .strict();

export const backlogSummarySchema = z.object({ quantity_kg: nonNegativeDecimalSchema }).strict();

export const policyVersionsSchema = z.object({ forecast: z.string().min(1) }).strict();

export const forecastSummarySchema = z
  .object({
    run_id: sha256Schema,
    status: z.string().min(1),
    daily_p50_series: z.array(forecastDailyRowSchema).readonly(),
    daily_p80_series: z.array(forecastDailyRowSchema).readonly(),
    daily_p90_series: z.array(forecastDailyRowSchema).readonly(),
    single_day_peak: singleDayPeakSchema,
    sustained_seven_day_peak: sustainedSevenDayPeakSchema,
    season_cumulative_quantity: nonNegativeDecimalSchema.nullable(),
    mature_inventory_summary: inventorySummarySchema,
    backlog_summary: backlogSummarySchema,
    data_gap_summaries: z.array(z.string()).readonly(),
    blocker_summaries: z.array(z.string()).readonly(),
    model_version: z.string().min(1),
    parameter_version: z.string().min(1),
    policy_versions: policyVersionsSchema,
    canonical_public_hash: sha256Schema,
    forecast_scope: forecastScopeSchema.nullable(),
    forecast_start_date: dateSchema.nullable(),
    forecast_end_date: dateSchema.nullable(),
    forecast_cutoff_at: timestampSchema.nullable(),
    forecast_input_authority_hash: sha256Schema.nullable(),
    plan_row_hash: sha256Schema.nullable(),
    planting_area_mu: nonNegativeDecimalSchema.nullable(),
    policy_identity: z.string().min(1).nullable(),
    policy_hash: sha256Schema.nullable(),
    model_identity: z.string().min(1).nullable(),
    parameter_identity: z.string().min(1).nullable(),
    code_authority_identity: z.string().min(1).nullable(),
    task8_identity: z.string().min(1).nullable(),
    task9_identity: z.string().min(1).nullable(),
    result_hash: sha256Schema.nullable(),
    curve_hash: sha256Schema.nullable(),
    metrics_hash: sha256Schema.nullable(),
  })
  .strict();

export const forecastDailyCurveSchema = z
  .object({
    run_id: sha256Schema,
    forecast_cutoff_at: timestampSchema,
    rows: z.array(forecastDailyRowSchema).readonly(),
    forecast_start_date: dateSchema.nullable(),
    forecast_end_date: dateSchema.nullable(),
    forecast_scope: forecastScopeSchema.nullable(),
  })
  .strict();

export type ForecastInputAuthority = z.infer<typeof forecastInputAuthoritySchema>;
export type ForecastInputAuthorityItem = z.infer<typeof forecastInputAuthorityItemSchema>;
export type ForecastSummary = z.infer<typeof forecastSummarySchema>;
export type ForecastDailyCurve = z.infer<typeof forecastDailyCurveSchema>;
export type ForecastDailyRow = z.infer<typeof forecastDailyRowSchema>;
export type TrialForecastRequest = {
  farm_business_key: string;
  subfarm_business_key_or_null: string | null;
  variety_business_key: string;
  season_business_key: string;
  destination_factory_business_key: string;
  forecast_cutoff_at: string;
  forecast_input_authority_hash: string;
  plan_row_hash: string;
  planting_area_mu: string;
  flowering_date_or_null: string | null;
  maturity_stage_or_null: string | null;
  already_picked_quantity_kg_or_null: string | null;
};
