import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Dashboard } from "../dashboard/app/Dashboard";
import { ForecastProvider, useForecast } from "../dashboard/context/ForecastContext";
import { useResource } from "../dashboard/context/useResource";
import { SeriesChart } from "../dashboard/charts/Curves";
import { StatusPanel, DecimalPreview } from "../dashboard/components/presentation";
import {
  readSchemas,
  decisionSchemas,
  forecastQuery,
  simulationRequest,
  comparisonRequest,
  statuses,
} from "../dashboard/schemas/contracts";
import {
  assertIdentity,
  compare,
  cost,
  COSTS,
  quality,
  read,
  request,
  safeError,
  simulate,
} from "../dashboard/api/client";
import { parseDraft } from "../dashboard/pages/CapacityPage";
import fixture from "./fixtures/dashboard-synthetic.json";

const query = forecastQuery.parse(fixture.query);
const reply = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
function mockApi() {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const path = String(input).split("?")[0];
    const kind = path.split("/").pop()!;
    if (kind === "quality")
      return reply(
        String(input).includes("CURRENT_PRODUCTION") ? fixture.current : fixture.quality,
      );
    if (kind === "business-loss") return reply(fixture.cost);
    if (kind === "simulate-capacity") return reply(fixture.simulation);
    if (kind === "compare-capacity-scenarios") return reply(fixture.comparison);
    return reply(fixture.reads[kind as keyof typeof fixture.reads]);
  });
}
function Seed() {
  const { commit } = useForecast();
  return (
    <button
      onClick={() =>
        commit({ query, curve: readSchemas.curve.parse(fixture.reads.curve), key: "SYNTHETIC" })
      }
    >
      TEST ONLY seed
    </button>
  );
}
beforeEach(() => {
  // jsdom does not implement native dialog methods; browser E2E covers the real API.
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
});
afterEach(() => vi.restoreAllMocks());

it("labels long metric text excerpts while retaining the exact accessible value", () => {
  const exact = "0.86666666666666666666666666666666666666666666666667";
  render(<DecimalPreview value={exact} />);
  expect(screen.getByLabelText(exact).getAttribute("title")).toBe(exact);
  expect(screen.getByLabelText(exact).textContent).toBe("0.8666666666…");
});

describe("actual Pydantic service response fixture", () => {
  it.each(Object.keys(fixture.reads) as (keyof typeof fixture.reads)[])(
    "parses %s without changing raw strings or hashes",
    (key) => {
      expect(readSchemas[key].parse(fixture.reads[key])).toEqual(fixture.reads[key]);
    },
  );
  it.each(["quality", "current"] as const)("parses %s", (key) =>
    expect(readSchemas.quality.parse(fixture[key])).toEqual(fixture[key]),
  );
  it.each([
    ["business-loss", "cost"],
    ["simulate-capacity", "simulation"],
    ["compare-capacity-scenarios", "comparison"],
  ] as const)("parses %s frozen-engine output", (key, item) =>
    expect(decisionSchemas[key].parse(fixture[item])).toEqual(fixture[item]),
  );
  it("preserves request strings and rejects client forecasts/cost overrides/initial backlog", () => {
    expect(simulationRequest.parse(fixture.simulation_request)).toEqual(fixture.simulation_request);
    expect(comparisonRequest.parse(fixture.comparison_request)).toEqual(fixture.comparison_request);
    for (const extra of [{ forecast_curve: [] }, { initial_backlog_kg: "10" }, { c_under: "0" }])
      expect(simulationRequest.safeParse({ ...fixture.simulation_request, ...extra }).success).toBe(
        false,
      );
  });
  it("rejects missing data, NaN and future attribution payloads", () => {
    expect(readSchemas.overview.safeParse({ ...fixture.reads.overview, data: null }).success).toBe(
      false,
    );
    expect(
      readSchemas.curve.safeParse({
        ...fixture.reads.curve,
        data: {
          ...fixture.reads.curve.data,
          daily_rows: [{ ...fixture.reads.curve.data.daily_rows[0], point_forecast_kg: NaN }],
        },
      }).success,
    ).toBe(false);
    expect(
      readSchemas.attribution.safeParse({
        ...fixture.reads.attribution,
        status: "READY",
        data: { features: [] },
      }).success,
    ).toBe(false);
  });
});

