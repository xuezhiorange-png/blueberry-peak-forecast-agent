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

const secondAuthorityItem = {
  ...authority.items[0],
  farm_business_key: "farm-2",
  subfarm_business_key_or_null: "subfarm-2",
  variety_business_key: "variety-2",
  plan_row_hash: "c".repeat(64),
  planting_area_mu: "8.000000",
};

function forecastRow() {
  return {
    target_date: "2026-02-28",
    p50_value_kg: "1.000000",
    p80_value_kg: "1.100000",
    p90_value_kg: "1.200000",
    row_status: "AVAILABLE",
    reason_codes: [],
  };
}

function forecastSummary(runId = "d".repeat(64)) {
  const row = forecastRow();
  return {
    run_id: runId,
    status: "COMPLETED",
    daily_p50_series: [row],
    daily_p80_series: [row],
    daily_p90_series: [row],
    single_day_peak: {
      date: "2026-02-28",
      quantity_kg: "1.000000",
      tie_break: "EARLIEST_DATE",
    },
    sustained_seven_day_peak: {
      start_date: "2026-02-22",
      end_date: "2026-02-28",
      cumulative_quantity_kg: "7.000000",
      daily_average_kg_per_day: "1.000000",
      window_days: 7,
      metric: "ROLLING_CUMULATIVE",
      date_continuity: "STRICT_CALENDAR_DAYS",
      tie_break: "EARLIEST_START_DATE",
    },
    season_cumulative_quantity: "1.000000",
    mature_inventory_summary: { opening_quantity_kg: "2.000000", closing_quantity_kg: "1.000000" },
    backlog_summary: { quantity_kg: "0.000000" },
    data_gap_summaries: [],
    blocker_summaries: [],
    model_version: "model-v1",
    parameter_version: "parameter-v1",
    policy_versions: { forecast: "policy-v1" },
    canonical_public_hash: "e".repeat(64),
    forecast_scope: {
      farm_business_key: "farm-1",
      subfarm_business_key_or_null: "subfarm-1",
      season_business_key: "season-2026",
      variety_business_key: "variety-1",
      destination_factory_business_key: "factory-1",
    },
    forecast_start_date: "2026-02-28",
    forecast_end_date: "2026-02-28",
    forecast_cutoff_at: "2026-02-01T12:00:00Z",
    forecast_input_authority_hash: "a".repeat(64),
    plan_row_hash: "b".repeat(64),
    planting_area_mu: "12.500000",
    policy_identity: "policy-v1",
    policy_hash: "f".repeat(64),
    model_identity: "model-v1",
    parameter_identity: "parameter-v1",
    code_authority_identity: null,
    task8_identity: null,
    task9_identity: null,
    result_hash: "1".repeat(64),
    curve_hash: "2".repeat(64),
    metrics_hash: "3".repeat(64),
  };
}

