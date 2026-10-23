import { z } from "zod";

const hash = z.string().regex(/^[0-9a-f]{64}$/);
const day = z.iso.date();
const kg = z.string().regex(/^\d+\.\d{6}$/);
const signed = z.string().regex(/^-?\d+(?:\.\d+)?$/);
const peak = z.object({
  forecast_total_kg: kg,
  single_day_peak_date: day,
  single_day_peak_kg: signed,
  rolling_7day_peak_start: day,
  rolling_7day_peak_end: day,
  rolling_7day_peak_cumulative_kg: signed,
  scope: z.literal("THIS_FORECAST_WINDOW_ONLY"),
});
const model = z
  .object({
    status: z.enum(["COMPUTED", "NOT_COMPUTABLE"]),
    model_id: z.string(),
    model_artifact_hash: hash,
    daily_forecast_kg: z.array(z.object({ date: day, kg })),
    H7: peak.nullable(),
    H15: peak.nullable(),
    blocker_reason: z.array(z.string()).nullable(),
  })
  .superRefine((v, ctx) => {
    if (
      (v.status === "COMPUTED" && (v.daily_forecast_kg.length !== 15 || !v.H7 || !v.H15)) ||
      (v.status === "NOT_COMPUTABLE" && (v.daily_forecast_kg.length || v.H7 || v.H15))
    )
      ctx.addIssue({ code: "custom", message: "INCONSISTENT_ROLLING_RESULT" });
  });
export const rollingRun = z
  .object({
    run_id: z.number().int().positive(),
    base_id: z.string(),
    target_season: z.string(),
    origin_date: day,
    origin_cutoff_at: z.iso.datetime({ offset: true }),
    created_at: z.iso.datetime({ offset: true }),
    issued_at: z.null(),
    status: z.enum(["COMPUTED", "PARTIAL", "BLOCKED"]),
    input_hash: hash,
    result_hash: hash,
    input: z.object({
      issue: z.object({
        base_id: z.string(),
        target_season: z.string(),
        origin_date: day,
        origin_cutoff_at: z.iso.datetime({ offset: true }),
        observation_snapshot_reference: z.string(),
        area_authority_reference: z.string(),
        frozen_model_artifact_reference: z.string(),
        execution_mode: z.enum(["RESEARCH_SHADOW", "RETROSPECTIVE_DATE_BOUND"]),
      }),
    }),
    result: z.object({
      models: z.object({ M0: model, M1: model }),
      feature_snapshot: z.object({
        quantity_basis: z.string().nullable(),
        visibility: z.string(),
        complete: z.boolean(),
        reasons: z.array(z.string()),
        feature_hash: hash,
      }),
      strict_pit: z.literal(false),
      production_model: z.literal(false),
      point_is_p50: z.literal(false),
      uncertainty_status: z.literal("NOT_AVAILABLE"),
    }),
  })
  .superRefine((v, ctx) => {
    if (
      v.result.models.M0.model_id !== "BASE10_RIDGE_MATCHED_CONTROL" ||
      v.result.models.M1.model_id !== "BASE10_PLUS_HARVEST_STATE_V1"
    )
      ctx.addIssue({ code: "custom", message: "ROLLING_MODEL_IDENTITY_MISMATCH" });
    if (
      v.base_id !== v.input.issue.base_id ||
      v.target_season !== v.input.issue.target_season ||
      v.origin_date !== v.input.issue.origin_date
    )
      ctx.addIssue({ code: "custom", message: "ROLLING_IDENTITY_MISMATCH" });
    for (const m of Object.values(v.result.models))
      for (const [i, row] of m.daily_forecast_kg.entries()) {
        const d = new Date(v.origin_date + "T00:00:00Z");
        d.setUTCDate(d.getUTCDate() + i + 1);
        if (row.date !== d.toISOString().slice(0, 10))
          ctx.addIssue({ code: "custom", message: "ROLLING_TARGET_MISMATCH" });
      }
  });
export type RollingRun = z.infer<typeof rollingRun>;
export const rollingHistory = z.object({
  items: z.array(
    z.object({
      run_id: z.number().int().positive(),
      base_id: z.string(),
      target_season: z.string(),
      origin_date: day,
      status: z.string(),
      result_hash: hash,
    }),
  ),
  resources: z.array(
    z.object({
      base_id: z.string(),
      target_season: z.string(),
      area_authority_reference: z.string(),
      observation_snapshot_references: z.array(z.string()).min(1),
      frozen_model_artifact_references: z.array(z.string()).min(1),
      execution_modes: z.array(z.enum(["RESEARCH_SHADOW", "RETROSPECTIVE_DATE_BOUND"])).min(1),
    }),
  ),
  offset: z.number(),
  limit: z.number(),
});
export const rollingComparison = z.object({
  left_run: z.number(),
  right_run: z.number(),
  left_origin: day,
  right_origin: day,
  left_result_hash: hash,
  right_result_hash: hash,
  comparison_hash: hash,
  left_quantity_basis: z.string().nullable(),
  right_quantity_basis: z.string().nullable(),
  models: z.record(
    z.enum(["M0", "M1"]),
    z.object({
      status: z.string(),
      windows: z
        .record(
          z.enum(["H7", "H15"]),
          z.object({
            total_delta_kg: signed,
            single_peak_date_delta_days: z.number(),
            single_peak_kg_delta: signed,
            rolling7_start_delta_days: z.number(),
            rolling7_kg_delta: signed,
            meaning: z.literal("DIFFERENT_ORIGIN_WINDOW_TOTALS_NOT_SAME_DATE_REVISION"),
          }),
        )
        .optional(),
      common_target_daily_delta_kg: z.array(z.object({ date: day, kg: signed })).optional(),
    }),
  ),
  production_model: z.literal(false),
});
export function rollingEnvelope<T>(data: z.ZodType<T>) {
  return z.object({
    schema_version: z.literal("ROLLING_SHADOW_V1"),
    status: z.literal("READY"),
    data,
  });
}
