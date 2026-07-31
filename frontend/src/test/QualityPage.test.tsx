import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QualityPage } from "../pages/QualityPage";

describe("QualityPage", () => {
  it("keeps import and quality mutation controls disabled until the chain is proven", () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("must not call fetch"));
    render(<QualityPage />);
    expect(document.getElementById("actual-harvest-file")).toBeTruthy();
    expect((screen.getByRole("button", { name: "上传并校验" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect((screen.getByRole("button", { name: "提交导入" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(
      (screen.getByRole("button", { name: "生成质量报告" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(
      screen.getByText("TRIAL_IMPORT_FULL_CHAIN_AVAILABLE=false；不会发起 mutation。"),
    ).toBeTruthy();
    expect(screen.getByText("PARSING")).toBeTruthy();
    expect(screen.getByText("COMMITTING")).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
