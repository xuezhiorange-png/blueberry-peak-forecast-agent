import { z } from "zod";
import { describe, expect, it, vi } from "vitest";
import { TrialClientError, downloadCsv, getJson, postBytes } from "../api/trialClient";
import {
  importApi,
  importCommitResponseSchema,
  importCreateResponseSchema,
  importInvalidRowsResponseSchema,
  importReadStatusResponseSchema,
  importUploadResponseSchema,
} from "../features/actualHarvest/importApi";
import { getOrCreateIdempotencyKey } from "../lib/idempotency";

const okSchema = z.object({ ok: z.boolean() }).strict();
const uploadHash = "a".repeat(64);

function response(body: unknown, status = 200, headers?: HeadersInit) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

const createShape = {
  import_id: "import-1",
  status: "RECEIVED",
  source_system: "harvest-console",
  source_dataset: "daily-harvest",
  source_version: "2026-01",
  expected_record_count_or_null: null,
  policy_version: "policy-1",
  canonical_public_hash: "b".repeat(64),
};

const readShape = {
  import_id: "import-1",
  status: "VALIDATED",
  record_count: 2,
  valid_record_count: 1,
  invalid_record_count: 1,
  committed_record_count: 0,
  validation_status: "VALIDATION_FAILED",
  validation_reason_codes: ["ROW_INVALID"],
  validation_evidence_hash: "c".repeat(64),
};

const uploadShape = {
  import_id: "import-1",
  server_status: "VALIDATED",
  source_file_name: "harvest.csv",
  source_mime_type: "text/csv",
  source_file_sha256: uploadHash,
  uploaded_record_count: 2,
  valid_record_count: 1,
  invalid_record_count: 1,
  validation_status: "VALIDATION_FAILED",
  validation_run_instance_identity_hash_or_null: "d".repeat(64),
  validation_result_hash_or_null: "e".repeat(64),
  reason_codes: ["ROW_INVALID"],
};

const rowsShape = {
  import_id: "import-1",
  validation_status: "VALIDATION_FAILED",
  validation_run_instance_identity_hash_or_null: "d".repeat(64),
  rows: [
    {
      severity: "ERROR",
      error_code: "INVALID_DATE",
      record_index: 1,
      external_logical_record_id: "row-1",
      external_revision_id: "rev-1",
      field_path: "target_date",
      message_template_id: "INVALID_DATE",
      details: { expected: "date" },
    },
  ],
  next_page_token: null,
};

const commitShape = {
  import_id: "import-1",
  status: "COMMITTED",
  committed_record_count: 1,
  commit_policy_version: "commit-policy-1",
  commit_manifest_hash: "f".repeat(64),
  reused_existing_commit: false,
};

