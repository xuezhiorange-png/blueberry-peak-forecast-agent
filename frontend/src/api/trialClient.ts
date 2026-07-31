import { z } from "zod";
import { trialErrorMessage, type TrialErrorCode } from "./errorCatalog";

const errorSchema = z.object({
  code: z.string().optional(),
  retryable: z.boolean().optional(),
  status: z.number().optional(),
});

export class TrialClientError extends Error {
  readonly code: string;
  readonly status: number;
  readonly retryable: boolean;

  constructor(code: string, status: number, retryable = false) {
    super(trialErrorMessage(code, status));
    this.name = "TrialClientError";
    this.code = code;
    this.status = status;
    this.retryable = retryable;
  }
}

export type Fetcher = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

function requestId(): string {
  return typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `trial-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function assertTrialPath(path: string): void {
  const url = new URL(path, "http://trial.local");
  if (!url.pathname.startsWith("/api/v1/trial/")) {
    throw new TrialClientError("TRIAL_REQUEST_INVALID", 400);
  }
}

async function parseError(response: Response): Promise<TrialClientError> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  const parsed = errorSchema.safeParse(payload);
  const code = parsed.success ? parsed.data.code : undefined;
  const retryable = parsed.success ? parsed.data.retryable === true : response.status === 503;
  return new TrialClientError(code ?? fallbackCode(response.status), response.status, retryable);
}

function fallbackCode(status: number): TrialErrorCode {
  if (status === 404) return "RESOURCE_NOT_FOUND";
  if (status === 403) return "TRIAL_AUTHORIZATION_FORBIDDEN";
  if (status === 409) return "CONCURRENCY_CONFLICT";
  if (status === 415) return "TRIAL_UNSUPPORTED_CONTENT_TYPE";
  if (status === 422) return "TRIAL_REQUEST_INVALID";
  if (status === 503) return "TRIAL_SERVICE_UNAVAILABLE";
  return "TRIAL_INTERNAL_ERROR";
}

async function request<T>(
  path: string,
  init: RequestInit,
  schema: z.ZodType<T>,
  fetcher: Fetcher = fetch,
): Promise<T> {
  assertTrialPath(path);
  const headers = new Headers(init.headers);
  headers.set("x-request-id", headers.get("x-request-id") ?? requestId());
  const response = await fetcher(path, { ...init, headers });
  if (!response.ok) throw await parseError(response);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new TrialClientError("TRIAL_INTERNAL_ERROR", response.status);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new TrialClientError("TRIAL_INTERNAL_ERROR", 502);
  return parsed.data;
}

export function getJson<T>(
  path: string,
  schema: z.ZodType<T>,
  fetcher?: Fetcher,
  signal?: AbortSignal,
) {
  return request(path, { method: "GET", signal }, schema, fetcher);
}

export function postJson<T>(
  path: string,
  body: unknown,
  schema: z.ZodType<T>,
  fetcher?: Fetcher,
  signal?: AbortSignal,
) {
  return request(
    path,
    {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "content-type": "application/json" },
      signal,
    },
    schema,
    fetcher,
  );
}

export function postBytes<T>(
  path: string,
  bytes: ArrayBuffer,
  headers: Record<string, string>,
  schema: z.ZodType<T>,
  fetcher?: Fetcher,
  signal?: AbortSignal,
) {
  return request(path, { method: "POST", body: bytes, headers, signal }, schema, fetcher);
}

export async function downloadCsv(
  path: string,
  fetcher: Fetcher = fetch,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
  assertTrialPath(path);
  const headers = new Headers({ "x-request-id": requestId() });
  const response = await fetcher(path, { method: "GET", headers, signal });
  if (!response.ok) throw await parseError(response);
  const disposition = response.headers.get("content-disposition") ?? "";
  const filename = disposition.match(/filename="?([^";]+)"?/i)?.[1] ?? "trial-export.csv";
  return { blob: await response.blob(), filename };
}

export const trialClient = { getJson, postJson, postBytes, downloadCsv };
