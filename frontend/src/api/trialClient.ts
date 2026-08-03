import { z } from "zod";
import { trialErrorMessage, type TrialErrorCode } from "./errorCatalog";

const trialErrorResponseSchema = z
  .object({
    request_id: z.string().nullable(),
    status: z.literal("ERROR"),
    code: z.string(),
    message_template_id: z.string(),
    retryable: z.boolean(),
    details: z.record(z.string(), z.unknown()),
  })
  .strict();

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
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
}

function assertTrialPath(path: string): void {
  const url = new URL(path, "http://trial.local");
  if (url.origin !== "http://trial.local" || !url.pathname.startsWith("/api/v1/trial/")) {
    throw new TrialClientError("TRIAL_REQUEST_INVALID", 400);
  }
}

function isJsonContentType(value: string | null): boolean {
  return value !== null && /(^|;)\s*application\/json\s*(;|$)/i.test(value);
}

function isCsvContentType(value: string | null): boolean {
  return value !== null && /(^|;)\s*text\/csv\s*(;|$)/i.test(value);
}

async function parseError(response: Response): Promise<TrialClientError> {
  let payload: unknown;
  try {
    if (isJsonContentType(response.headers.get("content-type"))) {
      payload = await response.json();
    }
  } catch {
    payload = undefined;
  }
  const parsed = trialErrorResponseSchema.safeParse(payload);
  if (parsed.success) {
    return new TrialClientError(parsed.data.code, response.status, parsed.data.retryable);
  }
  return new TrialClientError(
    fallbackCode(response.status),
    response.status,
    response.status === 503,
  );
}

function fallbackCode(status: number): TrialErrorCode {
  if (status === 404) return "RESOURCE_NOT_FOUND";
  if (status === 403) return "TRIAL_AUTHORIZATION_FORBIDDEN";
  if (status === 409) return "EVIDENCE_CONFLICT";
  if (status === 413) return "TRIAL_FILE_SIZE_EXCEEDED";
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
  headers.set("x-request-id", requestId());
  let response: Response;
  try {
    response = await fetcher(path, { ...init, headers });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new TrialClientError("TRIAL_SERVICE_UNAVAILABLE", 503, true);
  }
  if (!response.ok) throw await parseError(response);
  if (!isJsonContentType(response.headers.get("content-type"))) {
    throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
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

function safeFilename(value: string | null): string {
  const candidate =
    value?.match(/filename\*?=(?:UTF-8''|)?"?([^";]+)"?/i)?.[1] ?? "trial-export.csv";
  const decoded = candidate.trim();
  if (
    !decoded ||
    decoded.includes("/") ||
    decoded.includes("\\") ||
    /[\u0000-\u001f\u007f]/.test(decoded)
  ) {
    return "trial-export.csv";
  }
  return decoded.slice(0, 256);
}

export async function downloadCsv(
  path: string,
  fetcher: Fetcher = fetch,
  signal?: AbortSignal,
): Promise<{ blob: Blob; filename: string }> {
  assertTrialPath(path);
  const headers = new Headers({ "x-request-id": requestId() });
  let response: Response;
  try {
    response = await fetcher(path, { method: "GET", headers, signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new TrialClientError("TRIAL_SERVICE_UNAVAILABLE", 503, true);
  }
  if (!response.ok) throw await parseError(response);
  const contentType = response.headers.get("content-type");
  if (!isCsvContentType(contentType)) {
    throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  }
  let blob: Blob;
  try {
    blob = await response.blob();
  } catch {
    throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  }
  if (blob.size === 0) throw new TrialClientError("TRIAL_RESPONSE_CONTRACT_INVALID", 502);
  return { blob, filename: safeFilename(response.headers.get("content-disposition")) };
}

export { trialErrorResponseSchema };
export const trialClient = { getJson, postJson, postBytes, downloadCsv };
