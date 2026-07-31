import { downloadCsv, getJson, postJson, type Fetcher } from "../../api/trialClient";
import { qualityComparisonSchema, qualityReportSchema } from "./qualitySchemas";

export const qualityApi = {
  create(body: unknown, fetcher?: Fetcher, signal?: AbortSignal) {
    return postJson("/api/v1/trial/quality-reports", body, qualityReportSchema, fetcher, signal);
  },
  read(reportId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return getJson(
      `/api/v1/trial/quality-reports/${encodeURIComponent(reportId)}`,
      qualityReportSchema,
      fetcher,
      signal,
    );
  },
  comparison(reportId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return getJson(
      `/api/v1/trial/quality-reports/${encodeURIComponent(reportId)}/comparison`,
      qualityComparisonSchema,
      fetcher,
      signal,
    );
  },
  export(reportId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return downloadCsv(
      `/api/v1/trial/quality-reports/${encodeURIComponent(reportId)}/export.csv`,
      fetcher,
      signal,
    );
  },
};
