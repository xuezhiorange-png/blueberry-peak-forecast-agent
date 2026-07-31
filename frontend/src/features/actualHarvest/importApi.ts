import { z } from "zod";
import { getJson, postBytes, postJson, type Fetcher } from "../../api/trialClient";

const nullableString = z.string().nullable();

export const importCreateResponseSchema = z
  .object({
    import_id: z.string(),
    status: z.string(),
    source_system: z.string(),
    source_dataset: z.string(),
    source_version: z.string(),
    expected_record_count_or_null: z.number().int().nonnegative().nullable(),
    policy_version: z.string(),
    canonical_public_hash: z
      .string()
      .regex(/^[0-9a-f]{64}$/)
      .nullable(),
  })
  .passthrough();

export const importReadStatusResponseSchema = z
  .object({
    import_id: z.string(),
    status: z.string(),
    record_count: z.number(),
    valid_record_count: z.number(),
    invalid_record_count: z.number(),
    committed_record_count: z.number(),
    validation_status: z.string(),
    validation_reason_codes: z.array(z.string()),
    validation_evidence_hash: nullableString,
  })
  .passthrough();

export const importUploadResponseSchema = z
  .object({
    import_id: z.string(),
    server_status: z.string(),
    source_file_name: z.string(),
    source_mime_type: z.string(),
    source_file_sha256: z.string(),
    uploaded_record_count: z.number(),
    valid_record_count: z.number(),
    invalid_record_count: z.number(),
    validation_status: z.string(),
    validation_run_instance_identity_hash_or_null: nullableString,
    validation_result_hash_or_null: nullableString,
    reason_codes: z.array(z.string()),
  })
  .passthrough();

export const importInvalidRowSchema = z
  .object({
    severity: z.string(),
    error_code: z.string(),
    record_index: z.number().int().nonnegative().nullable(),
    external_logical_record_id: nullableString,
    external_revision_id: nullableString,
    field_path: nullableString,
    message_template_id: z.string(),
    details: z.record(z.string(), z.unknown()),
  })
  .passthrough();

export const importInvalidRowsResponseSchema = z
  .object({
    import_id: z.string(),
    validation_status: z.string(),
    validation_run_instance_identity_hash_or_null: nullableString,
    rows: z.array(importInvalidRowSchema),
    next_page_token: nullableString,
  })
  .passthrough();

export const importCommitResponseSchema = z
  .object({
    import_id: z.string(),
    status: z.string(),
    committed_record_count: z.number(),
    commit_policy_version: z.string(),
    commit_manifest_hash: z.string(),
    reused_existing_commit: z.boolean(),
  })
  .passthrough();

export type ImportStatus = z.infer<typeof importReadStatusResponseSchema>;
export type ImportInvalidRow = z.infer<typeof importInvalidRowSchema>;

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export const importApi = {
  create(body: unknown, fetcher?: Fetcher, signal?: AbortSignal) {
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
    return postBytes(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/upload`,
      await file.arrayBuffer(),
      {
        "content-type": file.type,
        "x-file-name": file.name,
        "x-file-sha256": hash,
      },
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
  errors(importId: string, pageToken?: string, fetcher?: Fetcher, signal?: AbortSignal) {
    const suffix = pageToken ? `?page_token=${encodeURIComponent(pageToken)}` : "";
    return getJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/errors${suffix}`,
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
