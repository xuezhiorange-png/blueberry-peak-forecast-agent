import { describe, expect, it, vi } from "vitest";
import { TrialClientError, downloadCsv, getJson, postBytes } from "../api/trialClient";
import { z } from "zod";

const okSchema = z.object({ ok: z.boolean() });

function response(body: unknown, status = 200, headers?: HeadersInit) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", ...headers },
  });
}

describe("trialClient", () => {
  it("rejects non-Trial URLs before fetch", async () => {
    const fetcher = vi.fn();
    await expect(
      getJson("/api/v1/actual-harvest/imports", okSchema, fetcher),
    ).rejects.toMatchObject({ code: "TRIAL_REQUEST_INVALID" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("maps concealed 404 and retryable 503 safely", async () => {
    const notFound = vi.fn().mockResolvedValue(response({}, 404));
    await expect(getJson("/api/v1/trial/forecasts/x", okSchema, notFound)).rejects.toMatchObject({
      code: "RESOURCE_NOT_FOUND",
      status: 404,
    });
    const unavailable = vi
      .fn()
      .mockResolvedValue(response({ code: "TRIAL_SERVICE_UNAVAILABLE", retryable: true }, 503));
    await expect(getJson("/api/v1/trial/forecasts/x", okSchema, unavailable)).rejects.toMatchObject(
      { retryable: true, status: 503 },
    );
  });

  it("sends raw bytes with required headers", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ ok: true }));
    await postBytes(
      "/api/v1/trial/actual-harvest/imports/x/upload",
      new TextEncoder().encode("a").buffer,
      { "content-type": "text/csv", "x-file-name": "x.csv", "x-file-sha256": "a".repeat(64) },
      okSchema,
      fetcher,
    );
    const init = fetcher.mock.calls[0]?.[1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(init.method).toBe("POST");
    expect(headers.get("content-type")).toBe("text/csv");
    expect(headers.get("x-file-name")).toBe("x.csv");
    expect(headers.get("x-request-id")).toBeTruthy();
  });

  it("extracts the server CSV filename and supports abort", async () => {
    const csv = vi.fn().mockResolvedValue(
      new Response("a,b\n", {
        headers: { "content-disposition": 'attachment; filename="report.csv"' },
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

  it("turns invalid network JSON into a safe client error", async () => {
    const fetcher = vi.fn().mockResolvedValue(response({ ok: "not-a-boolean" }));
    const error = await getJson("/api/v1/trial/forecasts/x", okSchema, fetcher).catch(
      (value) => value,
    );
    expect(error).toBeInstanceOf(TrialClientError);
    if (error instanceof TrialClientError) {
      expect(error.code).toBe("TRIAL_INTERNAL_ERROR");
      expect(error.message).not.toContain("not-a-boolean");
    }
  });
});
