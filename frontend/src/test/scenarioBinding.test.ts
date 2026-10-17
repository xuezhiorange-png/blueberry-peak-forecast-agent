// SYNTHETIC=true: existing frozen service payloads, not production data.
import { afterEach, expect, it, vi } from "vitest";
import { compare, request, simulate } from "../dashboard/api/client";
import { invalidateSecurity, subscribeSecurity } from "../dashboard/api/security";
import { decimalIdentity, frozenDigest } from "../dashboard/api/scenarioBinding";
import { comparisonRequest, readSchemas, simulationRequest } from "../dashboard/schemas/contracts";
import { auth, reply } from "./businessFixtures";
import fixture from "./fixtures/dashboard-synthetic.json";
import workforce from "./fixtures/option-b-workforce-synthetic.json";

afterEach(() => vi.restoreAllMocks());
function mockResult(result: unknown) {
  return vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (url) =>
      reply(
        String(url).endsWith("/csrf") ? auth({ csrf_token: "SYNTHETIC", expires_in: 300 }) : result,
      ),
    );
}
const signal = () => new AbortController().signal;

it("accepts unchanged DIRECT and comparison payloads including WORKFORCE_DERIVED", async () => {
  mockResult(fixture.simulation);
  expect(await simulate(simulationRequest.parse(fixture.simulation_request), signal())).toEqual(
    fixture.simulation,
  );
  vi.restoreAllMocks();
  mockResult(workforce.simulation);
  expect(await simulate(simulationRequest.parse(workforce.simulation_request), signal())).toEqual(
    workforce.simulation,
  );
  vi.restoreAllMocks();
  mockResult(workforce.comparison);
  expect(await compare(comparisonRequest.parse(workforce.comparison_request), signal())).toEqual(
    workforce.comparison,
  );
});
it("uses exact value-canonical Decimal strings, without losing a last digit", async () => {
  expect(decimalIdentity("000140.000000")).toBe("140");
  expect(decimalIdentity("000.000")).toBe("0");
  expect(decimalIdentity("9007199254740993.0000000000000000001")).not.toBe(
    decimalIdentity("9007199254740993.0000000000000000002"),
  );
  const input = simulationRequest.parse(fixture.simulation_request);
  if (input.capacity_rows[0].capacity_mode !== "DIRECT") throw new Error("Fixture changed");
  input.capacity_rows[0].daily_handling_capacity_kg = "00140.000000";
  mockResult(fixture.simulation);
  expect(await simulate(input, signal())).toEqual(fixture.simulation);
});
it.each([
  "scenario_version",
  "scenario_id",
  "direct",
  "buffer_presence",
  "buffer_value",
  "capacity_mode",
] as const)("rejects changed submitted %s, not only a changed response hash", async (field) => {
  const input = simulationRequest.parse(fixture.simulation_request);
  if (field === "scenario_version") input.scenario_version = "SYNTHETIC_OTHER_VERSION";
  if (field === "scenario_id") input.scenario_id = "SYNTHETIC_OTHER_ID";
  const row = input.capacity_rows[0];
  if (row.capacity_mode !== "DIRECT") throw new Error("Fixture changed");
  if (field === "direct") row.daily_handling_capacity_kg = "140.000000000000000001";
  if (field === "buffer_presence") delete row.buffer_handling_capacity_kg;
  if (field === "buffer_value") row.buffer_handling_capacity_kg = "0.000000000000000001";
  if (field === "capacity_mode")
    input.capacity_rows[0] = {
      date: row.date,
      capacity_mode: "WORKFORCE_DERIVED",
      workforce_count: 14,
      productivity_kg_per_person_day: "10",
      buffer_handling_capacity_kg: "0",
    };
  mockResult(fixture.simulation);
  await expect(simulate(input, signal())).rejects.toMatchObject({ status: 409 });
});
it.each(["workforce_count", "productivity", "version", "buffer"] as const)(
  "comparison rejects changed WORKFORCE %s",
  async (field) => {
    const input = comparisonRequest.parse(workforce.comparison_request);
    const scenario = input.scenarios.find((s) =>
      s.capacity_rows.some((r) => r.capacity_mode === "WORKFORCE_DERIVED"),
    );
    if (!scenario) throw new Error("Missing actual workforce fixture");
    const row = scenario.capacity_rows[0];
    if (row.capacity_mode !== "WORKFORCE_DERIVED") throw new Error("Fixture changed");
    if (field === "workforce_count") row.workforce_count++;
    if (field === "productivity") row.productivity_kg_per_person_day = "0.0000000000000000001";
    if (field === "version") scenario.scenario_version = "SYNTHETIC_OTHER_VERSION";
    if (field === "buffer") row.buffer_handling_capacity_kg = "1";
    mockResult(workforce.comparison);
    await expect(compare(input, signal())).rejects.toMatchObject({ status: 409 });
  },
);
it.each(["row_hash", "result_hash", "scenario_hash", "projection_hash", "unknown_policy"] as const)(
  "rejects altered %s",
  async (field) => {
    const response = structuredClone(fixture.simulation);
    if (field === "row_hash") response.data.daily_rows[0].row_hash = "0".repeat(64);
    if (field === "result_hash")
      response.data.result_hash = response.engine_result_hash = "0".repeat(64);
    if (field === "scenario_hash") response.data.scenario_hash = "0".repeat(64);
    if (field === "projection_hash") response.projection_hash = "0".repeat(64);
    if (field === "unknown_policy") response.engine_policy_versions.what_if = "UNKNOWN";
    mockResult(response);
    await expect(
      simulate(simulationRequest.parse(fixture.simulation_request), signal()),
    ).rejects.toMatchObject({ status: 409 });
  },
);
it("rechecks cancellation and security revision after asynchronous native hash verification", async () => {
  mockResult(fixture.simulation);
  const original = crypto.subtle.digest.bind(crypto.subtle);
  let release!: () => void;
  const hold = new Promise<void>((done) => {
    release = done;
  });
  let entered!: () => void;
  const started = new Promise<void>((done) => {
    entered = done;
  });
  const spy = vi.spyOn(crypto.subtle, "digest").mockImplementationOnce(async (...args) => {
    entered();
    await hold;
    return original(...args);
  });
  const pending = simulate(simulationRequest.parse(fixture.simulation_request), signal());
  await started;
  invalidateSecurity("session");
  // A fresh user's request succeeds while the previous validation is held.
  expect(await simulate(simulationRequest.parse(fixture.simulation_request), signal())).toEqual(
    fixture.simulation,
  );
  release();
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  spy.mockRestore();
});
it("aborted requests cannot return an otherwise valid response", async () => {
  let complete!: (response: Response) => void;
  let entered!: () => void;
  const started = new Promise<void>((done) => {
    entered = done;
  });
  vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
    if (String(url).endsWith("/csrf"))
      return reply(auth({ csrf_token: "SYNTHETIC", expires_in: 300 }));
    entered();
    return new Promise<Response>((done) => {
      complete = done;
    });
  });
  const controller = new AbortController();
  const pending = simulate(simulationRequest.parse(fixture.simulation_request), controller.signal);
  await started;
  controller.abort();
  complete(reply(fixture.simulation));
  await expect(pending).rejects.toMatchObject({ name: "AbortError" });
});
it("ordinary Quality 403 is independent and does not emit forecast invalidation", async () => {
  vi.spyOn(globalThis, "fetch").mockResolvedValue(reply({ data: null }, 403));
  const observed: string[] = [];
  const unsubscribe = subscribeSecurity((kind) => observed.push(kind));
  try {
    await expect(
      request("/api/v1/forecast-intelligence/quality", readSchemas.quality, signal()),
    ).rejects.toMatchObject({ status: 403 });
    expect(observed).toEqual([]);
  } finally {
    unsubscribe();
  }
});
it("native canonical hashing does not turn unsafe numeric values into authority", async () => {
  await expect(frozenDigest({ quantity: Number.MAX_SAFE_INTEGER + 1 })).rejects.toThrow(
    "UNSAFE_CANONICAL_NUMBER",
  );
});