describe("trialClient", () => {
  it("rejects non-Trial URLs before fetch", async () => {
    const fetcher = vi.fn();
    await expect(
      getJson("/api/v1/actual-harvest/imports", okSchema, fetcher),
    ).rejects.toMatchObject({
      code: "TRIAL_REQUEST_INVALID",
    });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("parses the real TrialErrorResponse and separates payload status from HTTP status", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response(
        {
          request_id: "request-1",
          status: "ERROR",
          code: "CONFLICTING_REPLAY",
          message_template_id: "CONFLICTING_REPLAY",
          retryable: false,
          details: {},
        },
        409,
      ),
    );
    await expect(getJson("/api/v1/trial/forecasts/x", okSchema, fetcher)).rejects.toMatchObject({
      code: "CONFLICTING_REPLAY",
      status: 409,
      retryable: false,
    });
  });

  it("keeps retryable true for the real 503 error shape", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response(
        {
          request_id: "request-2",
          status: "ERROR",
          code: "TRIAL_SERVICE_UNAVAILABLE",
          message_template_id: "TRIAL_SERVICE_UNAVAILABLE",
          retryable: true,
          details: {},
        },
        503,
      ),
    );
    await expect(getJson("/api/v1/trial/forecasts/x", okSchema, fetcher)).rejects.toMatchObject({
      code: "TRIAL_SERVICE_UNAVAILABLE",
      status: 503,
      retryable: true,
    });
  });

  it("uses concealed RESOURCE_NOT_FOUND for an unparseable 404", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({}, 404));
    await expect(getJson("/api/v1/trial/forecasts/x", okSchema, fetcher)).rejects.toMatchObject({
      code: "RESOURCE_NOT_FOUND",
      status: 404,
    });
  });

  it("maps a structured 422 without retrying or exposing payload details", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      response(
        {
          request_id: null,
          status: "ERROR",
          code: "TRIAL_REQUEST_INVALID",
          message_template_id: "TRIAL_REQUEST_INVALID",
          retryable: false,
          details: { internal: "must not be shown" },
        },
        422,
      ),
    );
    const error = await getJson("/api/v1/trial/forecasts/x", okSchema, fetcher).catch(
      (value) => value,
    );
    expect(error).toMatchObject({ code: "TRIAL_REQUEST_INVALID", status: 422, retryable: false });
    expect(String(error)).not.toContain("must not be shown");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("rejects unknown success keys as a response contract error", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ ok: true, extra: "unexpected" }));
    await expect(getJson("/api/v1/trial/forecasts/x", okSchema, fetcher)).rejects.toMatchObject({
      code: "TRIAL_RESPONSE_CONTRACT_INVALID",
      status: 502,
    });
  });

  it("uses a safe HTTP fallback for invalid JSON", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response("not-json", { status: 502 }));
    const error = await getJson("/api/v1/trial/forecasts/x", okSchema, fetcher).catch(
      (value) => value,
    );
    expect(error).toBeInstanceOf(TrialClientError);
    if (error instanceof TrialClientError) {
      expect(error.code).toBe("TRIAL_INTERNAL_ERROR");
      expect(error.message).not.toContain("not-json");
    }
  });

  it("sends raw bytes and generates one correlation request id", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ ok: true }));
    await postBytes(
      "/api/v1/trial/actual-harvest/imports/x/upload",
      new TextEncoder().encode("a").buffer,
      { "content-type": "text/csv", "x-file-name": "x.csv" },
      okSchema,
      fetcher,
    );
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(init.method).toBe("POST");
    expect(headers.get("x-request-id")).toBeTruthy();
  });

  it("maps CSV filename from a server export and supports abort", async () => {
    const csv = vi.fn().mockResolvedValue(
      new Response("a,b\n", {
        headers: {
          "content-type": "text/csv",
          "content-disposition": 'attachment; filename="report.csv"',
        },
      }),
    );
    const result = await downloadCsv("/api/v1/trial/quality-reports/x/export.csv", csv);
    expect(result.filename).toBe("report.csv");
    const abort = new AbortController();
    const abortFetcher = vi.fn().mockRejectedValue(new DOMException("Aborted", "AbortError"));
    await expect(
      getJson("/api/v1/trial/forecasts/x", okSchema, abortFetcher, abort.signal),
    ).rejects.toBeInstanceOf(DOMException);
  });

  it("validates all five import response shapes", async () => {
    expect(importCreateResponseSchema.parse(createShape).status).toBe("RECEIVED");
    expect(importReadStatusResponseSchema.parse(readShape).status).toBe("VALIDATED");
    expect(importUploadResponseSchema.parse(uploadShape).server_status).toBe("VALIDATED");
    expect(importInvalidRowsResponseSchema.parse(rowsShape).rows[0]?.error_code).toBe(
      "INVALID_DATE",
    );
    expect(importCommitResponseSchema.parse(commitShape).status).toBe("COMMITTED");
  });

  it("accepts nullable create fields and nullable invalid-row indexes", () => {
    expect(
      importCreateResponseSchema.parse({
        ...createShape,
        expected_record_count_or_null: 12,
      }).expected_record_count_or_null,
    ).toBe(12);
    expect(
      importCreateResponseSchema.parse({
        ...createShape,
        canonical_public_hash: null,
      }).canonical_public_hash,
    ).toBeNull();
    expect(
      importInvalidRowsResponseSchema.parse({
        ...rowsShape,
        rows: [{ ...rowsShape.rows[0], record_index: null }],
      }).rows[0]?.record_index,
    ).toBeNull();
  });

  it("rejects invalid import nullable field values", () => {
    expect(() =>
      importCreateResponseSchema.parse({
        ...createShape,
        expected_record_count_or_null: "12",
      }),
    ).toThrow();
    expect(() =>
      importCreateResponseSchema.parse({
        ...createShape,
        canonical_public_hash: "not-a-sha",
      }),
    ).toThrow();
    expect(() =>
      importInvalidRowsResponseSchema.parse({
        ...rowsShape,
        rows: [{ ...rowsShape.rows[0], record_index: -1 }],
      }),
    ).toThrow();
  });

  it("uses status for GET, server_status for upload, and status for commit", async () => {
    const statusFetcher = vi.fn().mockResolvedValue(response(readShape));
    expect((await importApi.status("import-1", statusFetcher)).status).toBe("VALIDATED");
    const uploadFetcher = vi.fn().mockResolvedValue(response(uploadShape));
    const file = new File(["row"], "harvest.csv", { type: "text/csv" });
    const result = await importApi.upload("import-1", file, uploadHash, uploadFetcher);
    expect(result.server_status).toBe("VALIDATED");
    const commitFetcher = vi.fn().mockResolvedValue(response(commitShape));
    expect((await importApi.commit("import-1", "d".repeat(64), commitFetcher)).status).toBe(
      "COMMITTED",
    );
  });

  it("uses the displayed precomputed hash as x-file-sha256 and separates request id", async () => {
    const fetcher = vi.fn().mockResolvedValue(response(uploadShape));
    const file = new File(["row"], "harvest.csv", { type: "text/csv" });
    await importApi.upload("import-1", file, uploadHash, fetcher);
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    const idempotencyKey = getOrCreateIdempotencyKey("upload");
    expect(headers.get("x-file-sha256")).toBe(uploadHash);
    expect(headers.get("x-request-id")).toBeTruthy();
    expect(headers.get("x-request-id")).not.toBe(idempotencyKey);
  });
});
