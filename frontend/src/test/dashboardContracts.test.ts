import { describe, expect, it } from "vitest";
import { capacityInput, forecastQuery, quantity } from "../dashboard/schemas/contracts";
import { identityMatches } from "../dashboard/api/client";

describe("Dashboard boundary contracts", () => {
  it.each([1, true, -1, "NaN", "Infinity", "-1", "1e3", "1".repeat(65)])(
    "rejects unsafe capacity %s",
    (value) => expect(quantity.safeParse(value).success).toBe(false),
  );
  it("retains exact decimal strings, including confirmed zero", () => {
    expect(quantity.parse("0.000")).toBe("0.000");
    expect(quantity.parse("12345678901234567890.123456789")).toBe("12345678901234567890.123456789");
  });
  it("does not accept authority-free selection or invented hierarchy", () => {
    expect(forecastQuery.safeParse({ run_id: 1 }).success).toBe(false);
    expect(forecastQuery.safeParse({ hierarchy_level: "FARM" }).success).toBe(false);
  });
  it("rejects mixed capacity provenance and bool workforce", () => {
    expect(
      capacityInput.safeParse({
        date: "2026-01-02",
        capacity_mode: "DIRECT",
        daily_handling_capacity_kg: "120",
        workforce_count: 10,
      }).success,
    ).toBe(false);
    expect(
      capacityInput.safeParse({
        date: "2026-01-02",
        capacity_mode: "WORKFORCE_DERIVED",
        workforce_count: true,
        productivity_kg_per_person_day: "12",
      }).success,
    ).toBe(false);
  });
  it("matches identity by fields rather than object key order", () => {
    expect(
      identityMatches({ run_id: 1, entity_id: "SYNTHETIC" }, { entity_id: "SYNTHETIC", run_id: 1 }),
    ).toBe(true);
    expect(identityMatches({ run_id: 1 }, { run_id: 2 })).toBe(false);
  });
});