describe("single-authority client", () => {
  it.each(Object.keys(fixture.reads) as (keyof typeof fixture.reads)[])(
    "reads %s with full identity and original projection hash",
    async (key) => {
      const fetcher = mockApi();
      const value = await read(key, query, new AbortController().signal);
      expect(value).toEqual(fixture.reads[key]);
      expect(String(fetcher.mock.calls[0][0])).toContain("expected_source_result_hash=");
    },
  );
  it("uses quality independently, exact cost, simulation and comparison", async () => {
    mockApi();
    const signal = new AbortController().signal;
    expect(await quality(signal)).toEqual(fixture.quality);
    expect(await quality(signal, true)).toEqual(fixture.current);
    expect(await cost("SYNTHETIC_UNDER_4X_R1", signal)).toEqual(fixture.cost);
    expect(await simulate(simulationRequest.parse(fixture.simulation_request), signal)).toEqual(
      fixture.simulation,
    );
    expect(await compare(comparisonRequest.parse(fixture.comparison_request), signal)).toEqual(
      fixture.comparison,
    );
  });
  it.each([401, 403, 404, 409, 413, 422, 503])(
    "sanitizes HTTP %s without echoing private diagnostics",
    async (status) => {
      vi.spyOn(globalThis, "fetch").mockResolvedValue(
        reply({ detail: "SYNTHETIC_SECRET_SQL_PRIVATE_PATH_DO_NOT_RENDER" }, status),
      );
      try {
        await read("curve", query, new AbortController().signal);
        expect.fail();
      } catch (error) {
        expect(safeError(error)).not.toMatch(/SECRET|SQL|private/);
      }
    },
  );
  it("rejects network errors, wrong content type, malformed payload and unsafe path", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("private"));
    await expect(read("curve", query, new AbortController().signal)).rejects.toMatchObject({
      status: 0,
    });
    fetcher.mockResolvedValue(new Response("{}", { headers: { "Content-Type": "text/html" } }));
    await expect(read("curve", query, new AbortController().signal)).rejects.toMatchObject({
      status: 502,
    });
    fetcher.mockResolvedValue(reply({ data: 0 }));
    await expect(read("curve", query, new AbortController().signal)).rejects.toMatchObject({
      status: 502,
    });
    await expect(
      request("/api/v1/trial/forecasts", readSchemas.curve, new AbortController().signal),
    ).rejects.toMatchObject({ status: 422 });
  });
  it("rejects mismatched run/hash/capability/row before projection", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch");
    for (const change of [
      { source_result_hash: "a".repeat(64) },
      { forecast_identity: { ...fixture.reads.curve.forecast_identity, run_id: 2 } },
      { capability: "GET_FORECAST_OVERVIEW" },
      {
        data: {
          ...fixture.reads.curve.data,
          daily_rows: [{ ...fixture.reads.curve.data.daily_rows[0], entity_id: "OTHER" }],
        },
      },
    ]) {
      fetcher.mockResolvedValue(reply({ ...fixture.reads.curve, ...change }));
      await expect(read("curve", query, new AbortController().signal)).rejects.toMatchObject({
        status: 409,
      });
    }
    expect(() =>
      assertIdentity(fixture.reads.curve, {
        ...query,
        expected_source_result_hash: "b".repeat(64),
      }),
    ).toThrow();
  });
  it("does not silently accept another cost contract", async () => {
    mockApi();
    await expect(cost("SYNTHETIC_BALANCED_R1", new AbortController().signal)).rejects.toMatchObject(
      { status: 409 },
    );
    expect(Object.keys(COSTS)).toHaveLength(3);
  });
  it("rejects oversized body before fetch", async () => {
    const fetcher = vi.spyOn(globalThis, "fetch");
    await expect(
      request(
        "/api/v1/decision-support/simulate-capacity",
        decisionSchemas["simulate-capacity"],
        new AbortController().signal,
        undefined,
        { data: "x".repeat(131073) },
      ),
    ).rejects.toMatchObject({ status: 413 });
    expect(fetcher).not.toHaveBeenCalled();
  });
});

