import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, expect, it, vi } from "vitest";
import { RollingForecastPanel } from "../dashboard/components/RollingForecastPanel";
import { invalidateSecurity } from "../dashboard/api/security";

const state = vi.hoisted(() => ({ principal: "SYNTHETIC-A", request: vi.fn() }));
vi.mock("../dashboard/context/SessionContext", () => ({
  useSession: () => ({ user: { principal_id: state.principal } }),
}));
vi.mock("../dashboard/api/client", async () => {
  const original =
    await vi.importActual<typeof import("../dashboard/api/client")>("../dashboard/api/client");
  return { ...original, request: state.request };
});
const resource = {
  base_id: "SYNTHETIC_BASE",
  target_season: "2026-2027",
  area_authority_reference: "AREA",
  observation_snapshot_references: ["OBS"],
  frozen_model_artifact_references: ["FIT"],
  execution_modes: ["RESEARCH_SHADOW"],
};
const listing = { data: { items: [], resources: [resource], offset: 0, limit: 20 } };

function payload(issue: Record<string, string>) {
  const daily = Array.from({ length: 15 }, (_, i) => {
    const d = new Date(issue.origin_date + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + i + 1);
    return { date: d.toISOString().slice(0, 10), kg: "10.000000" };
  });
  const peak = {
    single_day_peak_date: daily[0].date,
    single_day_peak_kg: "10.000000",
    rolling_7day_peak_start: daily[0].date,
    rolling_7day_peak_end: daily[6].date,
    rolling_7day_peak_cumulative_kg: "70.000000",
    scope: "THIS_FORECAST_WINDOW_ONLY",
  };
  const model = {
    model_id: "SYNTHETIC_RIDGE",
    model_artifact_hash: "a".repeat(64),
    status: "COMPUTED",
    H7: { ...peak, forecast_total_kg: "70.000000" },
    H15: { ...peak, forecast_total_kg: "150.000000" },
    daily_forecast_kg: daily,
  };
  return {
    data: {
      ...issue,
      run_id: 1,
      input_hash: "a".repeat(64),
      result_hash: "b".repeat(64),
      input: { issue },
      result: {
        models: { M0: model, M1: model },
        feature_snapshot: {
          quantity_basis: "FIELD_HARVEST_WEIGHT",
          visibility: "TRUSTED_AS_OF_CUTOFF",
          feature_hash: "c".repeat(64),
        },
      },
    },
  };
}

async function prepare() {
  fireEvent.click(screen.getByRole("button", { name: "查询研究预测" }));
  await screen.findByLabelText("Origin 日期");
  fireEvent.change(screen.getByLabelText("Origin 日期"), { target: { value: "2026-11-05" } });
}
afterEach(() => {
  state.request.mockReset();
  state.principal = "SYNTHETIC-A";
});

it("StrictMode retains server quantities and invalidates results on input revision", async () => {
  state.request.mockImplementation(async (_p, _s, _signal, _params, body) =>
    body ? payload(body) : listing,
  );
  render(
    <StrictMode>
      <RollingForecastPanel />
    </StrictMode>,
  );
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "生成并保存研究预测" }));
  const region = await screen.findByRole("region", { name: "滚动预测结果" });
  expect(within(region).getAllByRole("table")).toHaveLength(2);
  expect(within(region).getAllByText("10.000000")).toHaveLength(30);
  fireEvent.change(screen.getByLabelText("Origin 日期"), { target: { value: "2026-11-06" } });
  expect(screen.queryByRole("region", { name: "滚动预测结果" })).toBeNull();
});

