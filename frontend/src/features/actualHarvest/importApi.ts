import { z } from "zod";
import { getJson, postBytes, postJson, type Fetcher } from "../../api/trialClient";
import { sha256Schema } from "../forecast/forecastSchemas";

const nullableString = z.string().nullable();
const nullableHash = sha256Schema.nullable();
const importStatusSchema = z.enum([
  "RECEIVED",
  "UPLOADING",
  "SEALED",
  "PARSING",
  "PARSE_FAILED",
  "VALIDATING",
  "VALIDATION_FAILED",
  "VALIDATED",
  "COMMITTING",
  "COMMITTED",
  "COMMIT_FAILED",
  "CANCELLED",
]);
const validationStatusSchema = z.enum(["VALIDATING", "VALIDATION_FAILED", "VALIDATED"]);

export const importCreateResponseSchema = z
  .object({
    import_id: z.string().min(1),
    status: importStatusSchema,
    source_system: z.string().min(1),
    source_dataset: z.string().min(1),
    source_version: z.string().min(1),
    expected_record_count_or_null: z.number().int().nonnegative().nullable(),
    policy_version: z.string().min(1),
    canonical_public_hash: nullableHash,
  })
  .strict();

export const importReadStatusResponseSchema = z
  .object({
    import_id: z.string().min(1),
    status: importStatusSchema,
    record_count: z.number().int().nonnegative(),
    valid_record_count: z.number().int().nonnegative(),
    invalid_record_count: z.number().int().nonnegative(),
    committed_record_count: z.number().int().nonnegative(),
    validation_status: validationStatusSchema,
    validation_reason_codes: z.array(z.string()).readonly(),
    validation_evidence_hash: nullableHash,
  })
  .strict();

export const importUploadResponseSchema = z
  .object({
    import_id: z.string().min(1),
    server_status: validationStatusSchema,
    source_file_name: z.string().min(1),
    source_mime_type: z.enum([
      "text/csv",
      "application/csv",
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ]),
    source_file_sha256: sha256Schema,
    uploaded_record_count: z.number().int().nonnegative(),
    valid_record_count: z.number().int().nonnegative(),
    invalid_record_count: z.number().int().nonnegative(),
    validation_status: validationStatusSchema,
    validation_run_instance_identity_hash_or_null: nullableHash,
    validation_result_hash_or_null: nullableHash,
    reason_codes: z.array(z.string()).readonly(),
  })
  .strict();

export const importInvalidRowSchema = z
  .object({
    severity: z.enum(["ERROR", "WARNING"]),
    error_code: z.string().min(1),
    record_index: z.number().int().nonnegative().nullable(),
    external_logical_record_id: nullableString,
    external_revision_id: nullableString,
    field_path: nullableString,
    message_template_id: z.string().min(1),
    details: z.record(z.string(), z.unknown()),
  })
  .strict();

export const importInvalidRowsResponseSchema = z
  .object({
    import_id: z.string().min(1),
    validation_status: validationStatusSchema,
    validation_run_instance_identity_hash_or_null: nullableHash,
    rows: z.array(importInvalidRowSchema).readonly(),
    next_page_token: nullableString,
  })
  .strict();

export const importCommitResponseSchema = z
  .object({
    import_id: z.string().min(1),
    status: z.literal("COMMITTED"),
    committed_record_count: z.number().int().nonnegative(),
    commit_policy_version: z.string().min(1),
    commit_manifest_hash: sha256Schema,
    reused_existing_commit: z.boolean(),
  })
  .strict();

export type ImportStatus = z.infer<typeof importReadStatusResponseSchema>;
export type ImportCreateResponse = z.infer<typeof importCreateResponseSchema>;
export type ImportUploadResponse = z.infer<typeof importUploadResponseSchema>;
export type ImportInvalidRow = z.infer<typeof importInvalidRowSchema>;
export type ImportInvalidRowsResponse = z.infer<typeof importInvalidRowsResponseSchema>;
export type ImportCommitResponse = z.infer<typeof importCommitResponseSchema>;

export type TrialImportCreateRequest = {
  source_system: string;
  source_dataset: string;
  source_version: string;
  external_batch_id: string;
  expected_record_count_or_null: number | null;
  request_idempotency_key: string;
};

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export function fileMimeType(
  file: File,
): "text/csv" | "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" | null {
  const lowerName = file.name.toLowerCase();
  if (
    lowerName.endsWith(".csv") &&
    (!file.type || file.type === "text/csv" || file.type === "application/csv")
  ) {
    return "text/csv";
  }
  if (
    lowerName.endsWith(".xlsx") &&
    (!file.type ||
      file.type === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
  ) {
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
  }
  return null;
}

export const importApi = {
  create(body: TrialImportCreateRequest, fetcher?: Fetcher, signal?: AbortSignal) {
    return postJson(
      "/api/v1/trial/actual-harvest/imports",
      body,
      importCreateResponseSchema,
      fetcher,
      signal,
    );
  },
  async upload(
    importId: string,
    file: File,
    hash: string,
    fetcher?: Fetcher,
    signal?: AbortSignal,
  ) {
    const mimeType = fileMimeType(file);
    if (!mimeType) throw new Error("UNSUPPORTED_FILE");
    return postBytes(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/upload`,
      await file.arrayBuffer(),
      { "content-type": mimeType, "x-file-name": file.name, "x-file-sha256": hash },
      importUploadResponseSchema,
      fetcher,
      signal,
    );
  },
  status(importId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return getJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}`,
      importReadStatusResponseSchema,
      fetcher,
      signal,
    );
  },
  errors(
    importId: string,
    pageToken?: string,
    fetcher?: Fetcher,
    signal?: AbortSignal,
    pageSize = 100,
  ) {
    const params = new URLSearchParams({ page_size: String(pageSize) });
    if (pageToken) params.set("page_token", pageToken);
    return getJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/errors?${params.toString()}`,
      importInvalidRowsResponseSchema,
      fetcher,
      signal,
    );
  },
  commit(importId: string, evidenceIdentity: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return postJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/commit`,
      { validation_run_instance_identity_hash: evidenceIdentity },
      importCommitResponseSchema,
      fetcher,
      signal,
    );
  },
};