function forecastCurve(runId = "d".repeat(64)) {
  return {
    run_id: runId,
    forecast_cutoff_at: "2026-02-01T12:00:00Z",
    rows: [forecastRow()],
    forecast_start_date: "2026-02-28",
    forecast_end_date: "2026-02-28",
    forecast_scope: forecastSummary(runId).forecast_scope,
  };
}

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

  it("resets area confirmation when the selected authority item changes", async () => {
    const fetchSpy = vi
      .spyOn(window, "fetch")
      .mockResolvedValue(
        new Response(
          JSON.stringify({ ...authority, items: [authority.items[0], secondAuthorityItem] }),
          { headers: { "content-type": "application/json" } },
        ),
      );
    render(<ForecastPage />);
    await waitFor(() =>
      expect((screen.getByLabelText("农场") as HTMLSelectElement).value).toBe("farm-1"),
    );
    fireEvent.click(screen.getByLabelText("我确认使用服务端权威面积"));
    await waitFor(() =>
      expect((screen.getByLabelText("我确认使用服务端权威面积") as HTMLInputElement).checked).toBe(
        true,
      ),
    );
    expect((screen.getByRole("button", { name: "生成预测" }) as HTMLButtonElement).disabled).toBe(
      false,
    );

    fireEvent.change(screen.getByLabelText("农场"), { target: { value: "farm-2" } });
    expect((screen.getByLabelText("权威种植面积（亩）") as HTMLInputElement).value).toBe(
      "8.000000",
    );
    expect((screen.getByLabelText("我确认使用服务端权威面积") as HTMLInputElement).checked).toBe(
      false,
    );
    expect((screen.getByRole("button", { name: "生成预测" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    fetchSpy.mockRestore();
  });

  it("disables unsupported optional inputs and submits them as null", async () => {
    const runId = "d".repeat(64);
    const summary = forecastSummary(runId);
    const fetchSpy = vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === "/api/v1/trial/forecast-input-authority")
        return new Response(JSON.stringify(authority), {
          headers: { "content-type": "application/json" },
        });
      if (init?.method === "POST")
        return new Response(JSON.stringify(summary), {
          headers: { "content-type": "application/json" },
        });
      if (url.pathname.endsWith("/daily-curve"))
        return new Response(JSON.stringify(forecastCurve(runId)), {
          headers: { "content-type": "application/json" },
        });
      return new Response(JSON.stringify(summary), {
        headers: { "content-type": "application/json" },
      });
    });
    render(<ForecastPage />);
    await waitFor(() =>
      expect((screen.getByLabelText("农场") as HTMLSelectElement).value).toBe("farm-1"),
    );
    expect((screen.getByLabelText("开花日期（可选）") as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText("成熟阶段（可选）") as HTMLSelectElement).disabled).toBe(true);
    expect((screen.getByLabelText("已采摘数量 kg（可选）") as HTMLInputElement).disabled).toBe(
      true,
    );
    fireEvent.click(screen.getByLabelText("我确认使用服务端权威面积"));
    fireEvent.click(screen.getByRole("button", { name: "生成预测" }));
    await waitFor(() => expect(screen.getByTestId("forecast-run-id").textContent).toBe(runId));
    const createCall = fetchSpy.mock.calls.find(([, request]) => request?.method === "POST");
    expect(JSON.parse(String(createCall?.[1]?.body))).toMatchObject({
      flowering_date_or_null: null,
      maturity_stage_or_null: null,
      already_picked_quantity_kg_or_null: null,
    });
    fetchSpy.mockRestore();
  });

  it("hides stale Forecast evidence when a subsequent readback fails", async () => {
    const runId = "d".repeat(64);
    const summary = forecastSummary(runId);
    let readCount = 0;
    const fetchSpy = vi.spyOn(window, "fetch").mockImplementation(async (input, init) => {
      const url = new URL(String(input), window.location.origin);
      if (url.pathname === "/api/v1/trial/forecast-input-authority")
        return new Response(JSON.stringify(authority), {
          headers: { "content-type": "application/json" },
        });
      if (init?.method === "POST")
        return new Response(JSON.stringify(summary), {
          headers: { "content-type": "application/json" },
        });
      if (url.pathname.endsWith("/daily-curve"))
        return new Response(JSON.stringify(forecastCurve(runId)), {
          headers: { "content-type": "application/json" },
        });
      readCount += 1;
      if (readCount > 1) return new Response("failure", { status: 503 });
      return new Response(JSON.stringify(summary), {
        headers: { "content-type": "application/json" },
      });
    });
    render(<ForecastPage />);
    await waitFor(() =>
      expect((screen.getByLabelText("农场") as HTMLSelectElement).value).toBe("farm-1"),
    );
    fireEvent.click(screen.getByLabelText("我确认使用服务端权威面积"));
    fireEvent.click(screen.getByRole("button", { name: "生成预测" }));
    await waitFor(() => expect(screen.getByTestId("forecast-run-id").textContent).toBe(runId));
    fireEvent.click(screen.getByRole("button", { name: "生成预测" }));
    await waitFor(() => expect(screen.getByText("预测结果不可用")).toBeTruthy());
    expect(screen.queryByTestId("forecast-run-id")).toBeNull();
    expect(
      (screen.getByRole("button", { name: "导出 Forecast CSV" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    fetchSpy.mockRestore();
  });
});
