import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { sha256Hex } from "../features/actualHarvest/importApi";
import { collectInvalidRows, QualityPage, qualityReportRequestScope } from "../pages/QualityPage";
import { getOrCreateIdempotencyKey } from "../lib/idempotency";

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

  it("reads every invalid-row page and fails closed on a repeated token", async () => {
    const page = (index: number, next_page_token: string | null) => ({
      rows: [
        {
          severity: "ERROR" as const,
          error_code: `ROW_${index}`,
          record_index: index,
          external_logical_record_id: `row-${index}`,
          external_revision_id: `rev-${index}`,
          field_path: "harvest_business_date",
          message_template_id: "INVALID_DATE",
          details: {},
        },
      ],
      next_page_token,
    });
    const loadPage = vi
      .fn()
      .mockImplementation((token?: string) =>
        Promise.resolve(token === "page-2" ? page(2, null) : page(1, "page-2")),
      );
    await expect(collectInvalidRows(loadPage)).resolves.toHaveLength(2);
    expect(loadPage).toHaveBeenCalledTimes(2);

    const repeated = vi.fn().mockResolvedValue(page(1, "same-token"));
    await expect(collectInvalidRows(repeated)).rejects.toMatchObject({
      code: "TRIAL_RESPONSE_CONTRACT_INVALID",
    });
    expect(repeated).toHaveBeenCalledTimes(2);
  });
});
