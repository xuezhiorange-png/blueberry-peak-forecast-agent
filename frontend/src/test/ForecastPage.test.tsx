import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ForecastPage } from "../pages/ForecastPage";

const authority = {
  forecast_input_authority_hash: "a".repeat(64),
  authority_available_at: "2026-02-01T12:00:00Z",
  authority_version: "authority-v1",
  items: [
    {
      farm_business_key: "farm-1",
      subfarm_business_key_or_null: "subfarm-1",
      season_business_key: "season-2026",
      variety_business_key: "variety-1",
      destination_factory_business_key: "factory-1",
      plan_version: "plan-v1",
      plan_row_hash: "b".repeat(64),
      planting_area_mu: "12.500000",
    },
  ],
};

describe("ForecastPage", () => {
  it("loads server authority and requires area confirmation before create", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockResolvedValue(
      new Response(JSON.stringify(authority), {
        headers: { "content-type": "application/json" },
      }),
    );
    render(<ForecastPage />);
    expect(screen.getByRole("heading", { name: "预测输入" })).toBeTruthy();
    expect(screen.getByLabelText("加工厂")).toBeTruthy();
    expect(screen.getByLabelText("产季")).toBeTruthy();
    expect(screen.getByLabelText("农场")).toBeTruthy();
    expect(screen.getByLabelText("分场")).toBeTruthy();
    expect(screen.getByLabelText("品种")).toBeTruthy();

    await waitFor(() =>
      expect((screen.getByLabelText("农场") as HTMLSelectElement).value).toBe("farm-1"),
    );
    expect((screen.getByLabelText("权威种植面积（亩）") as HTMLInputElement).value).toBe(
      "12.500000",
    );
    expect((screen.getByRole("button", { name: "生成预测" }) as HTMLButtonElement).disabled).toBe(
      true,
    );

    fireEvent.click(screen.getByLabelText("我确认使用服务端权威面积"));
    expect((screen.getByRole("button", { name: "生成预测" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
    expect(fetchSpy).toHaveBeenCalledWith(
      "/api/v1/trial/forecast-input-authority",
      expect.objectContaining({ method: "GET" }),
    );
    fetchSpy.mockRestore();
  });

  it("renders a safe unavailable state when authority cannot be loaded", async () => {
    const fetchSpy = vi.spyOn(window, "fetch").mockRejectedValue(new Error("network"));
    render(<ForecastPage />);
    await waitFor(() => expect(screen.getByText("输入权威不可用")).toBeTruthy());
    expect(screen.getByText("后端能力暂不可用，请稍后重试。")).toBeTruthy();
    fetchSpy.mockRestore();
  });
});
