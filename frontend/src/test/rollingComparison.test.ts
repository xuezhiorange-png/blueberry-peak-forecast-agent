import { expect, it } from "vitest";
import { rollingComparison } from "../dashboard/schemas/rolling";

function comparison(status: "NOT_COMPARABLE" | "NOT_COMPUTABLE") {
  return {
    left_run: 1,
    right_run: 2,
    left_origin: "2026-11-05",
    right_origin: "2026-11-06",
    left_result_hash: "a".repeat(64),
    right_result_hash: "b".repeat(64),
    comparison_hash: "c".repeat(64),
    left_quantity_basis: "FIELD_HARVEST_WEIGHT",
    right_quantity_basis: "FIELD_HARVEST_WEIGHT",
    models: { M0: { status, reasons: ["UNVERIFIED"] }, M1: { status, reasons: ["UNVERIFIED"] } },
    production_model: false,
  };
}

it.each(["NOT_COMPARABLE", "NOT_COMPUTABLE"] as const)(
  "%s accepts reasons but rejects numerical deltas",
  (status) => {
    const value = comparison(status);
    expect(rollingComparison.safeParse(value).success).toBe(true);
    expect(
      rollingComparison.safeParse({
        ...value,
        models: { ...value.models, M1: { ...value.models.M1, windows: {} } },
      }).success,
    ).toBe(false);
    expect(
      rollingComparison.safeParse({
        ...value,
        models: { ...value.models, M1: { ...value.models.M1, common_target_daily_delta_kg: [] } },
      }).success,
    ).toBe(false);
  },
);
