import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ForecastPage } from "../pages/ForecastPage";

describe("ForecastPage", () => {
  it("renders the complete disabled forecast contract without requesting data", () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("must not call fetch"));
    render(<ForecastPage />);
    expect(screen.getByRole("heading", { name: "预测输入" })).toBeTruthy();
    expect(screen.getByLabelText("加工厂")).toBeTruthy();
    expect(screen.getByLabelText("产季")).toBeTruthy();
    expect(screen.getByLabelText("农场")).toBeTruthy();
    expect(screen.getByLabelText("分场")).toBeTruthy();
    expect(screen.getByLabelText("品种")).toBeTruthy();
    expect((screen.getByRole("button", { name: "生成预测" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(screen.getByText("预测后端能力未就绪")).toBeTruthy();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });
});
