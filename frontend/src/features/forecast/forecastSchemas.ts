import { z } from "zod";

export const forecastSummarySchema = z
  .object({
    run_id: z.string(),
    forecast_date: z.string().optional(),
    model_version: z.string().optional(),
    parameter_version: z.string().optional(),
    policy_version: z.string().optional(),
  })
  .passthrough();

export const forecastDailyCurveSchema = z
  .object({
    run_id: z.string(),
    rows: z.array(
      z
        .object({ target_date: z.string(), forecast_p50: z.string().nullable().optional() })
        .passthrough(),
    ),
  })
  .passthrough();

export type ForecastSummary = z.infer<typeof forecastSummarySchema>;
export type ForecastDailyCurve = z.infer<typeof forecastDailyCurveSchema>;
