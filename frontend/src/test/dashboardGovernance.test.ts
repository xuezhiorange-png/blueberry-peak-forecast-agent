import { readFileSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { createHash } from "node:crypto";
import { describe, expect, it } from "vitest";
import { designTokens } from "../dashboard/styles/tokens";
import {
  readSchemas,
  comparisonRequest,
  simulationRequest,
  forecastQuery,
} from "../dashboard/schemas/contracts";
import { compare, read, simulate } from "../dashboard/api/client";
import fixture from "./fixtures/dashboard-synthetic.json";

const root = resolve(process.cwd(), "..");
const load = (path: string) => readFileSync(resolve(root, path), "utf8");
function sources(directory: string): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) =>
    entry.isDirectory()
      ? sources(resolve(directory, entry.name))
      : [resolve(directory, entry.name)],
  );
}
const production = sources(resolve(root, "frontend/src/dashboard"));
describe("frozen design and scope", () => {
  it("binds all frozen sources and captured browser screenshots to exact bytes", () => {
    const evidence = JSON.parse(
      load("docs/v0-17/evidence/v0.17-s5-dashboard-implementation-r1.json"),
    );
    for (const group of ["source_evidence_sha256", "screenshot_sha256"])
      for (const [path, expected] of Object.entries(evidence[group]))
        expect(
          createHash("sha256")
            .update(readFileSync(resolve(root, path)))
            .digest("hex"),
          path,
        ).toBe(expected);
    expect(evidence.source_evidence_count).toBe(
      Object.keys(evidence.source_evidence_sha256).length,
    );
    expect(evidence.visual_qa.screenshot_count).toBe(
      Object.keys(evidence.screenshot_sha256).length,
    );
  });
  it("keeps formal and production gates pending and the S5 snapshot canonical", () => {
    const text = load("docs/v0-17/evidence/v0.17-s5-dashboard-implementation-r1.json");
    const evidence = JSON.parse(text);
    expect(evidence.governance).toMatchObject({
      s5_implementation_authorized: true,
      s5_formal_complete: false,
      s6_authorized: false,
      ready_authorized: false,
      merge_authorized: false,
      deploy_authorized: false,
      tag_authorized: false,
      release_authorized: false,
    });
    expect(evidence.product_readiness).toMatchObject({
      business_run_selector_backend_ready: false,
      normal_business_discovery_available: false,
      production_multi_user_scope_validated: false,
      s5_business_selection_ready: false,
      s5_production_ready: false,
    });
    const canonical = (v: unknown): unknown =>
      Array.isArray(v)
        ? v.map(canonical)
        : v !== null && typeof v === "object"
          ? Object.fromEntries(
              Object.entries(v)
                .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
                .map(([key, value]) => [key, canonical(value)]),
            )
          : v;
    expect(text).toBe(JSON.stringify(canonical(evidence), null, 2) + "\n");
  });
  it("implements all 29 named S4 components rather than changing the contract", () => {
    const contract = JSON.parse(load("docs/v0-17/design/s4/dashboard-contract-r1.json"));
    const source = production.map((p) => readFileSync(p, "utf8")).join("\n");
    expect(Object.keys(contract.components)).toHaveLength(29);
    for (const name of Object.keys(contract.components))
      expect(source).toContain(`export function ${name}(`);
  });
  it("uses the actual frozen token build input and core responsive CSS", () => {
    expect(designTokens).toEqual(JSON.parse(load("docs/v0-17/design/s4/design-tokens-r1.json")));
    const css = load("frontend/src/dashboard/styles/dashboard.css");
    for (const color of ["brand", "canvas", "panel", "ink", "secondary", "border"] as const)
      expect(css).toContain(designTokens.color[color]);
    for (const breakpoint of Object.values(designTokens.breakpoint))
      expect(css).toContain(`max-width: ${breakpoint}px`);
    expect(css).toContain("prefers-reduced-motion");
    expect(css).not.toContain("overflow: hidden");
  });
  it("keeps old Trial entry/routes/style exact, as pinned by S4", () => {
    const evidence = JSON.parse(
      load("docs/v0-17/evidence/v0.17-s4-dashboard-design-freeze-r1.json"),
    );
    for (const path of [
      "frontend/src/app/App.tsx",
      "frontend/src/app/routes.tsx",
      "frontend/src/app/app.css",
    ])
      expect(createHash("sha256").update(load(path)).digest("hex")).toBe(
        evidence.source_evidence_sha256[path],
      );
  });
  it("contains no test fixture, private credential, actual reader or browser business calculation", () => {
    for (const path of production.filter(
      (p) => !p.endsWith("Curves.tsx") && !p.endsWith("presentation.tsx"),
    )) {
      const code = readFileSync(path, "utf8");
      for (const forbidden of [
        ".reduce(",
        "localStorage",
        "SYNTHETIC_BASE_1",
        "dashboard-synthetic.json",
        "MCP_SECRET",
        "DATABASE_URL",
        "row_loss",
        "fit_predict",
        "actual_harvest",
        "XMLHttpRequest",
        "WebSocket",
      ])
        expect(code, path).not.toContain(forbidden);
    }
  });
});
describe("resource and authority boundaries", () => {
  it("rejects duplicated dates in both simulation and comparison", () => {
    const simulation = structuredClone(fixture.simulation_request);
    simulation.capacity_rows[1].date = simulation.capacity_rows[0].date;
    expect(simulationRequest.safeParse(simulation).success).toBe(false);
    const comparison = structuredClone(fixture.comparison_request);
    comparison.scenarios[0].capacity_rows = simulation.capacity_rows;
    expect(comparisonRequest.safeParse(comparison).success).toBe(false);
  });
  it("rejects excess scenario/day limits and undeclared request fields", () => {
    expect(
      comparisonRequest.safeParse({
        ...fixture.comparison_request,
        scenarios: Array.from({ length: 21 }, (_, i) => ({
          ...fixture.comparison_request.scenarios[0],
          scenario_id: `S${i}`,
        })),
      }).success,
    ).toBe(false);
    expect(
      simulationRequest.safeParse({
        ...fixture.simulation_request,
        capacity_rows: Array(16).fill(fixture.simulation_request.capacity_rows[0]),
      }).success,
    ).toBe(false);
    expect(
      simulationRequest.safeParse({ ...fixture.simulation_request, initial_backlog_kg: "1" })
        .success,
    ).toBe(false);
  });
  it("round-trips every original service payload without float conversion", () => {
    for (const key of Object.keys(fixture.reads) as (keyof typeof fixture.reads)[])
      expect(readSchemas[key].parse(fixture.reads[key])).toEqual(fixture.reads[key]);
  });
  it("rejects altered scenario source/date/rank hashes", async () => {
    const { vi } = await import("vitest");
    const reply = (value: unknown) =>
      new Response(JSON.stringify(value), { headers: { "Content-Type": "application/json" } });
    const fetch = vi.spyOn(globalThis, "fetch");
    try {
      const simulation = structuredClone(fixture.simulation);
      simulation.data.saved_forecast_hash = "0".repeat(64);
      fetch.mockResolvedValue(reply(simulation));
      await expect(
        simulate(simulationRequest.parse(fixture.simulation_request), new AbortController().signal),
      ).rejects.toMatchObject({ status: 409 });
      const comparison = structuredClone(fixture.comparison);
      comparison.data.comparison.rankings[0].result_hash = "0".repeat(64);
      fetch.mockResolvedValue(reply(comparison));
      await expect(
        compare(comparisonRequest.parse(fixture.comparison_request), new AbortController().signal),
      ).rejects.toMatchObject({ status: 409 });
      const curve = structuredClone(fixture.reads.curve);
      curve.data.daily_rows.reverse();
      fetch.mockResolvedValue(reply(curve));
      await expect(
        read("curve", forecastQuery.parse(fixture.query), new AbortController().signal),
      ).rejects.toMatchObject({ status: 409 });
    } finally {
      fetch.mockRestore();
    }
  });
});
