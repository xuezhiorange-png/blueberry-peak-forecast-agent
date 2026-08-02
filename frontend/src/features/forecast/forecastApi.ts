import { downloadCsv, getJson, postJson, type Fetcher } from "../../api/trialClient";
import {
  forecastDailyCurveSchema,
  forecastInputAuthoritySchema,
  forecastSummarySchema,
  type ForecastInputAuthority,
  type TrialForecastRequest,
} from "./forecastSchemas";

export type { TrialForecastRequest } from "./forecastSchemas";

export const forecastApi = {
  authority(fetcher?: Fetcher, signal?: AbortSignal): Promise<ForecastInputAuthority> {
    return getJson(
      "/api/v1/trial/forecast-input-authority",
      forecastInputAuthoritySchema,
      fetcher,
      signal,
    );
  },
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
