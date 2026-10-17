// Verify the existing frozen Python canonical hash commitment, not business math.
// No demand/capacity multiplication, backlog, loss, utilization or ranking calculation.
import type { SimulationRequest, SimulationResult } from "../schemas/contracts";

const policies = {
  what_if: "V0_16_WHAT_IF_DECISION_SIMULATOR_R1",
  capacity: "V0_16_EXPLICIT_DAILY_HANDLING_CAPACITY_R1",
  backlog: "V0_16_DETERMINISTIC_BACKLOG_BALANCE_R1",
  loss_mapping: "V0_16_PLANNING_DEMAND_VS_CAPACITY_LOSS_R1",
} as const;

export class BindingError extends Error {}

export function decimalIdentity(value: string): string {
  if (!/^[0-9]+(?:\.[0-9]+)?$/.test(value)) throw new BindingError("DECIMAL_INPUT_INVALID");
  const [whole, fraction = ""] = value.split(".");
  const integer = whole.replace(/^0+(?=\d)/, "");
  const tail = fraction.replace(/0+$/, "");
  return tail ? `${integer}.${tail}` : integer;
}

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered);
  if (value !== null && typeof value === "object")
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([key, item]) => [key, ordered(item)]),
    );
  if (typeof value === "number" && !Number.isSafeInteger(value))
    throw new BindingError("UNSAFE_CANONICAL_NUMBER");
  return value;
}

export async function frozenDigest(value: unknown): Promise<string> {
  if (!globalThis.crypto?.subtle) throw new BindingError("BLOCKED_API_CONTRACT_INSUFFICIENT");
  const bytes = new TextEncoder().encode(JSON.stringify(ordered(value)) + "\n");
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest), (v) => v.toString(16).padStart(2, "0")).join("");
}

export async function verifyDigest(value: Record<string, unknown>, key: string) {
  const withoutHash = Object.fromEntries(Object.entries(value).filter(([name]) => name !== key));
  if ((await frozenDigest(withoutHash)) !== value[key]) throw new BindingError("HASH_MISMATCH");
}

export function authority(result: SimulationResult) {
  return {
    saved_forecast_hash: result.saved_forecast_hash,
    forecast_curve_hash: result.forecast_curve_hash,
    forecast_source_hash: result.forecast_source_hash,
    forecast_origin: result.forecast_origin,
    hierarchy_level: result.hierarchy_level,
    hierarchy_entity_id: result.hierarchy_entity_id,
    hierarchy_authority_hash: result.hierarchy_authority_hash,
    planning_level: result.planning_level,
    cost_contract_hash: result.cost_contract_hash,
    loss_unit: result.loss_unit,
    dates: result.dates,
    initial_backlog_kg: result.initial_backlog_kg,
    backlog_policy_version: result.backlog_policy_version,
  };
}

export async function verifyInputCommitment(
  result: SimulationResult,
  request: SimulationRequest,
  enginePolicies: Record<string, string>,
) {
  for (const [key, version] of Object.entries(policies))
    if (enginePolicies[key] !== version)
      throw new BindingError("BLOCKED_API_CONTRACT_INSUFFICIENT");
  const capacityRows = [...request.capacity_rows]
    .sort((a, b) => a.date.localeCompare(b.date))
    .map((row, index) => {
      const output = result.daily_rows[index];
      const direct = row.capacity_mode === "DIRECT";
      const supplied = row.buffer_handling_capacity_kg != null;
      const buffer = decimalIdentity(row.buffer_handling_capacity_kg ?? "0");
      if (
        !output ||
        output.date !== row.date ||
        output.capacity_mode !== row.capacity_mode ||
        output.planning_level !== request.planning_level ||
        output.buffer_supplied !== supplied ||
        decimalIdentity(output.buffer_handling_capacity_kg) !== buffer ||
        (direct
          ? decimalIdentity(output.daily_handling_capacity_kg) !==
              decimalIdentity(row.daily_handling_capacity_kg) ||
            output.workforce_count !== null ||
            output.productivity_kg_per_person_day !== null
          : output.workforce_count !== row.workforce_count ||
            output.productivity_kg_per_person_day === null ||
            decimalIdentity(output.productivity_kg_per_person_day) !==
              decimalIdentity(row.productivity_kg_per_person_day))
      )
        throw new BindingError("SCENARIO_INPUT_MISMATCH");
      return {
        date: row.date,
        capacity_mode: row.capacity_mode,
        daily_handling_capacity_kg: direct ? decimalIdentity(row.daily_handling_capacity_kg) : null,
        workforce_count: direct ? null : row.workforce_count,
        productivity_kg_per_person_day: direct
          ? null
          : decimalIdentity(row.productivity_kg_per_person_day),
        buffer_supplied: supplied,
        buffer_handling_capacity_kg: buffer,
      };
    });
  const expected = {
    ...authority(result),
    scenario_id: request.scenario_id,
    scenario_version: request.scenario_version,
    policy_version: policies.what_if,
    capacity_policy_version: policies.capacity,
    decision_loss_mapping_policy_version: policies.loss_mapping,
    capacity_rows: capacityRows,
  };
  if ((await frozenDigest(expected)) !== result.scenario_hash)
    throw new BindingError("SCENARIO_INPUT_COMMITMENT_MISMATCH");
  for (const row of result.daily_rows) await verifyDigest(row, "row_hash");
  await verifyDigest(result, "result_hash");
}
