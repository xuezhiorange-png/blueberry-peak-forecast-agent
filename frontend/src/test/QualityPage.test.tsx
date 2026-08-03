import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { sha256Hex, type ImportStatus } from "../features/actualHarvest/importApi";
import { QualityReport as QualityReportComponent } from "../features/quality/QualityReport";
import type {
  QualityComparison,
  QualityReport as QualityReportData,
} from "../features/quality/qualitySchemas";
import {
  actualHarvestCreateRequestScope,
  collectInvalidRows,
  pollImportStatus,
  QualityPage,
  qualityReportRequestScope,
} from "../pages/QualityPage";
import { getOrCreateIdempotencyKey } from "../lib/idempotency";

function importStatus(status: ImportStatus["status"]): ImportStatus {
  return {
    import_id: "import-1",
    status,
    record_count: 0,
    valid_record_count: 0,
    invalid_record_count: 0,
    committed_record_count: 0,
    validation_status:
      status === "VALIDATION_FAILED"
        ? "VALIDATION_FAILED"
        : status === "VALIDATED" || status === "COMMITTED"
          ? "VALIDATED"
          : "VALIDATING",
    validation_reason_codes: [],
    validation_evidence_hash: null,
  };
}

function invalidPage(
  importId: string,
  validationIdentity: string,
  rows: number[],
  nextPageToken: string | null,
  validationStatus: "VALIDATION_FAILED" | "VALIDATED" = "VALIDATION_FAILED",
) {
  return {
    import_id: importId,
    validation_status: validationStatus,
    validation_run_instance_identity_hash_or_null: validationIdentity,
    rows: rows.map((index) => ({
      severity: "ERROR" as const,
      error_code: `ROW_${index}`,
      record_index: index,
      external_logical_record_id: `row-${index}`,
      external_revision_id: `rev-${index}`,
      field_path: "harvest_business_date",
      message_template_id: "INVALID_DATE",
      details: {},
    })),
    next_page_token: nextPageToken,
  };
}

