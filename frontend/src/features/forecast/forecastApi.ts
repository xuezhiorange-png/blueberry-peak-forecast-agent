import { downloadCsv, getJson, postJson, type Fetcher } from "../../api/trialClient";
import { forecastDailyCurveSchema, forecastSummarySchema } from "./forecastSchemas";

export type TrialForecastRequest = {
  farm: string;
  subfarm: string;
  variety: string;
  season: string;
  forecast_date: string;
  planting_area_mu: string;
  flowering_date: string | null;
  maturity_stage: string | null;
  already_picked_quantity_kg: string | null;
};

export const forecastApi = {
  create(request: TrialForecastRequest, fetcher?: Fetcher, signal?: AbortSignal) {
    return postJson("/api/v1/trial/forecasts", request, forecastSummarySchema, fetcher, signal);
  },
  read(runId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return getJson(
      `/api/v1/trial/forecasts/${encodeURIComponent(runId)}`,
      forecastSummarySchema,
      fetcher,
      signal,
    );
  },
  daily(runId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return getJson(
      `/api/v1/trial/forecasts/${encodeURIComponent(runId)}/daily-curve`,
      forecastDailyCurveSchema,
      fetcher,
      signal,
    );
  },
  export(runId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return downloadCsv(
      `/api/v1/trial/forecasts/${encodeURIComponent(runId)}/export.csv`,
      fetcher,
      signal,
    );
  },
};