describe("render and request state contracts", () => {
  it.each(statuses)("renders %s as text, never missing as zero", (status) => {
    render(<StatusPanel status={status} reason="SYNTHETIC reason" />);
    expect(screen.getByRole("status").getAttribute("data-state")).toBe(status);
    expect(screen.getByRole("status").textContent).not.toContain("NaN");
  });
  it.each(["overview", "forecast", "attribution", "capacity", "quality"])(
    "has five navigation links and independent %s route",
    async (path) => {
      mockApi();
      render(
        <MemoryRouter initialEntries={["/dashboard/" + path]}>
          <Dashboard />
        </MemoryRouter>,
      );
      expect(
        screen.getByRole("navigation", { name: "Dashboard 主导航" }).querySelectorAll("a"),
      ).toHaveLength(5);
      expect(screen.queryByText("当前仅开放 Trial 合同能力")).toBeNull();
      await waitFor(() => expect(screen.queryByText("正在读取已验证来源")).toBeNull());
    },
  );
  it("uses original chart strings; missing lead creates a new SVG segment", () => {
    render(
      <SeriesChart
        label="SYNTHETIC"
        rows={[
          { date: "2026-01-02", lead: 1, values: ["80.000000"] },
          { date: "2026-01-04", lead: 3, values: ["120.000000"] },
        ]}
        series={["POINT"]}
      />,
    );
    expect(document.querySelector("path")?.getAttribute("d")?.match(/M/g)).toHaveLength(2);
    expect(screen.getByText("80.000000")).toBeTruthy();
  });
  it("does not calculate capacity in the browser and validates every explicit day", () => {
    expect(
      parseDraft({
        scenario_id: "C",
        scenario_version: "R1",
        days: [
          {
            date: "2026-01-02",
            capacity_mode: "WORKFORCE_DERIVED",
            direct: "",
            workforce: "10",
            productivity: "12",
            buffer: "20",
          },
        ],
      }).capacity_rows[0],
    ).toEqual({
      date: "2026-01-02",
      capacity_mode: "WORKFORCE_DERIVED",
      workforce_count: 10,
      productivity_kg_per_person_day: "12",
      buffer_handling_capacity_kg: "20",
    });
    expect(() =>
      parseDraft({
        scenario_id: "A",
        scenario_version: "R1",
        days: [
          {
            date: "2026-01-02",
            capacity_mode: "DIRECT",
            direct: "",
            workforce: "",
            productivity: "",
            buffer: "",
          },
        ],
      }),
    ).toThrow();
  });
  it("cancels old requests and rejects late resolutions, even when fetch ignores abort", async () => {
    const resolves: ((v: { status: string; unavailable_reason: string }) => void)[] = [];
    const signals: AbortSignal[] = [];
    function Probe({ id }: { id: string }) {
      const state = useResource(id, (signal) => {
        signals.push(signal);
        return new Promise<{ status: string; unavailable_reason: string }>((resolve) =>
          resolves.push(resolve),
        );
      });
      return <span>{state.value?.unavailable_reason ?? state.status}</span>;
    }
    const view = render(<Probe id="old" />);
    view.rerender(<Probe id="new" />);
    expect(signals[0].aborted).toBe(true);
    await act(async () => resolves[1]({ status: "READY", unavailable_reason: "NEW" }));
    expect(screen.getByText("NEW")).toBeTruthy();
    await act(async () => resolves[0]({ status: "READY", unavailable_reason: "OLD" }));
    expect(screen.queryByText("OLD")).toBeNull();
  });
  it("keeps synthetic seed component test-only", () => {
    render(
      <ForecastProvider>
        <Seed />
      </ForecastProvider>,
    );
    fireEvent.click(screen.getByText("TEST ONLY seed"));
  });
});