describe("QualityPage", () => {
  it("starts idle with mutation controls disabled before file selection", () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("must not fetch"));
    render(<QualityPage />);
    const input = document.getElementById("actual-harvest-file") as HTMLInputElement;
    expect(input).toBeTruthy();
    expect(input.disabled).toBe(false);
    expect((screen.getByRole("button", { name: "上传并校验" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole("button", { name: "提交导入" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(
      (screen.getByRole("button", { name: "生成质量报告" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("shows local file metadata and a lowercase SHA-256 without fetching", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("must not fetch"));
    render(<QualityPage />);
    const input = document.getElementById("actual-harvest-file") as HTMLInputElement;
    const file = new File(["blueberry"], "harvest.csv", { type: "text/csv" });
    const expectedHash = await sha256Hex(file);
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText(expectedHash)).toBeTruthy());
    expect(screen.getAllByText("harvest.csv")).toHaveLength(2);
    expect(screen.getByText("text/csv")).toBeTruthy();
    expect(screen.getByText("9 B")).toBeTruthy();
    expect(expectedHash).toMatch(/^[0-9a-f]{64}$/);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("discards a stale hash when a new file is selected", async () => {
    render(<QualityPage />);
    const input = document.getElementById("actual-harvest-file") as HTMLInputElement;
    const first = new File(["first"], "first.csv", { type: "text/csv" });
    const second = new File(["second"], "second.xlsx", {
      type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    });
    const firstHash = await sha256Hex(first);
    const secondHash = await sha256Hex(second);
    fireEvent.change(input, { target: { files: [first] } });
    await waitFor(() => expect(screen.getByText(firstHash)).toBeTruthy());
    fireEvent.change(input, { target: { files: [second] } });
    await waitFor(() => expect(screen.getByText(secondHash)).toBeTruthy());
    expect(screen.queryByText(firstHash)).toBeNull();
  });

  it("rejects unsupported files locally and never calls Quality APIs", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("must not fetch"));
    render(<QualityPage />);
    const input = document.getElementById("actual-harvest-file") as HTMLInputElement;
    const unsupported = new File(["not a spreadsheet"], "notes.txt", { type: "text/plain" });
    fireEvent.change(input, { target: { files: [unsupported] } });
    await waitFor(() =>
      expect(
        screen.getByText("不支持的文件类型或 MIME，仅允许 .csv 或 .xlsx。文件未上传。"),
      ).toBeTruthy(),
    );
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("reuses a Quality idempotency key only for the same logical request", () => {
    const first = qualityReportRequestScope({
      forecastRunId: "a".repeat(64),
      importId: "import-a",
      forecastCutoffAt: "2026-03-01T00:00:00Z",
      labelCutoffAt: "2026-03-10T00:00:00Z",
      horizons: [7, 14, 21],
    });
    const same = qualityReportRequestScope({
      forecastRunId: "a".repeat(64),
      importId: "import-a",
      forecastCutoffAt: "2026-03-01T00:00:00Z",
      labelCutoffAt: "2026-03-10T00:00:00Z",
      horizons: [7, 14, 21],
    });
    const different = qualityReportRequestScope({
      forecastRunId: "a".repeat(64),
      importId: "import-a",
      forecastCutoffAt: "2026-03-01T00:00:00Z",
      labelCutoffAt: "2026-03-11T00:00:00Z",
      horizons: [7, 14, 21],
    });
    expect(first).toBe(same);
    expect(first).not.toBe(different);
    expect(getOrCreateIdempotencyKey(first)).toBe(getOrCreateIdempotencyKey(same));
    expect(getOrCreateIdempotencyKey(first)).not.toBe(getOrCreateIdempotencyKey(different));
  });

  it("scopes Actual Harvest create idempotency to trimmed metadata, not file identity", () => {
    const base = {
      sourceSystem: " trial-api ",
      sourceDataset: " daily-harvest ",
      sourceVersion: " 2026-01 ",
      externalBatchId: " batch-1 ",
      expectedRecordCountOrNull: null,
    };
    const same = actualHarvestCreateRequestScope({ ...base });
    expect(same).toBe(
      actualHarvestCreateRequestScope({
        ...base,
        sourceSystem: "trial-api",
        sourceDataset: "daily-harvest",
        sourceVersion: "2026-01",
        externalBatchId: "batch-1",
      }),
    );
    for (const field of [
      "sourceSystem",
      "sourceDataset",
      "sourceVersion",
      "externalBatchId",
    ] as const) {
      expect(
        actualHarvestCreateRequestScope({ ...base, [field]: `${base[field]}-changed` }),
      ).not.toBe(same);
    }
    expect(actualHarvestCreateRequestScope({ ...base, expectedRecordCountOrNull: 1 })).not.toBe(
      same,
    );
    expect(same).toContain("<null>");
    expect(same).not.toContain("sha256");
  });

  it("keeps a verified report exportable after an isolated export failure", async () => {
    const report = {
      report_id: "a".repeat(64),
      computability_status: "AVAILABLE",
      forecast_cutoff_at: "2026-03-01T00:00:00Z",
      label_observation_cutoff_at: "2026-03-10T00:00:00Z",
      horizons: [
        {
          horizon_days: 7,
          daily_overlay: [],
          daily_metrics: [],
          cumulative_metric: { metric_status: "AVAILABLE", metric_value_or_null: "1.000000" },
          single_day_peak: { metric_status: "AVAILABLE", metric_value_or_null: "1.000000" },
          sustained_seven_day_peak: {
            metric_status: "AVAILABLE",
            metric_value_or_null: "1.000000",
          },
          p80_coverage: {
            metric_status: "AVAILABLE",
            coverage_ratio_or_null: "1.000000",
            reason_codes: [],
          },
          p90_coverage: {
            metric_status: "AVAILABLE",
            coverage_ratio_or_null: "1.000000",
            reason_codes: [],
          },
          interval_metric: {
            lower_bound_available: true,
            lower_bound_value_or_null: "1.000000",
          },
          coverage_counts: { total: 1, comparable: 1, covered: 1 },
          excluded_row_counts: { excluded: 0, not_computable: 0 },
          reason_codes: [],
        },
      ],
    } as unknown as QualityReportData;
    const comparison = { model_baseline_deltas: [] } as unknown as QualityComparison;
    const onExport = vi.fn().mockResolvedValue(undefined);
    render(
      <QualityReportComponent
        forecastRunId={"b".repeat(64)}
        onForecastRunIdChange={vi.fn()}
        forecastCutoffAt="2026-03-01T00:00:00Z"
        labelCutoffAt="2026-03-10T00:00"
        onLabelCutoffAtChange={vi.fn()}
        onLoadForecast={vi.fn()}
        loadingForecast={false}
        committedImportId="import-1"
        onCreateReport={vi.fn()}
        report={report}
        comparison={comparison}
        creating={false}
        onExport={onExport}
        exporting={false}
        errorMessage={null}
        exportErrorMessage="导出失败，请重试。"
      />,
    );
    expect(screen.getByText("Quality report ID")).toBeTruthy();
    expect(screen.getByText("导出失败，请重试。")).toBeTruthy();
    const exportButton = screen.getByRole("button", { name: "导出质量 CSV" });
    expect((exportButton as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(exportButton);
    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1));
  });

  it("polls only until a terminal import state and makes timeout explicit", async () => {
    const loadStatus = vi
      .fn<() => Promise<ImportStatus>>()
      .mockResolvedValueOnce(importStatus("PARSING"))
      .mockResolvedValueOnce(importStatus("VALIDATED"));
    const result = await pollImportStatus(loadStatus, {
      maxAttempts: 5,
      wait: async () => undefined,
    });
    expect(result).toEqual({ status: importStatus("VALIDATED"), timedOut: false });
    expect(loadStatus).toHaveBeenCalledTimes(2);

    const timeoutLoad = vi
      .fn<() => Promise<ImportStatus>>()
      .mockResolvedValue(importStatus("PARSING"));
    const timeout = await pollImportStatus(timeoutLoad, {
      maxAttempts: 2,
      wait: async () => undefined,
    });
    expect(timeout.timedOut).toBe(true);
    expect(timeout.status.import_id).toBe("import-1");
    expect(timeoutLoad).toHaveBeenCalledTimes(2);
  });

  it("aborts polling without publishing a stale response", async () => {
    const controller = new AbortController();
    const loadStatus = vi.fn(async () => {
      controller.abort();
      return importStatus("PARSING");
    });
    await expect(pollImportStatus(loadStatus, { signal: controller.signal })).rejects.toMatchObject(
      { name: "AbortError" },
    );
  });

  it("reads every invalid-row page and validates evidence continuity", async () => {
    const loadPage = vi
      .fn()
      .mockImplementation((token?: string) =>
        Promise.resolve(
          token === "page-2"
            ? invalidPage("import-1", "d".repeat(64), [2], null)
            : invalidPage("import-1", "d".repeat(64), [1], "page-2"),
        ),
      );
    await expect(
      collectInvalidRows(loadPage, {
        importId: "import-1",
        validationIdentity: "d".repeat(64),
      }),
    ).resolves.toHaveLength(2);
    expect(loadPage).toHaveBeenCalledTimes(2);

    const repeated = vi
      .fn()
      .mockResolvedValue(invalidPage("import-1", "d".repeat(64), [1], "same-token"));
    await expect(
      collectInvalidRows(repeated, {
        importId: "import-1",
        validationIdentity: "d".repeat(64),
      }),
    ).rejects.toMatchObject({
      code: "TRIAL_RESPONSE_CONTRACT_INVALID",
    });
    expect(repeated).toHaveBeenCalledTimes(2);
  });

  it.each([
    ["import ID", invalidPage("other-import", "d".repeat(64), [1], null)],
    ["validation status", invalidPage("import-1", "d".repeat(64), [1], null, "VALIDATED")],
    ["validation identity", invalidPage("import-1", "e".repeat(64), [1], null)],
  ])("rejects invalid-row evidence continuity for %s", async (_label, response) => {
    await expect(
      collectInvalidRows(vi.fn().mockResolvedValue(response), {
        importId: "import-1",
        validationIdentity: "d".repeat(64),
      }),
    ).rejects.toMatchObject({ code: "TRIAL_RESPONSE_CONTRACT_INVALID" });
  });

  it("enforces the page ceiling and never publishes partial rows", async () => {
    const rows = await collectInvalidRows(
      vi
        .fn()
        .mockImplementation((token?: string) =>
          Promise.resolve(invalidPage("import-1", "d".repeat(64), token ? [2] : [1], "next-token")),
        ),
      { importId: "import-1", validationIdentity: "d".repeat(64) },
      undefined,
      2,
    ).catch((error: unknown) => {
      expect(error).toMatchObject({ code: "TRIAL_RESPONSE_CONTRACT_INVALID" });
      return [];
    });
    expect(rows).toEqual([]);
  });

  it("clears prior import evidence when create metadata changes", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("network"));
    render(<QualityPage />);
    const input = document.getElementById("actual-harvest-file") as HTMLInputElement;
    const file = new File(["blueberry"], "harvest.csv", { type: "text/csv" });
    fireEvent.change(input, { target: { files: [file] } });
    await waitFor(() => expect(screen.getByText("SHA-256 已完成")).toBeTruthy());
    fireEvent.change(screen.getByLabelText("source system"), { target: { value: "new-system" } });
    expect(screen.getByText("Import ID").parentElement?.textContent).toContain("—");
    expect((screen.getByRole("button", { name: "上传并校验" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    fetchSpy.mockRestore();
  });
});
