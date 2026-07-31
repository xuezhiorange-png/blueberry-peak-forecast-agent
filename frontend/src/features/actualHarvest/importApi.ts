import { getJson, postBytes, postJson, type Fetcher } from "../../api/trialClient";
import { createIdempotencyKey } from "../../lib/idempotency";
import { z } from "zod";

export const importStatusSchema = z
  .object({
    import_id: z.string(),
    server_status: z.string(),
    validation_status: z.string().optional(),
    validation_run_instance_identity_hash_or_null: z.string().nullable().optional(),
  })
  .passthrough();
export const importCreateSchema = z.object({ import_id: z.string() }).passthrough();
export const invalidRowsSchema = z
  .object({ rows: z.array(z.record(z.string(), z.unknown())).default([]) })
  .passthrough();
export const commitSchema = z.object({ server_status: z.string() }).passthrough();

export type ImportStatus = z.infer<typeof importStatusSchema>;

export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export const importApi = {
  create(body: unknown, fetcher?: Fetcher, signal?: AbortSignal) {
    return postJson(
      "/api/v1/trial/actual-harvest/imports",
      body,
      importCreateSchema,
      fetcher,
      signal,
    );
  },
  upload(importId: string, file: File, _hash: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return uploadRawFile(importId, file, fetcher, signal);
  },
  status(importId: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return getJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}`,
      importStatusSchema,
      fetcher,
      signal,
    );
  },
  errors(importId: string, pageToken?: string, fetcher?: Fetcher, signal?: AbortSignal) {
    const suffix = pageToken ? `?page_token=${encodeURIComponent(pageToken)}` : "";
    return getJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/errors${suffix}`,
      invalidRowsSchema,
      fetcher,
      signal,
    );
  },
  commit(importId: string, evidenceIdentity: string, fetcher?: Fetcher, signal?: AbortSignal) {
    return postJson(
      `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/commit`,
      { validation_run_instance_identity_hash: evidenceIdentity },
      commitSchema,
      fetcher,
      signal,
    );
  },
};

export async function uploadRawFile(
  importId: string,
  file: File,
  fetcher?: Fetcher,
  signal?: AbortSignal,
) {
  const hash = await sha256Hex(file);
  return postBytes(
    `/api/v1/trial/actual-harvest/imports/${encodeURIComponent(importId)}/upload`,
    await file.arrayBuffer(),
    {
      "content-type": file.type,
      "x-file-name": file.name,
      "x-file-sha256": hash,
      "x-request-id": createIdempotencyKey("upload"),
    },
    importStatusSchema,
    fetcher,
    signal,
  );
}