it.each(["cancel", "input", "revocation", "account"])(
  "late response cannot revive data after %s",
  async (action) => {
    let finish!: (value: unknown) => void;
    let submitted: Record<string, string> = {};
    state.request.mockImplementation(async (_p, _s, _signal, _params, body) => {
      if (!body) return listing;
      submitted = body;
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    const view = render(<RollingForecastPanel />);
    await prepare();
    fireEvent.click(screen.getByRole("button", { name: "生成并保存研究预测" }));
    await waitFor(() => expect(finish).toBeDefined());
    if (action === "cancel") fireEvent.click(screen.getByRole("button", { name: "取消研究请求" }));
    if (action === "input")
      fireEvent.change(screen.getByLabelText("Origin 日期"), { target: { value: "2026-11-06" } });
    if (action === "revocation") act(() => invalidateSecurity("access"));
    if (action === "account") {
      state.principal = "SYNTHETIC-B";
      view.rerender(<RollingForecastPanel />);
    }
    await act(async () => {
      finish(payload(submitted));
    });
    expect(screen.queryByRole("region", { name: "滚动预测结果" })).toBeNull();
  },
);

it("mismatched submission response is rejected rather than displayed", async () => {
  state.request.mockImplementation(async (_p, _s, _signal, _params, body) =>
    body ? payload({ ...body, observation_snapshot_reference: "OTHER" }) : listing,
  );
  render(<RollingForecastPanel />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "生成并保存研究预测" }));
  await screen.findByText("响应输入不匹配，已拒绝展示。");
  expect(screen.queryByRole("region", { name: "滚动预测结果" })).toBeNull();
});

it("noncomparable responses never display supplied numeric deltas", async () => {
  state.request.mockImplementation(async (path) => {
    if (path.endsWith("/compare"))
      return {
        data: {
          left_run: 1,
          right_run: 2,
          left_origin: "2026-11-05",
          right_origin: "2026-11-06",
          models: {
            M1: {
              status: "NOT_COMPARABLE",
              reasons: ["BASE_MISMATCH"],
              windows: { H7: { total_delta_kg: "999.000000" } },
              common_target_daily_delta_kg: [{ date: "2026-11-07", kg: "888.000000" }],
            },
          },
        },
      };
    return {
      data: {
        ...listing.data,
        items: [1, 2].map((run_id) => ({
          run_id,
          base_id: "SYNTHETIC_BASE",
          target_season: "2026-2027",
          origin_date: "2026-11-05",
          status: "COMPUTED",
          result_hash: "a".repeat(64),
        })),
      },
    };
  });
  render(<RollingForecastPanel />);
  await prepare();
  fireEvent.change(screen.getByLabelText("比较起点"), { target: { value: "1" } });
  fireEvent.change(screen.getByLabelText("比较终点"), { target: { value: "2" } });
  fireEvent.click(screen.getByRole("button", { name: "比较两个研究 Origin" }));
  const region = await screen.findByRole("region", { name: "研究 Origin 对比" });
  expect(region.textContent).not.toContain("999.000000");
  expect(region.textContent).not.toContain("888.000000");
  expect(within(region).queryByRole("table")).toBeNull();
  expect(region.textContent).toContain("BASE_MISMATCH");
});

it("shows model target separately from feature observation basis", async () => {
  state.request.mockImplementation(async (_p, _s, _signal, _params, body) => {
    if (!body) return listing;
    const value = payload(body);
    for (const model of Object.values(value.data.result.models))
      Object.assign(model, {
        model_training_target_quantity_basis: "RECORDED_INBOUND_WEIGHT",
        forecast_target_quantity_basis: "RECORDED_INBOUND_WEIGHT",
        model_provenance: "REAL_FROZEN_S6",
      });
    return value;
  });
  render(<RollingForecastPanel />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "生成并保存研究预测" }));
  const region = await screen.findByRole("region", { name: "滚动预测结果" });
  expect(region.textContent).toContain("特征观测口径：FIELD_HARVEST_WEIGHT");
  expect(region.textContent).toContain("训练目标口径：RECORDED_INBOUND_WEIGHT");
  expect(region.textContent).toContain("预测目标口径：RECORDED_INBOUND_WEIGHT");
});
