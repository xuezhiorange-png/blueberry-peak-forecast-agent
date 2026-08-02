import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { sha256Hex } from "../features/actualHarvest/importApi";
import { QualityPage } from "../pages/QualityPage";

describe("QualityPage", () => {
  it("keeps mutation controls disabled while allowing local file selection", () => {
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
});
